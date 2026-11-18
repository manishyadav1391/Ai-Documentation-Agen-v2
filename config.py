"""
Configuration management for the Documentation Automation Bot.

Loads user-editable settings from ``config.yaml`` and injects sensitive
API keys from environment variables or a local ``.env`` file.
"""

import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, Field
import yaml


# Attempt to load .env if present (silently ignore if missing)
_env_loaded = False
from docbot import paths


def _ensure_env() -> None:
    global _env_loaded
    if not _env_loaded:
        dotenv_path = paths.data_dir() / ".env"
        if dotenv_path.exists():
            load_dotenv(dotenv_path, override=False)
            logger.debug(f"Loaded .env from {dotenv_path.resolve()}")
        _env_loaded = True


# -----------------------------------------------------------------------------
# Provider-specific config blocks
# -----------------------------------------------------------------------------

class BrowserProviderConfig(BaseModel):
    """Browser copy-paste mode — no keys, just a local editor."""
    editor_command: str = "notepad"


class AnthropicProviderConfig(BaseModel):
    """Anthropic API provider settings."""
    api_key_env: str = "ANTHROPIC_API_KEY"
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8000


class OpenAICompatProviderConfig(BaseModel):
    """OpenAI-compatible endpoint settings (Groq, Together AI, etc.)."""
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    max_tokens: int = 8000


class OpenRouterProviderConfig(BaseModel):
    """OpenRouter settings (OpenAI-compatible gateway to many models)."""
    api_key_env: str = "OPENROUTER_API_KEY"
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "~openai/gpt-sol-latest"
    max_tokens: int = 8000
    site_url: str = ""      # optional HTTP-Referer header (rankings on openrouter.ai)
    app_name: str = "DocBot"  # optional X-OpenRouter-Title header


class OllamaProviderConfig(BaseModel):
    """Ollama local / remote API settings."""
    host: str = "http://localhost:11434"
    model: str = "llama3.2"
    api_key_env: str = "OLLAMA_API_KEY"
    max_tokens: int = 8000


# -----------------------------------------------------------------------------
# Rendering & misc blocks
# -----------------------------------------------------------------------------

class RenderConfig(BaseModel):
    """Visual tuning for annotated screenshots."""
    label_font_size: int = 20
    region_stroke_width: int = 3
    callout_border_width: int = 2


class CaptureConfig(BaseModel):
    """Capture behaviour settings."""
    mode: Literal["viewport", "full_page", "both"] = "viewport"
    scroll_capture: bool = True


class ProvidersConfig(BaseModel):
    """All provider-specific blocks."""
    browser: BrowserProviderConfig = Field(default_factory=BrowserProviderConfig)
    anthropic: AnthropicProviderConfig = Field(default_factory=AnthropicProviderConfig)
    openai_compat: OpenAICompatProviderConfig = Field(default_factory=OpenAICompatProviderConfig)
    openrouter: OpenRouterProviderConfig = Field(default_factory=OpenRouterProviderConfig)
    ollama: OllamaProviderConfig = Field(default_factory=OllamaProviderConfig)


# -----------------------------------------------------------------------------
# Root config
# -----------------------------------------------------------------------------

class Config(BaseModel):
    """
    Root application configuration.

    Values are loaded from ``config.yaml`` and fall back to the defaults
    defined here. API keys are **never** stored in this object; only the
    name of the environment variable that holds the key is stored.

    Note: the ``theme:`` block present in v2 config.yaml has been removed.
    Branding is now controlled per-client via ``clients/<key>/style.yaml``.
    """
    provider: Literal["browser", "anthropic", "openai_compat", "openrouter", "ollama"] = "browser"
    default_template: str = "corporate"
    current_client: str = "ncb"
    content_dir: str = "content"
    clients_dir: str = "clients"
    styles_dir: str = "styles"
    sessions_dir: str = "sessions"
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    first_run_done: bool = False
    window_geometry: Optional[str] = None
    review_geometry: Optional[str] = None

    def get_current_client(self) -> str:
        """Return the active client identifier."""
        return self.current_client

    def validate_client_exists(self, client_key: str) -> bool:
        """Validate if the client's manifest exists (new clients/ layout first, legacy content/ fallback)."""
        new_path = paths.clients_dir() / client_key / "manifest.yaml"
        legacy_path = paths.content_dir() / client_key / "manifest.yaml"
        return new_path.exists() or legacy_path.exists()

    @property
    def sessions_path(self) -> Path:
        """Absolute Path to the session output folder."""
        return paths.sessions_dir()

    def get_active_provider_config(self) -> BaseModel:
        """Return the config block for the currently selected provider."""
        mapping = {
            "browser": self.providers.browser,
            "anthropic": self.providers.anthropic,
            "openai_compat": self.providers.openai_compat,
            "openrouter": self.providers.openrouter,
            "ollama": self.providers.ollama,
        }
        try:
            return mapping[self.provider]
        except KeyError as exc:
            raise ValueError(f"Unknown provider: {self.provider}") from exc

    def get_api_key(self, provider_name: Optional[str] = None) -> Optional[str]:
        """
        Return the resolved API key for the active or specified provider.

        Returns ``None`` when using browser mode.
        """
        _ensure_env()
        p = provider_name or self.provider
        if p == "browser":
            return None
        mapping = {
            "browser": self.providers.browser,
            "anthropic": self.providers.anthropic,
            "openai_compat": self.providers.openai_compat,
            "openrouter": self.providers.openrouter,
            "ollama": self.providers.ollama,
        }
        provider_cfg = mapping.get(p)
        env_name = getattr(provider_cfg, "api_key_env", None)
        
        # 1. Check environment variable
        if env_name and os.environ.get(env_name):
            return os.environ.get(env_name)
            
        # 2. Check secrets.yaml in data_dir
        secrets_path = paths.data_dir() / "secrets.yaml"
        if secrets_path.exists():
            try:
                with secrets_path.open("r", encoding="utf-8") as f:
                    secrets = yaml.safe_load(f) or {}
                # "openai_api_key" is the name older builds of the Settings
                # dialog used for the openai_compat provider.
                candidates = [f"{p}_api_key"]
                if p == "openai_compat":
                    candidates.append("openai_api_key")
                for sec_key in candidates:
                    if secrets.get(sec_key):
                        return str(secrets[sec_key]).strip()
            except Exception as e:
                logger.warning(f"Could not read secrets.yaml: {e}")
                
        return None


