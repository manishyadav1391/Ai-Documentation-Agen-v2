"""Anthropic API provider for the Documentation Automation Bot.

Uses Anthropic's native ``/v1/messages`` endpoint via ``httpx``.
Vision support (base64 PNG image blocks) is implemented but currently
dormant — enabled automatically when a vision-capable model is configured.
"""

import base64
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from config import get_config
from .base import Provider


_MAX_IMG_LONG_EDGE = 1568  # Anthropic recommended limit


def _downscale_image_bytes(img_bytes: bytes, max_edge: int = _MAX_IMG_LONG_EDGE) -> bytes:
    """Downscale image so the longest edge is at most *max_edge* pixels."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
        if max(w, h) <= max_edge:
            return img_bytes
        if w >= h:
            new_w, new_h = max_edge, int(h * max_edge / w)
        else:
            new_w, new_h = int(w * max_edge / h), max_edge
        img = img.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"Could not downscale image: {e}")
        return img_bytes


class AnthropicProvider(Provider):
    """HTTP provider for Anthropic's native Messages API."""

    def __init__(self) -> None:
        cfg = get_config()
        self.provider_cfg = cfg.providers.anthropic
        self.api_key = cfg.get_api_key("anthropic")
        self.model = self.provider_cfg.model
        self.max_tokens = self.provider_cfg.max_tokens

        self.client = httpx.Client(
            base_url="https://api.anthropic.com",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key or "",
                "anthropic-version": "2023-06-01",
            },
            timeout=httpx.Timeout(120.0, connect=15.0),
        )

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, prompt: str, *, max_tokens: int | None = None,
             temperature: float = 0.2, system: str | None = None) -> str:
        """Call Anthropic Messages API with exponential-backoff retry."""
        return self._call_api(
            content=[{"type": "text", "text": prompt}],
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            system=system,
        )

    def chat_vision(self, prompt: str, images: list[Path], **kw) -> str:
        """Send prompt + base64-encoded PNG images in a single API call."""
        content: list[dict[str, Any]] = []
        for img_path in images:
            try:
                raw = img_path.read_bytes()
                raw = _downscale_image_bytes(raw)
                b64 = base64.b64encode(raw).decode()
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64},
                })
            except Exception as e:
                logger.warning(f"Could not encode image {img_path}: {e}")
        content.append({"type": "text", "text": prompt})
        return self._call_api(
            content=content,
            max_tokens=kw.get("max_tokens", self.max_tokens),
            temperature=kw.get("temperature", 0.2),
            system=kw.get("system"),
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _call_api(
        self,
        content: list[dict],
        max_tokens: int,
        temperature: float,
        system: str | None,
    ) -> str:
        """POST to /v1/messages with exponential-backoff retry (3 attempts)."""
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            payload["system"] = system

        delays = [2, 6]
        for attempt in range(3):
            try:
                resp = self.client.post("/v1/messages", json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    if attempt < 2:
                        wait = delays[attempt]
                        logger.warning(
                            f"Anthropic HTTP {resp.status_code} on attempt {attempt + 1}; "
                            f"retrying in {wait}s…"
                        )
                        time.sleep(wait)
                        continue
                resp.raise_for_status()
                data = resp.json()
                return data["content"][0]["text"]
            except httpx.TimeoutException as exc:
                if attempt < 2:
                    wait = delays[attempt]
                    logger.warning(f"Anthropic timeout on attempt {attempt + 1}; retrying in {wait}s…")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"Anthropic API timed out after 3 attempts: {exc}") from exc
            except (KeyError, IndexError) as exc:
                raise ValueError(f"Unexpected Anthropic response format: {exc}") from exc
        raise RuntimeError("Anthropic API failed after 3 attempts.")