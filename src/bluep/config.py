"""BlueP configuration management.

Settings come from three layers (later layers override earlier):
1. Built-in dataclass defaults.
2. Environment variables / .env file (read once at import).
3. Persisted user preferences at ~/.config/bluep/settings.json.

The persisted file is the single source of truth after first run; the
.env file seeds the initial values and the BLUEP_SUPERVISED flag, which
cannot be unset from the UI (it is a deployment/teacher lock).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path


# ── .env loading ──────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """Load .env file if python-dotenv is available, else parse manually."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        env_path = Path(os.getcwd()) / ".env"
        if not env_path.exists():
            # Try project root
            env_path = Path(__file__).resolve().parents[3] / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = value


# Load on import
_load_dotenv()


# ── Settings directory ────────────────────────────────────────────────

def _settings_dir() -> Path:
    """Return the user settings directory, creating it if needed."""
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    sdir = base / "bluep"
    sdir.mkdir(parents=True, exist_ok=True)
    return sdir


def _settings_file() -> Path:
    return _settings_dir() / "settings.json"


# ── Config dataclasses ───────────────────────────────────────────────

@dataclass
class AIConfig:
    """AI agent configuration."""
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    max_tokens: int = 4096
    temperature: float = 0.7

    @classmethod
    def from_env(cls) -> AIConfig:
        return cls(
            enabled=os.getenv("BLUEP_AI_ENABLED", "false").lower() in ("true", "1", "yes"),
            provider=os.getenv("BLUEP_AI_PROVIDER", "openai"),
            model=os.getenv("BLUEP_AI_MODEL", "gpt-4o"),
            api_key=os.getenv("BLUEP_AI_API_KEY", ""),
            base_url=os.getenv("BLUEP_AI_BASE_URL", "https://api.openai.com/v1"),
            max_tokens=int(os.getenv("BLUEP_AI_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("BLUEP_AI_TEMPERATURE", "0.7")),
        )


@dataclass
class EditorConfig:
    """Editor preferences (font, indentation, feature toggles).

    The autocomplete and ai_completion toggles are placeholders for
    future features; they persist now so enabling them later requires
    no schema migration.
    """
    tab_width: int = 4
    insert_spaces: bool = True
    font_family: str = "Monospace"
    font_size: int = 12
    show_line_numbers: bool = True
    highlight_current_line: bool = True
    auto_indent: bool = True
    smart_backspace: bool = True
    enable_syntax_highlighting: bool = True
    enable_autocomplete: bool = True
    enable_ai_completion: bool = False
    completion_accept_key: str = "tab"

    @classmethod
    def from_env(cls) -> EditorConfig:
        def _bool(name: str, default: bool) -> bool:
            return os.getenv(name, str(default)).lower() in ("true", "1", "yes")

        def _int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)))
            except ValueError:
                return default

        return cls(
            tab_width=_int("BLUEP_EDITOR_TAB_WIDTH", 4),
            insert_spaces=_bool("BLUEP_EDITOR_INSERT_SPACES", True),
            font_family=os.getenv("BLUEP_EDITOR_FONT", "Monospace"),
            font_size=_int("BLUEP_EDITOR_FONT_SIZE", 12),
            show_line_numbers=_bool("BLUEP_EDITOR_LINE_NUMBERS", True),
            highlight_current_line=_bool("BLUEP_EDITOR_HIGHLIGHT_CURRENT_LINE", True),
            auto_indent=_bool("BLUEP_EDITOR_AUTO_INDENT", True),
            smart_backspace=_bool("BLUEP_EDITOR_SMART_BACKSPACE", True),
            enable_syntax_highlighting=_bool("BLUEP_EDITOR_SYNTAX_HIGHLIGHTING", True),
            enable_autocomplete=_bool("BLUEP_EDITOR_AUTOCOMPLETE", True),
            enable_ai_completion=_bool("BLUEP_EDITOR_AI_COMPLETION", False),
            completion_accept_key=os.getenv("BLUEP_EDITOR_COMPLETION_ACCEPT_KEY", "tab"),
        )


