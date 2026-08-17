# UI modules

## `main_window.py`

The main application window. Wires together all UI components, registers
actions (New Project, Open, Save, Compile, Preferences, etc.), manages the
editor notebook tabs, applies supervised gating, and shows error/confirmation
dialogs.

Key responsibilities:

- **Tab management** — notebook with VSCode-style tabs, save indicators (`●`
  prefix when modified), close buttons
- **Panel hide/show** — each bottom notebook tab (Terminal, Code Pad,
  Debugger, AI) has a close button on its tab label; closing a tab moves
  it to a labeled restore bar at the bottom of the editor area, and the
  `show-terminal` / `show-code-pad` / `show-debugger` / `show-ai` actions
  restore it. When all 4 bottom tabs are closed the bottom area
  auto-collapses so the object bench expands to fill the space; restoring
  any panel re-shows the bottom area. The `toggle-bottom-panel` menu item
  hides the bottom area when visible, shows it only when there are tabs to
  show, and no-ops when the notebook is empty. The code editor can be
  collapsed to a thin vertical restore button on the right edge; when the
  last editor tab is closed (via close button or dismissing the welcome
  tab) the editor auto-hides and the restore button appears. The welcome
  tab has a close button for dismissal
- **Supervised gating** — disables AI panel and locked settings tabs when
  `BLUEP_SUPERVISED=true`
- **Dialogs** — error popups (`Gtk.AlertDialog`) for compile/instantiation
  failures, confirmation dialogs for delete and unsaved-close
- **Editor wiring** — applies `EditorConfig` to each editor on open, connects
  modified/compile/breakpoint signals

## `class_diagram.py`

Visual canvas showing class boxes. Supports drag-and-drop positioning,
dependency arrow drawing, right-click context menus, and selection.

## `code_editor.py`

The Python code editor. Features:

- **Tab key** — intercepts Tab to insert configured spaces (fixes GTK's
  8-space default)
- **Autocomplete** — inline ghost text preview (no dropdown popover); sources
  from Python keywords, builtins, buffer words, and bench object attributes;
  `Up`/`Down` cycles candidates, `Tab`/`Enter` accepts
- **Bracket auto-closing** — `()`, `[]`, `{}`, `''`, `""`
- **Auto-indent** — copies leading whitespace, adds extra indent after `:`
- **Breakpoints** — gutter click or `Ctrl+B`
- **Font** — applied via `Gtk.CssProvider` (works in both GtkSourceView and
  TextView fallback paths)

## `dialogs.py`

Dialog windows:

- `PreferencesDialog` — tabbed (General, Python, Editor, AI), supervised locks
  Python and AI tabs
- `RenameClassDialog` — validates empty/same/duplicate/invalid identifier,
  emits `class-renamed` signal
- `NewClassDialog` — name + kind selection with explanatory help text
- `ConstructorDialog` — parameter input with tips
- `MethodCallDialog` — method list with argument input and result display
- `ObjectInspectorDialog` — instance and static field inspection

## `object_bench.py`

Bottom panel holding instantiated objects as tiles. Each tile shows the object
name and class. Right-click for inspect, call method, remove.

## `code_pad.py`

REPL-style expression evaluator. Has access to all bench objects by name.

## `terminal.py`

Embedded terminal output for compile results and runtime messages.

## `debugger_panel.py`

Variable inspector and call-stack view during debugging.

## `ai_panel.py`

Chat interface for the AI agent. Hidden when AI is disabled or supervised.
