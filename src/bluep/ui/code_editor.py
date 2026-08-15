"""Code editor widget for BlueP.

A syntax-highlighted Python code editor with:
- Line numbers
- Breakpoint gutter (click to toggle)
- Syntax highlighting via Pygments
- Auto-indentation
- Bracket matching
- Compile action (Ctrl+S or toolbar)
- Error highlighting
- Python autocomplete (keywords + builtins + buffer words)
- Bracket auto-closing
- Configurable tab width (Tab key inserts N spaces)

Mirrors BlueJ's "Moe" editor.
"""

from __future__ import annotations

import builtins as _builtins_mod
import keyword
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango

from bluep.core.class_info import ClassInfo

# Python completion sources
_PYTHON_KEYWORDS = sorted(keyword.kwlist)
_PYTHON_BUILTINS = sorted(
    name for name in dir(_builtins_mod)
    if not name.startswith("_") and name[0].isalpha()
)
_COMPLETION_WORDS = sorted(set(_PYTHON_KEYWORDS + _PYTHON_BUILTINS))

# Bracket auto-closing pairs
_BRACKET_PAIRS = {
    "(": ")",
    "[": "]",
    "{": "}",
}
_QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
}


class CodeEditor(Gtk.Box):
    """A Python source code editor with syntax highlighting.

    Features:
    - Line numbers gutter
    - Breakpoint gutter (click to toggle)
    - Syntax highlighting (Pygments-based)
    - Auto-indent
    - Compile on save
    - Error markers
    - Python autocomplete popup
    - Bracket auto-closing
    - Configurable tab width
    """

    __gsignals__ = {
        "modified-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "compile-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "breakpoint-toggled": (GObject.SignalFlags.RUN_FIRST, None, (str, int)),
    }

    def __init__(self, file_path: Path | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self.file_path = file_path
        self._modified = False
        self._breakpoints: set[int] = set()
        self._error_lines: set[int] = set()
        self._class_name: str | None = None

        # Editor config (used by key handler; defaults match EditorConfig)
        self._tab_width: int = 4
        self._insert_spaces: bool = True
        self._auto_indent: bool = True
        self._enable_autocomplete: bool = True

        # Completion state
        self._completion_popover: Gtk.Popover | None = None
        self._completion_list: Gtk.ListBox | None = None
        self._completion_words: list[str] = []
        self._completion_prefix: str = ""
        self._completion_blocked: bool = False

        # Source view with GtkSourceView
        try:
            gi.require_version("GtkSource", "5")
            from gi.repository import GtkSource
            self._buffer = GtkSource.Buffer.new()
            self._view = GtkSource.View.new_with_buffer(self._buffer)
            # Set up syntax highlighting
            manager = GtkSource.LanguageManager.new()
            lang = manager.get_language("python")
            if lang:
                self._buffer.set_language(lang)
            # Style
            style_manager = GtkSource.StyleSchemeManager.new()
            # Try to find a dark scheme
            for scheme_id in ["Catppuccin-mocha", "cobalt", "dark", "Kate", "oblivion"]:
                scheme = style_manager.get_scheme(scheme_id)
                if scheme:
                    self._buffer.set_style_scheme(scheme)
                    break
            # Line numbers
            self._view.set_show_line_numbers(True)
            # Highlight current line
            self._view.set_highlight_current_line(True)
            # Auto-indent
            self._view.set_auto_indent(True)
            # Smart backspace/home
            self._view.set_smart_backspace(True)
            self._view.set_smart_home_end(GtkSource.SmartHomeEndType.AFTER)
            # Tab width
            self._view.set_tab_width(4)
            self._view.set_insert_spaces_instead_of_tabs(True)
            # Font
            self._view.set_monospace(True)
            self._has_sourceview = True
        except (ImportError, ValueError):
            # Fall back to plain TextView
            self._buffer = Gtk.TextBuffer.new()
            self._view = Gtk.TextView.new_with_buffer(self._buffer)
            self._view.set_monospace(True)
            self._has_sourceview = False

        # Common view settings
        self._view.set_vexpand(True)
        self._view.set_hexpand(True)
        self._view.set_top_margin(8)
        self._view.set_left_margin(8)
        self._view.set_right_margin(8)
        self._view.set_bottom_margin(8)
        self._view.set_wrap_mode(Gtk.WrapMode.NONE)
        self._view.set_editable(True)
        self._view.set_cursor_visible(True)
        self._view.add_css_class("bluep-editor")

        # Buffer change tracking
        self._buffer.connect("changed", self._on_buffer_changed)

        # Key press for compile (Ctrl+S), Tab, brackets, autocomplete
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self._view.add_controller(key_controller)

        # Scrollable area
        scroll = Gtk.ScrolledWindow.new()
        scroll.set_child(self._view)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        self.append(scroll)

        # Build completion popover (lazy, shown on demand)
        self._init_completion()

        # Load file if provided
        if file_path and file_path.exists():
            self.load_file(file_path)

    # ── Completion ───────────────────────────────────────────────────

    def _init_completion(self) -> None:
        """Create the autocomplete popover (hidden by default)."""
        popover = Gtk.Popover.new()
        popover.set_parent(self._view)
        popover.set_autohide(False)
        popover.set_has_arrow(False)
        popover.add_css_class("bluep-completion")

        scrolled = Gtk.ScrolledWindow.new()
        scrolled.set_max_content_height(180)
        scrolled.set_max_content_width(280)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_propagate_natural_width(True)

        lst = Gtk.ListBox.new()
        lst.set_selection_mode(Gtk.SelectionMode.SINGLE)
        lst.add_css_class("bluep-completion-list")
        lst.connect("row-activated", self._on_completion_activated)
        scrolled.set_child(lst)
        popover.set_child(scrolled)

        self._completion_popover = popover
        self._completion_list = lst

    def _current_word_bounds(self) -> tuple[Any, Any, str]:
        """Return (start_iter, end_iter, word) at the cursor.

        The word is the maximal run of [A-Za-z0-9_] ending at the cursor.
        """
        cursor_mark = self._buffer.get_insert()
        end = self._buffer.get_iter_at_mark(cursor_mark)
        start = end.copy()
        # Walk back while previous char is a word char
        while start.backward_char():
            ch = start.get_char()
            if not (ch.isalnum() or ch == "_"):
                start.forward_char()
                break
        word = self._buffer.get_text(start, end, True)
        return start, end, word

    def _gather_completions(self, prefix: str) -> list[str]:
        """Return completion candidates for `prefix` (lowercased match).."""
        if not prefix:
            return []
        pre = prefix.lower()
        # Static keywords + builtins
        candidates = [w for w in _COMPLETION_WORDS if w.lower().startswith(pre)]
        # Words from current buffer
        text = self.get_text()
        seen = set(candidates)
        for m in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]{1,}\b", text):
            w = m.group(0)
            if w.lower().startswith(pre) and w not in seen:
                candidates.append(w)
                seen.add(w)
            if len(candidates) >= 40:
                break
        return candidates[:20]

    def _show_completions(self) -> None:
        """Compute completions for the current word and show the popover."""
        if not self._enable_autocomplete or self._completion_blocked:
            return
        start, end, word = self._current_word_bounds()
        # Need at least 1 char to trigger
        if len(word) < 1:
            self._hide_completions()
            return
        candidates = self._gather_completions(word)
        if not candidates:
            self._hide_completions()
            return
        # If the only candidate equals the word exactly, hide
        if len(candidates) == 1 and candidates[0] == word:
            self._hide_completions()
            return

        self._completion_words = candidates
        self._completion_prefix = word

        # Populate list
        lst = self._completion_list
        # Clear existing rows
        while True:
            row = lst.get_first_child()
            if row is None:
                break
            lst.remove(row)
        for w in candidates:
            label = Gtk.Label.new(w)
            label.set_xalign(0.0)
            label.set_halign(Gtk.Align.START)
            row = Gtk.ListBoxRow.new()
            row.set_child(label)
            row.add_css_class("bluep-completion-row")
            lst.append(row)
        # Select first
        first = lst.get_first_child()
        if first is not None:
            lst.select_row(first)

        # Position popover at the start of the current word
        location = self._view.get_iter_location(start)
        # Convert buffer coords to window coords (GTK4 returns x, y only)
        try:
            x, y = self._view.buffer_to_window_coords(
                Gtk.TextWindowType.TEXT,  # type: ignore[attr-defined]
                location.x,
                location.y + location.height,
            )
        except (ValueError, TypeError):
            x, y = location.x, location.y + location.height
        rect = Gdk.Rectangle()
        rect.x = x
        rect.y = y
        rect.width = 1
        rect.height = 1
        self._completion_popover.set_pointing_to(rect)
        if self._view.get_root() is not None:
            self._completion_popover.popup()

    def _hide_completions(self) -> None:
        if self._completion_popover is not None:
            self._completion_popover.popdown()

    def _completion_visible(self) -> bool:
        return self._completion_popover is not None and self._completion_popover.is_visible()

    def _on_completion_activated(self, lst: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        self._apply_completion(row)

    def _apply_completion(self, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        label = row.get_child()
        if label is None:
            return
        text = label.get_text() if hasattr(label, "get_text") else ""
        if not text:
            return
        start, end, word = self._current_word_bounds()
        # Replace the current word with the completion
        self._completion_blocked = True
        self._buffer.delete(start, end)
        self._buffer.insert(start, text, -1)
        self._completion_blocked = False
        self._hide_completions()

    def _move_completion(self, direction: int) -> None:
        """Move selection in the completion list (direction: +1 down, -1 up)."""
        lst = self._completion_list
        cur = lst.get_selected_row()
        if direction > 0:
            nxt = lst.get_row_at_index(
                (cur.get_index() + 1) if cur is not None else 0
            ) if cur is not None else lst.get_first_child()
        else:
            if cur is None:
                return
            idx = cur.get_index()
            nxt = lst.get_row_at_index(idx - 1) if idx > 0 else None
        if nxt is not None:
            lst.select_row(nxt)

    # ── Text insertion helpers ──────────────────────────────────────

    def _insert_at_cursor(self, text: str) -> None:
        """Insert text at the cursor and leave the cursor after it."""
        self._buffer.insert_at_cursor(text, -1)

    def _insert_tab(self) -> None:
        """Insert a tab worth of spaces (or a tab char) per config."""
        if self._insert_spaces:
            self._insert_at_cursor(" " * self._tab_width)
        else:
            self._insert_at_cursor("\t")

    def _handle_bracket_close(self, open_ch: str) -> bool:
        """Auto-close a bracket/quote pair. Returns True if handled."""
        # Bracket pair
        if open_ch in _BRACKET_PAIRS:
            close_ch = _BRACKET_PAIRS[open_ch]
            self._insert_at_cursor(open_ch + close_ch)
            # Move cursor back one
            cursor = self._buffer.get_insert()
            iter_ = self._buffer.get_iter_at_mark(cursor)
            iter_.backward_char()
            self._buffer.place_cursor(iter_)
            return True
        # Quote pair — only auto-close if the next char isn't the same quote
        if open_ch in _QUOTE_PAIRS:
            close_ch = _QUOTE_PAIRS[open_ch]
            # Check next char — if it's the same quote, just skip over it
            cursor = self._buffer.get_insert()
            iter_ = self._buffer.get_iter_at_mark(cursor)
            if iter_.get_char() == open_ch:
                iter_.forward_char()
                self._buffer.place_cursor(iter_)
                return True
            self._insert_at_cursor(open_ch + close_ch)
            iter_ = self._buffer.get_iter_at_mark(self._buffer.get_insert())
            iter_.backward_char()
            self._buffer.place_cursor(iter_)
            return True
        return False

    def _handle_enter_autoindent(self) -> bool:
        """For the fallback TextView path: auto-indent on Enter.

        GtkSourceView handles this natively. Returns True if handled.
        """
        if self._has_sourceview:
            return False
        if not self._auto_indent:
            return False
        cursor = self._buffer.get_insert()
        iter_ = self._buffer.get_iter_at_mark(cursor)
        line_start = iter_.copy()
        line_start.set_line(line_start.get_line())
        line_text = self._buffer.get_text(line_start, iter_, True)
        indent = ""
        for ch in line_text:
            if ch in (" ", "\t"):
                indent += ch
            else:
                break
        stripped = line_text.rstrip()
        if stripped.endswith(":"):
            indent += " " * self._tab_width
        self._insert_at_cursor("\n" + indent)
        return True

    # ── Config ───────────────────────────────────────────────────────

    def load_file(self, path: Path) -> None:
        """Load a file into the editor."""
        self.file_path = path
        content = path.read_text()
        self._buffer.set_text(content)
        self._modified = False
        self._class_name = path.stem

    def get_text(self) -> str:
        """Get the editor content."""
        start = self._buffer.get_start_iter()
        end = self._buffer.get_end_iter()
        return self._buffer.get_text(start, end, True)

    def set_text(self, text: str) -> None:
        """Set the editor content."""
        self._buffer.set_text(text)
        self._modified = False

    @property
    def is_modified(self) -> bool:
        return self._modified

    def apply_config(self, editor_config: object) -> None:
        """Apply EditorConfig settings to the underlying view.

        Silently skips properties not supported by the fallback TextView.
        """
        ec = editor_config
        view = self._view

        # Store for key handler (works in both paths)
        self._tab_width = int(getattr(ec, "tab_width", 4))
        self._insert_spaces = bool(getattr(ec, "insert_spaces", True))
        self._auto_indent = bool(getattr(ec, "auto_indent", True))
        self._enable_autocomplete = bool(getattr(ec, "enable_autocomplete", True))

        def _set(attr: str, method: str) -> None:
            if hasattr(view, method):
                getattr(view, method)(getattr(ec, attr))

        _set("tab_width", "set_tab_width")
        _set("insert_spaces", "set_insert_spaces_instead_of_tabs")
        _set("auto_indent", "set_auto_indent")
        _set("smart_backspace", "set_smart_backspace")
        _set("show_line_numbers", "set_show_line_numbers")
        _set("highlight_current_line", "set_highlight_current_line")

        if self._has_sourceview:
            try:
                from gi.repository import GtkSource
                highlight = bool(getattr(ec, "enable_syntax_highlighting", True))
                if highlight:
                    manager = GtkSource.LanguageManager.new()
                    lang = manager.get_language("python")
                    if lang:
                        self._buffer.set_language(lang)
                else:
                    self._buffer.set_language(None)
            except (ImportError, ValueError):
                pass

        # Apply font via CSS (works in both GtkSourceView and TextView)
        font_family = str(getattr(ec, "font_family", "Monospace"))
        font_size = int(getattr(ec, "font_size", 12))
        # Escape family for CSS (quote if it contains spaces)
        if " " in font_family or "," in font_family:
            font_family = f'"{font_family}"'
        css = (
            "textview.bluep-editor, "
            "textview.bluep-editor text {\n"
            f"  font-family: {font_family}, monospace;\n"
            f"  font-size: {font_size}pt;\n"
            "}\n"
        )
        try:
            provider = Gtk.CssProvider.new()
            provider.load_from_data(css.encode("utf-8"))
            self._view.get_style_context().add_provider(
                provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        except Exception:
            pass
        # Keep a Pango description for tests/inspection
        try:
            desc = Pango.FontDescription.new()
            desc.set_family(getattr(ec, "font_family", "Monospace"))
            desc.set_size(font_size * 1024)
            self._font_desc = desc
        except Exception:
            pass

    # ── Save / load ──────────────────────────────────────────────────

    def save(self) -> bool:
        """Save the editor content to file."""
        if self.file_path is None:
            return False
        self.file_path.write_text(self.get_text())
        self._modified = False
        self.emit("modified-changed", False)
        return True

    def save_as(self, path: Path) -> bool:
        """Save to a new file."""
        self.file_path = path
        return self.save()

    # ── Breakpoints ──────────────────────────────────────────────────

    def toggle_breakpoint(self, line: int) -> None:
        """Toggle a breakpoint at the given line (1-indexed)."""
        if line in self._breakpoints:
            self._breakpoints.discard(line)
        else:
            self._breakpoints.add(line)
        if self.file_path:
            self.emit("breakpoint-toggled", str(self.file_path), line)
        self._update_breakpoint_marks()

    def get_breakpoints(self) -> list[int]:
        """Get all breakpoint line numbers."""
        return sorted(self._breakpoints)

    def clear_breakpoints(self) -> None:
        """Clear all breakpoints."""
        self._breakpoints.clear()
        self._update_breakpoint_marks()

    # ── Error markers ────────────────────────────────────────────────

    def set_error_line(self, line: int) -> None:
        """Highlight an error line."""
        self._error_lines.add(line)
        self._highlight_error(line)

    def clear_errors(self) -> None:
        """Clear all error highlights."""
        self._error_lines.clear()
        if self._has_sourceview:
            from gi.repository import GtkSource
            # Remove error marks
            mark_type = self._buffer.get_mark("error")
            if mark_type:
                self._buffer.delete_mark(mark_type)

    def _highlight_error(self, line: int) -> None:
        """Highlight a line as an error."""
        if not self._has_sourceview:
            return
        from gi.repository import GtkSource
        success, start = self._buffer.get_iter_at_line(line - 1)
        if not success:
            return
        mark = GtkSource.Mark.new("error", "error")
        self._buffer.add_mark(mark, start)

    def _update_breakpoint_marks(self) -> None:
        """Update breakpoint markers in the gutter."""
        if not self._has_sourceview:
            return
        # GtkSourceView shows marks via mark attributes
        from gi.repository import GtkSource
        # Clear old marks
        marks = self._buffer.get_marks()
        for mark in marks:
            if mark.get_name() and mark.get_name().startswith("breakpoint"):
                self._buffer.delete_mark(mark)
        # Add new marks
        attr = GtkSource.MarkAttributes.new()
        # Use a red circle for breakpoints
        # In a full impl we'd set a pixbuf or icon
        for line in self._breakpoints:
            success, iter_ = self._buffer.get_iter_at_line(line - 1)
            if not success:
                continue
            mark = GtkSource.Mark.new(f"breakpoint-{line}", "breakpoint")
            self._buffer.add_mark(mark, iter_)

    # ── Buffer change tracking ────────────────────────────────────────

    def _on_buffer_changed(self, buffer: Any) -> None:
        if not self._modified:
            self._modified = True
            self.emit("modified-changed", True)
        # Trigger completions after a buffer change (unless we caused it)
        if not self._completion_blocked:
            self._show_completions()

    # ── Key handling ─────────────────────────────────────────────────

    def _on_key_pressed(self, controller: Gtk.EventControllerKey, keyval: int,
                        keycode: int, state: Gdk.ModifierType) -> bool:
        """Handle key press events."""
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        # Ctrl+S = save/compile
        if ctrl and keyval in (ord("s"), ord("S")):
            self.save()
            self.emit("compile-requested")
            self._hide_completions()
            return True

        # Ctrl+B = toggle breakpoint
        if ctrl and keyval in (ord("b"), ord("B")):
            cursor = self._buffer.get_insert()
            iter_ = self._buffer.get_iter_at_mark(cursor)
            line = iter_.get_line() + 1
            self.toggle_breakpoint(line)
            self._hide_completions()
            return True

        # Ctrl+space = force completion
        if ctrl and keyval in (ord(" "), Gdk.KEY_space):
            self._show_completions()
            return True

        # ── Completion navigation (when popover is visible) ──
        if self._completion_visible():
            if keyval == Gdk.KEY_Escape:
                self._hide_completions()
                return True
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_Tab):
                lst = self._completion_list
                row = lst.get_selected_row() if lst is not None else None
                self._apply_completion(row)
                # For Tab, also insert a normal tab after completion
                return True
            if keyval == Gdk.KEY_Down:
                self._move_completion(+1)
                return True
            if keyval == Gdk.KEY_Up:
                self._move_completion(-1)
                return True

        # ── Tab key: insert configured spaces ──
        if keyval == Gdk.KEY_Tab:
            # If completion visible, handled above; otherwise insert tab
            self._insert_tab()
            self._hide_completions()
            return True

        # ── Bracket auto-closing (no modifier) ──
        if not ctrl and not shift:
            ch = chr(keyval) if 0 <= keyval < 0x110000 else ""
            if ch in _BRACKET_PAIRS or ch in _QUOTE_PAIRS:
                self._handle_bracket_close(ch)
                return True

        # ── Enter: auto-indent for fallback path ──
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._hide_completions()
            return self._handle_enter_autoindent()

        # Any other key: hide completions on navigation keys
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Home, Gdk.KEY_End,
                       Gdk.KEY_BackSpace, Gdk.KEY_Delete):
            self._hide_completions()

        return False

    # ── Cursor / navigation ──────────────────────────────────────────

    def goto_line(self, line: int) -> None:
        """Move cursor to a specific line."""
        success, iter_ = self._buffer.get_iter_at_line(line - 1)
        if not success:
            return
        self._buffer.place_cursor(iter_)
        self._view.scroll_to_iter(iter_, 0.0, True, 0.5, 0.5)

    def get_cursor_line(self) -> int:
        """Get the current cursor line (1-indexed)."""
        cursor = self._buffer.get_insert()
        iter_ = self._buffer.get_iter_at_mark(cursor)
        return iter_.get_line() + 1

    def grab_focus_editor(self) -> None:
        """Focus the editor."""
        self._view.grab_focus()
