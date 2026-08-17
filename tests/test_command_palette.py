#!/usr/bin/env python3
"""Verify command palette: structure, filter, action registration."""
import sys
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, GLib

from bluep.ui.main_window import MainWindow
from bluep.ui.command_palette import CommandPalette
from bluep.config import Config


def main():
    app = Gtk.Application.new("com.bluep.test", 0)

    def on_activate(a):
        config = Config()
        win = MainWindow(a, config)
        win.present()
        for _ in range(50):
            GLib.MainContext.default().iteration(False)
        run_tests(win, app)

    app.connect("activate", on_activate)
    app.run()


def run_tests(win, app):
    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS: {name}")
        else:
            failed += 1
            print(f"  FAIL: {name}")

    print("=== Command Palette ===")

    commands = [
        ("New Class", "win.new-class"),
        ("Compile All", "win.compile-all"),
        ("Show Terminal", "win.show-terminal"),
        ("About", "win.about"),
        ("Preferences", "win.preferences"),
    ]

    palette = CommandPalette(win, commands)

    check("palette is a Gtk.Window", isinstance(palette, Gtk.Window))
    check("palette has search entry", hasattr(palette, "_search"))
    check("palette has list", hasattr(palette, "_list"))
    check("palette has 5 commands", len(palette._commands) == 5)
    check("palette has 5 filtered initially", len(palette._filtered) == 5)

    print("\n=== Filter ===")

    palette._search.set_text("compile")
    palette._populate_list()
    check("filtered to 1 (compile)", len(palette._filtered) == 1)
    check("filtered row is Compile All",
          palette._filtered[0][0] == "Compile All")

    palette._search.set_text("show")
    palette._populate_list()
    check("filtered to 1 (show)", len(palette._filtered) == 1)
    check("filtered row is Show Terminal",
          palette._filtered[0][0] == "Show Terminal")

    palette._search.set_text("xyz")
    palette._populate_list()
    check("filtered to 0 (no match)", len(palette._filtered) == 0)

    palette._search.set_text("")
    palette._populate_list()
    check("cleared filter back to 5", len(palette._filtered) == 5)

    print("\n=== Case-insensitive filter ===")

    palette._search.set_text("NEW")
    palette._populate_list()
    check("uppercase filter matches New Class", len(palette._filtered) == 1)

    palette._search.set_text("ABOUT")
    palette._populate_list()
    check("uppercase About matches", len(palette._filtered) == 1)

    palette._search.set_text("")
    palette._populate_list()

    print("\n=== Action registration ===")

    check("Ctrl+Shift+P accel registered",
          len(app.get_accels_for_action("win.command-palette")) > 0)

    check("command-palette in _setup_actions source",
          "command-palette" in
          open("src/bluep/ui/main_window.py").read())

    palette.close()

    print(f"\n{passed} passed, {failed} failed")
    app.quit()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
