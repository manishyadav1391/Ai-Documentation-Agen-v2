"""OpenAI-compatible API provider for the Documentation Automation Bot.

Supports Groq, OpenAI, Together AI, and any other service with an
OpenAI-compatible ``/chat/completions`` endpoint.

Vision support uses ``image_url`` data-URI blocks (OpenAI-style).
"""

import base64
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from config import get_config
from .base import Provider


class OpenAICompatProvider(Provider):
    """HTTP provider for OpenAI-compatible LLM endpoints."""

    def __init__(self) -> None:
        cfg = get_config()
        self.provider_cfg = cfg.providers.openai_compat
        self.api_key = cfg.get_api_key("openai_compat")
        self.model = self.provider_cfg.model
        self.base_url = self.provider_cfg.base_url
        self.max_tokens = self.provider_cfg.max_tokens

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(120.0, connect=15.0),
        )

    @property
    def name(self) -> str:
        return "openai_compat"

    def is_available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def chat(self, prompt: str, *, max_tokens: int | None = None,
             temperature: float = 0.2, system: str | None = None) -> str:
        """Call the OpenAI-compatible chat completions endpoint."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._call_api(messages, max_tokens=max_tokens or self.max_tokens, temperature=temperature)

    def chat_vision(self, prompt: str, images: list[Path], **kw) -> str:
        """Send prompt + images as data-URI image_url blocks."""
        content: list[dict[str, Any]] = []
        for img_path in images:
            try:
                raw = img_path.read_bytes()
                b64 = base64.b64encode(raw).decode()
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
                })
            except Exception as e:
                logger.warning(f"Could not encode image {img_path}: {e}")
        content.append({"type": "text", "text": prompt})

        messages = []
        if kw.get("system"):
            messages.append({"role": "system", "content": kw["system"]})
        messages.append({"role": "user", "content": content})
        return self._call_api(messages, max_tokens=kw.get("max_tokens", self.max_tokens),
                              temperature=kw.get("temperature", 0.2))

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _call_api(self, messages: list[dict], max_tokens: int, temperature: float) -> str:
        """POST to /chat/completions with exponential-backoff retry."""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        delays = [2, 6]
        for attempt in range(3):
            try:
                resp = self.client.post("/chat/completions", json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    if attempt < 2:
                        wait = delays[attempt]
                        logger.warning(
                            f"OpenAI-compat HTTP {resp.status_code} on attempt {attempt + 1}; "
                            f"retrying in {wait}s…"
                        )
                        time.sleep(wait)
                        continue
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.TimeoutException as exc:
                if attempt < 2:
                    wait = delays[attempt]
                    logger.warning(f"OpenAI-compat timeout on attempt {attempt + 1}; retrying in {wait}s…")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"OpenAI-compat API timed out after 3 attempts: {exc}") from exc
            except (KeyError, IndexError) as exc:
                raise ValueError(f"Unexpected response format from {self.base_url}: {exc}") from exc
        raise RuntimeError(f"OpenAI-compat API failed after 3 attempts (base_url={self.base_url}).")