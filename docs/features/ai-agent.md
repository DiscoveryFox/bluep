# AI agent

BlueP has an optional AI agent panel for code generation and assistance. It is
disabled by default and can be completely locked out in
[supervised mode](../configuration/supervised-mode.md).

## Enabling

Set the following in your `.env`:

```ini
BLUEP_AI_ENABLED=true
BLUEP_AI_PROVIDER=openai
BLUEP_AI_MODEL=gpt-4o
BLUEP_AI_API_KEY=your-key-here
BLUEP_AI_BASE_URL=https://api.openai.com/v1
```

Or change the settings in **Edit → Preferences → AI**.

## Using the panel

The AI panel is on the right side of the main window. Type a prompt and the
agent responds with code suggestions, explanations, or completions. The
response is shown in the panel; you can copy it into your source files.

## Custom providers

`BLUEP_AI_BASE_URL` accepts any OpenAI-compatible API endpoint, so you can
point it at local models (e.g. Ollama, LM Studio) or other hosted providers.

## Supervised lock

When `BLUEP_SUPERVISED=true` is set in the environment:

- The AI panel is hidden and disabled
- The AI settings tab is disabled
- The Python interpreter settings tab is disabled
- The AI completion toggle in the editor settings is disabled

This lock is read-only from the environment and cannot be relaxed from the UI
or the persisted settings file.
