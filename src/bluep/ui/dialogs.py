"""Dialogs for BlueP.

Object Inspector dialog: shows fields, types, values (like BlueJ's inspector).
Method Call dialog: prompts for method parameters and shows results.
New Class dialog: creates new classes with templates.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango

from bluep.config import Config, AIConfig, EditorConfig, PythonConfig
from bluep.core.class_info import ClassInfo, ClassKind, create_default_template
from bluep.core.executor import BenchObject, CodeExecutor, ExecutionResult


class ObjectInspectorDialog(Gtk.Window):
    """Dialog for inspecting an object's fields and methods.

    Mirrors BlueJ's Object Inspector:
    - Shows all instance fields with values
    - Can inspect nested object references
    - Toggle to show static/class fields
    - Shows method list
    """

    def __init__(self, bench_object: BenchObject, parent: Gtk.Window | None = None) -> None:
        super().__init__()
        self.set_title(f"Inspect: {bench_object.name}")
        self.set_default_size(450, 400)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("bluep-dialog")

        self.bench_object = bench_object
        self._show_static = False
        self._inspectors: list[ObjectInspectorDialog] = []

        # Main container
        main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.set_child(main_box)

        # Header bar
        header = Gtk.HeaderBar.new()
        header.set_title_widget(Gtk.Label.new(f"Inspect: {bench_object.name}"))
        main_box.append(header)

        # Content
        content = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        main_box.append(content)

        # Object info
        info_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        info_label = Gtk.Label.new(f"Object: ")
        info_label.add_css_class("bluep-debug-variable-name")
        info_box.append(info_label)

        name_label = Gtk.Label.new(bench_object.name)
        name_label.add_css_class("bluep-debug-variable-value")
        info_box.append(name_label)

        info_box.append(Gtk.Label.new("    Class: "))

        class_label = Gtk.Label.new(bench_object.class_name)
        class_label.add_css_class("bluep-debug-variable-value")
        info_box.append(class_label)

        content.append(info_box)

        help_label = Gtk.Label.new(
            "Inspect the live state of this object. Double-click a field value "
            "to inspect nested objects. Toggle 'Show static fields' to see "
            "class-level attributes shared across all instances."
        )
        help_label.set_halign(Gtk.Align.START)
        help_label.set_xalign(0)
        help_label.set_wrap(True)
        help_label.add_css_class("bluep-status-bar")
        help_label.set_margin_bottom(4)
        content.append(help_label)

        # Show static fields toggle
        toggle_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        self._static_toggle = Gtk.CheckButton.new_with_label("Show static fields")
        self._static_toggle.connect("toggled", self._on_toggle_static)
        toggle_box.append(self._static_toggle)
        content.append(toggle_box)

        # Fields section
        fields_label = Gtk.Label.new("Instance Fields")
        fields_label.set_halign(Gtk.Align.START)
        fields_label.add_css_class("bluep-class-name")
        content.append(fields_label)

        # Fields list
        self._fields_list = Gtk.ListBox.new()
        self._fields_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._fields_list.connect("row-activated", self._on_field_activated)
        scroll_fields = Gtk.ScrolledWindow.new()
        scroll_fields.set_child(self._fields_list)
        scroll_fields.set_vexpand(True)
        scroll_fields.set_min_content_height(150)
        content.append(scroll_fields)

        # Static fields section (hidden by default)
        self._static_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 4)
        self._static_box.set_visible(False)
        static_label = Gtk.Label.new("Static Fields")
        static_label.set_halign(Gtk.Align.START)
        static_label.add_css_class("bluep-class-name")
        self._static_box.append(static_label)

        self._static_list = Gtk.ListBox.new()
        scroll_static = Gtk.ScrolledWindow.new()
        scroll_static.set_child(self._static_list)
        scroll_static.set_min_content_height(100)
        self._static_box.append(scroll_static)
        content.append(self._static_box)

        # Methods section
        methods_label = Gtk.Label.new("Methods")
        methods_label.set_halign(Gtk.Align.START)
        methods_label.add_css_class("bluep-class-name")
        methods_label.set_margin_top(8)
        content.append(methods_label)

        self._methods_list = Gtk.ListBox.new()
        scroll_methods = Gtk.ScrolledWindow.new()
        scroll_methods.set_child(self._methods_list)
        scroll_methods.set_vexpand(True)
        scroll_methods.set_min_content_height(100)
        content.append(scroll_methods)

        # Close button
        btn_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)
        btn_close = Gtk.Button.new_with_label("Close")
        btn_close.add_css_class("bluep-btn")
        btn_close.connect("clicked", lambda b: self.destroy())
        btn_box.append(btn_close)
        content.append(btn_box)

        # Populate
        self._populate_fields()
        self._populate_methods()

    def _populate_fields(self) -> None:
        """Populate the fields list."""
        # Clear
        while self._fields_list.get_first_child():
            self._fields_list.remove(self._fields_list.get_first_child())

        fields = self.bench_object.get_fields()
        for name, value_str in fields:
            row = self._create_field_row(name, value_str)
            self._fields_list.append(row)

        if not fields:
            row = Gtk.Label.new("(no instance fields)")
            row.add_css_class("bluep-status-bar")
            self._fields_list.append(row)

        # Static fields
        while self._static_list.get_first_child():
            self._static_list.remove(self._static_list.get_first_child())
        if self._show_static:
            cls = type(self.bench_object.instance)
            for name in dir(cls):
                if not name.startswith("_"):
                    attr = inspect.getattr_static(cls, name, None)
                    if attr is not None and not callable(attr):
                        row = self._create_field_row(name, repr(attr))
                        self._static_list.append(row)

    def _create_field_row(self, name: str, value_str: str) -> Gtk.Widget:
        """Create a row for a field."""
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 12)
        row.set_margin_start(8)
        row.set_margin_end(8)
        row.set_margin_top(4)
        row.set_margin_bottom(4)

        # Name
        name_label = Gtk.Label.new(name)
        name_label.set_halign(Gtk.Align.START)
        name_label.add_css_class("bluep-debug-variable-name")
        name_label.set_xalign(0)
        name_label.set_size_request(100, -1)
        row.append(name_label)

        # Value
        value_label = Gtk.Label.new(value_str[:80])
        value_label.set_halign(Gtk.Align.START)
        value_label.set_xalign(0)
        value_label.set_hexpand(True)
        value_label.add_css_class("bluep-debug-variable-value")
        value_label.set_selectable(True)
        row.append(value_label)

        return row

    def _populate_methods(self) -> None:
        """Populate the methods list."""
        while self._methods_list.get_first_child():
            self._methods_list.remove(self._methods_list.get_first_child())

        methods = self.bench_object.get_public_methods()
        for name in methods:
            row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(2)
            row.set_margin_bottom(2)

            label = Gtk.Label.new(f"  {name}()")
            label.set_halign(Gtk.Align.START)
            label.set_xalign(0)
            row.append(label)
            self._methods_list.append(row)

        if not methods:
            row = Gtk.Label.new("(no public methods)")
            row.add_css_class("bluep-status-bar")
            self._methods_list.append(row)

    def _on_toggle_static(self, button: Gtk.CheckButton) -> None:
        self._show_static = button.get_active()
        self._static_box.set_visible(self._show_static)
        self._populate_fields()

    def _on_field_activated(self, list_box: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        """Handle field double-click - inspect if object."""
        # Could open a nested inspector for object fields
        pass


class MethodCallDialog(Gtk.Window):
    """Dialog for calling a method with parameters and showing the result.

    Mirrors BlueJ's method call dialog:
    - Shows method signature and docstring
    - Parameter input fields
    - History of previous calls
    - Result display with option to place on bench
    """

    __gsignals__ = {
        "object-created": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, bench_object: BenchObject, method_name: str,
                 executor: CodeExecutor, parent: Gtk.Window | None = None) -> None:
        super().__init__()
        self.set_title(f"Call: {method_name}")
        self.set_default_size(400, 300)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("bluep-dialog")

        self.bench_object = bench_object
        self.method_name = method_name
        self.executor = executor

        # Get method info
        method = getattr(bench_object.instance, method_name)
        self.signature = inspect.signature(method)
        self.docstring = inspect.getdoc(method)

        # Main container
        main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.set_child(main_box)

        # Header
        header = Gtk.HeaderBar.new()
        header.set_title_widget(Gtk.Label.new(f"Call: {method_name}"))
        main_box.append(header)

        content = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        main_box.append(content)

        # Method signature
        sig_label = Gtk.Label.new(f"void {method_name}{self.signature}")
        sig_label.set_halign(Gtk.Align.START)
        sig_label.add_css_class("bluep-debug-variable-name")
        content.append(sig_label)

        help_label = Gtk.Label.new(
            "Fill in the parameters and click Call to invoke this method on "
            "the selected object. The result is shown below; if it returns "
            "an object, click Get to place it on the object bench."
        )
        help_label.set_halign(Gtk.Align.START)
        help_label.set_xalign(0)
        help_label.set_wrap(True)
        help_label.add_css_class("bluep-status-bar")
        help_label.set_margin_bottom(4)
        content.append(help_label)

        # Docstring
        if self.docstring:
            doc_frame = Gtk.Frame.new("Description")
            doc_label = Gtk.Label.new(self.docstring)
            doc_label.set_halign(Gtk.Align.START)
            doc_label.set_xalign(0)
            doc_label.set_margin_start(8)
            doc_label.set_margin_end(8)
            doc_label.set_margin_top(4)
            doc_label.set_margin_bottom(4)
            doc_label.set_selectable(True)
            doc_label.set_wrap(True)
            doc_frame.set_child(doc_label)
            content.append(doc_frame)

        # Parameter inputs
        params_label = Gtk.Label.new("Parameters:")
        params_label.set_halign(Gtk.Align.START)
        params_label.set_margin_top(8)
        content.append(params_label)

        self._param_entries: dict[str, Gtk.Entry] = {}
        params = list(self.signature.parameters.values())

        if params:
            params_box = Gtk.Grid.new()
            params_box.set_row_spacing(4)
            params_box.set_column_spacing(8)
            for i, param in enumerate(params):
                # Label
                param_type = str(param.annotation) if param.annotation != param.empty else "Any"
                label_text = f"{param.name}: {param_type}"
                if param.default != param.empty:
                    label_text += f" = {param.default}"
                label = Gtk.Label.new(label_text)
                label.set_halign(Gtk.Align.START)
                params_box.attach(label, 0, i, 1, 1)

                # Entry
                entry = Gtk.Entry.new()
                entry.set_placeholder_text(f"Enter value for {param.name}")
                if param.default != param.empty:
                    entry.set_text(str(param.default))
                entry.set_hexpand(True)
                self._param_entries[param.name] = entry
                params_box.attach(entry, 1, i, 1, 1)
            content.append(params_box)
        else:
            content.append(Gtk.Label.new("(no parameters)"))

        # Hint about bench objects
        bench_names = list(executor.bench.keys())
        if bench_names:
            hint = Gtk.Label.new(f"Tip: Bench objects available: {', '.join(bench_names)}")
            hint.set_halign(Gtk.Align.START)
            hint.add_css_class("bluep-status-bar")
            content.append(hint)

        # Buttons
        btn_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        btn_cancel = Gtk.Button.new_with_label("Cancel")
        btn_cancel.add_css_class("bluep-btn")
        btn_cancel.connect("clicked", lambda b: self.destroy())
        btn_box.append(btn_cancel)

        btn_call = Gtk.Button.new_with_label("Call")
        btn_call.add_css_class("bluep-btn-primary")
        btn_call.connect("clicked", self._on_call)
        btn_box.append(btn_call)

        content.append(btn_box)

        # Result area (shown after call)
        self._result_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 4)
        self._result_box.set_visible(False)
        content.append(self._result_box)

        # Focus first entry or call button
        if self._param_entries:
            first_entry = list(self._param_entries.values())[0]
            GLib.idle_add(lambda: first_entry.grab_focus() and False)

    def _on_call(self, button: Gtk.Button) -> None:
        """Execute the method call."""
        # Parse parameters
        args: list[Any] = []
        kwargs: dict[str, Any] = {}

        for param_name, entry in self._param_entries.items():
            text = entry.get_text().strip()
            if not text:
                continue
            try:
                value = eval(text, self.executor.namespace)
                kwargs[param_name] = value
            except Exception:
                # Treat as string
                kwargs[param_name] = text

        # Call the method
        result = self.executor.call_bench_method(
            self.bench_object.name, self.method_name, *args, **kwargs
        )

        # Show result
        self._show_result(result)

    def _show_result(self, result: ExecutionResult) -> None:
        """Show the call result."""
        # Clear previous result
        while self._result_box.get_first_child():
            self._result_box.remove(self._result_box.get_first_child())

        self._result_box.set_visible(True)

        sep = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
        self._result_box.append(sep)

        if result.success:
            if result.output:
                output_frame = Gtk.Frame.new("Output")
                output_label = Gtk.Label.new(result.output)
                output_label.set_halign(Gtk.Align.START)
                output_label.set_xalign(0)
                output_label.set_margin_start(8)
                output_label.set_margin_end(8)
                output_label.set_margin_top(4)
                output_label.set_margin_bottom(4)
                output_label.set_selectable(True)
                output_label.set_wrap(True)
                output_frame.set_child(output_label)
                self._result_box.append(output_frame)

            if result.value is not None:
                value_frame = Gtk.Frame.new("Return Value")
                value_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
                value_box.set_margin_start(8)
                value_box.set_margin_end(8)
                value_box.set_margin_top(4)
                value_box.set_margin_bottom(4)

                value_str = repr(result.value)
                type_name = type(result.value).__name__
                value_label = Gtk.Label.new(f"{value_str}   ({type_name})")
                value_label.set_halign(Gtk.Align.START)
                value_label.set_xalign(0)
                value_label.set_selectable(True)
                value_label.set_hexpand(True)
                value_box.append(value_label)

                # If it's an object, offer to put on bench
                if not isinstance(result.value, (int, float, str, bool, type(None), list, dict, tuple)):
                    btn_bench = Gtk.Button.new_with_label("Get")
                    btn_bench.set_tooltip_text("Place result on object bench")
                    btn_bench.connect("clicked", lambda b: self._put_on_bench(result.value))
                    value_box.append(btn_bench)

                value_frame.set_child(value_box)
                self._result_box.append(value_frame)
            else:
                self._result_box.append(Gtk.Label.new("(no return value)"))
        else:
            error_frame = Gtk.Frame.new("Error")
            error_label = Gtk.Label.new(result.error)
            error_label.set_halign(Gtk.Align.START)
            error_label.set_xalign(0)
            error_label.set_margin_start(8)
            error_label.set_margin_end(8)
            error_label.set_margin_top(4)
            error_label.set_margin_bottom(4)
            error_label.set_selectable(True)
            error_label.set_wrap(True)
            error_frame.set_child(error_label)
            self._result_box.append(error_frame)

    def _put_on_bench(self, value: Any) -> None:
        """Put a return value onto the object bench."""
        # Create a bench object from the return value
        from bluep.core.executor import BenchObject
        class_name = type(value).__name__
        name = self.executor._generate_bench_name(class_name)
        obj = BenchObject(name=name, instance=value, class_name=class_name)
        self.executor.bench[name] = obj
        self.emit("object-created", name)


class NewClassDialog(Gtk.Window):
    """Dialog for creating a new class - mirrors BlueJ's New Class dialog."""

    __gsignals__ = {
        "class-created": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, parent: Gtk.Window | None = None,
                 on_create: Any = None) -> None:
        super().__init__()
        self.set_title("New Class")
        self.set_default_size(350, 250)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("bluep-dialog")

        self._on_create = on_create

        main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.set_child(main_box)

        header = Gtk.HeaderBar.new()
        header.set_title_widget(Gtk.Label.new("Create New Class"))
        main_box.append(header)

        content = Gtk.Box.new(Gtk.Orientation.VERTICAL, 12)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        main_box.append(content)

        # Class name
        name_label = Gtk.Label.new("Class Name:")
        name_label.set_halign(Gtk.Align.START)
        content.append(name_label)

        self._name_entry = Gtk.Entry.new()
        self._name_entry.set_placeholder_text("e.g., Student, Person, Car")
        content.append(self._name_entry)

        # Kind selector
        kind_label = Gtk.Label.new("Class Type:")
        kind_label.set_halign(Gtk.Align.START)
        kind_label.set_margin_top(8)
        content.append(kind_label)

        self._kind_combo = Gtk.DropDown.new_from_strings([
            "Concrete Class",
            "Abstract Class",
            "Interface (ABC)",
            "Enumeration",
            "Dataclass",
        ])
        self._kind_combo.connect("notify::selected", self._on_kind_changed)
        content.append(self._kind_combo)

        self._kind_help = Gtk.Label.new("")
        self._kind_help.set_halign(Gtk.Align.START)
        self._kind_help.set_xalign(0)
        self._kind_help.set_wrap(True)
        self._kind_help.add_css_class("bluep-status-bar")
        self._kind_help.set_margin_top(4)
        content.append(self._kind_help)
        self._update_kind_help(0)

        # Buttons
        btn_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(16)

        btn_cancel = Gtk.Button.new_with_label("Cancel")
        btn_cancel.add_css_class("bluep-btn")
        btn_cancel.connect("clicked", lambda b: self.destroy())
        btn_box.append(btn_cancel)

        btn_create = Gtk.Button.new_with_label("Create")
        btn_create.add_css_class("bluep-btn-primary")
        btn_create.connect("clicked", self._on_create_clicked)
        btn_box.append(btn_create)

        content.append(btn_box)

        GLib.idle_add(self._grab_name_focus)

    def _grab_name_focus(self) -> bool:
        self._name_entry.grab_focus()
        return False

    _KIND_HELP = {
        0: "Concrete Class — a normal class you can instantiate. Use this for "
           "most cases. Provides a default __init__, getters, and setters.",
        1: "Abstract Class — cannot be instantiated directly; subclasses must "
           "implement its @abstractmethod declarations. Good for shared interfaces.",
        2: "Interface (ABC) — a pure contract: defines method signatures with "
           "@abstractmethod but no implementation. Other classes implement it.",
        3: "Enumeration — a set of named constants. Use for fixed value sets "
           "like days of the week, colors, or status codes.",
        4: "Dataclass — auto-generates __init__, __repr__, and __eq__ from "
           "annotated fields. Great for simple data containers.",
    }

    def _on_kind_changed(self, combo: Gtk.DropDown, _pspec: Any) -> None:
        self._update_kind_help(combo.get_selected())

    def _update_kind_help(self, index: int) -> None:
        text = self._KIND_HELP.get(index, "")
        self._kind_help.set_text(text)

    def _on_create_clicked(self, button: Gtk.Button) -> None:
        """Handle create button click."""
        name = self._name_entry.get_text().strip()
        if not name:
            return

        # Validate Python identifier
        if not name.isidentifier():
            return

        kind_index = self._kind_combo.get_selected()
        kind_map = {
            0: ClassKind.CONCRETE,
            1: ClassKind.ABSTRACT,
            2: ClassKind.INTERFACE,
            3: ClassKind.ENUM,
            4: ClassKind.DATACLASS,
        }
        kind = kind_map.get(kind_index, ClassKind.CONCRETE)

        if self._on_create:
            self._on_create(name, kind)

        self.emit("class-created", name)
        self.destroy()