# -----------------------------------------------------------------------------
# Global singleton helpers
# -----------------------------------------------------------------------------

_config_instance: Optional[Config] = None


def load_config(config_path: Any = None) -> Config:
    """
    Load and validate configuration from ``config.yaml``.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        A validated ``Config`` instance.
    """
    _ensure_env()
    if config_path is None:
        config_path = paths.config_path()
    config_path = Path(config_path)
    raw: Dict[str, Any] = {}
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as e:
            logger.warning(f"Could not read {config_path} ({e}); using all defaults.")
            _backup_invalid(config_path)
            raw = {}
        if not isinstance(raw, dict):
            logger.warning(f"{config_path} does not contain a settings mapping; using all defaults.")
            _backup_invalid(config_path)
            raw = {}
        # Drop legacy theme block — it is now per-client in clients/<key>/style.yaml
        raw.pop("theme", None)
        _normalise_provider(raw)
    else:
        logger.warning(f"Config file not found at {config_path}; using all defaults.")
    return _build_config(raw)


def _backup_invalid(config_path: Path) -> None:
    """Keep a copy of an unreadable config.yaml before a later save overwrites it."""
    try:
        import shutil
        shutil.copy2(config_path, config_path.with_name(config_path.name + ".invalid"))
    except OSError:
        pass


_PROVIDER_ALIASES = {"openai": "openai_compat", "groq": "openai_compat", "claude": "anthropic"}


def _normalise_provider(raw: Dict[str, Any]) -> None:
    """Map hand-edited provider names (``openai``, ``Browser``) to valid ones."""
    if "provider" not in raw:
        return
    valid = Config.model_fields["provider"].annotation.__args__
    name = str(raw["provider"] or "").strip().lower()
    name = _PROVIDER_ALIASES.get(name, name)
    if name not in valid:
        logger.warning(f"Unknown provider {raw['provider']!r} in config.yaml; using 'browser'.")
        name = "browser"
    raw["provider"] = name


def _build_config(raw: Dict[str, Any]) -> Config:
    """Validate *raw*; drop invalid top-level keys (with a warning) instead of crashing."""
    try:
        return Config(**raw)
    except Exception as e:
        bad = set()
        for err in getattr(e, "errors", lambda: [])():
            if err.get("loc"):
                bad.add(err["loc"][0])
        if not bad:
            logger.warning(f"Invalid config.yaml ({e}); using all defaults.")
            return Config()
        logger.warning(f"Invalid config.yaml values for {sorted(map(str, bad))}; using defaults for those. ({e})")
        try:
            return Config(**{k: v for k, v in raw.items() if k not in bad})
        except Exception as e2:
            logger.warning(f"Invalid config.yaml ({e2}); using all defaults.")
            return Config()


def get_config(config_path: Any = None) -> Config:
    """Return the cached global config, loading if necessary."""
    global _config_instance
    if _config_instance is None:
        _config_instance = load_config(config_path)
    return _config_instance


def reload_config(config_path: Any = None) -> Config:
    """Reload config from disk; useful when the user edits settings at runtime."""
    global _config_instance
    fresh = load_config(config_path)
    if _config_instance is None:
        _config_instance = fresh
    else:
        # Update the existing object in place: the launcher, the review window
        # and the dialogs all keep a reference to it, and replacing the object
        # would leave them holding (and later re-saving) stale settings.
        for field_name in type(fresh).model_fields:
            setattr(_config_instance, field_name, getattr(fresh, field_name))
    logger.info("Configuration reloaded from disk.")
    return _config_instance


def save_config(config_obj: Config, config_path: Any = None) -> None:
    """Save the Config instance back to the config.yaml file."""
    if config_path is None:
        config_path = paths.config_path()
    config_path = Path(config_path)
    data = config_obj.model_dump()
    with config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    logger.info(f"Config saved to {config_path}")