"""Command palette — VSCode-style quick action picker.

A modal popup triggered by Ctrl+Shift+P that lets the user search and
execute any registered window action by name. Mirrors VSCode's
command palette UX: type to filter, Up/Down to navigate, Enter to run,
Escape to close.
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, Pango


class CommandPalette(Gtk.Window):
    """Modal command palette with search + filtered list.

    Typing filters by case-insensitive substring match. Up/Down
    navigates, Enter activates the selected command, Escape closes.
    """

    __gtype_name__ = "BluePCommandPalette"

    def __init__(self, parent: Gtk.Window, commands: list[tuple[str, str]]) -> None:
        super().__init__(transient_for=parent, modal=True, deletable=False)
        self._parent = parent
        self._commands = commands
        self._filtered: list[tuple[str, str]] = list(commands)

        self.set_default_size(520, -1)
        self.add_css_class("bluep-command-palette")

        self._build_ui()
        self._populate_list()

        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.add_controller(key_controller)

    def _build_ui(self) -> None:
        outer = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)

        self._search = Gtk.SearchEntry.new()
        self._search.set_placeholder_text("Type a command name...")
        self._search.add_css_class("bluep-palette-search")
        self._search.connect("search-changed", self._on_search_changed)
        self._search.connect("activate", self._on_search_activate)
        outer.append(self._search)

        self._scrolled = Gtk.ScrolledWindow.new()
        self._scrolled.set_hexpand(True)
        self._scrolled.set_max_content_height(350)
        self._scrolled.set_propagate_natural_height(True)

        self._list = Gtk.ListBox.new()
        self._list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list.add_css_class("bluep-palette-list")
        self._list.connect("row-activated", self._on_row_activated)

        self._scrolled.set_child(self._list)
        outer.append(self._scrolled)

        self.set_child(outer)

    def _populate_list(self) -> None:
        while row := self._list.get_first_child():
            self._list.remove(row)
        self._filtered = self._filter(self._search.get_text())
        for label, action in self._filtered:
            row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 6)
            row.set_margin_start(12)
            row.set_margin_end(12)
            row.set_margin_top(6)
            row.set_margin_bottom(6)
            lbl = Gtk.Label.new(label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_hexpand(True)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            row.append(lbl)
            row._action = action  # type: ignore[attr-defined]
            self._list.append(row)
        if self._filtered:
            self._list.select_row(self._list.get_first_child())

    def _filter(self, text: str) -> list[tuple[str, str]]:
        query = text.strip().lower()
        if not query:
            return list(self._commands)
        return [
            (label, action)
            for label, action in self._commands
            if query in label.lower()
        ]

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        self._populate_list()

    def _on_search_activate(self, _entry: Gtk.SearchEntry) -> None:
        row = self._list.get_selected_row()
        if row is not None:
            self._execute(row.get_child())

    def _on_row_activated(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        self._execute(row.get_child())

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._move_selection(-1)
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._move_selection(1)
            return True
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _move_selection(self, delta: int) -> None:
        row = self._list.get_selected_row()
        if row is None:
            return
        n = self._list.get_n_children()
        idx = row.get_index()
        next_idx = (idx + delta) % n if n > 0 else 0
        target = self._list.get_row_at_index(next_idx)
        if target:
            self._list.select_row(target)

    def _execute(self, row: Gtk.Widget) -> None:
        action = getattr(row, "_action", None)
        if action:
            action_name = action.split(".", 1)[1] if "." in action else action
            self._parent.activate_action(action_name)
        self.close()

    def present_with_focus(self) -> None:
        self.present()
        self._search.grab_focus()
