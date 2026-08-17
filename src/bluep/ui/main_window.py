"""Main window for BlueP.

The central window that integrates all BlueP components:
- Class diagram (visual class layout)
- Code editor (source editing)
- Object bench (live objects)
- Terminal (program output)
- Code pad (expression evaluation)
- Debugger panel (stepping, variables)
- AI panel (AI assistant)

Mirrors BlueJ's main window layout: class diagram on top, object bench
below, and a tabbed bottom panel for terminal/code pad/debugger/AI.
"""

from __future__ import annotations

import inspect
import io
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Gio, Pango

from bluep.config import Config, AIConfig
from bluep.core.class_info import ClassInfo, ClassKind, ClassAnalyzer, create_default_template
from bluep.core.executor import CodeExecutor, BenchObject, ExecutionResult
from bluep.core.project import Project
from bluep.core.debugger import BluePDebugger, DebugState
from bluep.core.ai_agent import AIAgent

from bluep.ui.class_diagram import ClassDiagram
from bluep.ui.code_editor import CodeEditor, HAS_GTKSOURCE
from bluep.ui.object_bench import ObjectBench
from bluep.ui.code_pad import CodePad
from bluep.ui.terminal import Terminal
from bluep.ui.debugger_panel import DebuggerPanel
from bluep.ui.ai_panel import AIPanel
from bluep.ui.dialogs import (
    ObjectInspectorDialog,
    MethodCallDialog,
    NewClassDialog,
    ConstructorDialog,
    PreferencesDialog,
    RenameClassDialog,
)
from bluep.ui.class_editor import ClassEditorDialog


