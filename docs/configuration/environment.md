# Environment variables

Copy `.env.example` to `.env` and adjust as needed. All variables are
optional; the defaults listed below apply when the variable is absent.

## Supervised mode

| Variable | Default | Description |
|---|---|---|
| `BLUEP_SUPERVISED` | `false` | Lock AI features and interpreter settings (see [Supervised Mode](supervised-mode.md)) |

## AI agent

| Variable | Default | Description |
|---|---|---|
| `BLUEP_AI_ENABLED` | `false` | Enable the AI agent panel |
| `BLUEP_AI_PROVIDER` | `openai` | Provider name |
| `BLUEP_AI_MODEL` | `gpt-4o` | Model name |
| `BLUEP_AI_API_KEY` | *(empty)* | API key |
| `BLUEP_AI_BASE_URL` | `https://api.openai.com/v1` | API base URL (any OpenAI-compatible endpoint) |
| `BLUEP_AI_MAX_TOKENS` | `4096` | Max response tokens |
| `BLUEP_AI_TEMPERATURE` | `0.7` | Sampling temperature |

## Theme

| Variable | Default | Description |
|---|---|---|
| `BLUEP_THEME` | `dark` | UI theme (`dark` or `light`) |

## Editor

| Variable | Default | Description |
|---|---|---|
| `BLUEP_EDITOR_TAB_WIDTH` | `4` | Spaces inserted per Tab key press |
| `BLUEP_EDITOR_INSERT_SPACES` | `true` | Insert spaces instead of `\t` |
| `BLUEP_EDITOR_FONT` | `Monospace` | Editor font family |
| `BLUEP_EDITOR_FONT_SIZE` | `12` | Editor font size in pt |
| `BLUEP_EDITOR_LINE_NUMBERS` | `true` | Show line number gutter |
| `BLUEP_EDITOR_HIGHLIGHT_CURRENT_LINE` | `true` | Highlight the cursor line |
| `BLUEP_EDITOR_AUTO_INDENT` | `true` | Auto-indent on Enter |
| `BLUEP_EDITOR_SMART_BACKSPACE` | `true` | Smart backspace (unindent to previous level) |
| `BLUEP_EDITOR_SYNTAX_HIGHLIGHTING` | `true` | Toggle syntax highlighting |
| `BLUEP_EDITOR_AUTOCOMPLETE` | `false` | Enable the autocomplete popup |
| `BLUEP_EDITOR_AI_COMPLETION` | `false` | AI completion (placeholder) |

## Python

| Variable | Default | Description |
|---|---|---|
| `BLUEP_PYTHON_INTERPRETER` | `python3` | Interpreter used to run code |
| `BLUEP_PYTHON_STARTUP` | *(empty)* | Startup script executed on interpreter launch |
| `BLUEP_AUTO_COMPILE_ON_SAVE` | `true` | Compile when saving a class |
| `BLUEP_CLEAR_BENCH_ON_RECOMPILE` | `true` | Clear the object bench on recompile |

## Boolean values

Boolean variables accept `true`, `1`, `yes` (case-insensitive) as true;
anything else is false.
