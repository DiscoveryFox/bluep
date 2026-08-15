# Configuration overview

BlueP settings come from three layers, applied in order (later layers
override earlier):

1. **Built-in defaults** defined in the dataclasses in `config.py`.
2. **Environment variables / `.env`** — seed the initial values on first run.
3. **Persisted user preferences** at `~/.config/bluep/settings.json`.

After the first run, the JSON file is the source of truth for user-editable
preferences. The `.env` file is only consulted to seed defaults the first time.

## The one exception: supervised mode

The `BLUEP_SUPERVISED` flag is **always** re-read from the environment on every
load. The persisted settings file cannot relax it. This makes it safe for
classroom/exam deployments: an instructor sets `BLUEP_SUPERVISED=true` in the
environment, and no amount of UI changes or file edits can re-enable the
locked features.

See [Supervised Mode](supervised-mode.md) for details.

## Editing settings

Open **Edit → Preferences** to edit settings in a tabbed dialog:

- **General** — Theme
- **Python** — Interpreter, startup script, compile/bench options
- **Editor** — Tab width, font, line numbers, highlighting, autocomplete
- **AI** — Provider, model, API key, base URL

Click **Apply** to persist to `~/.config/bluep/settings.json` immediately.

## Resetting to defaults

Delete `~/.config/bluep/settings.json` and restart BlueP. The `.env` defaults
(or the built-in defaults if no `.env` is present) are used as the new baseline.
