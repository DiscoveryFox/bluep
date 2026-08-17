#!/usr/bin/env python3
"""Verify panel hide/show functionality."""
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, GLib, Gdk

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

        run_tests(win, a)

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

    print("=== Panel Hide/Show Tests ===")

    check("editor_box visible by default", win._editor_box.get_visible())
    check("restore btn hidden by default", not win._editor_restore_btn.get_visible())

    win._hide_editor()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("editor_box hidden after _hide_editor", not win._editor_box.get_visible())
    check("restore btn visible after _hide_editor", win._editor_restore_btn.get_visible())

    win._show_editor()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("editor_box visible after _show_editor", win._editor_box.get_visible())
    check("restore btn hidden after _show_editor", not win._editor_restore_btn.get_visible())

    page_num = win._editor_notebook.page_num(win._welcome_page)
    check("welcome page in notebook", page_num >= 0)

    win._dismiss_welcome()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    page_num = win._editor_notebook.page_num(win._welcome_page)
    check("welcome page removed after dismiss", page_num < 0)

    check("bottom_box visible by default", win._bottom_box.get_visible())

    win._action_toggle_bottom_panel()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("bottom_box hidden after toggle", not win._bottom_box.get_visible())
    win._action_toggle_bottom_panel()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("bottom_box visible after second toggle", win._bottom_box.get_visible())

    win.activate_action("win.hide-editor")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("hide-editor action hides editor", not win._editor_box.get_visible())
    check("restore btn visible after hide-editor action", win._editor_restore_btn.get_visible())

    print(f"\n{passed} passed, {failed} failed")
    app.quit()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
