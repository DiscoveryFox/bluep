# BlueP

A BlueJ-inspired IDE for Python, built with GTK4 and PyGObject.

BlueP mirrors the visual, object-oriented workflow of BlueJ — class diagrams,
an interactive object bench, instant object inspection, a code pad — and
adapts it to Python. It is designed for teaching object-oriented programming
and for rapid prototyping of class-based Python projects.

## Features

- **Visual class diagram** — Drag-and-drop class boxes with live dependency
  arrows. Create, rename, and delete classes from the diagram or the context
  menu.
- **Interactive object bench** — Instantiate any class, call methods, inspect
  fields, and keep live objects on the bench for further experimentation.
- **Code editor** — Syntax-highlighted Python editor (GtkSourceView) with:
  - Configurable tab width (Tab key inserts N spaces, not an 8-space tab)
  - Python autocomplete (keywords, builtins, buffer words; Ctrl+Space to force)
  - Bracket auto-closing for `()`, `[]`, `{}`, `''`, `""`
  - Auto-indent (extra indent after `:` for block starts)
  - Line numbers, current-line highlight, smart backspace/home
  - Breakpoint gutter (click to toggle, Ctrl+B at cursor)
  - Compile-on-save (Ctrl+S)
- **Code pad** — A REPL-style scratch pad for evaluating Python expressions
  against the current project state.
- **Terminal** — Embedded terminal output for compile results and runtime
  messages.
- **Debugger** — Step-by-step debugging with variable inspection, breakpoint
  management, and call-stack view.
- **AI agent panel** — Optional integration with OpenAI-compatible APIs for
  code generation and assistance. Disabled by default; can be locked out
  entirely in supervised mode.
- **Supervised mode** — A deployment/teacher lock (`BLUEP_SUPERVISED=true` in
  the environment) that disables the AI panel, AI settings, Python interpreter
  settings, and the AI completion toggle. The flag is read only from the
  environment and cannot be relaxed from the UI or the persisted settings
  file — making it safe for classroom/exam use.
- **Tabbed settings** — A preferences dialog with General, Python, Editor, and
  AI tabs. Settings persist to `~/.config/bluep/settings.json` and override
  the `.env` defaults on subsequent loads.
- **Polished dialogs** — Every destructive action (delete class, close
  unsaved editor) asks for confirmation. Errors (compile failures,
  instantiation errors) show popup dialogs instead of silently going to the
  terminal.

## Requirements

- Python ≥ 3.14
- GTK 4
- PyGObject (`gi`)
- GtkSourceView 5 (optional — the editor falls back to a plain `Gtk.TextView`
  when unavailable, but syntax highlighting, native auto-indent, and
  breakpoints require it)
- [uv](https://docs.astral.sh/uv/) (recommended for running)

## Quick start

```bash
# Clone
git clone https://github.com/DiscoveryFox/bluep.git
cd bluep

# Run (uv resolves and installs dependencies automatically)
uv run bluep

# Or open a project directly
uv run bluep /path/to/my/project
```

Copy `.env.example` to `.env` and adjust values as needed. After the first
run, preferences are read from `~/.config/bluep/settings.json`.

## Configuration

Settings come from three layers (later layers override earlier):

1. **Built-in defaults** in the dataclasses (`config.py`).
2. **Environment variables / `.env`** — seed the initial values.
3. **Persisted user preferences** at `~/.config/bluep/settings.json`.

The `BLUEP_SUPERVISED` flag is always re-read from the environment and can
never be relaxed by the persisted file.

| Variable | Default | Description |
|---|---|---|
| `BLUEP_SUPERVISED` | `false` | Lock AI features and interpreter settings |
| `BLUEP_AI_ENABLED` | `false` | Enable the AI agent panel |
| `BLUEP_AI_PROVIDER` | `openai` | AI provider name |
| `BLUEP_AI_MODEL` | `gpt-4o` | Model name |
| `BLUEP_AI_API_KEY` | *(empty)* | API key for the provider |
| `BLUEP_AI_BASE_URL` | `https://api.openai.com/v1` | API base URL |
| `BLUEP_THEME` | `dark` | UI theme |
| `BLUEP_EDITOR_TAB_WIDTH` | `4` | Spaces per Tab key press |
| `BLUEP_EDITOR_INSERT_SPACES` | `true` | Insert spaces instead of `\t` |
| `BLUEP_EDITOR_FONT` | `Monospace` | Editor font family |
| `BLUEP_EDITOR_FONT_SIZE` | `12` | Editor font size (pt) |
| `BLUEP_EDITOR_LINE_NUMBERS` | `true` | Show line number gutter |
| `BLUEP_EDITOR_HIGHLIGHT_CURRENT_LINE` | `true` | Highlight the cursor line |
| `BLUEP_EDITOR_AUTO_INDENT` | `true` | Auto-indent on Enter |
| `BLUEP_EDITOR_SMART_BACKSPACE` | `true` | Smart backspace |
| `BLUEP_EDITOR_SYNTAX_HIGHLIGHTING` | `true` | Toggle syntax highlighting |
| `BLUEP_EDITOR_AUTOCOMPLETE` | `false` | Enable autocomplete popup |
| `BLUEP_EDITOR_AI_COMPLETION` | `false` | AI completion (placeholder) |
| `BLUEP_PYTHON_INTERPRETER` | `python3` | Interpreter for running code |
| `BLUEP_PYTHON_STARTUP` | *(empty)* | Startup script path |
| `BLUEP_AUTO_COMPILE_ON_SAVE` | `true` | Compile on save |
| `BLUEP_CLEAR_BENCH_ON_RECOMPILE` | `true` | Clear bench on recompile |

## Project structure

```
bluep/
├── src/bluep/
│   ├── app.py              # Gtk.Application entry point, CSS theme loading
│   ├── config.py           # Config dataclasses, env loading, JSON persistence
│   ├── __main__.py         # CLI entry point
│   ├── core/
│   │   ├── ai_agent.py     # AI agent integration
│   │   ├── class_info.py   # Class analysis, ClassInfo, ProjectModel
│   │   ├── debugger.py     # Debugger state machine
│   │   ├── executor.py     # Code execution engine, object bench
│   │   └── project.py      # Project lifecycle, file management, persistence
│   ├── ui/
│   │   ├── ai_panel.py     # AI chat panel
│   │   ├── class_diagram.py # Visual class diagram canvas
│   │   ├── code_editor.py  # Code editor (autocomplete, brackets, tabs)
│   │   ├── code_pad.py     # REPL-style code pad
│   │   ├── debugger_panel.py # Debug variable/stack view
│   │   ├── dialogs.py      # Preferences, rename, new class, method call
│   │   ├── main_window.py  # Main window, actions, notebook, wiring
│   │   ├── object_bench.py # Object bench tiles
│   │   └── terminal.py     # Terminal output widget
│   └── resources/
│       └── styles.css      # Catppuccin Mocha dark theme
├── tests/                  # Test suite
├── pyproject.toml
├── mkdocs.yml             # Documentation site config
└── docs/                  # MkDocs source pages
```

## Documentation

**Online**: [https://discoveryfox.github.io/bluep/](https://discoveryfox.github.io/bluep/)

The docs site is built and deployed automatically by a GitHub Actions workflow
(`.github/workflows/docs.yml`) on every push to `master` that touches `docs/`
or `mkdocs.yml`.

**Locally**: serve the docs with MkDocs:

```bash
uv run mkdocs serve
```

This starts a local docs site at `http://127.0.0.1:8000`.

## License

GPL-3.0
