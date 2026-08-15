# Core modules

## `config.py`

Configuration management with a three-layer override system:

```python
Config.from_env()        # env + .env defaults
Config.load()            # env defaults + persisted JSON overrides
config.save()            # persist to ~/.config/bluep/settings.json
config.is_feature_locked("ai_panel")  # supervised mode check
```

The `supervised` flag is always re-read from the environment and is never
persisted, making it a deployment lock that cannot be bypassed from the UI.

## `class_info.py`

Static analysis of Python source files using the `ast` module. Extracts:

- Class name, kind (concrete, abstract, interface, enum, dataclass)
- Fields and methods
- Constructor signature
- Inheritance relationships

`ClassAnalyzer.analyze_file(path)` returns a list of `ClassInfo` objects.
`ProjectModel` aggregates all classes in a project.

## `project.py`

Project lifecycle management. A BlueP project is a directory containing
`.py` source files and a `.bluep/` metadata directory (like BlueJ's
`bluej.pkg`).

| Method | Purpose |
|---|---|
| `Project.create(path)` | Create a new project directory |
| `Project.open(path)` | Open or adopt an existing directory |
| `project.add_class_file(name, kind)` | Create a class file with template |
| `project.rename_class(old, new)` | Rename file + class definition |
| `project.remove_class(name)` | Delete a class file |
| `project.save()` | Persist metadata and diagram positions |

## `executor.py`

Code execution engine. Compiles `.py` files, instantiates classes on the
object bench, and evaluates code-pad expressions. Manages the live object
namespace that the code pad and method-call dialog use.

## `debugger.py`

Debugger state machine. Tracks execution state (idle, running, paused,
stepping), manages breakpoints, and exposes variable inspection and call-stack
introspection.

## `ai_agent.py`

AI integration with OpenAI-compatible APIs. Sends prompts to the configured
provider and returns responses. Disabled when `BLUEP_AI_ENABLED=false` or
when supervised mode is active.
