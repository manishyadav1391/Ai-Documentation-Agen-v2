"""OpenRouter provider for the Documentation Automation Bot.

OpenRouter (https://openrouter.ai) exposes many models (OpenAI, Anthropic,
Google, DeepSeek, ...) behind one OpenAI-compatible ``/chat/completions``
endpoint, so this reuses ``OpenAICompatProvider`` and only adds the
OpenRouter-specific attribution headers.

The API key is read from ``OPENROUTER_API_KEY`` (``.env``) or
``openrouter_api_key`` in ``secrets.yaml``.
"""

from .openai_compat import OpenAICompatProvider


class OpenRouterProvider(OpenAICompatProvider):
    """HTTP provider for OpenRouter."""

    config_key = "openrouter"

    def _extra_headers(self) -> dict[str, str]:
        headers = {}
        site_url = getattr(self.provider_cfg, "site_url", "")
        app_name = getattr(self.provider_cfg, "app_name", "")
        if site_url:
            headers["HTTP-Referer"] = site_url
        if app_name:
            headers["X-OpenRouter-Title"] = app_name
            headers["X-Title"] = app_name  # older header name, still accepted
        return headers
