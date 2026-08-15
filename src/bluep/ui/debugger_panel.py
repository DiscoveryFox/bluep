"""Debugger panel widget for BlueP.

Mirrors BlueJ's debugger window:
- Step / Step Into / Continue / Terminate buttons
- Call stack display (clickable to inspect each frame)
- Local variables list (double-click to inspect object values)
- Current execution position indicator

Connects to BluePDebugger and updates when execution pauses at breakpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango

from bluep.core.debugger import BluePDebugger, DebugState, StackFrame


class DebuggerPanel(Gtk.Box):
    """Debugger control panel - mirrors BlueJ's debugger window.

    Shows:
    - Execution control buttons (Step, Step Into, Continue, Terminate)
    - Call stack with clickable frames
    - Local variables for the selected stack frame
    """

    __gsignals__ = {
        "step": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "step-into": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "step-out": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "continue-exec": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "terminate": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "frame-selected": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self, debugger: BluePDebugger) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.debugger = debugger
        self.add_css_class("bluep-debug-panel")

        self._current_frame_index = 0
        self._state: DebugState | None = None

        # --- Toolbar with execution control buttons ---
        toolbar = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        toolbar.set_margin_start(4)
        toolbar.set_margin_end(4)
        toolbar.set_margin_top(4)
        toolbar.set_margin_bottom(4)

        self._btn_step = Gtk.Button.new_with_label("Step")
        self._btn_step.set_tooltip_text("Step over (execute whole method call)")
        self._btn_step.set_sensitive(False)
        self._btn_step.connect("clicked", lambda b: self.emit("step"))
        toolbar.append(self._btn_step)

        self._btn_step_into = Gtk.Button.new_with_label("Step Into")
        self._btn_step_into.set_tooltip_text("Step into method call")
        self._btn_step_into.set_sensitive(False)
        self._btn_step_into.connect("clicked", lambda b: self.emit("step-into"))
        toolbar.append(self._btn_step_into)

        self._btn_step_out = Gtk.Button.new_with_label("Step Out")
        self._btn_step_out.set_tooltip_text("Step out of current method")
        self._btn_step_out.set_sensitive(False)
        self._btn_step_out.connect("clicked", lambda b: self.emit("step-out"))
        toolbar.append(self._btn_step_out)

        self._btn_continue = Gtk.Button.new_with_label("Continue")
        self._btn_continue.set_tooltip_text("Continue execution until next breakpoint")
        self._btn_continue.set_sensitive(False)
        self._btn_continue.connect("clicked", lambda b: self.emit("continue-exec"))
        toolbar.append(self._btn_continue)

        self._btn_terminate = Gtk.Button.new_with_label("Terminate")
        self._btn_terminate.set_tooltip_text("Terminate execution")
        self._btn_terminate.set_sensitive(False)
        self._btn_terminate.add_css_class("bluep-btn-danger")
        self._btn_terminate.connect("clicked", lambda b: self.emit("terminate"))
        toolbar.append(self._btn_terminate)

        self.append(toolbar)
        self.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))

        # --- Content area: stack + variables side by side ---
        paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        paned.set_hexpand(True)

        # --- Call stack ---
        stack_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        stack_label = Gtk.Label.new("Call Stack")
        stack_label.set_halign(Gtk.Align.START)
        stack_label.add_css_class("bluep-class-name")
        stack_label.set_margin_start(8)
        stack_label.set_margin_top(4)
        stack_box.append(stack_label)

        self._stack_list = Gtk.ListBox.new()
        self._stack_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._stack_list.connect("row-selected", self._on_stack_row_selected)
        stack_scroll = Gtk.ScrolledWindow.new()
        stack_scroll.set_child(self._stack_list)
        stack_scroll.set_vexpand(True)
        stack_scroll.set_min_content_width(200)
        stack_box.append(stack_scroll)

        paned.set_start_child(stack_box)
        paned.set_shrink_start_child(False)

        # --- Variables ---
        vars_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        vars_label = Gtk.Label.new("Variables")
        vars_label.set_halign(Gtk.Align.START)
        vars_label.add_css_class("bluep-class-name")
        vars_label.set_margin_start(8)
        vars_label.set_margin_top(4)
        vars_box.append(vars_label)

        self._vars_list = Gtk.ListBox.new()
        self._vars_list.set_selection_mode(Gtk.SelectionMode.NONE)
        vars_scroll = Gtk.ScrolledWindow.new()
        vars_scroll.set_child(self._vars_list)
        vars_scroll.set_vexpand(True)
        vars_scroll.set_min_content_width(200)
        vars_box.append(vars_scroll)

        paned.set_end_child(vars_box)
        paned.set_shrink_end_child(False)

        paned.set_position(250)
        self.append(paned)

        # --- Status ---
        self._status_label = Gtk.Label.new("Debugger ready")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.add_css_class("bluep-status-bar")
        self._status_label.set_margin_start(8)
        self._status_label.set_margin_top(2)
        self._status_label.set_margin_bottom(2)
        self.append(self._status_label)

    def update_state(self, state: DebugState) -> None:
        """Update the panel with current debugger state.

        Called when the debugger pauses at a breakpoint.
        """
        self._state = state
        self._current_frame_index = 0

        # Enable control buttons
        running = state.is_paused
        self._btn_step.set_sensitive(running)
        self._btn_step_into.set_sensitive(running)
        self._btn_step_out.set_sensitive(running)
        self._btn_continue.set_sensitive(running)
        self._btn_terminate.set_sensitive(running or state.is_running)

        # Update status
        if state.is_paused:
            pos = f"{state.current_function} ({state.current_file}:{state.current_line})"
            self._status_label.set_text(f"Paused at: {pos}")
        elif state.is_running:
            self._status_label.set_text("Running...")
        else:
            self._status_label.set_text("Debugger ready")

        # Populate call stack
        self._populate_stack(state.call_stack)

        # Populate variables for the current frame
        self._populate_variables(state)

    def set_idle(self) -> None:
        """Set the panel to idle state (not debugging)."""
        self._state = None
        self._btn_step.set_sensitive(False)
        self._btn_step_into.set_sensitive(False)
        self._btn_step_out.set_sensitive(False)
        self._btn_continue.set_sensitive(False)
        self._btn_terminate.set_sensitive(False)
        self._status_label.set_text("Debugger ready")

        # Clear lists
        self._clear_listbox(self._stack_list)
        self._clear_listbox(self._vars_list)

    def _populate_stack(self, stack: list[StackFrame]) -> None:
        """Populate the call stack list."""
        self._clear_listbox(self._stack_list)

        if not stack:
            self._stack_list.append(Gtk.Label.new("(no call stack)"))
            return

        for i, frame in enumerate(stack):
            row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(4)
            row.set_margin_bottom(4)

            # Frame index
            idx_label = Gtk.Label.new(str(i))
            idx_label.add_css_class("bluep-debug-variable-name")
            idx_label.set_size_request(20, -1)
            row.append(idx_label)

            # Frame info
            info_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
            info_box.set_hexpand(True)

            func_label = Gtk.Label.new(frame.function_name)
            func_label.set_halign(Gtk.Align.START)
            func_label.set_xalign(0)
            func_label.add_css_class("bluep-debug-variable-name")
            info_box.append(func_label)

            from pathlib import Path
            file_label = Gtk.Label.new(f"{Path(frame.filename).name}:{frame.line_number}")
            file_label.set_halign(Gtk.Align.START)
            file_label.set_xalign(0)
            file_label.add_css_class("bluep-status-bar")
            info_box.append(file_label)

            row.append(info_box)
            self._stack_list.append(row)

        # Select the first row (current frame)
        first_row = self._stack_list.get_row_at_index(0)
        if first_row:
            self._stack_list.select_row(first_row)

    def _populate_variables(self, state: DebugState) -> None:
        """Populate the variables list for the selected frame."""
        self._clear_listbox(self._vars_list)

        if self._current_frame_index < len(state.call_stack):
            frame = state.call_stack[self._current_frame_index]
            variables = frame.local_vars
        else:
            variables = state.local_variables

        if not variables:
            self._vars_list.append(Gtk.Label.new("(no variables)"))
            return

        # Section header: Local Variables
        header = Gtk.Label.new("Local Variables")
        header.set_halign(Gtk.Align.START)
        header.set_margin_start(8)
        header.set_margin_top(4)
        header.add_css_class("bluep-class-name")
        self._vars_list.append(header)

        for name, value_str in sorted(variables.items()):
            row = self._create_var_row(name, value_str)
            self._vars_list.append(row)

        # Also show global variables
        if state.global_variables:
            header2 = Gtk.Label.new("Global Variables")
            header2.set_halign(Gtk.Align.START)
            header2.set_margin_start(8)
            header2.set_margin_top(8)
            header2.add_css_class("bluep-class-name")
            self._vars_list.append(header2)

            for name, value_str in sorted(state.global_variables.items()):
                row = self._create_var_row(name, value_str)
                self._vars_list.append(row)

    def _create_var_row(self, name: str, value_str: str) -> Gtk.Widget:
        """Create a variable display row."""
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 12)
        row.set_margin_start(8)
        row.set_margin_end(8)
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        name_label = Gtk.Label.new(name)
        name_label.set_halign(Gtk.Align.START)
        name_label.set_xalign(0)
        name_label.add_css_class("bluep-debug-variable-name")
        name_label.set_size_request(100, -1)
        row.append(name_label)

        # Try to detect type from value
        type_label = Gtk.Label.new("=")
        type_label.set_halign(Gtk.Align.START)
        type_label.add_css_class("bluep-status-bar")
        row.append(type_label)

        value_label = Gtk.Label.new(value_str[:80])
        value_label.set_halign(Gtk.Align.START)
        value_label.set_xalign(0)
        value_label.set_hexpand(True)
        value_label.add_css_class("bluep-debug-variable-value")
        value_label.set_selectable(True)
        row.append(value_label)

        return row

    def _on_stack_row_selected(self, list_box: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        """Handle stack frame selection."""
        if row is None or self._state is None:
            return
        index = row.get_index()
        self._current_frame_index = index
        self.emit("frame-selected", index)
        self._populate_variables(self._state)

    def _clear_listbox(self, listbox: Gtk.ListBox) -> None:
        """Remove all rows from a ListBox."""
        while True:
            row = listbox.get_first_child()
            if row is None:
                break
            listbox.remove(row)