class ConstructorDialog(Gtk.Window):
    """Dialog for creating a new instance - mirrors BlueJ's constructor dialog.

    Prompts for object name and constructor parameters.
    """

    __gsignals__ = {
        "instance-created": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, class_name: str, class_info: ClassInfo | None,
                 executor: CodeExecutor, parent: Gtk.Window | None = None,
                 on_create: Any = None) -> None:
        super().__init__()
        self.set_title(f"Create: {class_name}")
        self.set_default_size(400, 300)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("bluep-dialog")

        self.class_name = class_name
        self.class_info = class_info
        self.executor = executor
        self._on_create = on_create

        main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.set_child(main_box)

        header = Gtk.HeaderBar.new()
        header.set_title_widget(Gtk.Label.new(f"Create {class_name} instance"))
        main_box.append(header)

        content = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        main_box.append(content)

        help_label = Gtk.Label.new(
            "Create a new instance of this class on the object bench. The "
            "name is how you will refer to this object in the code pad. "
            "Parameters are evaluated as Python expressions, so you can "
            "pass bench objects, literals, or expressions like 2+3."
        )
        help_label.set_halign(Gtk.Align.START)
        help_label.set_xalign(0)
        help_label.set_wrap(True)
        help_label.add_css_class("bluep-status-bar")
        help_label.set_margin_bottom(4)
        content.append(help_label)

        # Object name
        name_label = Gtk.Label.new("Name of instance:")
        name_label.set_halign(Gtk.Align.START)
        content.append(name_label)

        self._name_entry = Gtk.Entry.new()
        # Default name: lowercase first letter + count
        default_name = class_name[0].lower() + class_name[1:] if class_name else "obj"
        count = executor._bench_counter.get(class_name, 0) + 1
        self._name_entry.set_text(f"{default_name}{count}")
        content.append(self._name_entry)

        # Constructor parameters
        constructor = None
        if class_info:
            constructor = next((m for m in class_info.methods if m.is_constructor), None)

        if constructor and constructor.params:
            params_label = Gtk.Label.new("Constructor Parameters:")
            params_label.set_halign(Gtk.Align.START)
            params_label.set_margin_top(8)
            content.append(params_label)

            self._param_entries: dict[str, Gtk.Entry] = {}
            params_box = Gtk.Grid.new()
            params_box.set_row_spacing(4)
            params_box.set_column_spacing(8)
            for i, (param_name, param_type) in enumerate(constructor.params):
                label_text = f"{param_name}: {param_type or 'Any'}"
                label = Gtk.Label.new(label_text)
                label.set_halign(Gtk.Align.START)
                params_box.attach(label, 0, i, 1, 1)

                entry = Gtk.Entry.new()
                entry.set_placeholder_text(f"Enter value for {param_name}")
                entry.set_hexpand(True)
                self._param_entries[param_name] = entry
                params_box.attach(entry, 1, i, 1, 1)
            content.append(params_box)
        else:
            self._param_entries = {}
            content.append(Gtk.Label.new("(no constructor parameters)"))

        # Buttons
        btn_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        btn_cancel = Gtk.Button.new_with_label("Cancel")
        btn_cancel.add_css_class("bluep-btn")
        btn_cancel.connect("clicked", lambda b: self.destroy())
        btn_box.append(btn_cancel)

        btn_create = Gtk.Button.new_with_label("Create")
        btn_create.add_css_class("bluep-btn-primary")
        btn_create.connect("clicked", self._on_create_clicked)
        btn_box.append(btn_create)

        content.append(btn_box)

    def _on_create_clicked(self, button: Gtk.Button) -> None:
        """Handle create button."""
        name = self._name_entry.get_text().strip()
        if not name or not name.isidentifier():
            return

        # Parse parameters
        args: list[Any] = []
        for param_name, entry in self._param_entries.items():
            text = entry.get_text().strip()
            if not text:
                continue
            try:
                value = eval(text, self.executor.namespace)
                args.append(value)
            except Exception:
                args.append(text)

        if self._on_create:
            self._on_create(name, self.class_name, args)

        self.emit("instance-created", name)
        self.destroy()


