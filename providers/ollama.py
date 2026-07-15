"""Ollama provider for the Documentation Automation Bot.

Uses httpx to POST directly to Ollama's /api/chat endpoint.
The ``ollama`` Python package is NOT required — this is a pure httpx
implementation that works with any Ollama-compatible endpoint (including
Ollama cloud with a Bearer key).

Vision support: the ``images`` field (list of base64 strings) is sent
when images are provided. Enable by using a vision-capable model name
(e.g. llava, bakllava) in config.yaml — zero code changes required.

Current default model is text-only (gpt-oss:120b).
"""

import base64
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from config import get_config
from .base import Provider


class OllamaProvider(Provider):
    """httpx-based Ollama provider (works with local and cloud endpoints)."""

    def __init__(self) -> None:
        cfg = get_config()
        self.provider_cfg = cfg.providers.ollama
        self.model = self.provider_cfg.model
        self.host = self.provider_cfg.host.rstrip("/")
        self.max_tokens = self.provider_cfg.max_tokens
        self.api_key = cfg.get_api_key("ollama")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.Client(
            base_url=self.host,
            headers=headers,
            timeout=httpx.Timeout(180.0, connect=15.0),
        )

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """True if host and api_key are configured (key required for cloud)."""
        return bool(self.host and self.api_key)

    def chat(self, prompt: str, *, max_tokens: int | None = None,
             temperature: float = 0.1, system: str | None = None) -> str:
        """Send a single-turn chat completion to Ollama."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._call_api(messages, images=[], max_tokens=max_tokens or self.max_tokens,
                              temperature=temperature)

    def chat_vision(self, prompt: str, images: list[Path], **kw) -> str:
        """Send prompt + images to Ollama (requires a vision-capable model)."""
        b64_images: list[str] = []
        for img_path in images:
            try:
                raw = img_path.read_bytes()
                b64_images.append(base64.b64encode(raw).decode())
            except Exception as e:
                logger.warning(f"Could not encode image {img_path}: {e}")

        messages = []
        if kw.get("system"):
            messages.append({"role": "system", "content": kw["system"]})
        messages.append({
            "role": "user",
            "content": prompt,
            "images": b64_images,
        })
        return self._call_api(
            messages,
            images=b64_images,
            max_tokens=kw.get("max_tokens", self.max_tokens),
            temperature=kw.get("temperature", 0.1),
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _call_api(
        self,
        messages: list[dict],
        images: list[str],
        max_tokens: int,
        temperature: float,
    ) -> str:
        """POST to /api/chat with exponential-backoff retry (3 attempts)."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        delays = [3, 9]
        for attempt in range(3):
            try:
                resp = self.client.post("/api/chat", json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    if attempt < 2:
                        wait = delays[attempt]
                        logger.warning(
                            f"Ollama HTTP {resp.status_code} on attempt {attempt + 1}; "
                            f"retrying in {wait}s…"
                        )
                        time.sleep(wait)
                        continue
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]
            except httpx.TimeoutException as exc:
                if attempt < 2:
                    wait = delays[attempt]
                    logger.warning(f"Ollama timeout on attempt {attempt + 1}; retrying in {wait}s…")
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Ollama API timed out after 3 attempts ({self.host}, model={self.model}): {exc}"
                ) from exc
            except (KeyError, IndexError) as exc:
                raise ValueError(f"Unexpected Ollama response format: {exc}") from exc
        raise RuntimeError(f"Ollama API failed after 3 attempts (host={self.host}, model={self.model}).")