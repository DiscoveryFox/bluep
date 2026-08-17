#!/usr/bin/env python3
"""Verify keyboard shortcuts are registered via Gtk.Application.set_accels_for_action."""
import sys
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, GLib

from bluep.ui.main_window import MainWindow
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

    print("=== Keyboard Shortcut Registration ===")

    app_obj = win.get_application()
    check("app accessible from window", app_obj is not None)

    expected_actions = [
        "win.new-class",
        "win.compile-all",
        "win.save-project",
        "win.show-terminal",
        "win.show-code-pad",
        "win.show-debugger",
        "win.show-ai",
        "win.open-project",
    ]

    for action_name in expected_actions:
        accels = app_obj.get_accels_for_action(action_name)
        check(f"{action_name} has accel registered", len(accels) > 0)
        if accels:
            check(f"{action_name} accel value = {accels[0]}", len(accels[0]) > 0)

    check("win.command-palette has accel",
          len(app_obj.get_accels_for_action("win.command-palette")) > 0)

    check("no manual shortcut controller on window",
          not hasattr(win, "_shortcut_controller"))

    print(f"\n{passed} passed, {failed} failed")
    app.quit()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
