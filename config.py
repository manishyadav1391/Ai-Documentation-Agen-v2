"""
Configuration management for the Documentation Automation Bot.

Loads user-editable settings from ``config.yaml`` and injects sensitive
API keys from environment variables or a local ``.env`` file.
"""

import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import yaml


# Attempt to load .env if present (silently ignore if missing)
_env_loaded = False


def _ensure_env() -> None:
    global _env_loaded
    if not _env_loaded:
        dotenv_path = Path(".env")
        if dotenv_path.exists():
            load_dotenv(dotenv_path, override=False)
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
    model: str = "claude-3-5-sonnet-20241022"
    max_tokens: int = 1000


class OpenAICompatProviderConfig(BaseModel):
    """OpenAI-compatible endpoint settings (Groq, Together AI, etc.)."""
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    max_tokens: int = 1000


class OllamaProviderConfig(BaseModel):
    """Ollama local / remote API settings."""
    host: str = "http://localhost:11434"
    model: str = "llama3.2"
    api_key_env: str = "OLLAMA_API_KEY"


# -----------------------------------------------------------------------------
# Rendering & misc blocks
# -----------------------------------------------------------------------------

class RenderConfig(BaseModel):
    """Visual tuning for annotated screenshots."""
    label_font_size: int = 20
    region_stroke_width: int = 3
    callout_border_width: int = 2


class ProvidersConfig(BaseModel):
    """All provider-specific blocks."""
    browser: BrowserProviderConfig = Field(default_factory=BrowserProviderConfig)
    anthropic: AnthropicProviderConfig = Field(default_factory=AnthropicProviderConfig)
    openai_compat: OpenAICompatProviderConfig = Field(default_factory=OpenAICompatProviderConfig)
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
    """
    provider: Literal["browser", "anthropic", "openai_compat", "ollama"] = "browser"
    default_template: str = "ncd"
    sessions_dir: str = "sessions"
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)

    @property
    def sessions_path(self) -> Path:
        """Absolute Path to the session output folder."""
        return Path(self.sessions_dir).resolve()

    def get_active_provider_config(self) -> BaseModel:
        """Return the config block for the currently selected provider."""
        mapping = {
            "browser": self.providers.browser,
            "anthropic": self.providers.anthropic,
            "openai_compat": self.providers.openai_compat,
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
            "ollama": self.providers.ollama,
        }
        provider_cfg = mapping.get(p)
        env_name = getattr(provider_cfg, "api_key_env", None)
        if env_name:
            return os.environ.get(env_name)
        return None


# -----------------------------------------------------------------------------
# Global singleton helpers
# -----------------------------------------------------------------------------

_config_instance: Optional[Config] = None


def load_config(config_path: Any = Path("config.yaml")) -> Config:
    """
    Load and validate configuration from ``config.yaml``.

    Args:
        config_path: Path to the YAML config file (expected next to the .exe).

    Returns:
        A validated ``Config`` instance.
    """
    _ensure_env()
    config_path = Path(config_path)
    raw: Dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    return Config(**raw)


def get_config(config_path: Any = Path("config.yaml")) -> Config:
    """Return the cached global config, loading if necessary."""
    global _config_instance
    if _config_instance is None:
        _config_instance = load_config(config_path)
    return _config_instance


def reload_config(config_path: Any = Path("config.yaml")) -> Config:
    """Reload config from disk; useful when the user edits settings at runtime."""
    global _config_instance
    _config_instance = load_config(config_path)
    return _config_instance