class RenameClassDialog(Gtk.Window):
    """Dialog for renaming a class.

    Renames both the source file (e.g. `Student.py` → `Person.py`) and the
    `class Student:` definition inside it. Other references to the old name
    in the same file are NOT rewritten — the user is warned about this.
    """

    __gsignals__ = {
        "class-renamed": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
    }

    def __init__(self, class_name: str, existing_names: list[str],
                 parent: Gtk.Window | None = None,
                 on_rename: Any = None) -> None:
        super().__init__()
        self.set_title(f"Rename Class: {class_name}")
        self.set_default_size(420, 280)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("bluep-dialog")

        self._old_name = class_name
        self._existing = [n for n in existing_names if n != class_name]
        self._on_rename = on_rename

        main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.set_child(main_box)

        header = Gtk.HeaderBar.new()
        header.set_title_widget(Gtk.Label.new(f"Rename {class_name}"))
        main_box.append(header)

        content = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        main_box.append(content)

        help_label = Gtk.Label.new(
            "Renames the source file and the class definition inside it. "
            "References to the old name in OTHER files (imports, type hints, "
            "instantiations) are not automatically updated — review and fix "
            "those after renaming."
        )
        help_label.set_halign(Gtk.Align.START)
        help_label.set_xalign(0)
        help_label.set_wrap(True)
        help_label.add_css_class("bluep-status-bar")
        content.append(help_label)

        current_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        current_box.append(Gtk.Label.new("Current name:"))
        cur = Gtk.Label.new(class_name)
        cur.add_css_class("bluep-debug-variable-value")
        cur.set_xalign(0)
        current_box.append(cur)
        content.append(current_box)

        new_label = Gtk.Label.new("New name:")
        new_label.set_halign(Gtk.Align.START)
        content.append(new_label)

        self._name_entry = Gtk.Entry.new()
        self._name_entry.set_text(class_name)
        self._name_entry.connect("changed", self._on_name_changed)
        content.append(self._name_entry)

        self._status = Gtk.Label.new("")
        self._status.set_halign(Gtk.Align.START)
        self._status.set_xalign(0)
        self._status.set_wrap(True)
        self._status.add_css_class("bluep-status-bar")
        content.append(self._status)

        btn_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        btn_cancel = Gtk.Button.new_with_label("Cancel")
        btn_cancel.add_css_class("bluep-btn")
        btn_cancel.connect("clicked", lambda b: self.destroy())
        btn_box.append(btn_cancel)

        self._btn_rename = Gtk.Button.new_with_label("Rename")
        self._btn_rename.add_css_class("bluep-btn-primary")
        self._btn_rename.connect("clicked", self._on_rename_clicked)
        btn_box.append(self._btn_rename)

        content.append(btn_box)

        self._validate()
        GLib.idle_add(self._grab_focus)

    def _grab_focus(self) -> bool:
        self._name_entry.grab_focus()
        self._name_entry.select_region(0, -1)
        return False

    def _on_name_changed(self, entry: Gtk.Entry) -> None:
        self._validate()

    def _validate(self) -> bool:
        name = self._name_entry.get_text().strip()
        if not name:
            self._status.set_text("Enter a new class name.")
            self._btn_rename.set_sensitive(False)
            return False
        if name == self._old_name:
            self._status.set_text("New name is the same as the current name.")
            self._btn_rename.set_sensitive(False)
            return False
        if not name.isidentifier():
            self._status.set_text("Not a valid Python identifier (letters, digits, _, no leading digit).")
            self._btn_rename.set_sensitive(False)
            return False
        if name in self._existing:
            self._status.set_text(f"A class named '{name}' already exists in this project.")
            self._btn_rename.set_sensitive(False)
            return False
        if not name[0].isupper():
            self._status.set_text("Warning: class names usually start with an uppercase letter.")
            self._btn_rename.set_sensitive(True)
            return True
        self._status.set_text("")
        self._btn_rename.set_sensitive(True)
        return True

    def _on_rename_clicked(self, button: Gtk.Button) -> None:
        if not self._validate():
            return
        new_name = self._name_entry.get_text().strip()
        if self._on_rename:
            self._on_rename(self._old_name, new_name)
        self.emit("class-renamed", self._old_name, new_name)
        self.destroy()


