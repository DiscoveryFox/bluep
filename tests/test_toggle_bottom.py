#!/usr/bin/env python3
"""Verify _action_toggle_bottom_panel does not show an empty bottom box.

Regression covered: the old toggle was
    self._bottom_box.set_visible(not self._bottom_box.get_visible())
which, when all 4 panels were closed (notebook empty, bottom box
auto-hidden), would show an empty box with 0 tabs — confusing.

The new toggle hides when visible, shows only when there are tabs to
show, and no-ops when the notebook is empty.
"""
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

    print("=== Toggle Bottom Panel ===")

    # Baseline: visible, 4 tabs
    check("bottom_box visible initially", win._bottom_box.get_visible())
    check("4 tabs initially", win._bottom_notebook.get_n_pages() == 4)

    # Close all 4 tabs — bottom auto-collapses (iterate between hides)
    for name in ["Terminal", "Code Pad", "Debugger", "AI"]:
        win._hide_bottom_panel(name)
        for _ in range(5):
            GLib.MainContext.default().iteration(False)
    check("bottom_box auto-hidden when all closed",
          not win._bottom_box.get_visible())
    check("0 tabs in notebook", win._bottom_notebook.get_n_pages() == 0)

    # Toggle while notebook empty — should NO-OP, not show empty box
    win._action_toggle_bottom_panel()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("toggle no-ops when notebook empty (box stays hidden)",
          not win._bottom_box.get_visible())
    check("still 0 tabs in notebook",
          win._bottom_notebook.get_n_pages() == 0)

    # Restore one panel — toggle should work again
    win._show_bottom_panel_named("Terminal")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("bottom_box visible after restore",
          win._bottom_box.get_visible())
    check("1 tab in notebook", win._bottom_notebook.get_n_pages() == 1)

    # Toggle hidden with 1 tab
    win._action_toggle_bottom_panel()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("bottom_box hidden after toggle (1 tab)",
          not win._bottom_box.get_visible())
    check("1 tab still in notebook", win._bottom_notebook.get_n_pages() == 1)

    # Toggle visible with 1 tab
    win._action_toggle_bottom_panel()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("bottom_box visible after toggle back (1 tab)",
          win._bottom_box.get_visible())

    print(f"\n{passed} passed, {failed} failed")
    app.quit()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
