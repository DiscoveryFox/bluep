"""BlueP GTK application entry point.

BluePApp is a Gtk.Application that loads the Catppuccin Mocha theme,
registers the application ID, and creates the MainWindow on activation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gtk, Gdk, Gio, GLib

from bluep import __version__
from bluep.config import Config, config as global_config
from bluep.ui.main_window import MainWindow


class BluePApp(Gtk.Application):
    """GTK Application for BlueP IDE.

    Handles application lifecycle, CSS theme loading, and window creation.
    """

    __gtype_name__ = "BluePApp"

    def __init__(self) -> None:
        super().__init__(application_id="io.bluep.BlueP")
        self.set_flags(Gio.ApplicationFlags.NON_UNIQUE | Gio.ApplicationFlags.HANDLES_OPEN)
        self._config: Config = global_config
        self._main_window: MainWindow | None = None
        self._project_paths: list[str] = []

    # ── Lifecycle ───────────────────────────────────────────────

    def do_startup(self) -> None:
        """Called once at application startup — load theme, register actions."""
        Gtk.Application.do_startup(self)
        self._load_css_theme()

        # Quit action (Ctrl+Q handled at window level, but also register)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda a, p: self.quit())
        self.add_action(quit_action)

        # About action
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

    def do_activate(self) -> None:
        """Called when the application is activated — create and show window."""
        if self._main_window is None:
            self._main_window = MainWindow(self, self._config)
            self._main_window.connect("close-request", self._on_window_close)

        self._main_window.present()

        # If a project path was passed on the command line, open it
        if self._project_paths:
            path = Path(self._project_paths[0])
            if path.exists():
                self._main_window.open_project(path, create=False)

    def do_open(self, files: list[Gio.File], hint: str) -> None:
        """Handle file open requests (e.g., double-clicking a .bluep file)."""
        if files:
            self._project_paths.append(files[0].get_path())
        self.activate()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        """Handle command-line arguments — check for project path."""
        args = command_line.get_arguments()
        if len(args) > 1:
            # First arg after program name could be a project path
            self._project_paths.append(args[1])
        self.activate()
        return 0

    # ── Private helpers ─────────────────────────────────────────

    def _load_css_theme(self) -> None:
        """Load the Catppuccin Mocha CSS theme from the package resources."""
        css_path = Path(__file__).parent / "resources" / "styles.css"
        if not css_path.exists():
            print(f"Warning: CSS theme not found at {css_path}", file=sys.stderr)
            return

        provider = Gtk.CssProvider()
        try:
            provider.load_from_path(str(css_path))
        except GLib.Error as e:
            print(f"Warning: Failed to load CSS theme: {e}", file=sys.stderr)
            return

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _on_about(self, action: Gio.SimpleAction, param: object) -> None:
        """Show the About dialog."""
        dialog = Gtk.AboutDialog()
        dialog.set_program_name("BlueP")
        dialog.set_version(__version__)
        dialog.set_comments("A BlueJ-inspired IDE for Python")
        dialog.set_copyright("© 2026 BlueP")
        dialog.set_license_type(Gtk.License.GPL_3_0)
        dialog.set_website("https://bluep.io")
        dialog.set_transient_for(self._main_window)
        dialog.set_modal(True)
        dialog.present()

    def _on_window_close(self, window: MainWindow) -> bool:
        """Handle main window close — quit the application."""
        self.quit()
        return False
