# Architecture overview

BlueP is a GTK4 desktop application written in Python 3.14, using PyGObject for
GTK bindings. It follows a layered architecture:

```mermaid
graph TD
    A[app.py — Gtk.Application] --> B[main_window.py — MainWindow]
    B --> C[core/ — Domain logic]
    B --> D[ui/ — Widgets and panels]
    C --> E[class_info.py — Class analysis]
    C --> F[project.py — Project lifecycle]
    C --> G[executor.py — Code execution]
    C --> H[debugger.py — Debugger state]
    C --> I[ai_agent.py — AI integration]
    D --> J[class_diagram.py]
    D --> K[code_editor.py]
    D --> L[object_bench.py]
    D --> M[code_pad.py]
    D --> N[dialogs.py]
    D --> O[terminal.py]
    D --> P[debugger_panel.py]
    D --> Q[ai_panel.py]
    C --> R[config.py — Settings & env]
```

## Layers

| Layer | Responsibility |
|---|---|
| `app.py` | Application lifecycle, CSS theme loading, command-line handling |
| `ui/` | GTK widgets: main window, diagram, editor, bench, panels |
| `core/` | Domain logic: class analysis, project model, executor, debugger |
| `config.py` | Settings dataclasses, env loading, JSON persistence |

## Design principles

- **Visual-first**: class diagrams and object bench are the primary interface.
- **Config-driven**: all editor and Python settings flow through `Config`.
- **Graceful degradation**: the editor falls back to plain `Gtk.TextView` when
  GtkSourceView is unavailable.
- **Deployment-safe**: supervised mode is an environment lock, not a pref.
