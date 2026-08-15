"""Code Pad widget for BlueP.

An interactive expression evaluator - mirrors BlueJ's Code Pad.
Type Python expressions and see results instantly. Objects on the bench
are available as variables.

Features:
- Expression evaluation (eval)
- Statement execution (exec)
- Multi-line input (Shift+Enter)
- Command history (up/down arrows)
- Result display with type info
- Drag results onto the object bench
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango

from bluep.core.executor import CodeExecutor


class CodePad(Gtk.Box):
    """Interactive code pad for BlueP - like BlueJ's Code Pad.

    Allows evaluating Python expressions and statements interactively.
    Objects on the bench are available as variables.
    """

    __gsignals__ = {
        "expression-evaluated": (GObject.SignalFlags.RUN_FIRST, None, (str, str, bool)),
        "object-created": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, executor: CodeExecutor) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.executor = executor
        self.add_css_class("bluep-code-pad")

        self._history: list[str] = []
        self._history_index: int = -1
        self._multiline_buffer: list[str] = []

        # Output area (top)
        self._output = Gtk.TextView.new()
        self._output.set_editable(False)
        self._output.set_monospace(True)
        self._output.set_wrap_mode(Gtk.WrapMode.CHAR)
        self._output.set_top_margin(8)
        self._output.set_left_margin(8)
        self._output.set_right_margin(8)
        self._output.set_bottom_margin(8)

        buffer = self._output.get_buffer()
        buffer.create_tag("prompt", foreground="#89b4fa", family="monospace", weight=Pango.Weight.BOLD)
        buffer.create_tag("input", foreground="#cdd6f4", family="monospace")
        buffer.create_tag("output", foreground="#a6e3a1", family="monospace")
        buffer.create_tag("error", foreground="#f38ba8", family="monospace")
        buffer.create_tag("info", foreground="#a6adc8", family="monospace", style=Pango.Style.ITALIC)

        scroll_out = Gtk.ScrolledWindow.new()
        scroll_out.set_child(self._output)
        scroll_out.set_vexpand(True)
        scroll_out.set_hexpand(True)
        self.append(scroll_out)

        # Separator
        self.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))

        # Input area (bottom)
        input_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)

        prompt_label = Gtk.Label.new(">>>")
        prompt_label.add_css_class("bluep-status-bar")
        prompt_label.set_margin_start(8)
        prompt_label.set_margin_end(4)
        prompt_label.set_margin_top(8)
        prompt_label.set_margin_bottom(8)
        input_box.append(prompt_label)

        self._input = Gtk.TextView.new()
        self._input.set_monospace(True)
        self._input.set_wrap_mode(Gtk.WrapMode.CHAR)
        self._input.set_top_margin(6)
        self._input.set_bottom_margin(6)
        self._input.set_left_margin(4)
        self._input.set_right_margin(8)
        self._input.set_hexpand(True)
        self._input.set_size_request(-1, 32)

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key)
        self._input.add_controller(key_ctrl)

        scroll_in = Gtk.ScrolledWindow.new()
        scroll_in.set_child(self._input)
        scroll_in.set_size_request(-1, 40)
        scroll_in.set_hexpand(True)
        input_box.append(scroll_in)

        self.append(input_box)

        # Welcome message
        self._write_output("BlueP Code Pad - type expressions and press Enter to evaluate.\n", "info")
        self._write_output("Press Shift+Enter for multi-line input. Up/Down for history.\n\n", "info")

        # Focus input
        GLib.idle_add(self._focus_input)

    def _focus_input(self) -> bool:
        self._input.grab_focus()
        return False

    def _on_key(self, controller: Gtk.EventControllerKey, keyval: int,
                keycode: int, state: Gdk.ModifierType) -> bool:
        """Handle key press in the input area."""
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            if shift:
                # Multi-line: add to buffer, don't execute
                buffer = self._input.get_buffer()
                start = buffer.get_start_iter()
                end = buffer.get_end_iter()
                text = buffer.get_text(start, end, True)
                self._multiline_buffer.append(text)
                self._write_output("... " + text + "\n", "input")
                buffer.set_text("")
                return True
            else:
                # Execute
                self._execute_input()
                return True

        elif keyval == Gdk.KEY_Up:
            if self._history:
                if self._history_index < 0:
                    self._history_index = len(self._history)
                self._history_index = max(0, self._history_index - 1)
                self._input.get_buffer().set_text(self._history[self._history_index])
                return True

        elif keyval == Gdk.KEY_Down:
            if self._history and self._history_index >= 0:
                self._history_index = min(len(self._history), self._history_index + 1)
                if self._history_index < len(self._history):
                    self._input.get_buffer().set_text(self._history[self._history_index])
                else:
                    self._input.get_buffer().set_text("")
                return True

        return False

    def _execute_input(self) -> None:
        """Execute the current input."""
        buffer = self._input.get_buffer()
        start = buffer.get_start_iter()
        end = buffer.get_end_iter()
        text = buffer.get_text(start, end, True)

        if not text.strip():
            return

        # Combine multiline buffer with current input
        if self._multiline_buffer:
            full_input = "\n".join(self._multiline_buffer) + "\n" + text
            self._multiline_buffer.clear()
        else:
            full_input = text

        # Show the input
        self._write_output(">>> " + full_input.replace("\n", "\n... ") + "\n", "prompt")

        # Add to history
        self._history.append(text)
        self._history_index = -1

        # Clear input
        buffer.set_text("")

        # Try to evaluate first (expression)
        result = self.executor.evaluate_expression(full_input)
        if result.success:
            value_str = repr(result.value) if result.value is not None else "None"
            type_name = type(result.value).__name__ if result.value is not None else "NoneType"
            self._write_output(f"{value_str}   ({type_name})\n", "output")
            self.emit("expression-evaluated", full_input, value_str, True)
        else:
            # Try to exec (statement)
            exec_result = self.executor.execute_code(full_input)
            if exec_result.success:
                if exec_result.output:
                    self._write_output(exec_result.output, "output")
                else:
                    self._write_output("(executed)\n", "output")
                if exec_result.value is not None:
                    self._write_output(f"{repr(exec_result.value)}\n", "output")
                self.emit("expression-evaluated", full_input, "", True)
            else:
                error_msg = exec_result.error
                if exec_result.traceback_str:
                    # Show just the last line of traceback
                    lines = exec_result.traceback_str.strip().splitlines()
                    if lines:
                        error_msg = lines[-1]
                self._write_output(f"Error: {error_msg}\n", "error")
                self.emit("expression-evaluated", full_input, error_msg, False)

    def _write_output(self, text: str, tag_name: str = "output") -> None:
        """Write text to the output area."""
        buffer = self._output.get_buffer()
        end = buffer.get_end_iter()
        tag = buffer.get_tag_table().lookup(tag_name)
        buffer.insert_with_tags(end, text, tag)
        end = buffer.get_end_iter()
        self._output.scroll_to_iter(end, 0.0, True, 0.5, 0.5)

    def clear(self) -> None:
        """Clear the output."""
        self._output.get_buffer().set_text("")

    def add_bench_object_var(self, name: str) -> None:
        """Make a bench object available in the code pad."""
        obj = self.executor.bench.get(name)
        if obj:
            self.executor.namespace[name] = obj.instance
