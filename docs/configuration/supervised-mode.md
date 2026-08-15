# Supervised mode

Supervised mode is a deployment/teacher lock that disables features
inappropriate for classroom or exam settings.

## Enabling

Set `BLUEP_SUPERVISED=true` in the environment or in `.env`:

```ini
BLUEP_SUPERVISED=true
```

Restart BlueP. The lock is active.

## What it locks

| Feature | Status when supervised |
|---|---|
| AI agent panel | Hidden and disabled |
| AI settings tab | Disabled (greyed out) |
| Python interpreter settings tab | Disabled |
| Editor AI completion toggle | Disabled |

All other editor features (autocomplete, tab width, font, syntax highlighting)
remain user-configurable — only AI and interpreter tampering are locked.

## Why it cannot be bypassed

The `BLUEP_SUPERVISED` flag is **always** re-read from the environment on
every `Config.load()` call. It is never written to the persisted settings
file (`~/.config/bluep/settings.json`), so editing that file cannot relax
the lock.

This means a student cannot:

- Edit the settings file to re-enable AI
- Use the preferences dialog to change the interpreter
- Toggle the AI completion checkbox

The only way to disable supervised mode is to change the environment variable
and restart BlueP.

## Locked feature names

For programmatic checks, `Config.supervised_locked_features()` returns:

```python
["ai_panel", "ai_settings_tab", "python_settings_tab", "editor_ai_completion_toggle"]
```

Use `Config.is_feature_locked(name)` to check individual features.
