# BlueP

A BlueJ-inspired IDE for Python, built with GTK4 and PyGObject.

BlueP mirrors the visual, object-oriented workflow of BlueJ — class diagrams,
an interactive object bench, instant object inspection, a code pad — and
adapts it to Python. It is designed for teaching object-oriented programming
and for rapid prototyping of class-based Python projects.

## Why BlueP?

| BlueJ | BlueP |
|---|---|
| Java | Python |
| Swing | GTK4 |
| Class diagram | Class diagram |
| Object bench | Object bench |
| Code pad (Moe) | Code pad |
| Debugger | Debugger |
| — | AI agent (optional) |
| — | Supervised mode (exam lock) |

## Get started in 30 seconds

```bash
git clone https://github.com/DiscoveryFox/bluep.git
cd bluep
uv run bluep
```

## Key features

- :material-file-code: **Visual class diagram** — drag, drop, rename, delete
- :material-clipboard-list: **Object bench** — instantiate, call methods, inspect
- :material-code-brackets: **Code editor** — autocomplete, bracket closing, configurable tabs
- :material-console: **Code pad** — REPL-style expression evaluation
- :material-bug: **Debugger** — breakpoints, step, variable inspection
- :material-robot: **AI agent** — optional OpenAI-compatible integration
- :material-shield-lock: **Supervised mode** — classroom/exam deployment lock

!!! tip "Supervised mode"
    Set `BLUEP_SUPERVISED=true` in the environment to disable AI features and
    interpreter settings for exam use. This lock cannot be bypassed from the UI.
