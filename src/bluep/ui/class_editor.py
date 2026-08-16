"""Graphical class editor with graphics/code view toggle.

A dialog for creating and editing classes with two views:
- Graphics: form-based editor for class name, kind, fields, methods
- Code: raw Python source editor

The two views stay in sync: editing the form regenerates code,
and switching to code view lets the user edit the source directly.
"""

from __future__ import annotations

import ast
import re
from typing import Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango

from bluep.core.class_info import (
    ClassInfo, ClassKind, FieldInfo, MethodInfo,
    create_default_template,
)
from bluep.ui.code_editor import CodeEditor


_KIND_OPTIONS = [
    ("Concrete Class", ClassKind.CONCRETE),
    ("Abstract Class", ClassKind.ABSTRACT),
    ("Interface (ABC)", ClassKind.INTERFACE),
    ("Enumeration", ClassKind.ENUM),
    ("Dataclass", ClassKind.DATACLASS),
]


class ClassEditorDialog(Gtk.Window):
    """Graphical class editor with graphics/code view toggle."""

    __gsignals__ = {
        "class-saved": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(
        self,
        parent: Gtk.Window | None = None,
        class_info: ClassInfo | None = None,
        on_save: Any = None,
    ) -> None:
        super().__init__()
        self.set_title("Class Editor")
        self.set_default_size(900, 700)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("bluep-dialog")

        self._on_save = on_save
        self._class_info = class_info
        self._is_new = class_info is None
        self._suppress_sync = False

        if class_info is not None:
            self._name = class_info.name
            self._kind = class_info.kind
            self._fields = list(class_info.fields)
            self._methods = list(class_info.methods)
            initial_code = (
                class_info.source_file.read_text()
                if class_info.source_file and class_info.source_file.exists()
                else create_default_template(class_info.name, class_info.kind)
            )
        else:
            self._name = ""
            self._kind = ClassKind.CONCRETE
            self._fields = []
            self._methods = []
            initial_code = ""

        main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.set_child(main_box)

        header = Gtk.HeaderBar.new()
        header.set_title_widget(Gtk.Label.new(
            "New Class" if self._is_new else f"Edit {self._name}"
        ))
        main_box.append(header)

        view_switcher = Gtk.StackSwitcher.new()
        view_switcher.set_margin_start(8)
        view_switcher.set_margin_end(8)
        view_switcher.set_margin_top(8)
        main_box.append(view_switcher)

        self._stack = Gtk.Stack.new()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_vexpand(True)
        self._stack.set_margin_start(12)
        self._stack.set_margin_end(12)
        self._stack.set_margin_top(4)
        self._stack.set_margin_bottom(12)
        main_box.append(self._stack)
        view_switcher.set_stack(self._stack)

        self._build_graphics_view()
        self._build_code_view(initial_code)

        btn_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.add_css_class("bluep-dialog-actions")
        btn_box.set_margin_start(12)
        btn_box.set_margin_end(12)
        btn_box.set_margin_bottom(12)

        btn_cancel = Gtk.Button.new_with_label("Cancel")
        btn_cancel.add_css_class("bluep-btn")
        btn_cancel.connect("clicked", lambda b: self.destroy())
        btn_box.append(btn_cancel)

        btn_save = Gtk.Button.new_with_label("Save")
        btn_save.add_css_class("bluep-btn-primary")
        btn_save.connect("clicked", self._on_save_clicked)
        btn_box.append(btn_save)

        main_box.append(btn_box)

        if not self._is_new:
            self._populate_from_class_info()

    def _build_graphics_view(self) -> None:
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)

        name_row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        name_label = Gtk.Label.new("Class Name:")
        name_label.set_xalign(0)
        name_label.set_size_request(100, -1)
        name_row.append(name_label)
        self._g_name = Gtk.Entry.new()
        self._g_name.set_placeholder_text("e.g., Student, Person, Car")
        self._g_name.set_hexpand(True)
        self._g_name.connect("changed", self._on_graphics_changed)
        name_row.append(self._g_name)
        box.append(name_row)

        kind_row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        kind_label = Gtk.Label.new("Class Type:")
        kind_label.set_xalign(0)
        kind_label.set_size_request(100, -1)
        kind_row.append(kind_label)
        self._g_kind = Gtk.DropDown.new_from_strings(
            [label for label, _ in _KIND_OPTIONS]
        )
        self._g_kind.connect("notify::selected", self._on_graphics_changed)
        kind_row.append(self._g_kind)
        box.append(kind_row)

        fields_pane = self._build_fields_pane()
        methods_pane = self._build_methods_pane()

        paned = Gtk.Paned.new(Gtk.Orientation.VERTICAL)
        paned.set_vexpand(True)
        paned.set_position(220)
        paned.set_start_child(fields_pane)
        paned.set_end_child(methods_pane)
        paned.set_resize_start_child(True)
        paned.set_resize_end_child(True)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        box.append(paned)

        self._stack.add_titled(box, "graphics", "Graphics")
        self._update_section_counts()

    def _build_fields_pane(self) -> Gtk.Box:
        pane = Gtk.Box.new(Gtk.Orientation.VERTICAL, 4)
        pane.set_vexpand(True)

        header_bar = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 6)
        self._fields_count_label = Gtk.Label.new("Fields")
        self._fields_count_label.set_halign(Gtk.Align.START)
        self._fields_count_label.set_hexpand(True)
        self._fields_count_label.add_css_class("bluep-welcome-section")
        header_bar.append(self._fields_count_label)
        btn_add_field = Gtk.Button.new_with_label("+ Add Field")
        btn_add_field.add_css_class("bluep-btn")
        btn_add_field.connect("clicked", lambda b: self._add_field_row())
        header_bar.append(btn_add_field)
        pane.append(header_bar)

        pane.append(self._build_field_col_header())

        self._fields_list = Gtk.Box.new(Gtk.Orientation.VERTICAL, 2)
        self._fields_empty = Gtk.Label.new(
            "No fields yet \u2014 click \"+ Add Field\" to create one."
        )
        self._fields_empty.add_css_class("bluep-editor-empty")
        self._fields_empty.set_halign(Gtk.Align.START)
        self._fields_empty.set_margin_start(8)
        self._fields_empty.set_margin_top(8)
        self._fields_empty.set_margin_bottom(8)
        self._fields_list.append(self._fields_empty)
        fields_scroll = Gtk.ScrolledWindow.new()
        fields_scroll.set_child(self._fields_list)
        fields_scroll.set_vexpand(True)
        fields_scroll.set_min_content_height(80)
        pane.append(fields_scroll)
        self._fields_scroll = fields_scroll
        return pane

    def _build_methods_pane(self) -> Gtk.Box:
        pane = Gtk.Box.new(Gtk.Orientation.VERTICAL, 4)
        pane.set_vexpand(True)

        header_bar = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 6)
        self._methods_count_label = Gtk.Label.new("Methods")
        self._methods_count_label.set_halign(Gtk.Align.START)
        self._methods_count_label.set_hexpand(True)
        self._methods_count_label.add_css_class("bluep-welcome-section")
        header_bar.append(self._methods_count_label)
        btn_add_method = Gtk.Button.new_with_label("+ Add Method")
        btn_add_method.add_css_class("bluep-btn")
        btn_add_method.connect("clicked", lambda b: self._add_method_row())
        header_bar.append(btn_add_method)
        pane.append(header_bar)

        pane.append(self._build_method_col_header())

        self._methods_list = Gtk.Box.new(Gtk.Orientation.VERTICAL, 2)
        self._methods_empty = Gtk.Label.new(
            "No methods yet \u2014 click \"+ Add Method\" to create one."
        )
        self._methods_empty.add_css_class("bluep-editor-empty")
        self._methods_empty.set_halign(Gtk.Align.START)
        self._methods_empty.set_margin_start(8)
        self._methods_empty.set_margin_top(8)
        self._methods_empty.set_margin_bottom(8)
        self._methods_list.append(self._methods_empty)
        methods_scroll = Gtk.ScrolledWindow.new()
        methods_scroll.set_child(self._methods_list)
        methods_scroll.set_vexpand(True)
        methods_scroll.set_min_content_height(80)
        pane.append(methods_scroll)
        self._methods_scroll = methods_scroll
        return pane

    def _build_field_col_header(self) -> Gtk.Box:
        header = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        header.add_css_class("bluep-editor-col-header")
        h_vis = Gtk.Label.new("Vis")
        h_vis.set_xalign(0.5)
        h_vis.set_size_request(40, -1)
        header.append(h_vis)
        h_cv = Gtk.Label.new("Scope")
        h_cv.set_xalign(0)
        h_cv.set_size_request(90, -1)
        header.append(h_cv)
        h_name = Gtk.Label.new("Name")
        h_name.set_xalign(0)
        h_name.set_hexpand(True)
        header.append(h_name)
        h_type = Gtk.Label.new("Type")
        h_type.set_xalign(0)
        h_type.set_hexpand(True)
        header.append(h_type)
        h_rm = Gtk.Label.new("")
        h_rm.set_size_request(32, -1)
        header.append(h_rm)
        return header

    def _build_method_col_header(self) -> Gtk.Box:
        header = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        header.add_css_class("bluep-editor-col-header")
        h_vis = Gtk.Label.new("Vis")
        h_vis.set_xalign(0.5)
        h_vis.set_size_request(40, -1)
        header.append(h_vis)
        h_name = Gtk.Label.new("Name")
        h_name.set_xalign(0)
        h_name.set_hexpand(True)
        header.append(h_name)
        h_params = Gtk.Label.new("Parameters")
        h_params.set_xalign(0)
        h_params.set_hexpand(True)
        header.append(h_params)
        h_ret = Gtk.Label.new("Return")
        h_ret.set_xalign(0)
        h_ret.set_hexpand(True)
        header.append(h_ret)
        h_rm = Gtk.Label.new("")
        h_rm.set_size_request(32, -1)
        header.append(h_rm)
        return header

    def _build_code_view(self, initial_code: str) -> None:
        self._code_editor = CodeEditor()
        self._code_editor.set_text(initial_code)
        self._code_editor.set_hexpand(True)
        self._code_editor.set_vexpand(True)
        self._stack.add_titled(self._code_editor, "code", "Code")
        self._stack.connect("notify::visible-child", self._on_view_changed)

    def _populate_from_class_info(self) -> None:
        if self._class_info is None:
            return
        self._suppress_sync = True
        self._g_name.set_text(self._class_info.name)
        for i, (_, kind) in enumerate(_KIND_OPTIONS):
            if kind == self._class_info.kind:
                self._g_kind.set_selected(i)
                break
        for field in self._class_info.fields:
            self._add_field_row(field)
        for method in self._class_info.methods:
            self._add_method_row(method)
        self._suppress_sync = False
        self._sync_code_from_graphics()

    def _add_field_row(self, field: FieldInfo | None = None) -> None:
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        row.add_css_class("bluep-editor-row")

        vis_combo = Gtk.DropDown.new_from_strings(["+", "-"])
        vis_combo.set_selected(0 if field is None or not field.is_private else 1)
        vis_combo.set_valign(Gtk.Align.CENTER)
        vis_combo.set_size_request(40, -1)
        row.append(vis_combo)

        cv_combo = Gtk.DropDown.new_from_strings(["instance", "class ($)"])
        cv_combo.set_selected(1 if field is not None and field.is_class_var else 0)
        cv_combo.set_valign(Gtk.Align.CENTER)
        cv_combo.set_size_request(90, -1)
        row.append(cv_combo)

        name_entry = Gtk.Entry.new()
        name_entry.set_placeholder_text("field_name")
        name_entry.set_hexpand(True)
        if field is not None:
            name_entry.set_text(field.name)
        name_entry.connect("changed", self._on_graphics_changed)
        row.append(name_entry)

        type_entry = Gtk.Entry.new()
        type_entry.set_placeholder_text("type (optional)")
        type_entry.set_hexpand(True)
        if field is not None and field.type_annotation:
            type_entry.set_text(field.type_annotation)
        type_entry.connect("changed", self._on_graphics_changed)
        row.append(type_entry)

        btn_remove = Gtk.Button.new_from_icon_name("list-remove-symbolic")
        btn_remove.add_css_class("bluep-btn-icon")
        btn_remove.set_tooltip_text("Remove field")
        btn_remove.set_valign(Gtk.Align.CENTER)
        btn_remove.connect("clicked", lambda b: self._remove_row(row, self._fields_list))
        row.append(btn_remove)

        row.vis_combo = vis_combo
        row.cv_combo = cv_combo
        row.name_entry = name_entry
        row.type_entry = type_entry
        self._fields_list.append(row)
        self._restripe_rows(self._fields_list)
        self._update_empty_states()
        self._update_section_counts()
        if field is None:
            GLib.idle_add(name_entry.grab_focus)
            GLib.idle_add(lambda: self._scroll_to_row(self._fields_scroll, row))

    def _add_method_row(self, method: MethodInfo | None = None) -> None:
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        row.add_css_class("bluep-editor-row")

        vis_combo = Gtk.DropDown.new_from_strings(["+", "-"])
        vis_combo.set_selected(0 if method is None or not method.is_private else 1)
        vis_combo.set_valign(Gtk.Align.CENTER)
        vis_combo.set_size_request(40, -1)
        row.append(vis_combo)

        name_entry = Gtk.Entry.new()
        name_entry.set_placeholder_text("method_name")
        name_entry.set_hexpand(True)
        if method is not None:
            name_entry.set_text(method.name)
        name_entry.connect("changed", self._on_graphics_changed)
        row.append(name_entry)

        params_entry = Gtk.Entry.new()
        params_entry.set_placeholder_text("params: name:type, name2:type2")
        params_entry.set_hexpand(True)
        if method is not None:
            params_str = ", ".join(
                f"{n}: {t}" if t else n for n, t in method.params
            )
            params_entry.set_text(params_str)
        params_entry.connect("changed", self._on_graphics_changed)
        row.append(params_entry)

        ret_entry = Gtk.Entry.new()
        ret_entry.set_placeholder_text("return type (optional)")
        ret_entry.set_hexpand(True)
        if method is not None and method.return_type:
            ret_entry.set_text(method.return_type)
        ret_entry.connect("changed", self._on_graphics_changed)
        row.append(ret_entry)

        btn_remove = Gtk.Button.new_from_icon_name("list-remove-symbolic")
        btn_remove.add_css_class("bluep-btn-icon")
        btn_remove.set_tooltip_text("Remove method")
        btn_remove.set_valign(Gtk.Align.CENTER)
        btn_remove.connect("clicked", lambda b: self._remove_row(row, self._methods_list))
        row.append(btn_remove)

        row.vis_combo = vis_combo
        row.name_entry = name_entry
        row.params_entry = params_entry
        row.ret_entry = ret_entry
        self._methods_list.append(row)
        self._restripe_rows(self._methods_list)
        self._update_empty_states()
        self._update_section_counts()
        if method is None:
            GLib.idle_add(name_entry.grab_focus)
            GLib.idle_add(lambda: self._scroll_to_row(self._methods_scroll, row))

    def _remove_row(self, row: Gtk.Widget, parent: Gtk.Box) -> None:
        parent.remove(row)
        self._restripe_rows(parent)
        self._update_empty_states()
        self._update_section_counts()
        self._on_graphics_changed()

    def _iter_children(self, container: Gtk.Box):
        child = container.get_first_child()
        while child is not None:
            yield child
            child = child.get_next_sibling()

    def _scroll_to_row(self, scroll: Gtk.ScrolledWindow, row: Gtk.Widget) -> None:
        vadj = scroll.get_vadjustment()
        alloc = row.get_allocation()
        y = alloc.y
        h = alloc.height
        value = vadj.get_value()
        page = vadj.get_page_size()
        if y < value:
            vadj.set_value(max(0, y - 4))
        elif y + h > value + page:
            vadj.set_value(y + h - page + 4)

    def _restripe_rows(self, container: Gtk.Box) -> None:
        idx = 0
        for child in self._iter_children(container):
            if isinstance(child, Gtk.Label):
                continue
            child.remove_css_class("bluep-editor-row-odd")
            child.remove_css_class("bluep-editor-row-even")
            child.add_css_class(
                "bluep-editor-row-odd" if idx % 2 else "bluep-editor-row-even"
            )
            idx += 1

    def _update_empty_states(self) -> None:
        fields_has_rows = any(
            not isinstance(c, Gtk.Label)
            for c in self._iter_children(self._fields_list)
        )
        self._fields_empty.set_visible(not fields_has_rows)
        methods_has_rows = any(
            not isinstance(c, Gtk.Label)
            for c in self._iter_children(self._methods_list)
        )
        self._methods_empty.set_visible(not methods_has_rows)

    def _update_section_counts(self) -> None:
        field_count = sum(
            1 for c in self._iter_children(self._fields_list)
            if not isinstance(c, Gtk.Label)
        )
        method_count = sum(
            1 for c in self._iter_children(self._methods_list)
            if not isinstance(c, Gtk.Label)
        )
        self._fields_count_label.set_text(f"Fields ({field_count})")
        self._methods_count_label.set_text(f"Methods ({method_count})")

    def _on_graphics_changed(self, *_args: Any) -> None:
        if self._suppress_sync:
            return
        self._sync_code_from_graphics()

    def _sync_code_from_graphics(self) -> None:
        name = self._g_name.get_text().strip() or "NewClass"
        kind_idx = self._g_kind.get_selected()
        kind = _KIND_OPTIONS[kind_idx][1] if kind_idx < len(_KIND_OPTIONS) else ClassKind.CONCRETE

        fields: list[FieldInfo] = []
        child = self._fields_list.get_first_child()
        while child is not None:
            vis = getattr(child, "vis_combo", None)
            cv = getattr(child, "cv_combo", None)
            ne = getattr(child, "name_entry", None)
            te = getattr(child, "type_entry", None)
            if isinstance(vis, Gtk.DropDown) and isinstance(ne, Gtk.Entry):
                fname = ne.get_text().strip()
                if fname:
                    fields.append(FieldInfo(
                        name=fname,
                        type_annotation=te.get_text().strip() or None,
                        is_class_var=cv.get_selected() == 1,
                        is_private=vis.get_selected() == 1,
                    ))
            child = child.get_next_sibling()

        methods: list[MethodInfo] = []
        child = self._methods_list.get_first_child()
        while child is not None:
            vis = getattr(child, "vis_combo", None)
            ne = getattr(child, "name_entry", None)
            pe = getattr(child, "params_entry", None)
            re_ = getattr(child, "ret_entry", None)
            if isinstance(vis, Gtk.DropDown) and isinstance(ne, Gtk.Entry):
                mname = ne.get_text().strip()
                if mname:
                    params = []
                    raw = pe.get_text().strip()
                    if raw:
                        for p in raw.split(","):
                            p = p.strip()
                            if ":" in p:
                                pn, pt = p.split(":", 1)
                                params.append((pn.strip(), pt.strip()))
                            elif p:
                                params.append((p, None))
                    methods.append(MethodInfo(
                        name=mname,
                        params=params,
                        return_type=re_.get_text().strip() or None,
                        is_private=vis.get_selected() == 1,
                    ))
            child = child.get_next_sibling()

        code = self._generate_code(name, kind, fields, methods)
        self._suppress_sync = True
        self._code_editor.set_text(code)
        self._suppress_sync = False

    def _generate_code(
        self, name: str, kind: ClassKind,
        fields: list[FieldInfo], methods: list[MethodInfo],
    ) -> str:
        lines: list[str] = [f'"""Class {name}."""', ""]

        if kind == ClassKind.INTERFACE:
            lines.append("from abc import ABC, abstractmethod")
            lines.append("")
            lines.append(f"class {name}(ABC):")
            lines.append(f'    """{name} interface."""')
            lines.append("")
            if not methods:
                lines.append("    pass")
            else:
                for m in methods:
                    params = ", ".join(
                        f"{n}: {t}" if t else n for n, t in m.params
                    )
                    ret = f" -> {m.return_type}" if m.return_type else " -> None"
                    lines.append("    @abstractmethod")
                    lines.append(f"    def {m.name}({params}){ret}:")
                    lines.append(f'        """{m.name}."""')
                    lines.append("        ...")
                    lines.append("")
            return "\n".join(lines) + "\n"

        if kind == ClassKind.ENUM:
            lines.append("from enum import Enum")
            lines.append("")
            lines.append(f"class {name}(Enum):")
            lines.append(f'    """{name} enumeration."""')
            lines.append("")
            if not fields:
                lines.append("    pass")
            else:
                for f in fields:
                    lines.append(f"    {f.name.upper()} = 0")
            return "\n".join(lines) + "\n"

        if kind == ClassKind.ABSTRACT:
            lines.append("from abc import ABC, abstractmethod")
            lines.append("")
            lines.append(f"class {name}(ABC):")
            lines.append(f'    """{name} abstract class."""')
            lines.append("")
        elif kind == ClassKind.DATACLASS:
            lines.append("from dataclasses import dataclass")
            lines.append("")
            lines.append("@dataclass")
            lines.append(f"class {name}:")
            lines.append(f'    """{name} dataclass."""')
            lines.append("")
            for f in fields:
                typ = f.type_annotation or "Any"
                if f.is_class_var:
                    lines.append(f"    {f.name}: {typ} = None")
                else:
                    lines.append(f"    {f.name}: {typ}")
            if not fields:
                lines.append("    pass")
            lines.append("")
            for m in methods:
                params = ", ".join(
                    f"{n}: {t}" if t else n for n, t in m.params
                )
                ret = f" -> {m.return_type}" if m.return_type else ""
                if m.is_private:
                    prefix = "_" if not m.name.startswith("_") else ""
                else:
                    prefix = ""
                lines.append(f"    def {prefix}{m.name}({params}){ret}:")
                lines.append(f'        """{m.name}."""')
                lines.append("        pass")
                lines.append("")
            return "\n".join(lines) + "\n"
        else:
            lines.append(f"class {name}:")
            lines.append(f'    """{name} class."""')
            lines.append("")

        has_init = any(m.name == "__init__" for m in methods)
        if not has_init and fields:
            params = ", ".join(f.name for f in fields if not f.is_class_var)
            lines.append(f"    def __init__(self, {params}) -> None:")
            lines.append(f'        """Initialize {name}."""')
            for f in fields:
                if not f.is_class_var:
                    lines.append(f"        self.{f.name} = {f.name}")
            lines.append("")

        for f in fields:
            if f.is_class_var:
                prefix = "_" if f.is_private else ""
                typ = f.type_annotation or "Any"
                lines.append(f"    {prefix}{f.name}: {typ} = None")

        for m in methods:
            params = ", ".join(
                f"{n}: {t}" if t else n for n, t in m.params
            )
            ret = f" -> {m.return_type}" if m.return_type else ""
            prefix = "_" if m.is_private and not m.name.startswith("_") else ""
            lines.append(f"    def {prefix}{m.name}({params}){ret}:")
            lines.append(f'        """{m.name}."""')
            lines.append("        pass")
            lines.append("")

        if not fields and not methods:
            lines.append("    pass")

        return "\n".join(lines) + "\n"

    def _on_view_changed(self, stack: Gtk.Stack, _pspec: Any) -> None:
        if self._suppress_sync:
            return
        visible = stack.get_visible_child_name()
        if visible == "code":
            self._sync_code_from_graphics()

    def _on_save_clicked(self, button: Gtk.Button) -> None:
        name = self._g_name.get_text().strip()
        if not name:
            return
        if not name.isidentifier():
            return

        code = self._code_editor.get_text()

        if self._on_save:
            self._on_save(name, code)
        self.emit("class-saved", name)
        self.destroy()

    def get_code(self) -> str:
        return self._code_editor.get_text()

    def get_class_name(self) -> str:
        return self._g_name.get_text().strip()

    def get_class_kind(self) -> ClassKind:
        idx = self._g_kind.get_selected()
        return _KIND_OPTIONS[idx][1] if idx < len(_KIND_OPTIONS) else ClassKind.CONCRETE