@dataclass
class PythonConfig:
    """Python interpreter settings used when running/compiling code."""
    interpreter: str = "python3"
    startup_script: str = ""
    auto_compile_on_save: bool = True
    clear_bench_on_recompile: bool = True

    @classmethod
    def from_env(cls) -> PythonConfig:
        def _bool(name: str, default: bool) -> bool:
            return os.getenv(name, str(default)).lower() in ("true", "1", "yes")

        return cls(
            interpreter=os.getenv("BLUEP_PYTHON_INTERPRETER", "python3"),
            startup_script=os.getenv("BLUEP_PYTHON_STARTUP", ""),
            auto_compile_on_save=_bool("BLUEP_AUTO_COMPILE_ON_SAVE", True),
            clear_bench_on_recompile=_bool("BLUEP_CLEAR_BENCH_ON_RECOMPILE", True),
        )


@dataclass
class Config:
    """Global BlueP configuration.

    The `supervised` flag is read from the environment and is immutable
    from the UI: it represents a deployment/teacher lock that disables
    features inappropriate in a supervised (classroom/exam) setting.
    """
    theme: str = "dark"
    supervised: bool = False
    ai: AIConfig = field(default_factory=AIConfig.from_env)
    editor: EditorConfig = field(default_factory=EditorConfig.from_env)
    python: PythonConfig = field(default_factory=PythonConfig.from_env)

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            theme=os.getenv("BLUEP_THEME", "dark"),
            supervised=os.getenv("BLUEP_SUPERVISED", "false").lower() in ("true", "1", "yes"),
            ai=AIConfig.from_env(),
            editor=EditorConfig.from_env(),
            python=PythonConfig.from_env(),
        )

    @classmethod
    def load(cls) -> Config:
        """Load config: env defaults, then override with persisted JSON.

        The `supervised` flag is ALWAYS taken from the environment and
        cannot be relaxed by the persisted file.
        """
        cfg = cls.from_env()
        path = _settings_file()
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}
        else:
            data = {}

        # Override from persisted file
        if "theme" in data:
            cfg.theme = data["theme"]
        if "ai" in data and isinstance(data["ai"], dict):
            cfg.ai = replace(cfg.ai, **_filter_known(cfg.ai, data["ai"]))
        if "editor" in data and isinstance(data["editor"], dict):
            cfg.editor = replace(cfg.editor, **_filter_known(cfg.editor, data["editor"]))
        if "python" in data and isinstance(data["python"], dict):
            cfg.python = replace(cfg.python, **_filter_known(cfg.python, data["python"]))

        # `supervised` is always re-read from env; the file cannot relax it
        cfg.supervised = os.getenv("BLUEP_SUPERVISED", "false").lower() in ("true", "1", "yes")
        return cfg

    def save(self) -> None:
        """Persist user-editable settings to ~/.config/bluep/settings.json.

        The `supervised` flag is intentionally NOT written: it is a
        deployment lock read from the environment, not a user pref.
        """
        data = {
            "theme": self.theme,
            "ai": asdict(self.ai),
            "editor": asdict(self.editor),
            "python": asdict(self.python),
        }
        path = _settings_file()
        try:
            path.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def supervised_locked_features(self) -> list[str]:
        """Return names of features locked (disabled) under supervised mode.

        These are the features a teacher/exam setting would disable to
        prevent AI-assisted workarounds or interpreter tampering.
        """
        if not self.supervised:
            return []
        return [
            "ai_panel",
            "ai_settings_tab",
            "python_settings_tab",
            "editor_ai_completion_toggle",
        ]

    def is_feature_locked(self, feature: str) -> bool:
        """Check if a named feature is locked by supervised mode."""
        return self.supervised and feature in self.supervised_locked_features()


def _filter_known(defaults_obj: object, data: dict) -> dict:
    """Keep only keys from `data` that exist as fields on `defaults_obj`."""
    known = set(asdict(defaults_obj).keys())  # type: ignore[arg-type]
    return {k: v for k, v in data.items() if k in known}


# Global config instance — loaded from env + persisted file
config = Config.load()
