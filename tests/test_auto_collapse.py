#!/usr/bin/env python3
"""Verify auto-collapse/expand: bottom panels + editor."""
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

    print("=== Bottom Panel Auto-Collapse Tests ===")

    check("bottom_box visible initially", win._bottom_box.get_visible())
    check("4 tabs initially", win._bottom_notebook.get_n_pages() == 4)

    # Hide 3 of 4 — bottom should still be visible (1 tab left)
    for name in ["Terminal", "Code Pad", "Debugger"]:
        win._hide_bottom_panel(name)
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("1 tab left after hiding 3", win._bottom_notebook.get_n_pages() == 1)
    check("bottom_box still visible with 1 tab", win._bottom_box.get_visible())

    # Hide the last one — bottom should auto-collapse
    win._hide_bottom_panel("AI")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("0 tabs after hiding all", win._bottom_notebook.get_n_pages() == 0)
    check("bottom_box auto-hidden when all closed", not win._bottom_box.get_visible())

    # Restore one — bottom should auto-expand
    win._show_bottom_panel_named("Terminal")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("1 tab after restoring Terminal", win._bottom_notebook.get_n_pages() == 1)
    check("bottom_box auto-shown when panel restored", win._bottom_box.get_visible())

    # Restore remaining 3
    for name in ["Code Pad", "Debugger", "AI"]:
        win._show_bottom_panel_named(name)
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("4 tabs after full restore", win._bottom_notebook.get_n_pages() == 4)
    check("bottom_box visible after full restore", win._bottom_box.get_visible())

    print("\n=== Editor Auto-Hide Tests ===")

    check("editor visible initially", win._editor_box.get_visible())
    check("restore btn hidden initially", not win._editor_restore_btn.get_visible())
    check("1 tab (welcome) initially", win._editor_notebook.get_n_pages() == 1)

    # Dismiss welcome — editor should auto-hide (0 tabs)
    win._dismiss_welcome()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("0 tabs after dismissing welcome", win._editor_notebook.get_n_pages() == 0)
    check("editor auto-hidden when no tabs", not win._editor_box.get_visible())
    check("restore btn visible after auto-hide", win._editor_restore_btn.get_visible())

    # Click restore — editor should show, welcome re-added
    win._show_editor()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("editor visible after restore", win._editor_box.get_visible())
    check("restore btn hidden after restore", not win._editor_restore_btn.get_visible())
    check("welcome re-added on restore", win._editor_notebook.get_n_pages() == 1)

    print("\n=== Round-Trip Tests ===")

    # Hide editor via action, restore, then dismiss welcome again
    win.activate_action("win.hide-editor")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("editor hidden via action", not win._editor_box.get_visible())

    # Dismissing welcome while editor hidden should not crash
    win._dismiss_welcome()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("0 tabs after dismiss while hidden", win._editor_notebook.get_n_pages() == 0)

    win._show_editor()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("welcome re-added on show_editor", win._editor_notebook.get_n_pages() == 1)

    print(f"\n{passed} passed, {failed} failed")
    app.quit()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