class PreferencesDialog(Gtk.Window):
    """Tabbed preferences dialog: General, Python, Editor, AI.

    Settings persist to ~/.config/bluep/settings.json via Config.save().
    The `supervised` flag is read-only here — it comes from the
    BLUEP_SUPERVISED environment variable and cannot be toggled from the UI.
    In supervised mode, the AI tab, Python tab, and the AI completion toggle
    are disabled.
    """

    __gsignals__ = {
        "settings-applied": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, config: Config, parent: Gtk.Window | None = None) -> None:
        super().__init__()
        self.set_title("Preferences")
        self.set_default_size(560, 520)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("bluep-dialog")

        self._config = config
        self._supervised = config.supervised

        main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.set_child(main_box)

        header = Gtk.HeaderBar.new()
        header.set_title_widget(Gtk.Label.new("Preferences"))
        main_box.append(header)

        notebook = Gtk.Notebook.new()
        notebook.set_scrollable(True)
        notebook.set_vexpand(True)
        main_box.append(notebook)

        notebook.append_page(self._build_general_tab(), Gtk.Label.new("General"))
        notebook.append_page(self._build_python_tab(), Gtk.Label.new("Python"))
        notebook.append_page(self._build_editor_tab(), Gtk.Label.new("Editor"))
        notebook.append_page(self._build_ai_tab(), Gtk.Label.new("AI"))

        btn_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_start(12)
        btn_box.set_margin_end(12)
        btn_box.set_margin_top(8)
        btn_box.set_margin_bottom(8)

        btn_cancel = Gtk.Button.new_with_label("Cancel")
        btn_cancel.add_css_class("bluep-btn")
        btn_cancel.connect("clicked", lambda b: self.destroy())
        btn_box.append(btn_cancel)

        btn_apply = Gtk.Button.new_with_label("Apply")
        btn_apply.add_css_class("bluep-btn-primary")
        btn_apply.connect("clicked", self._on_apply)
        btn_box.append(btn_apply)

        main_box.append(btn_box)

    # ── General tab ───────────────────────────────────────────────────

    def _build_general_tab(self) -> Gtk.Widget:
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)

        theme_label = Gtk.Label.new("Theme")
        theme_label.set_halign(Gtk.Align.START)
        theme_label.add_css_class("bluep-class-name")
        box.append(theme_label)

        self._theme_combo = Gtk.DropDown.new_from_strings(["dark", "light"])
        self._theme_combo.set_selected(0 if self._config.theme == "dark" else 1)
        box.append(self._theme_combo)

        sep = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        box.append(sep)

        supervised_label = Gtk.Label.new("Supervised Mode")
        supervised_label.set_halign(Gtk.Align.START)
        supervised_label.add_css_class("bluep-class-name")
        box.append(supervised_label)

        state = "ON (locked)" if self._supervised else "OFF"
        detail = (
            "When enabled via BLUEP_SUPERVISED=true in the environment, the AI "
            "panel, AI settings, Python settings, and AI completion toggle are "
            "disabled. This flag is read-only from the UI — it is meant for "
            "classroom/exam deployments."
        )
        state_label = Gtk.Label.new(f"Status: {state}\n\n{detail}")
        state_label.set_halign(Gtk.Align.START)
        state_label.set_xalign(0)
        state_label.set_wrap(True)
        state_label.add_css_class("bluep-status-bar")
        box.append(state_label)

        return box

    # ── Python tab ────────────────────────────────────────────────────

    def _build_python_tab(self) -> Gtk.Widget:
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)

        if self._supervised:
            lock = Gtk.Label.new(
                "Python settings are locked under supervised mode. "
                "Ask your instructor/administrator to change them."
            )
            lock.set_halign(Gtk.Align.START)
            lock.set_xalign(0)
            lock.set_wrap(True)
            lock.add_css_class("bluep-status-bar")
            box.append(lock)
            box.set_sensitive(False)
            return box

        p = self._config.python

        self._py_interpreter = self._row_entry(box, "Python interpreter:", p.interpreter)
        self._py_startup = self._row_entry(box, "Startup script (optional):", p.startup_script)

        self._py_auto_compile = self._row_switch(
            box, "Auto-compile on save", "Compile the class when you save the editor.", p.auto_compile_on_save
        )
        self._py_clear_bench = self._row_switch(
            box, "Clear object bench on recompile",
            "Remove all bench objects when recompiling (matches BlueJ).",
            p.clear_bench_on_recompile
        )
        return box

    # ── Editor tab ───────────────────────────────────────────────────

    def _build_editor_tab(self) -> Gtk.Widget:
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)

        e = self._config.editor

        indent_label = Gtk.Label.new("Indentation")
        indent_label.set_halign(Gtk.Align.START)
        indent_label.add_css_class("bluep-class-name")
        box.append(indent_label)

        self._ed_tab_width = self._row_spin(box, "Tab width (spaces):", 1, 16, e.tab_width)
        self._ed_insert_spaces = self._row_switch(
            box, "Insert spaces instead of tabs",
            "Use space characters rather than tab characters.", e.insert_spaces
        )

        font_label = Gtk.Label.new("Font")
        font_label.set_halign(Gtk.Align.START)
        font_label.add_css_class("bluep-class-name")
        font_label.set_margin_top(8)
        box.append(font_label)

        self._ed_font_family = self._row_entry(box, "Font family:", e.font_family)
        self._ed_font_size = self._row_spin(box, "Font size:", 6, 48, e.font_size)

        view_label = Gtk.Label.new("Display")
        view_label.set_halign(Gtk.Align.START)
        view_label.add_css_class("bluep-class-name")
        view_label.set_margin_top(8)
        box.append(view_label)

        self._ed_line_numbers = self._row_switch(
            box, "Show line numbers", "Display line numbers in the gutter.", e.show_line_numbers
        )
        self._ed_highlight_current = self._row_switch(
            box, "Highlight current line", "Tint the line under the cursor.", e.highlight_current_line
        )
        self._ed_auto_indent = self._row_switch(
            box, "Auto-indent", "Match indentation of the previous line on Enter.", e.auto_indent
        )
        self._ed_smart_backspace = self._row_switch(
            box, "Smart backspace", "Backspace dedents to the previous multiple of tab width.", e.smart_backspace
        )
        self._ed_syntax_highlight = self._row_switch(
            box, "Syntax highlighting",
            "Colour Python keywords, strings, and comments (GtkSourceView).",
            e.enable_syntax_highlighting
        )

        future_label = Gtk.Label.new("Future features")
        future_label.set_halign(Gtk.Align.START)
        future_label.add_css_class("bluep-class-name")
        future_label.set_margin_top(8)
        box.append(future_label)

        self._ed_autocomplete = self._row_switch(
            box, "Autocomplete",
            "Suggest attributes and keywords as you type (coming soon).",
            e.enable_autocomplete
        )

        can_ai_completion = bool(self._config.ai.api_key) and not self._supervised
        self._ed_ai_completion = self._row_switch(
            box, "AI code completion",
            "Suggest completions from the AI agent (coming soon; requires an API key and is disabled in supervised mode).",
            e.enable_ai_completion,
        )
        if not can_ai_completion:
            self._ed_ai_completion.set_sensitive(False)
            if self._supervised:
                self._ed_ai_completion.set_tooltip_text("Disabled under supervised mode.")
            elif not self._config.ai.api_key:
                self._ed_ai_completion.set_tooltip_text("Set an AI API key on the AI tab to enable this.")

        return box

    # ── AI tab ────────────────────────────────────────────────────────

    def _build_ai_tab(self) -> Gtk.Widget:
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 10)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)

        if self._supervised:
            lock = Gtk.Label.new(
                "AI settings are locked under supervised mode. The AI panel "
                "and any AI-powered features are disabled in this deployment."
            )
            lock.set_halign(Gtk.Align.START)
            lock.set_xalign(0)
            lock.set_wrap(True)
            lock.add_css_class("bluep-status-bar")
            box.append(lock)
            box.set_sensitive(False)
            return box

        a = self._config.ai

        self._ai_enabled = self._row_switch(
            box, "Enable AI agent",
            "Show the AI panel and allow the agent to interact with the project.",
            a.enabled
        )

        self._ai_provider = self._row_entry(box, "Provider:", a.provider)
        self._ai_model = self._row_entry(box, "Model:", a.model)
        self._ai_api_key = self._row_password(box, "API key:", a.api_key)
        self._ai_base_url = self._row_entry(box, "Base URL:", a.base_url)
        self._ai_max_tokens = self._row_spin(box, "Max tokens:", 64, 32768, a.max_tokens)
        self._ai_temperature = self._row_spin_float(box, "Temperature:", 0.0, 2.0, a.temperature, 0.1)
        return box

    # ── Row builders ──────────────────────────────────────────────────

    def _row_entry(self, parent: Gtk.Box, label_text: str, value: str) -> Gtk.Entry:
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        row.set_halign(Gtk.Align.FILL)
        label = Gtk.Label.new(label_text)
        label.set_xalign(0)
        label.set_size_request(140, -1)
        row.append(label)
        entry = Gtk.Entry.new()
        entry.set_text(value)
        entry.set_hexpand(True)
        row.append(entry)
        parent.append(row)
        return entry

    def _row_password(self, parent: Gtk.Box, label_text: str, value: str) -> Gtk.Entry:
        entry = self._row_entry(parent, label_text, value)
        entry.set_visibility(False)
        return entry

    def _row_spin(self, parent: Gtk.Box, label_text: str, lo: int, hi: int, value: int) -> Gtk.SpinButton:
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        row.set_halign(Gtk.Align.FILL)
        label = Gtk.Label.new(label_text)
        label.set_xalign(0)
        label.set_size_request(140, -1)
        row.append(label)
        spin = Gtk.SpinButton.new_with_range(lo, hi, 1)
        spin.set_value(value)
        spin.set_hexpand(True)
        row.append(spin)
        parent.append(row)
        return spin

    def _row_spin_float(self, parent: Gtk.Box, label_text: str, lo: float, hi: float,
                        value: float, step: float) -> Gtk.SpinButton:
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        row.set_halign(Gtk.Align.FILL)
        label = Gtk.Label.new(label_text)
        label.set_xalign(0)
        label.set_size_request(140, -1)
        row.append(label)
        spin = Gtk.SpinButton.new_with_range(lo, hi, step)
        spin.set_value(value)
        spin.set_hexpand(True)
        row.append(spin)
        parent.append(row)
        return spin

    def _row_switch(self, parent: Gtk.Box, label_text: str, tooltip: str, value: bool) -> Gtk.Switch:
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        row.set_halign(Gtk.Align.FILL)
        label = Gtk.Label.new(label_text)
        label.set_xalign(0)
        label.set_hexpand(True)
        label.set_tooltip_text(tooltip)
        row.append(label)
        sw = Gtk.Switch.new()
        sw.set_active(value)
        sw.set_tooltip_text(tooltip)
        row.append(sw)
        parent.append(row)
        return sw

    # ── Apply ────────────────────────────────────────────────────────

    def _on_apply(self, button: Gtk.Button) -> None:
        theme_idx = self._theme_combo.get_selected()
        self._config.theme = "dark" if theme_idx == 0 else "light"

        if not self._supervised:
            self._config.python.interpreter = self._py_interpreter.get_text().strip() or "python3"
            self._config.python.startup_script = self._py_startup.get_text().strip()
            self._config.python.auto_compile_on_save = self._py_auto_compile.get_active()
            self._config.python.clear_bench_on_recompile = self._py_clear_bench.get_active()

        self._config.editor.tab_width = int(self._ed_tab_width.get_value())
        self._config.editor.insert_spaces = self._ed_insert_spaces.get_active()
        self._config.editor.font_family = self._ed_font_family.get_text().strip() or "Monospace"
        self._config.editor.font_size = int(self._ed_font_size.get_value())
        self._config.editor.show_line_numbers = self._ed_line_numbers.get_active()
        self._config.editor.highlight_current_line = self._ed_highlight_current.get_active()
        self._config.editor.auto_indent = self._ed_auto_indent.get_active()
        self._config.editor.smart_backspace = self._ed_smart_backspace.get_active()
        self._config.editor.enable_syntax_highlighting = self._ed_syntax_highlight.get_active()
        self._config.editor.enable_autocomplete = self._ed_autocomplete.get_active()
        if self._ed_ai_completion.get_sensitive():
            self._config.editor.enable_ai_completion = self._ed_ai_completion.get_active()

        if not self._supervised:
            self._config.ai.enabled = self._ai_enabled.get_active()
            self._config.ai.provider = self._ai_provider.get_text().strip() or "openai"
            self._config.ai.model = self._ai_model.get_text().strip() or "gpt-4o"
            self._config.ai.api_key = self._ai_api_key.get_text()
            self._config.ai.base_url = self._ai_base_url.get_text().strip() or "https://api.openai.com/v1"
            self._config.ai.max_tokens = int(self._ai_max_tokens.get_value())
            self._config.ai.temperature = float(self._ai_temperature.get_value())

        self._config.save()
        self.emit("settings-applied")
        self.destroy()
