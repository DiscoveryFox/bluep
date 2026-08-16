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
from typing import TYPE_CHECKING, Any, NamedTuple

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango

from bluep.core.class_info import ClassInfo

try:
    gi.require_version("GtkSource", "5")
    from gi.repository import GtkSource as _GtkSource  # noqa: F401
    HAS_GTKSOURCE = True
except (ImportError, ValueError):
    HAS_GTKSOURCE = False

_PYTHON_LANG: Any = None
_PYTHON_SCHEME: Any = None


def _get_python_language() -> Any:
    global _PYTHON_LANG
    if _PYTHON_LANG is not None or not HAS_GTKSOURCE:
        return _PYTHON_LANG
    manager = _GtkSource.LanguageManager.get_default()
    _PYTHON_LANG = manager.get_language("python")
    return _PYTHON_LANG


def _get_python_scheme() -> Any:
    global _PYTHON_SCHEME
    if _PYTHON_SCHEME is not None or not HAS_GTKSOURCE:
        return _PYTHON_SCHEME
    style_manager = _GtkSource.StyleSchemeManager.get_default()
    for scheme_id in ["Catppuccin-mocha", "cobalt", "dark", "Kate", "oblivion"]:
        scheme = style_manager.get_scheme(scheme_id)
        if scheme:
            _PYTHON_SCHEME = scheme
            break
    return _PYTHON_SCHEME

# Python completion sources
_PYTHON_KEYWORDS = sorted(keyword.kwlist)
_PYTHON_BUILTINS = sorted(
    name for name in dir(_builtins_mod)
    if not name.startswith("_") and name[0].isalpha()
)
_COMPLETION_WORDS = sorted(set(_PYTHON_KEYWORDS + _PYTHON_BUILTINS))

_KW_SET = set(keyword.kwlist)
_BUILTIN_SET = set(
    name for name in dir(_builtins_mod)
    if not name.startswith("_") and name[0].isalpha()
)

# Precompute builtin details: (kind, detail_label, is_callable)
_BUILTIN_DETAILS: dict[str, tuple[str, str, bool]] = {}
for _bn in _PYTHON_BUILTINS:
    _bo = getattr(_builtins_mod, _bn, None)
    if _bo is None:
        continue
    if isinstance(_bo, type):
        _BUILTIN_DETAILS[_bn] = ("class", "type", True)
    elif callable(_bo):
        _BUILTIN_DETAILS[_bn] = ("builtin", "function", True)
    else:
        _BUILTIN_DETAILS[_bn] = ("constant", "const", False)


class CompletionItem(NamedTuple):
    text: str
    kind: str
    detail: str
    insert: str
    cursor_back: int


_COMPLETION_KIND_LABEL = {
    "keyword":   ("kw",    "#cba6f7"),
    "builtin":   ("fn",    "#89b4fa"),
    "class":     ("cls",   "#f9e2af"),
    "constant":  ("const", "#fab387"),
    "def":       ("def",   "#a6e3a1"),
    "buffer":    ("var",   "#a6e3a1"),
    "attr":      ("attr",  "#89dceb"),
    "module":    ("mod",   "#f5c2e7"),
    "import":    ("imp",   "#94e2d5"),
}

