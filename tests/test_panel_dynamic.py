#!/usr/bin/env python3
"""Verify editor restore on right + dynamic bottom panel hide/show."""
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

    def tab_name_at(idx):
        page = win._bottom_notebook.get_nth_page(idx)
        for name, widget in win._bottom_panels.items():
            if widget is page:
                return name
        return None

    print("=== Editor Restore Button (Right Side) Tests ===")

    main_box = win.get_child()
    children = []
    child = main_box.get_first_child()
    while child is not None:
        children.append(child)
        child = child.get_next_sibling()

    check("main_box is horizontal", main_box.get_orientation() == Gtk.Orientation.HORIZONTAL)
    check("main_box has 2 children", len(children) == 2)
    check("content_box is first child (left)", children[0] is win._content_box)
    check("restore btn is second child (right)", children[1] is win._editor_restore_btn)
    check("restore btn hidden by default", not win._editor_restore_btn.get_visible())

    win._hide_editor()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("editor hidden after _hide_editor", not win._editor_box.get_visible())
    check("restore btn visible after _hide_editor", win._editor_restore_btn.get_visible())

    win._show_editor()
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("editor visible after _show_editor", win._editor_box.get_visible())
    check("restore btn hidden after _show_editor", not win._editor_restore_btn.get_visible())

    print("\n=== Bottom Panel Tab Close + Restore Bar Tests ===")

    check("4 bottom panels registered", len(win._bottom_panels) == 4)
    check("restore bar hidden by default", not win._panel_restore_bar.get_visible())
    check("no restore buttons by default", len(win._restore_buttons) == 0)
    check("4 tabs in notebook initially", win._bottom_notebook.get_n_pages() == 4)

    # Hide Terminal
    win._hide_bottom_panel("Terminal")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("notebook has 3 pages after hiding Terminal", win._bottom_notebook.get_n_pages() == 3)
    check("restore bar visible after hiding Terminal", win._panel_restore_bar.get_visible())
    check("Terminal restore button exists", "Terminal" in win._restore_buttons)

    # Hide Debugger
    win._hide_bottom_panel("Debugger")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("notebook has 2 pages after hiding Debugger", win._bottom_notebook.get_n_pages() == 2)
    check("2 restore buttons exist", len(win._restore_buttons) == 2)

    # Restore Terminal
    win._show_bottom_panel_named("Terminal")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("notebook has 3 pages after restoring Terminal", win._bottom_notebook.get_n_pages() == 3)
    check("Terminal restore button removed", "Terminal" not in win._restore_buttons)
    check("1 restore button remains", len(win._restore_buttons) == 1)

    # Restore Debugger
    win._show_bottom_panel_named("Debugger")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("notebook has 4 pages after restoring Debugger", win._bottom_notebook.get_n_pages() == 4)
    check("no restore buttons remain", len(win._restore_buttons) == 0)
    check("restore bar hidden when all restored", not win._panel_restore_bar.get_visible())
    check("tab 0 is Terminal", tab_name_at(0) == "Terminal")
    check("tab 1 is Code Pad", tab_name_at(1) == "Code Pad")
    check("tab 2 is Debugger", tab_name_at(2) == "Debugger")
    check("tab 3 is AI", tab_name_at(3) == "AI")

    # Hide all 4 panels
    for name in ["Terminal", "Code Pad", "Debugger", "AI"]:
        win._hide_bottom_panel(name)
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("notebook has 0 pages after hiding all", win._bottom_notebook.get_n_pages() == 0)
    check("4 restore buttons", len(win._restore_buttons) == 4)
    check("divider collapsed when all closed",
          win._main_paned.get_position() >= win._main_paned.get_height() - 50)

    # Restore via action
    win.activate_action("win.show-terminal")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("show-terminal action restores tab", win._bottom_notebook.get_n_pages() == 1)
    check("3 restore buttons after action restore", len(win._restore_buttons) == 3)

    # hide-code-pad action
    win._show_bottom_panel_named("Code Pad")
    win._show_bottom_panel_named("Debugger")
    win._show_bottom_panel_named("AI")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("all 4 restored", win._bottom_notebook.get_n_pages() == 4)
    check("tab 0 is Terminal (action path)", tab_name_at(0) == "Terminal")
    check("tab 1 is Code Pad (action path)", tab_name_at(1) == "Code Pad")
    check("tab 2 is Debugger (action path)", tab_name_at(2) == "Debugger")
    check("tab 3 is AI (action path)", tab_name_at(3) == "AI")
    win.activate_action("win.hide-code-pad")
    for _ in range(10):
        GLib.MainContext.default().iteration(False)
    check("hide-code-pad action hides Code Pad", win._bottom_notebook.get_n_pages() == 3)
    check("Code Pad in restore buttons", "Code Pad" in win._restore_buttons)

    # Welcome tab still works
    page_num = win._editor_notebook.page_num(win._welcome_page)
    check("welcome page still in notebook", page_num >= 0)
    win._dismiss_welcome()
    page_num = win._editor_notebook.page_num(win._welcome_page)
    check("welcome page removed after dismiss", page_num < 0)

    print(f"\n{passed} passed, {failed} failed")
    app.quit()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
