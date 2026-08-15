"""Terminal/output window widget for BlueP.

Mirrors BlueJ's terminal window:
- Shows program output (stdout/stderr)
- Options menu: clear, save, record method calls, unlimited buffering
- Auto-pops up when output is written

In BlueP, this widget captures and displays all program output.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango


class Terminal(Gtk.Box):
    """Terminal output display for BlueP.

    Shows program output, can be cleared, saved, and configured.
    """

    __gsignals__ = {
        "output-written": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self.add_css_class("bluep-terminal")

        # Toolbar
        toolbar = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        toolbar.set_margin_start(4)
        toolbar.set_margin_end(4)
        toolbar.set_margin_top(4)
        toolbar.set_margin_bottom(4)

        self._unlimited = False
        self._record_calls = False
        self._clear_on_call = False
        self._max_lines = 500

        btn_clear = Gtk.Button.new_from_icon_name("edit-clear-all")
        btn_clear.set_tooltip_text("Clear terminal (Ctrl+K)")
        btn_clear.connect("clicked", lambda b: self.clear())
        toolbar.append(btn_clear)

        btn_save = Gtk.Button.new_from_icon_name("document-save")
        btn_save.set_tooltip_text("Save output to file")
        btn_save.connect("clicked", self._on_save)
        toolbar.append(btn_save)

        # Separator
        sep = Gtk.Separator.new(Gtk.Orientation.VERTICAL)
        toolbar.append(sep)

        # Toggle: Unlimited buffering
        self._toggle_unlimited = Gtk.ToggleButton.new()
        self._toggle_unlimited.set_label("Unlimited")
        self._toggle_unlimited.set_tooltip_text("Keep unlimited output lines")
        self._toggle_unlimited.connect("toggled", self._on_unlimited_toggled)
        toolbar.append(self._toggle_unlimited)

        # Toggle: Record method calls
        self._toggle_record = Gtk.ToggleButton.new()
        self._toggle_record.set_label("Record calls")
        self._toggle_record.set_tooltip_text("Record method call details")
        self._toggle_record.connect("toggled", self._on_record_toggled)
        toolbar.append(self._toggle_record)

        # Toggle: Clear at method call
        self._toggle_clear = Gtk.ToggleButton.new()
        self._toggle_clear.set_label("Auto-clear")
        self._toggle_clear.set_tooltip_text("Clear screen at each method call")
        self._toggle_clear.connect("toggled", self._on_clear_toggled)
        toolbar.append(self._toggle_clear)

        self.append(toolbar)

        # Separator
        self.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))

        # Output area
        self._textview = Gtk.TextView.new()
        self._textview.set_editable(False)
        self._textview.set_monospace(True)
        self._textview.set_wrap_mode(Gtk.WrapMode.CHAR)
        self._textview.set_top_margin(8)
        self._textview.set_left_margin(8)
        self._textview.set_right_margin(8)
        self._textview.set_bottom_margin(8)

        # Set dark theme via CSS
        buffer = self._textview.get_buffer()
        buffer.create_tag("stdout", foreground="#cdd6f4", family="monospace")
        buffer.create_tag("stderr", foreground="#f38ba8", family="monospace")
        buffer.create_tag("call", foreground="#89b4fa", family="monospace", weight=Pango.Weight.BOLD)
        buffer.create_tag("result", foreground="#a6e3a1", family="monospace")
        buffer.create_tag("error", foreground="#f38ba8", family="monospace", weight=Pango.Weight.BOLD)
        buffer.create_tag("info", foreground="#a6adc8", family="monospace", style=Pango.Style.ITALIC)
        buffer.create_tag("timestamp", foreground="#585b70", family="monospace", scale=0.8)

        scroll = Gtk.ScrolledWindow.new()
        scroll.set_child(self._textview)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        self.append(scroll)

        # Key controller for Ctrl+K
        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

    def write_output(self, text: str, stream: str = "stdout") -> None:
        """Write output to the terminal."""
        if self._clear_on_call and stream == "call":
            self.clear()

        tag_name = stream if stream in ("stdout", "stderr", "call", "result", "error", "info") else "stdout"

        buffer = self._textview.get_buffer()
        end_iter = buffer.get_end_iter()

        # Timestamp
        ts = time.strftime("%H:%M:%S")
        buffer.insert_with_tags(end_iter, f"[{ts}] ", buffer.get_tag_table().lookup("timestamp"))

        end_iter = buffer.get_end_iter()
        tag = buffer.get_tag_table().lookup(tag_name)
        buffer.insert_with_tags(end_iter, text + "\n", tag)

        self.emit("output-written", text)

        # Auto-scroll
        end_iter = buffer.get_end_iter()
        self._textview.scroll_to_iter(end_iter, 0.0, True, 0.5, 0.5)

        # Limit lines if not unlimited
        if not self._unlimited:
            self._trim_lines()

    def write_call(self, call_text: str) -> None:
        """Write a method call record."""
        if self._record_calls:
            self.write_output(call_text, "call")

    def write_result(self, result: str) -> None:
        """Write a result value."""
        self.write_output(result, "result")

    def write_error(self, error: str) -> None:
        """Write an error message."""
        self.write_output(error, "error")

    def write_info(self, info: str) -> None:
        """Write an info message."""
        self.write_output(info, "info")

    def clear(self) -> None:
        """Clear all output."""
        self._textview.get_buffer().set_text("")

    def get_text(self) -> str:
        """Get all terminal text."""
        buffer = self._textview.get_buffer()
        start = buffer.get_start_iter()
        end = buffer.get_end_iter()
        return buffer.get_text(start, end, True)

    def _trim_lines(self) -> None:
        """Trim output to max lines."""
        buffer = self._textview.get_buffer()
        line_count = buffer.get_line_count()
        if line_count > self._max_lines:
            start = buffer.get_start_iter()
            success, end = buffer.get_iter_at_line(line_count - self._max_lines)
            if success:
                buffer.delete(start, end)

    def _on_save(self, button: Gtk.Button) -> None:
        """Save terminal output to a file."""
        dialog = Gtk.FileChooserNative.new(
            "Save terminal output",
            None,
            Gtk.FileChooserAction.SAVE,
            "Save",
            "Cancel",
        )
        dialog.set_current_name("bluep_output.txt")
        dialog.connect("response", self._on_save_response)
        dialog.show()

    def _on_save_response(self, dialog: Gtk.Dialog, response: int) -> None:
        if response == Gtk.ResponseType.OK:
            filepath = dialog.get_file().get_path()
            if filepath:
                Path(filepath).write_text(self.get_text())
        dialog.destroy()

    def _on_unlimited_toggled(self, button: Gtk.ToggleButton) -> None:
        self._unlimited = button.get_active()

    def _on_record_toggled(self, button: Gtk.ToggleButton) -> None:
        self._record_calls = button.get_active()

    def _on_clear_toggled(self, button: Gtk.ToggleButton) -> None:
        self._clear_on_call = button.get_active()

    def _on_key(self, controller: Gtk.EventControllerKey, keyval: int,
                keycode: int, state: Gdk.ModifierType) -> bool:
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and keyval in (ord("k"), ord("K")):
            self.clear()
            return True
        return False