class MainWindow(Gtk.ApplicationWindow):
    """The main BlueP IDE window.

    Integrates the class diagram, code editor, object bench, terminal,
    code pad, debugger, and AI panel into a single cohesive interface
    that mirrors BlueJ's workflow.
    """

    def __init__(self, app: Gtk.Application, config: Config) -> None:
        super().__init__(application=app)
        self.set_title("BlueP")
        self.set_default_size(1200, 800)
        self.add_css_class("bluep-main")

        self.config = config
        self.project: Project | None = None
        self.executor = CodeExecutor()
        self.debugger = BluePDebugger()
        self.ai_agent: AIAgent | None = None
        self._open_editors: dict[str, CodeEditor] = {}
        self._current_class: str | None = None

        # Set up output capture
        self._stdout_capture = io.StringIO()
        self._old_stdout: Any = None

        # Build UI
        self._build_header_bar()
        self._build_main_layout()
        self._build_status_bar()
        self._setup_actions()
        self._setup_shortcuts()

        # Set up debugger callbacks
        self.debugger.set_pause_callback(self._on_debugger_pause)

        if not HAS_GTKSOURCE:
            self.terminal.write_error(
                "WARNING: GtkSourceView 5 is not available. "
                "The code editor is running in fallback mode (plain Gtk.TextView) - "
                "syntax highlighting, line numbers, and auto-indent are limited. "
                "Install gtksourceview5 for full editor features."
            )

        # AI agent is created when a project is opened (see open_project)

    # --- UI Construction ---

    def _build_header_bar(self) -> None:
        """Build the header bar with main toolbar buttons."""
        header = Gtk.HeaderBar.new()
        header.add_css_class("bluep-header")

        # Left side: New Class, Compile
        btn_new_class = Gtk.Button.new_from_icon_name("document-new")
        btn_new_class.set_tooltip_text("New Class (Ctrl+N)")
        btn_new_class.connect("clicked", lambda b: self._action_new_class())
        header.pack_start(btn_new_class)

        btn_compile = Gtk.Button.new_from_icon_name("system-run")
        btn_compile.set_tooltip_text("Compile all (Ctrl+Shift+C)")
        btn_compile.connect("clicked", lambda b: self._action_compile_all())
        header.pack_start(btn_compile)

        # Project name label
        self._project_label = Gtk.Label.new("No project open")
        self._project_label.add_css_class("bluep-class-name")
        header.set_title_widget(self._project_label)

        # Right side: menu button
        menu_btn = Gtk.MenuButton.new()
        menu = Gio.Menu.new()
        menu.append("New Project", "win.new-project")
        menu.append("Open Project...", "win.open-project")
        menu.append("Save Project", "win.save-project")
        menu.append_section(None, Gio.Menu.new())
        menu.append("New Class", "win.new-class")
        menu.append("Compile All", "win.compile-all")
        menu.append("Compile Current", "win.compile-current")
        menu.append_section(None, Gio.Menu.new())
        menu.append("Show Terminal", "win.show-terminal")
        menu.append("Show Code Pad", "win.show-code-pad")
        menu.append("Show Debugger", "win.show-debugger")
        menu.append("Show AI Panel", "win.show-ai")
        menu.append("Toggle Bottom Panel", "win.toggle-bottom-panel")
        menu.append_section(None, Gio.Menu.new())
        menu.append("Hide Code Editor", "win.hide-editor")
        menu.append("Hide Terminal", "win.hide-terminal")
        menu.append("Hide Code Pad", "win.hide-code-pad")
        menu.append("Hide Debugger", "win.hide-debugger")
        menu.append("Hide AI Panel", "win.hide-ai")
        menu.append_section(None, Gio.Menu.new())
        menu.append("Preferences", "win.preferences")
        menu.append("About", "win.about")

        menu_btn.set_menu_model(menu)
        menu_btn.set_icon_name("open-menu")
        menu_btn.set_tooltip_text("Menu")
        header.pack_end(menu_btn)

        self.set_titlebar(header)

    def _build_main_layout(self) -> None:
        """Build the main window layout."""
        main_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        self.set_child(main_box)

        content_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        content_box.set_hexpand(True)
        self._content_box = content_box
        main_box.append(content_box)

        # --- Right edge: editor restore button (hidden by default) ---
        self._editor_restore_btn = Gtk.Button.new_from_icon_name("go-previous")
        self._editor_restore_btn.set_tooltip_text("Show Code Editor")
        self._editor_restore_btn.add_css_class("bluep-editor-restore")
        self._editor_restore_btn.connect("clicked", lambda b: self._show_editor())
        self._editor_restore_btn.set_visible(False)
        main_box.append(self._editor_restore_btn)

        # --- Top section: class diagram + editor (side by side) ---
        self._top_paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        self._top_paned.set_vexpand(True)

        # Class diagram (left)
        diagram_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        diagram_label = Gtk.Label.new("Class Diagram")
        diagram_label.add_css_class("bluep-status-bar")
        diagram_label.set_halign(Gtk.Align.START)
        diagram_label.set_margin_start(8)
        diagram_box.append(diagram_label)

        # Placeholder diagram (will be replaced when project loads)
        self._diagram_container = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self._diagram_container.set_vexpand(True)
        placeholder = Gtk.Label.new("Open or create a project to see the class diagram.")
        placeholder.set_vexpand(True)
        placeholder.set_valign(Gtk.Align.CENTER)
        placeholder.add_css_class("bluep-status-bar")
        self._diagram_container.append(placeholder)
        diagram_box.append(self._diagram_container)

        self._top_paned.set_start_child(diagram_box)
        self._top_paned.set_shrink_start_child(False)
        self._top_paned.set_position(600)

        # Code editor (right)
        self._editor_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        editor_label = Gtk.Label.new("Code Editor")
        editor_label.add_css_class("bluep-status-bar")
        editor_label.set_halign(Gtk.Align.START)
        editor_label.set_margin_start(8)
        self._editor_box.append(editor_label)

        self._editor_notebook = Gtk.Notebook.new()
        self._editor_notebook.add_css_class("bluep-notebook")
        self._editor_notebook.set_vexpand(True)
        self._editor_notebook.set_scrollable(True)

        self._welcome_page = self._build_welcome_page()
        self._editor_notebook.append_page(self._welcome_page, self._build_welcome_tab())

        self._editor_box.append(self._editor_notebook)

        self._top_paned.set_end_child(self._editor_box)
        self._top_paned.set_shrink_end_child(False)

        # --- Upper section: diagram+editor + object bench ---
        upper_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        upper_box.append(self._top_paned)

        bench_separator = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
        upper_box.append(bench_separator)

        bench_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        bench_label = Gtk.Label.new("Object Bench")
        bench_label.add_css_class("bluep-status-bar")
        bench_label.set_halign(Gtk.Align.START)
        bench_label.set_margin_start(8)
        bench_box.append(bench_label)

        self.object_bench = ObjectBench()
        self.object_bench.connect("object-right-clicked", self._on_object_right_clicked)
        self.object_bench.connect("object-double-clicked", self._on_object_double_clicked)
        self.object_bench.connect("bench-right-clicked", self._on_bench_right_clicked)
        bench_box.append(self.object_bench)

        upper_box.append(bench_box)

        # --- Bottom notebook: Terminal, Code Pad, Debugger, AI ---
        self._bottom_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self._bottom_box.set_size_request(-1, 200)

        self._bottom_notebook = Gtk.Notebook.new()
        self._bottom_notebook.add_css_class("bluep-notebook")
        self._bottom_notebook.set_vexpand(False)

        self._bottom_panels: dict[str, Gtk.Widget] = {}
        self._restore_buttons: dict[str, Gtk.Button] = {}

        # Terminal
        self.terminal = Terminal()
        self.terminal.connect("output-written", self._on_terminal_output)
        self._bottom_panels["Terminal"] = self.terminal
        self._bottom_notebook.append_page(
            self.terminal, self._build_bottom_tab("Terminal"))

        # Code Pad
        self.code_pad = CodePad(self.executor)
        self.code_pad.connect("expression-evaluated", self._on_code_pad_evaluated)
        self.code_pad.connect("object-created", self._on_code_pad_object_created)
        self._bottom_panels["Code Pad"] = self.code_pad
        self._bottom_notebook.append_page(
            self.code_pad, self._build_bottom_tab("Code Pad"))

        # Debugger
        self.debugger_panel = DebuggerPanel(self.debugger)
        self.debugger_panel.connect("step", lambda p: self._debugger_step("next"))
        self.debugger_panel.connect("step-into", lambda p: self._debugger_step("step"))
        self.debugger_panel.connect("step-out", lambda p: self._debugger_step("return"))
        self.debugger_panel.connect("continue-exec", lambda p: self._debugger_step("continue"))
        self.debugger_panel.connect("terminate", lambda p: self._debugger_terminate())
        self._bottom_panels["Debugger"] = self.debugger_panel
        self._bottom_notebook.append_page(
            self.debugger_panel, self._build_bottom_tab("Debugger"))

        # AI Panel
        self.ai_panel = AIPanel()
        self._bottom_panels["AI"] = self.ai_panel
        self._bottom_notebook.append_page(
            self.ai_panel, self._build_bottom_tab("AI"))

        self._bottom_box.append(self._bottom_notebook)

        self._panel_restore_bar = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        self._panel_restore_bar.add_css_class("bluep-panel-restore-bar")
        self._panel_restore_bar.set_visible(False)
        self._bottom_box.append(self._panel_restore_bar)

        # --- Vertical paned: upper section (resizable) / bottom panel (resizable) ---
        self._main_paned = Gtk.Paned.new(Gtk.Orientation.VERTICAL)
        self._main_paned.set_vexpand(True)
        self._main_paned.set_start_child(upper_box)
        self._main_paned.set_shrink_start_child(False)
        self._main_paned.set_end_child(self._bottom_box)
        self._main_paned.set_shrink_end_child(False)
        self._main_paned.set_position(400)

        content_box.append(self._main_paned)

    def _build_welcome_page(self) -> Gtk.Widget:
        """Build the Welcome tab with useful information."""
        scrolled = Gtk.ScrolledWindow.new()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)

        outer = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        outer.set_margin_top(32)
        outer.set_margin_bottom(32)
        outer.set_margin_start(48)
        outer.set_margin_end(48)

        title = Gtk.Label.new("BlueP")
        title.add_css_class("bluep-welcome-title")
        title.set_halign(Gtk.Align.START)
        outer.append(title)

        subtitle = Gtk.Label.new("A BlueJ-style IDE for Python")
        subtitle.add_css_class("bluep-welcome-subtitle")
        subtitle.set_halign(Gtk.Align.START)
        subtitle.set_margin_bottom(24)
        outer.append(subtitle)

        editor_desc = Gtk.Label.new(
            "The BlueP code editor is a syntax-highlighted Python editor built on "
            "GtkSourceView 5 (with a plain Gtk.TextView fallback when GtkSourceView "
            "is unavailable)."
        )
        editor_desc.set_halign(Gtk.Align.START)
        editor_desc.set_wrap(True)
        editor_desc.set_margin_bottom(20)
        outer.append(editor_desc)

        features_header = Gtk.Label.new("Features")
        features_header.add_css_class("bluep-welcome-section")
        features_header.set_halign(Gtk.Align.START)
        features_header.set_margin_bottom(8)
        outer.append(features_header)

        for text in [
            "Visual class diagram - create, move, and inspect classes",
            "Code editor with Python syntax highlighting and autocomplete",
            "Object bench - instantiate classes and call methods interactively",
            "Integrated terminal for program output",
            "Code Pad for quick expression evaluation",
            "Step debugger with breakpoints and variable inspection",
            "AI assistant panel (requires API key)",
        ]:
            row = Gtk.Label.new(f"  • {text}")
            row.set_halign(Gtk.Align.START)
            row.set_margin_bottom(4)
            outer.append(row)

        shortcuts_header = Gtk.Label.new("Keyboard Shortcuts")
        shortcuts_header.add_css_class("bluep-welcome-section")
        shortcuts_header.set_halign(Gtk.Align.START)
        shortcuts_header.set_margin_top(16)
        shortcuts_header.set_margin_bottom(8)
        outer.append(shortcuts_header)

        shortcuts = [
            ("Ctrl+N", "New class"),
            ("Ctrl+O", "Open project"),
            ("Ctrl+S", "Save project"),
            ("Ctrl+Shift+C", "Compile all"),
            ("Ctrl+T", "Show terminal"),
            ("Ctrl+E", "Show Code Pad"),
            ("Ctrl+D", "Show debugger"),
        ]
        for key, desc in shortcuts:
            row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 12)
            row.set_margin_bottom(4)
            key_label = Gtk.Label.new(key)
            key_label.add_css_class("bluep-welcome-key")
            key_label.set_xalign(0)
            key_label.set_size_request(120, -1)
            desc_label = Gtk.Label.new(desc)
            desc_label.set_halign(Gtk.Align.START)
            row.append(key_label)
            row.append(desc_label)
            outer.append(row)

        getting_started = Gtk.Label.new("Getting Started")
        getting_started.add_css_class("bluep-welcome-section")
        getting_started.set_halign(Gtk.Align.START)
        getting_started.set_margin_top(16)
        getting_started.set_margin_bottom(8)
        outer.append(getting_started)

        for text in [
            "1. Click the menu button (top-right) and choose New Project or Open Project",
            "2. Click New Class in the toolbar to create a Python class",
            "3. Double-click a class in the diagram to open its editor",
            "4. Right-click a class to instantiate it on the object bench",
            "5. Right-click an object on the bench to call its methods",
        ]:
            row = Gtk.Label.new(text)
            row.set_halign(Gtk.Align.START)
            row.set_margin_bottom(4)
            outer.append(row)

        if not HAS_GTKSOURCE:
            warning_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
            warning_box.add_css_class("bluep-welcome-warning")
            warning_box.set_margin_top(20)
            warning_icon = Gtk.Label.new("⚠")
            warning_text = Gtk.Label.new(
                "GtkSourceView 5 is not installed. The editor is running in "
                "fallback mode - syntax highlighting and line numbers are "
                "disabled. Install gtksourceview5 for full features."
            )
            warning_text.set_wrap(True)
            warning_text.set_hexpand(True)
            warning_box.append(warning_icon)
            warning_box.append(warning_text)
            outer.append(warning_box)

        scrolled.set_child(outer)
        return scrolled

    def _build_welcome_tab(self) -> Gtk.Widget:
        tab_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        tab_label = Gtk.Label.new("Welcome")
        tab_box.append(tab_label)
        btn_close = Gtk.Button.new_from_icon_name("window-close")
        btn_close.set_has_frame(False)
        btn_close.set_size_request(20, 20)
        btn_close.connect("clicked", lambda b: self._dismiss_welcome())
        tab_box.append(btn_close)
        return tab_box

    def _build_bottom_tab(self, panel_name: str) -> Gtk.Widget:
        tab_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        tab_box._panel_name = panel_name
        tab_label = Gtk.Label.new(panel_name)
        tab_box.append(tab_label)
        btn_close = Gtk.Button.new_from_icon_name("window-close")
        btn_close.set_has_frame(False)
        btn_close.set_size_request(20, 20)
        btn_close.connect("clicked", lambda b: self._hide_bottom_panel(panel_name))
        tab_box.append(btn_close)
        return tab_box

    def _dismiss_welcome(self) -> None:
        page_num = self._editor_notebook.page_num(self._welcome_page)
        if page_num >= 0:
            self._editor_notebook.remove_page(page_num)
        self._check_editor_auto_hide()

    def _hide_editor(self) -> None:
        self._editor_box.set_visible(False)
        self._editor_restore_btn.set_visible(True)

    def _show_editor(self) -> None:
        self._editor_box.set_visible(True)
        self._editor_restore_btn.set_visible(False)
        if self._editor_notebook.get_n_pages() == 0:
            page_num = self._editor_notebook.page_num(self._welcome_page)
            if page_num < 0:
                self._editor_notebook.append_page(
                    self._welcome_page, self._build_welcome_tab())

    def _check_editor_auto_hide(self) -> None:
        if self._editor_notebook.get_n_pages() == 0:
            self._editor_box.set_visible(False)
            self._editor_restore_btn.set_visible(True)

    def _hide_bottom_panel(self, panel_name: str) -> None:
        if panel_name not in self._bottom_panels:
            return
        widget = self._bottom_panels[panel_name]
        page_num = self._bottom_notebook.page_num(widget)
        if page_num < 0:
            return
        self._bottom_notebook.remove_page(page_num)
        btn = Gtk.Button.new_with_label(panel_name)
        btn.add_css_class("bluep-panel-restore-btn")
        btn.set_tooltip_text(f"Show {panel_name} panel")
        btn.connect("clicked", lambda b: self._show_bottom_panel_named(panel_name))
        self._restore_buttons[panel_name] = btn
        self._panel_restore_bar.append(btn)
        self._panel_restore_bar.set_visible(True)
        if self._bottom_notebook.get_n_pages() == 0:
            self._bottom_box.set_visible(False)

    def _show_bottom_panel_named(self, panel_name: str) -> None:
        if panel_name not in self._bottom_panels:
            return
        if panel_name in self._restore_buttons:
            btn = self._restore_buttons.pop(panel_name)
            self._panel_restore_bar.remove(btn)
        widget = self._bottom_panels[panel_name]
        page_num = self._bottom_notebook.page_num(widget)
        if page_num < 0:
            self._bottom_notebook.append_page(
                widget, self._build_bottom_tab(panel_name))
        if not self._restore_buttons:
            self._panel_restore_bar.set_visible(False)
        self._bottom_box.set_visible(True)
        page_num = self._bottom_notebook.page_num(widget)
        if page_num >= 0:
            self._bottom_notebook.set_current_page(page_num)

    def _build_status_bar(self) -> None:
        """Build the bottom status bar."""
        status_bar = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        status_bar.add_css_class("bluep-status-bar")

        self._status_label = Gtk.Label.new("Ready")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.set_margin_start(8)
        self._status_label.set_margin_top(2)
        self._status_label.set_margin_bottom(2)
        status_bar.append(self._status_label)

        self._compile_status = Gtk.Label.new("")
        self._compile_status.set_halign(Gtk.Align.END)
        self._compile_status.set_hexpand(True)
        self._compile_status.set_margin_end(8)
        status_bar.append(self._compile_status)

        self._content_box.append(status_bar)

    # --- Actions ---

    def _setup_actions(self) -> None:
        """Set up window actions for the menu."""
        actions = {
            "new-project": (self._action_new_project, None),
            "open-project": (self._action_open_project, None),
            "save-project": (self._action_save_project, None),
            "new-class": (self._action_new_class, None),
            "compile-all": (self._action_compile_all, None),
            "compile-current": (self._action_compile_current, None),
            "show-terminal": (self._action_show_terminal, None),
            "show-code-pad": (self._action_show_code_pad, None),
            "show-debugger": (self._action_show_debugger, None),
            "show-ai": (self._action_show_ai, None),
            "toggle-bottom-panel": (self._action_toggle_bottom_panel, None),
            "hide-editor": (self._hide_editor, None),
            "hide-terminal": (lambda: self._hide_bottom_panel("Terminal"), None),
            "hide-code-pad": (lambda: self._hide_bottom_panel("Code Pad"), None),
            "hide-debugger": (lambda: self._hide_bottom_panel("Debugger"), None),
            "hide-ai": (lambda: self._hide_bottom_panel("AI"), None),
            "reset-view": (self._action_reset_view, None),
            "preferences": (self._action_preferences, None),
            "about": (self._action_about, None),
        }

        for name, (callback, param_type) in actions.items():
            action = Gio.SimpleAction.new(name, param_type)
            action.connect("activate", lambda a, p, cb=callback: cb())
            self.add_action(action)

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts."""
        shortcuts = {
            "<Ctrl>n": "win.new-class",
            "<Ctrl><Shift>c": "win.compile-all",
            "<Ctrl>s": "win.save-project",
            "<Ctrl>t": "win.show-terminal",
            "<Ctrl>e": "win.show-code-pad",
            "<Ctrl>d": "win.show-debugger",
            "<Ctrl>i": "win.show-ai",
            "<Ctrl>o": "win.open-project",
        }

        self._shortcut_controller = Gtk.ShortcutController.new()
        self._shortcut_controller.set_scope(Gtk.ShortcutScope.MANAGED)

        for shortcut, action in shortcuts.items():
            trigger = Gtk.ShortcutTrigger.parse_string(shortcut)
            action_obj = Gtk.CallbackAction.new(lambda _w, _a, act=action: self.activate_action(act.split(".")[1]) or True)
            shortcut_item = Gtk.Shortcut.new(trigger, action_obj)
            self._shortcut_controller.add_shortcut(shortcut_item)

        self.add_controller(self._shortcut_controller)

    # --- Action Handlers ---

    def _action_new_project(self) -> None:
        """Create a new project."""
        dialog = Gtk.FileChooserDialog(
            title="Select project directory",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Create", Gtk.ResponseType.ACCEPT)
        dialog.set_create_folders(True)
        dialog.connect("response", self._on_new_project_response)
        dialog.show()

    def _on_new_project_response(self, dialog: Gtk.FileChooserDialog, response: int) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            folder = dialog.get_file().get_path()
            if folder:
                self.open_project(Path(folder), create=True)
        dialog.destroy()

    def _action_open_project(self) -> None:
        """Open an existing project."""
        dialog = Gtk.FileChooserDialog(
            title="Open project directory",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Open", Gtk.ResponseType.ACCEPT)
        dialog.set_create_folders(True)
        dialog.connect("response", self._on_open_project_response)
        dialog.show()

    def _on_open_project_response(self, dialog: Gtk.FileChooserDialog, response: int) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            folder = dialog.get_file().get_path()
            if folder:
                self.open_project(Path(folder))
        dialog.destroy()

    def _action_save_project(self) -> None:
        """Save the current project and clear the save indicator."""
        if not self.project:
            self._set_status("No project to save")
            return
        for editor in self._open_editors.values():
            if editor.is_modified:
                editor.save()
        self.project.save()
        for class_name in list(self._open_editors.keys()):
            self._update_editor_tab_label(class_name, False)
        self._set_status(f"Project saved: {self.project.name}")

    def _action_new_class(self) -> None:
        """Create a new class using the graphical class editor."""
        if not self.project:
            self._set_status("Open or create a project first")
            return

        def on_save(name: str, code: str) -> None:
            self._create_class_from_editor(name, code)

        dialog = ClassEditorDialog(parent=self, class_info=None, on_save=on_save)
        dialog.show()

    def _create_class_from_editor(self, name: str, code: str) -> None:
        """Create a new class from the graphical editor's source code."""
        if self.project is None:
            return
        try:
            self.project.add_class_file(name, source=code)
            self._refresh_diagram()
            self._set_status(f"Created class: {name}")
            self._open_class_editor(name)
        except Exception as e:
            self._set_status(f"Error creating class: {e}")
            self._show_error("Cannot Create Class", str(e))

    def _edit_class_graphical(self, class_name: str) -> None:
        """Open the graphical class editor for an existing class."""
        if self.project is None:
            return
        cls_info = self.project.model.get_class(class_name)
        if cls_info is None:
            return

        def on_save(name: str, code: str) -> None:
            if self.project is None or cls_info.source_file is None:
                return
            if name != class_name:
                self.project.rename_class(class_name, name)
            cls_info.source_file.write_text(code)
            self._refresh_diagram()
            self._set_status(f"Saved class: {name}")

        dialog = ClassEditorDialog(parent=self, class_info=cls_info, on_save=on_save)
        dialog.show()

    def _create_class(self, name: str, kind: ClassKind) -> None:
        """Create a new class file in the project."""
        if self.project is None:
            return
        try:
            self.project.add_class_file(name, kind)
            self._refresh_diagram()
            self._set_status(f"Created class: {name}")
            # Open editor for the new class
            self._open_class_editor(name)
        except Exception as e:
            self._set_status(f"Error creating class: {e}")
            self._show_error("Cannot Create Class", str(e))

    def _action_compile_all(self) -> None:
        """Compile all classes in the project."""
        if not self.project:
            self._set_status("No project to compile")
            return

        results = {}
        all_success = True

        for py_file in self.project.get_source_files():
            # First check syntax
            compile_result = self.executor.compile_file(py_file)
            if not compile_result.success:
                results[py_file.stem] = compile_result.error
                all_success = False
            else:
                # Load into namespace
                exec_result = self.executor.load_module(py_file)
                if not exec_result.success:
                    results[py_file.stem] = exec_result.error
                    all_success = False
                else:
                    results[py_file.stem] = "OK"

        # Show results
        if all_success:
            self._compile_status.set_text("All classes compiled")
            self._set_status("Compile successful")
            self.terminal.write_info(f"Compiled {len(results)} classes - all OK")
        else:
            errors = "\n".join(f"  {name}: {err}" for name, err in results.items() if err != "OK")
            self._compile_status.set_text("Compilation errors")
            failed = sum(1 for v in results.values() if v != "OK")
            self._set_status(f"Compile errors in {failed} class(es)")
            self.terminal.write_error(f"Compilation errors:\n{errors}")
            self._show_error("Compilation Failed", f"{failed} class(es) failed to compile:\n\n{errors}")

        # Clear bench on recompile (like BlueJ)
        self.object_bench.clear()
        self.executor.clear_bench()

        # Refresh diagram
        self._refresh_diagram()

    def _action_compile_current(self) -> None:
        """Compile only the currently selected class."""
        if not self.project or not self._current_class:
            self._set_status("No class selected to compile")
            return

        cls_info = self.project.model.get_class(self._current_class)
        if cls_info is None or cls_info.source_file is None:
            return

        # Save editor if modified
        if self._current_class in self._open_editors:
            editor = self._open_editors[self._current_class]
            if editor.is_modified:
                editor.save()

        # Re-analyze
        self.project._analyze_and_add(cls_info.source_file)

        # Compile
        result = self.executor.load_module(cls_info.source_file)
        if result.success:
            self._compile_status.set_text(f"{self._current_class} compiled")
            self._set_status(f"Compiled: {self._current_class}")
            self.terminal.write_info(f"Compiled {self._current_class} - OK")
        else:
            self._compile_status.set_text(f"{self._current_class} error")
            self._set_status(f"Compile error: {result.error}")
            self.terminal.write_error(f"Error compiling {self._current_class}: {result.error}")
            self._show_error(f"Cannot Compile {self._current_class}", result.error)

        self._refresh_diagram()

    def _action_show_terminal(self) -> None:
        """Switch to the Terminal tab and focus it."""
        self._show_bottom_panel_named("Terminal")
        GLib.idle_add(lambda: self.terminal._textview.grab_focus() and False)

    def _action_show_code_pad(self) -> None:
        """Switch to the Code Pad tab and focus the input."""
        self._show_bottom_panel_named("Code Pad")
        GLib.idle_add(lambda: self.code_pad._input.grab_focus() and False)

    def _action_show_debugger(self) -> None:
        """Switch to the Debugger tab and focus the step button."""
        self._show_bottom_panel_named("Debugger")
        GLib.idle_add(lambda: self.debugger_panel._btn_step.grab_focus() and False)

    def _action_show_ai(self) -> None:
        """Switch to the AI Panel tab and focus the input."""
        self._show_bottom_panel_named("AI")
        GLib.idle_add(lambda: self.ai_panel._input.grab_focus() and False)

    def _action_toggle_bottom_panel(self) -> None:
        """Hide or show the bottom panel (terminal area)."""
        self._bottom_box.set_visible(not self._bottom_box.get_visible())

    def _action_reset_view(self) -> None:
        """Reset the class diagram zoom and pan."""
        if hasattr(self, "diagram"):
            self.diagram.reset_view()
            self._set_status("View reset")

    def _show_bottom_panel(self) -> None:
        """Ensure the bottom panel is visible."""
        if not self._bottom_box.get_visible():
            self._bottom_box.set_visible(True)

    def _action_preferences(self) -> None:
        """Show the preferences dialog and apply settings on Apply."""
        dialog = PreferencesDialog(self.config, parent=self)
        dialog.connect("settings-applied", self._on_settings_applied)
        dialog.show()

    def _on_settings_applied(self, dialog: PreferencesDialog) -> None:
        """Apply persisted settings to live widgets."""
        self._apply_editor_settings()
        self._apply_supervised_gating()
        self._set_status("Settings saved.")

    def _apply_editor_settings(self) -> None:
        """Apply editor config to all currently-open editors."""
        cfg = self.config.editor
        for class_name, editor in self._open_editors.items():
            editor.apply_config(cfg)
            self._update_editor_tab_label(class_name, editor.is_modified)

    def _apply_supervised_gating(self) -> None:
        """Enable/disable features based on supervised mode."""
        if not hasattr(self, "_bottom_notebook"):
            return
        # AI panel page is the 4th tab (index 3)
        ai_page = self._bottom_notebook.get_nth_page(3)
        if ai_page is None:
            return
        locked = self.config.is_feature_locked("ai_panel")
        ai_page.set_sensitive(not locked)
        if locked and not self.config.ai.enabled:
            self._set_status("Supervised mode: AI panel disabled.")
        elif locked:
            self._set_status("Supervised mode active — some features are locked.")

    def _action_about(self) -> None:
        """Show about dialog."""
        about = Gtk.AboutDialog.new()
        about.set_program_name("BlueP")
        about.set_version("1.0.0")
        about.set_comments("A BlueJ-inspired IDE for Python")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_transient_for(self)
        about.set_modal(True)
        about.show()

    # --- Project Management ---

    def open_project(self, path: Path, create: bool = False) -> None:
        """Open or create a project at the given path."""
        if create:
            self.project = Project.create(path)
        else:
            self.project = Project.open(path)

        # Update executor
        self.executor = CodeExecutor(path)
        self.executor.namespace["__file__"] = str(path)
        self.code_pad.update_executor(self.executor)

        # Update UI
        self._project_label.set_text(self.project.name)
        self._set_status(f"Project opened: {self.project.name}")

        # Build class diagram
        self._build_diagram()

        ai_allowed = self.config.ai.enabled and not self.config.supervised
        if ai_allowed:
            self.ai_agent = AIAgent(self.config.ai, self.project, self.executor)
            self.ai_panel.set_agent(self.ai_agent)

        self._apply_supervised_gating()

        self._action_compile_all()

    def _build_diagram(self) -> None:
        """Build or rebuild the class diagram widget."""
        if self.project is None:
            return

        # Clear existing diagram
        child = self._diagram_container.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._diagram_container.remove(child)
            child = next_child

        # Create new diagram
        self.diagram = ClassDiagram(self.project.model)
        self.diagram.connect("class-double-clicked", self._on_class_double_clicked)
        self.diagram.connect("class-right-clicked", self._on_class_right_clicked)
        self.diagram.connect("class-moved", self._on_class_moved)
        self.diagram.connect("diagram-right-clicked", self._on_diagram_right_clicked)
        self.diagram.connect("class-selected", self._on_class_selected)
        self.diagram.connect("class-collapsed", self._on_class_collapsed)
        self._diagram_container.append(self.diagram)

    def _refresh_diagram(self) -> None:
        """Refresh the class diagram after changes."""
        if hasattr(self, "diagram") and self.project:
            # Re-analyze all classes
            for py_file in self.project.get_source_files():
                self.project._analyze_and_add_all(py_file)
            self.diagram.refresh()

    # --- Class Diagram Handlers ---

    def _on_class_selected(self, diagram: ClassDiagram, name: str) -> None:
        """Handle class selection in the diagram."""
        self._current_class = name
        self._set_status(f"Selected: {name}")

    def _on_class_double_clicked(self, diagram: ClassDiagram, name: str) -> None:
        """Handle double-click on a class - open editor."""
        self._open_class_editor(name)

    def _on_class_right_clicked(self, diagram: ClassDiagram, name: str, x: float, y: float) -> None:
        """Handle right-click on a class - show context menu."""
        menu = Gio.Menu.new()

        cls_info = self.project.model.get_class(name) if self.project else None

        # Compile
        menu.append(f"Compile {name}", "win.compile-current")

        # Instantiate (if not abstract/interface)
        if cls_info and cls_info.kind not in (ClassKind.ABSTRACT, ClassKind.INTERFACE):
            menu.append(f"Instantiate {name}...", f"win.instantiate-{name}")

        menu.append_section(None, Gio.Menu.new())
        menu.append("Open Editor", f"win.open-editor-{name}")
        menu.append("Edit (Graphical)...", f"win.graphical-edit-{name}")
        menu.append("Rename...", f"win.rename-{name}")
        menu.append_section(None, Gio.Menu.new())
        menu.append("Delete", f"win.delete-class-{name}")

        # Create actions for dynamic menu items
        self._create_class_context_actions(name)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_has_arrow(False)
        popover.set_position(Gtk.PositionType.BOTTOM)

        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)

        popover.set_parent(self)
        popover.popup()

    def _create_class_context_actions(self, class_name: str) -> None:
        """Create dynamic actions for class context menu."""
        # Remove old dynamic actions
        for action_name in list(self.list_actions()):
            if action_name.startswith(("instantiate-", "open-editor-", "graphical-edit-", "rename-", "delete-class-")):
                self.remove_action(action_name)

        # Instantiate
        act = Gio.SimpleAction.new(f"instantiate-{class_name}", None)
        act.connect("activate", lambda a, p: self._instantiate_class(class_name))
        self.add_action(act)

        # Open editor
        act = Gio.SimpleAction.new(f"open-editor-{class_name}", None)
        act.connect("activate", lambda a, p: self._open_class_editor(class_name))
        self.add_action(act)

        # Graphical edit
        act = Gio.SimpleAction.new(f"graphical-edit-{class_name}", None)
        act.connect("activate", lambda a, p: self._edit_class_graphical(class_name))
        self.add_action(act)

        # Rename
        act = Gio.SimpleAction.new(f"rename-{class_name}", None)
        act.connect("activate", lambda a, p: self._rename_class(class_name))
        self.add_action(act)

        # Delete
        act = Gio.SimpleAction.new(f"delete-class-{class_name}", None)
        act.connect("activate", lambda a, p: self._delete_class(class_name))
        self.add_action(act)

    def _on_class_moved(self, diagram: ClassDiagram, name: str, x: float, y: float) -> None:
        """Handle class box movement - save position."""
        if self.project:
            self.project.set_class_position(name, x, y)

    def _on_class_collapsed(self, diagram: ClassDiagram, name: str, collapsed: bool) -> None:
        """Handle class box collapse/expand - save state."""
        if self.project:
            self.project.set_class_position(name, diagram._boxes[name].x, diagram._boxes[name].y)

    def _on_diagram_right_clicked(self, diagram: ClassDiagram, x: float, y: float) -> None:
        """Handle right-click on empty diagram area."""
        menu = Gio.Menu.new()
        menu.append("New Class...", "win.new-class")
        menu.append("Compile All", "win.compile-all")
        menu.append_section(None, Gio.Menu.new())
        menu.append("Reset View", "win.reset-view")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.set_parent(self)
        popover.popup()

    # --- Class Operations ---

    def _open_class_editor(self, class_name: str) -> None:
        """Open a class in the code editor."""
        if not self.project:
            return

        cls_info = self.project.model.get_class(class_name)
        if cls_info is None or cls_info.source_file is None:
            return

        # If already open, switch to it
        if class_name in self._open_editors:
            editor = self._open_editors[class_name]
            page_num = self._editor_notebook.page_num(editor)
            if page_num >= 0:
                self._editor_notebook.set_current_page(page_num)
            return

        # Create new editor
        editor = CodeEditor(cls_info.source_file)
        editor.apply_config(self.config.editor)
        editor.connect("compile-requested", lambda e: self._action_compile_current())
        editor.connect("modified-changed", self._on_editor_modified)
        editor.connect("breakpoint-toggled", self._on_breakpoint_toggled)

        # Tab with close button
        tab_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        tab_label = Gtk.Label.new(class_name)
        tab_box.append(tab_label)
        btn_close = Gtk.Button.new_from_icon_name("window-close")
        btn_close.set_has_frame(False)
        btn_close.set_size_request(20, 20)
        btn_close.connect("clicked", lambda b, cn=class_name: self._close_editor(cn))
        tab_box.append(btn_close)

        self._editor_notebook.append_page(editor, tab_box)
        self._open_editors[class_name] = editor
        self._current_class = class_name

        if not self._editor_box.get_visible():
            self._show_editor()

        # Switch to the new tab
        page_num = self._editor_notebook.page_num(editor)
        self._editor_notebook.set_current_page(page_num)

    def _close_editor(self, class_name: str) -> None:
        """Close an editor tab, prompting to save if modified."""
        if class_name not in self._open_editors:
            return

        editor = self._open_editors[class_name]
        if not editor.is_modified:
            self._remove_editor_tab(class_name, editor)
            return

        def on_response(index: int) -> None:
            if index == 2:
                editor.save()
                self._remove_editor_tab(class_name, editor)
            elif index == 1:
                self._remove_editor_tab(class_name, editor)

        self._show_confirm(
            f"Save changes to {class_name}?",
            f"{class_name} has unsaved changes. Save before closing?",
            on_response,
            confirm_label="Save",
            cancel_label="Cancel",
            discard_label="Don't Save",
        )

    def _remove_editor_tab(self, class_name: str, editor: CodeEditor) -> None:
        page_num = self._editor_notebook.page_num(editor)
        if page_num >= 0:
            self._editor_notebook.remove_page(page_num)
        del self._open_editors[class_name]
        self._check_editor_auto_hide()

    def _on_editor_modified(self, editor: CodeEditor, modified: bool) -> None:
        """Update the tab label with a dirty marker when the editor changes."""
        class_name = self._class_name_for_editor(editor)
        if class_name is None:
            return
        self._update_editor_tab_label(class_name, modified)
        if modified and self.project:
            self.project.mark_changed()
            self._update_save_indicator()

    def _class_name_for_editor(self, editor: CodeEditor) -> str | None:
        for name, ed in self._open_editors.items():
            if ed is editor:
                return name
        return None

    def _update_editor_tab_label(self, class_name: str, modified: bool) -> None:
        editor = self._open_editors.get(class_name)
        if editor is None:
            return
        tab_box = self._editor_notebook.get_tab_label(editor)
        if tab_box is None:
            return
        label_widget = tab_box.get_first_child()
        if isinstance(label_widget, Gtk.Label):
            text = f"● {class_name}" if modified else class_name
            label_widget.set_text(text)

    def _update_save_indicator(self) -> None:
        """Show project save state in the status bar."""
        if not self.project:
            return
        if self.project.is_changed:
            current = self._status_label.get_text()
            marker = " ●"
            if not current.endswith(marker):
                self._status_label.set_text(current + marker)
        else:
            current = self._status_label.get_text()
            if current.endswith(" ●"):
                self._status_label.set_text(current[:-2])

    def _on_breakpoint_toggled(self, editor: CodeEditor, filepath: str, line: int) -> None:
        """Handle breakpoint toggle in editor."""
        is_set = self.debugger.toggle_breakpoint(filepath, line)
        if is_set:
            self.terminal.write_info(f"Breakpoint set: {Path(filepath).name}:{line}")
        else:
            self.terminal.write_info(f"Breakpoint removed: {Path(filepath).name}:{line}")

    def _rename_class(self, old_name: str) -> None:
        """Rename a class via dialog."""
        if not self.project:
            return

        existing = list(self.project.model.classes.keys())
        was_open = old_name in self._open_editors
        editor_was_modified = False
        if was_open:
            editor_was_modified = self._open_editors[old_name].is_modified

        def on_rename(old: str, new: str) -> None:
            # Save current editor content first so the rename sees latest source
            if old in self._open_editors:
                ed = self._open_editors[old]
                if ed.is_modified:
                    ed.save()
            try:
                self.project.rename_class(old, new)
            except Exception as e:
                self._set_status(f"Rename failed: {e}")
                self.terminal.write_error(f"Rename failed: {e}")
                self._show_error("Rename Failed", str(e))
                return

            # Re-key the open editor and its tab label
            if old in self._open_editors:
                editor = self._open_editors.pop(old)
                self._open_editors[new] = editor
                editor.file_path = self.project.path / f"{new}.py"
                editor._class_name = new
                page_num = self._editor_notebook.page_num(editor)
                if page_num >= 0:
                    tab_box = self._editor_notebook.get_tab_label(editor)
                    label_widget = tab_box.get_first_child() if tab_box else None
                    if isinstance(label_widget, Gtk.Label):
                        label_widget.set_text(new)

            self._current_class = new if self._current_class == old else self._current_class
            self._refresh_diagram()
            self._set_status(f"Renamed {old} → {new}")
            self.terminal.write_info(f"Renamed class {old} → {new}")

        dialog = RenameClassDialog(old_name, existing, parent=self, on_rename=on_rename)
        dialog.show()

    def _delete_class(self, class_name: str) -> None:
        """Delete a class from the project after confirmation."""
        if not self.project:
            return

        def on_response(index: int) -> None:
            if index != 1:
                return
            if class_name in self._open_editors:
                self._remove_editor_tab(class_name, self._open_editors[class_name])
            try:
                self.project.remove_class(class_name)
                self._refresh_diagram()
                self._set_status(f"Deleted class: {class_name}")
            except Exception as e:
                self._set_status(f"Delete failed: {e}")
                self._show_error("Delete Failed", str(e))

        self._show_confirm(
            f"Delete {class_name}?",
            f"This will permanently remove the class '{class_name}' and its "
            f"source file from the project. This cannot be undone.",
            on_response,
            confirm_label="Delete",
            cancel_label="Cancel",
        )

    def _instantiate_class(self, class_name: str) -> None:
        """Instantiate a class - show constructor dialog."""
        if not self.project:
            return

        cls_info = self.project.model.get_class(class_name)

        def on_create(name: str, class_name: str, args: list) -> None:
            try:
                if self.debugger.get_breakpoints():
                    self._debug_instantiate(class_name, args, name)
                else:
                    obj = self.executor.instantiate(class_name, *args, name=name)
                    self.object_bench.add_object(obj)
                    self.terminal.write_info(f"Created: {obj.name} ({obj.class_name})")
            except Exception as e:
                self.terminal.write_error(f"Error creating {class_name}: {e}")
                self._show_error(f"Cannot Create {class_name}", str(e))

        dialog = ConstructorDialog(class_name, cls_info, self.executor, parent=self, on_create=on_create)
        dialog.show()

    def _debug_instantiate(self, class_name: str, args: list, name: str) -> None:
        """Instantiate a class under the debugger in a background thread."""
        cls = self.executor.namespace.get(class_name)
        if cls is None or not inspect.isclass(cls):
            self.terminal.write_error(f"Class '{class_name}' not found")
            return

        self._show_bottom_panel()
        self._bottom_notebook.set_current_page(2)  # Debugger tab
        self.terminal.write_info(f"Debugging: creating {class_name}...")

        def _run() -> None:
            try:
                instance = self.debugger.run_call(cls, *args)
                bench_obj = BenchObject(name=name, instance=instance, class_name=class_name)
                self.executor.bench[name] = bench_obj
                self.executor.namespace[name] = instance
                count = self.executor._bench_counter.get(class_name, 0) + 1
                self.executor._bench_counter[class_name] = count
                GLib.idle_add(lambda: self.object_bench.add_object(bench_obj))
                GLib.idle_add(lambda: self.terminal.write_info(f"Created: {name} ({class_name})"))
                GLib.idle_add(lambda: self.debugger_panel.set_idle())
            except Exception as e:
                err = str(e)
                GLib.idle_add(lambda: self.terminal.write_error(f"Error: {err}"))
                GLib.idle_add(lambda: self.debugger_panel.set_idle())
                GLib.idle_add(lambda: self._show_error(f"Cannot Create {class_name}", err))

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    # --- Object Bench Handlers ---

    def _on_object_right_clicked(self, bench: ObjectBench, name: str, x: float, y: float) -> None:
        """Handle right-click on an object in the bench."""
        obj = self.executor.bench.get(name)
        if obj is None:
            return

        menu = Gio.Menu.new()

        # Inspect
        menu.append("Inspect", f"win.inspect-{name}")

        # Methods submenu
        methods = obj.get_public_methods()
        if methods:
            methods_section = Gio.Menu.new()
            for method_name in methods[:20]:  # Limit to first 20
                methods_section.append(method_name, f"win.call-{name}-{method_name}")
            menu.append_section("Methods", methods_section)

        bluep_section = Gio.Menu.new()
        bluep_section.append("Remove", f"win.remove-{name}")
        menu.append_section("BlueP", bluep_section)

        # Create dynamic actions
        self._create_bench_context_actions(name)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        n_methods = len(methods) if methods else 0
        menu_height = min(n_methods * 30 + 140, 400)
        popover.set_size_request(240, menu_height)
        tx, ty = bench.translate_coordinates(self, x, y)
        rect = Gdk.Rectangle()
        rect.x = int(tx)
        rect.y = int(ty)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.set_parent(self)
        popover.popup()

    def _create_bench_context_actions(self, obj_name: str) -> None:
        """Create dynamic actions for object bench context menu."""
        obj = self.executor.bench.get(obj_name)
        if obj is None:
            return

        # Remove old bench actions
        for action_name in list(self.list_actions()):
            if action_name.startswith(("inspect-", "remove-", "call-", "clear-all")):
                self.remove_action(action_name)

        # Inspect
        act = Gio.SimpleAction.new(f"inspect-{obj_name}", None)
        act.connect("activate", lambda a, p: self._inspect_object(obj_name))
        self.add_action(act)

        # Remove
        act = Gio.SimpleAction.new(f"remove-{obj_name}", None)
        act.connect("activate", lambda a, p: self._remove_bench_object(obj_name))
        self.add_action(act)

        # Method calls
        for method_name in obj.get_public_methods()[:20]:
            act = Gio.SimpleAction.new(f"call-{obj_name}-{method_name}", None)
            act.connect("activate", lambda a, p, mn=method_name: self._call_bench_method(obj_name, mn))
            self.add_action(act)

    def _on_object_double_clicked(self, bench: ObjectBench, name: str) -> None:
        """Handle double-click on object - inspect."""
        self._inspect_object(name)

    def _on_bench_right_clicked(self, bench: ObjectBench, x: float, y: float) -> None:
        """Handle right-click on empty bench area."""
        menu = Gio.Menu.new()
        menu.append("Clear All Objects", "win.clear-all")
        act = Gio.SimpleAction.new("clear-all", None)
        act.connect("activate", lambda a, p: self._clear_bench())
        self.add_action(act)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        tx, ty = bench.translate_coordinates(self, x, y)
        rect = Gdk.Rectangle()
        rect.x = int(tx)
        rect.y = int(ty)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.set_parent(self)
        popover.popup()

    def _inspect_object(self, name: str) -> None:
        """Open the object inspector for a bench object."""
        obj = self.executor.bench.get(name)
        if obj is None:
            return
        dialog = ObjectInspectorDialog(obj, parent=self)
        dialog.show()

    def _call_bench_method(self, obj_name: str, method_name: str) -> None:
        """Call a method on a bench object."""
        obj = self.executor.bench.get(obj_name)
        if obj is None:
            return
        dialog = MethodCallDialog(obj, method_name, self.executor, parent=self,
                                  debugger=self.debugger)
        dialog.connect("object-created", self._on_method_call_object_created)
        dialog.connect("debug-finished", lambda d: self.debugger_panel.set_idle())
        dialog.show()

    def _on_method_call_object_created(self, dialog: MethodCallDialog, name: str) -> None:
        """Handle object created via method call 'Get' button."""
        obj = self.executor.bench.get(name)
        if obj:
            self.object_bench.add_object(obj)
            self.terminal.write_info(f"Created via method call: {name}")

    def _remove_bench_object(self, name: str) -> None:
        """Remove an object from the bench."""
        self.object_bench.remove_object(name)
        self.executor.remove_bench_object(name)
        self.terminal.write_info(f"Removed: {name}")

    def _clear_bench(self) -> None:
        """Clear all objects from the bench."""
        self.object_bench.clear()
        self.executor.clear_bench()
        self.terminal.write_info("Bench cleared")

    # --- Code Pad Handlers ---

    def _on_code_pad_evaluated(self, pad: CodePad, expression: str, result: str, success: bool) -> None:
        """Handle code pad expression evaluation."""
        if not success:
            self._set_status(f"Code Pad error: {result[:50]}")

    def _on_code_pad_object_created(self, pad: CodePad, name: str) -> None:
        """Handle object created via code pad."""
        obj = self.executor.bench.get(name)
        if obj:
            self.object_bench.add_object(obj)
            self.terminal.write_info(f"Created via Code Pad: {name}")

    # --- Terminal Handlers ---

    def _on_terminal_output(self, terminal: Terminal, text: str) -> None:
        """Handle terminal output."""
        pass  # Terminal already displays the output

    # --- Debugger Handlers ---

    def _on_debugger_pause(self, state: DebugState) -> None:
        """Called when debugger pauses at a breakpoint."""
        GLib.idle_add(lambda: self._on_debugger_pause_idle(state))

    def _on_debugger_pause_idle(self, state: DebugState) -> bool:
        """Handle debugger pause in main thread."""
        self.debugger_panel.update_state(state)
        self._bottom_notebook.set_current_page(2)  # Switch to debugger tab

        # Show the current line in the editor
        if state.current_file and state.current_line:
            filename = Path(state.current_file).stem
            if filename in self._open_editors:
                self._open_editors[filename].goto_line(state.current_line)

        self._set_status(f"Paused at: {state.current_function}:{state.current_line}")
        return False

    def _debugger_step(self, action: str) -> None:
        """Execute a debugger step action."""
        if action == "next":
            self.debugger.step_over()
        elif action == "step":
            self.debugger.step_into()
        elif action == "return":
            self.debugger.step_out()
        elif action == "continue":
            self.debugger.continue_execution()

    def _debugger_terminate(self) -> None:
        """Terminate debugging."""
        self.debugger.stop_debugging()
        self.debugger_panel.set_idle()
        self._set_status("Debugging terminated")

    # --- Utility ---

    def _set_status(self, message: str) -> None:
        """Update the status bar."""
        self._status_label.set_text(message)
        self._compile_status.set_text("")

    def _show_error(self, title: str, detail: str) -> None:
        """Show an error popup dialog."""
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(detail)
        dialog.set_modal(True)
        dialog.show(self)

    def _show_confirm(self, title: str, detail: str,
                      on_confirm: object, confirm_label: str = "Confirm",
                      cancel_label: str = "Cancel",
                      discard_label: str | None = None) -> None:
        """Show a confirmation dialog and call on_confirm(index) when done.

        Button order: [cancel_label, confirm_label] or
        [cancel_label, discard_label, confirm_label] when discard_label is set.
        The callback receives the 0-based button index.
        """
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(detail)
        dialog.set_modal(True)
        if discard_label is not None:
            dialog.set_buttons([cancel_label, discard_label, confirm_label])
            dialog.set_cancel_button(0)
            dialog.set_default_button(2)
        else:
            dialog.set_buttons([cancel_label, confirm_label])
            dialog.set_cancel_button(0)
            dialog.set_default_button(1)

        def _on_response(dialog: Gtk.AlertDialog, result: object) -> None:
            try:
                index = dialog.choose_finish(result)
            except Exception:
                index = -1
            if on_confirm:
                on_confirm(index)

        dialog.choose(self, None, _on_response)

    def cleanup(self) -> None:
        """Clean up before closing."""
        # Save all open editors
        for editor in self._open_editors.values():
            if editor.is_modified:
                editor.save()

        # Save project
        if self.project:
            self.project.save()

        # Stop debugger
        self.debugger.stop_debugging()

        # Stop AI agent
        if self.ai_agent:
            self.ai_agent.stop()

    def do_close_request(self) -> bool:
        """Handle window close request."""
        self.cleanup()
        return False  # Allow close