_COMPLETION_KIND_CSS = {
    "keyword":   "bluep-kind-keyword",
    "builtin":   "bluep-kind-builtin",
    "class":     "bluep-kind-class",
    "constant":  "bluep-kind-constant",
    "def":       "bluep-kind-def",
    "buffer":    "bluep-kind-buffer",
    "attr":      "bluep-kind-attr",
    "module":    "bluep-kind-module",
    "import":    "bluep-kind-import",
}

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
        self._completion_accept_key: str = "tab"
        self._completion_active: bool = False

        self._font_family: str = "Monospace"
        self._font_size: int = 12
        self._css_provider: Gtk.CssProvider | None = None

        # Completion state
        self._completion_popover: Gtk.Popover | None = None
        self._completion_list: Gtk.ListBox | None = None
        self._completion_words: list[str] = []
        self._completion_prefix: str = ""
        self._completion_blocked: bool = False
        self._completion_debounce_id: int = 0

        # Ghost text state (VS Code-style inline preview)
        self._ghost_label: Gtk.Label | None = None
        self._ghost_item: CompletionItem | None = None

        # Source view with GtkSourceView
        try:
            gi.require_version("GtkSource", "5")
            from gi.repository import GtkSource
            self._buffer = GtkSource.Buffer.new()
            self._view = GtkSource.View.new_with_buffer(self._buffer)
            # Set up syntax highlighting
            lang = _get_python_language()
            if lang:
                self._buffer.set_language(lang)
            # Style
            scheme = _get_python_scheme()
            if scheme:
                self._buffer.set_style_scheme(scheme)
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
            self._buffer = Gtk.TextBuffer.new()
            self._view = Gtk.TextView.new_with_buffer(self._buffer)
            self._view.set_monospace(True)
            self._has_sourceview = False
            import warnings
            warnings.warn(
                "GtkSourceView 5 is not available - falling back to plain Gtk.TextView. "
                "Syntax highlighting, line numbers, and code folding are disabled. "
                "Install gtksourceview5 (e.g. 'pacman -S gtksourceview5' on Arch, "
                "'apt install libgtksourceview-5-dev' on Debian/Ubuntu) for full editor features.",
                stacklevel=2,
            )

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
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self._view.add_controller(key_controller)

        # Scrollable area inside overlay (for ghost text positioning)
        self._overlay = Gtk.Overlay.new()
        scroll = Gtk.ScrolledWindow.new()
        scroll.set_child(self._view)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        self._overlay.set_child(scroll)

        self._ghost_label = Gtk.Label.new("")
        self._ghost_label.add_css_class("bluep-ghost-text")
        self._ghost_label.set_visible(False)
        self._ghost_label.set_can_target(False)
        self._overlay.add_overlay(self._ghost_label)
        self._overlay.connect("get-child-position", self._on_overlay_get_child_position)

        self.append(self._overlay)
        self.connect("destroy", self._on_destroy)

        # Build completion popover (lazy, shown on demand)
        self._init_completion()

        self._apply_font_css()

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
        scrolled.set_max_content_height(240)
        scrolled.set_max_content_width(360)
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

    def _build_completion_row(self, item: CompletionItem) -> Gtk.ListBoxRow:
        badge_text, badge_color = _COMPLETION_KIND_LABEL.get(
            item.kind, ("?", "#a6adc8")
        )
        hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        badge = Gtk.Label.new(badge_text)
        badge.set_size_request(22, -1)
        badge.set_xalign(0.5)
        badge.set_valign(Gtk.Align.CENTER)
        badge.add_css_class("bluep-completion-badge")
        kind_css = _COMPLETION_KIND_CSS.get(item.kind)
        if kind_css:
            badge.add_css_class(kind_css)
        hbox.append(badge)
        name = Gtk.Label.new(item.text)
        name.set_xalign(0.0)
        name.set_halign(Gtk.Align.START)
        name.set_hexpand(True)
        name.add_css_class("bluep-completion-name")
        hbox.append(name)
        if item.detail:
            detail = Gtk.Label.new(item.detail)
            detail.set_xalign(1.0)
            detail.set_halign(Gtk.Align.END)
            detail.set_valign(Gtk.Align.CENTER)
            detail.add_css_class("bluep-completion-detail")
            hbox.append(detail)
        row = Gtk.ListBoxRow.new()
        row.set_child(hbox)
        row.add_css_class("bluep-completion-row")
        row.completion_item = item  # type: ignore[attr-defined]
        return row

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

    def _make_std_item(self, w: str) -> CompletionItem:
        if w in _KW_SET:
            return CompletionItem(w, "keyword", "keyword", w, 0)
        kind, detail, callable_ = _BUILTIN_DETAILS.get(w, ("builtin", "builtin", False))
        if callable_:
            return CompletionItem(w, kind, detail, w + "()", 1)
        return CompletionItem(w, kind, detail, w, 0)

    def _parse_buffer_names(self, text: str) -> dict[str, tuple[str, str]]:
        """Classify buffer identifiers as def/class/import/local."""
        out: dict[str, tuple[str, str]] = {}
        for line in text.splitlines():
            s = line.lstrip()
            m = re.match(r"def\s+(\w+)", s)
            if m:
                out[m.group(1)] = ("def", "def")
                continue
            m = re.match(r"class\s+(\w+)", s)
            if m:
                out[m.group(1)] = ("class", "class")
                continue
            m = re.match(r"from\s+\S+\s+import\s+(.+)", s)
            if m:
                for name in re.findall(r"\b(\w+)\b", m.group(1)):
                    if name != "as":
                        out[name] = ("import", "import")
                continue
            m = re.match(r"import\s+(\S+)\s+as\s+(\w+)", s)
            if m:
                out[m.group(2)] = ("import", "import")
                continue
            m = re.match(r"import\s+(\w+)", s)
            if m:
                out[m.group(1)] = ("import", "import")
        return out

    def _dot_object_before(self, start_iter: Any) -> str | None:
        """Return the identifier before a dot at start_iter, or None."""
        before = start_iter.copy()
        if not before.backward_char():
            return None
        if before.get_char() != ".":
            return None
        obj_end = before.copy()
        obj_start = obj_end.copy()
        while obj_start.backward_char():
            ch = obj_start.get_char()
            if not (ch.isalnum() or ch == "_"):
                obj_start.forward_char()
                break
        obj_name = self._buffer.get_text(obj_start, obj_end, True)
        return obj_name if obj_name else None

    def _gather_name_completions(self, prefix: str, exclude: str = "") -> list[CompletionItem]:
        if not prefix:
            return []
        pre = prefix.lower()
        do_substr = len(pre) >= 2
        prefix_items: list[CompletionItem] = []
        substr_items: list[CompletionItem] = []
        seen: set[str] = set()
        if exclude:
            seen.add(exclude)

        for w in _COMPLETION_WORDS:
            wl = w.lower()
            if wl.startswith(pre):
                prefix_items.append(self._make_std_item(w))
                seen.add(w)
            elif do_substr and pre in wl:
                substr_items.append(self._make_std_item(w))
                seen.add(w)

        text = self.get_text()
        classifications = self._parse_buffer_names(text)
        for m in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]{1,}\b", text):
            w = m.group(0)
            if w in seen:
                continue
            seen.add(w)
            wl = w.lower()
            kind, detail = classifications.get(w, ("buffer", "local"))
            item = CompletionItem(w, kind, detail, w, 0)
            if wl.startswith(pre):
                prefix_items.append(item)
            elif do_substr and pre in wl:
                substr_items.append(item)

        prefix_items.sort(key=lambda it: len(it.text))
        substr_items.sort(key=lambda it: len(it.text))
        return (prefix_items + substr_items)[:50]

    def _gather_attr_completions(self, obj_name: str, prefix: str) -> list[CompletionItem]:
        """Complete attributes of a builtin object after a dot."""
        obj = getattr(_builtins_mod, obj_name, None)
        if obj is None:
            return []
        pre = prefix.lower()
        do_substr = len(pre) >= 2
        prefix_items: list[CompletionItem] = []
        substr_items: list[CompletionItem] = []

        for attr in dir(obj):
            if attr.startswith("_"):
                continue
            al = attr.lower()
            attr_obj = getattr(obj, attr, None)
            if callable(attr_obj):
                item = CompletionItem(attr, "builtin", "method", attr + "()", 1)
            else:
                item = CompletionItem(attr, "constant", "attr", attr, 0)
            if al.startswith(pre):
                prefix_items.append(item)
            elif do_substr and pre in al:
                substr_items.append(item)

        prefix_items.sort(key=lambda it: len(it.text))
        substr_items.sort(key=lambda it: len(it.text))
        return (prefix_items + substr_items)[:50]

    def _show_completions(self) -> None:
        if not self._enable_autocomplete or self._completion_blocked:
            return
        start, end, word = self._current_word_bounds()
        cursor_iter = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        line_end = cursor_iter.copy()
        line_end.forward_to_line_end()
        text_after = self._buffer.get_text(cursor_iter, line_end, True)
        if text_after and not text_after.isspace():
            self._hide_completions()
            self._clear_completion_list()
            self._hide_ghost_text()
            return
        dot_obj = self._dot_object_before(start)
        if len(word) < 1 and dot_obj is None:
            self._hide_completions()
            self._clear_completion_list()
            self._hide_ghost_text()
            return
        if dot_obj is not None:
            candidates = self._gather_attr_completions(dot_obj, word)
        else:
            candidates = self._gather_name_completions(word, exclude=word)
        if not candidates:
            self._hide_completions()
            self._clear_completion_list()
            self._hide_ghost_text()
            return
        if len(candidates) == 1 and candidates[0].text == word:
            self._hide_completions()
            self._clear_completion_list()
            self._hide_ghost_text()
            return

        self._completion_words = [item.text for item in candidates]
        self._completion_prefix = word

        self._clear_completion_list()

        if len(candidates) == 1:
            self._hide_completions()
            self._update_ghost_text(candidates, word)
            return

        lst = self._completion_list
        for item in candidates:
            row = self._build_completion_row(item)
            lst.append(row)
        first = lst.get_first_child()
        if first is not None:
            lst.select_row(first)

        self._completion_active = True
        self._update_ghost_text(candidates, word)

    def _hide_completions(self) -> None:
        if self._completion_popover is not None:
            self._completion_popover.popdown()
        self._completion_active = False

    def _clear_completion_list(self) -> None:
        lst = self._completion_list
        while True:
            row = lst.get_first_child()
            if row is None:
                break
            lst.remove(row)

    def _completion_visible(self) -> bool:
        return self._completion_active

    def _on_completion_activated(self, lst: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        self._apply_completion(row)

    def _apply_completion(self, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        item: CompletionItem | None = getattr(row, "completion_item", None)
        if item is None:
            return
        start, end, word = self._current_word_bounds()
        self._completion_blocked = True
        self._buffer.delete(start, end)
        self._buffer.insert(start, item.insert, -1)
        if item.cursor_back > 0:
            cursor = self._buffer.get_insert()
            iter_ = self._buffer.get_iter_at_mark(cursor)
            for _ in range(item.cursor_back):
                iter_.backward_char()
            self._buffer.place_cursor(iter_)
        self._completion_blocked = False
        self._hide_completions()
        self._hide_ghost_text()

    def _move_completion(self, direction: int) -> None:
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
            self._scroll_completion_to_row(nxt)
            item = getattr(nxt, "completion_item", None)
            if item is not None and self._completion_prefix:
                self._update_ghost_text([item], self._completion_prefix)

    def _scroll_completion_to_row(self, row: Gtk.ListBoxRow) -> None:
        scrolled = self._completion_popover.get_child()
        if scrolled is None or not isinstance(scrolled, Gtk.ScrolledWindow):
            return
        vadj = scrolled.get_vadjustment()
        row_h = row.get_allocated_height()
        if row_h <= 0:
            row_h = 24
        row_y = row.get_index() * row_h
        value = vadj.get_value()
        page = vadj.get_page_size()
        if row_y < value:
            vadj.set_value(row_y)
        elif row_y + row_h > value + page:
            vadj.set_value(row_y + row_h - page)

    def _on_overlay_get_child_position(
        self, overlay: Gtk.Overlay, child: Gtk.Widget, rect: Gdk.Rectangle
    ) -> bool:
        if child is not self._ghost_label or not self._ghost_label.get_visible():
            return False
        cursor_mark = self._buffer.get_insert()
        cursor_iter = self._buffer.get_iter_at_mark(cursor_mark)
        location = self._view.get_iter_location(cursor_iter)
        try:
            x, y = self._view.buffer_to_window_coords(
                Gtk.TextWindowType.WIDGET,  # type: ignore[attr-defined]
                location.x,
                location.y,
            )
        except (ValueError, TypeError):
            x, y = location.x, location.y
        result = self._view.translate_coordinates(overlay, float(x), float(y))
        if result is not None:
            rect.x = int(result[0])
            rect.y = int(result[1])
        else:
            rect.x = x
            rect.y = y
        _min_w, nat_w, _min_b, _nat_b = self._ghost_label.measure(
            Gtk.Orientation.HORIZONTAL, -1
        )
        rect.width = max(int(nat_w), 1)
        rect.height = location.height if location.height > 0 else 20
        return True

    def _update_ghost_text(self, candidates: list[CompletionItem], word: str) -> None:
        if not candidates or not word:
            self._hide_ghost_text()
            return
        top = candidates[0]
        insert = top.insert
        if not insert.lower().startswith(word.lower()):
            self._hide_ghost_text()
            return
        suffix = insert[len(word):]
        if not suffix:
            self._hide_ghost_text()
            return
        self._ghost_item = top
        self._ghost_label.set_text(suffix)
        self._ghost_label.set_visible(True)
        self._ghost_label.queue_resize()

    def _hide_ghost_text(self) -> None:
        if self._ghost_label is not None:
            self._ghost_label.set_visible(False)
        self._ghost_item = None

    def _accept_ghost_text(self) -> None:
        item = self._ghost_item
        if item is None:
            return
        start, end, _word = self._current_word_bounds()
        self._completion_blocked = True
        self._buffer.delete(start, end)
        self._buffer.insert(start, item.insert, -1)
        if item.cursor_back > 0:
            cursor = self._buffer.get_insert()
            iter_ = self._buffer.get_iter_at_mark(cursor)
            for _ in range(item.cursor_back):
                iter_.backward_char()
            self._buffer.place_cursor(iter_)
        self._completion_blocked = False
        self._hide_ghost_text()
        self._hide_completions()

    def _schedule_completion(self) -> None:
        if self._completion_debounce_id > 0:
            GLib.source_remove(self._completion_debounce_id)
        self._completion_debounce_id = GLib.timeout_add(
            50, self._debounced_show_completions
        )

    def _debounced_show_completions(self) -> bool:
        self._completion_debounce_id = 0
        self._show_completions()
        return False

    def _on_destroy(self, widget: Gtk.Widget) -> None:
        if self._completion_debounce_id > 0:
            GLib.source_remove(self._completion_debounce_id)
            self._completion_debounce_id = 0

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
        self._completion_accept_key = str(getattr(ec, "completion_accept_key", "tab"))

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
            highlight = bool(getattr(ec, "enable_syntax_highlighting", True))
            if highlight:
                lang = _get_python_language()
                if lang:
                    self._buffer.set_language(lang)
            else:
                self._buffer.set_language(None)

        self._font_family = str(getattr(ec, "font_family", "Monospace"))
        self._font_size = int(getattr(ec, "font_size", 12))
        self._apply_font_css()

    def _apply_font_css(self) -> None:
        font_family = self._font_family
        if " " in font_family or "," in font_family:
            font_family = f'"{font_family}"'
        css = (
            "textview.bluep-editor, "
            "textview.bluep-editor text, "
            "label.bluep-ghost-text {\n"
            f"  font-family: {font_family}, monospace;\n"
            f"  font-size: {self._font_size}pt;\n"
            "}\n"
        )
        try:
            if self._css_provider is not None:
                self._view.get_style_context().remove_provider(self._css_provider)
                if self._ghost_label is not None:
                    self._ghost_label.get_style_context().remove_provider(
                        self._css_provider
                    )
            self._css_provider = Gtk.CssProvider.new()
            self._css_provider.load_from_data(css.encode("utf-8"))
            self._view.get_style_context().add_provider(
                self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
            if self._ghost_label is not None:
                self._ghost_label.get_style_context().add_provider(
                    self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
                )
        except Exception:
            pass
        try:
            desc = Pango.FontDescription.new()
            desc.set_family(self._font_family)
            desc.set_size(self._font_size * 1024)
            self._font_desc = desc
        except Exception:
            pass

    def set_font_size(self, size: int) -> None:
        size = max(6, min(48, size))
        if size == self._font_size:
            return
        self._font_size = size
        self._apply_font_css()

    def zoom_in(self) -> None:
        self.set_font_size(self._font_size + 1)

    def zoom_out(self) -> None:
        self.set_font_size(self._font_size - 1)

    def zoom_reset(self) -> None:
        self.set_font_size(12)

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
        if not self._completion_blocked:
            self._schedule_completion()

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

        # Ctrl+Plus / Ctrl+Minus = zoom font size
        if ctrl and keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.zoom_in()
            return True
        if ctrl and keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.zoom_out()
            return True
        if ctrl and keyval == Gdk.KEY_0:
            self.zoom_reset()
            return True

        # Ctrl+space = force completion
        if ctrl and keyval in (ord(" "), Gdk.KEY_space):
            self._show_completions()
            return True

        # ── Completion navigation (when popover is visible) ──
        if self._completion_visible():
            if keyval == Gdk.KEY_Escape:
                self._hide_completions()
                self._hide_ghost_text()
                return True
            accept_keys = {Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_Tab}
            if self._completion_accept_key == "enter":
                accept_keys = {Gdk.KEY_Return, Gdk.KEY_KP_Enter}
            elif self._completion_accept_key == "tab":
                accept_keys = {Gdk.KEY_Tab}
            if keyval in accept_keys:
                lst = self._completion_list
                row = lst.get_selected_row() if lst is not None else None
                self._apply_completion(row)
                return True
            if keyval == Gdk.KEY_Down:
                self._move_completion(+1)
                return True
            if keyval == Gdk.KEY_Up:
                self._move_completion(-1)
                return True
            lst = self._completion_list
            if keyval == Gdk.KEY_Home and lst is not None:
                first = lst.get_first_child()
                if first is not None:
                    lst.select_row(first)
                    self._scroll_completion_to_row(first)
                return True
            if keyval == Gdk.KEY_End and lst is not None:
                last = lst.get_last_child()
                if last is not None:
                    lst.select_row(last)
                    self._scroll_completion_to_row(last)
                return True
            if keyval == Gdk.KEY_Page_Down:
                for _ in range(5):
                    self._move_completion(+1)
                return True
            if keyval == Gdk.KEY_Page_Up:
                for _ in range(5):
                    self._move_completion(-1)
                return True

        # ── Tab key: accept ghost text or insert configured spaces ──
        if keyval == Gdk.KEY_Tab:
            if self._ghost_label is not None and self._ghost_label.get_visible():
                self._accept_ghost_text()
                return True
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
            self._hide_ghost_text()

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
