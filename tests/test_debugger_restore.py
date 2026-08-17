#!/usr/bin/env python3
"""Verify debugger flows restore a hidden Debugger tab + re-show bottom box.

Regressions covered:
- _debug_instantiate used to call bare _show_bottom_panel() + set_current_page(2),
  which showed an empty bottom box and switched to the WRONG tab (or no-op'd)
  when the Debugger tab had been closed via its close button.
- _on_debugger_pause_idle used to call set_current_page(2) with no restore at
  all, so a breakpoint hit while the Debugger tab was hidden showed nothing.

Both now call _show_bottom_panel_named("Debugger"), which restores the tab
AND re-shows _bottom_box AND sets it as the current page.
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

    print("=== Debugger Restore While Hidden ===")

    debugger_widget = win._bottom_panels["Debugger"]

    # Baseline: Debugger tab present, bottom box visible
    check("Debugger tab present initially",
          win._bottom_notebook.page_num(debugger_widget) >= 0)
    check("bottom_box visible initially", win._bottom_box.get_visible())

    # Hide the Debugger tab via its close button (auto-collapse path)
    win._hide_bottom_panel("Debugger")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("Debugger tab gone after hide",
          win._bottom_notebook.page_num(debugger_widget) < 0)
    check("Debugger in restore bar",
          "Debugger" in win._restore_buttons)

    # Hide the remaining 3 so the bottom box auto-collapses
    for name in ["Terminal", "Code Pad", "AI"]:
        win._hide_bottom_panel(name)
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("bottom_box auto-hidden when all 4 closed",
          not win._bottom_box.get_visible())
    check("no tabs in notebook", win._bottom_notebook.get_n_pages() == 0)

    # Simulate what _debug_instantiate and _on_debugger_pause_idle now do
    win._show_bottom_panel_named("Debugger")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("Debugger tab restored",
          win._bottom_notebook.page_num(debugger_widget) >= 0)
    check("bottom_box re-shown on restore", win._bottom_box.get_visible())
    check("Debugger is current page",
          win._bottom_notebook.get_current_page()
          == win._bottom_notebook.page_num(debugger_widget))
    check("Debugger no longer in restore bar",
          "Debugger" not in win._restore_buttons)

    # The previously-buggy bare _show_bottom_panel() helper must be gone
    import inspect
    check("_show_bottom_panel helper deleted",
          not hasattr(win, "_show_bottom_panel"))

    # _debug_instantiate and _on_debugger_pause_idle source must use the
    # new call (defense against regressions reintroducing the old pattern)
    src = inspect.getsource(MainWindow)
    check("_debug_instantiate uses _show_bottom_panel_named",
          "self._show_bottom_panel_named(\"Debugger\")" in src)
    check("no bare _show_bottom_panel() calls remain",
          "self._show_bottom_panel()" not in src)

    print(f"\n{passed} passed, {failed} failed")
    app.quit()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
