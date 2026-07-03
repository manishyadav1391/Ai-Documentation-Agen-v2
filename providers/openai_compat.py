"""OpenAI-compatible API provider for the Documentation Automation Bot.

Supports Groq, OpenAI, Together AI, and any other service with an
OpenAI-compatible ``/chat/completions`` endpoint.
"""

import json
import re
from typing import Any, Dict, List

import httpx

from config import get_config
from .base import Provider, load_prompt


class OpenAICompatProvider(Provider):
    """HTTP provider for OpenAI-compatible LLM endpoints."""

    def __init__(self) -> None:
        cfg = get_config()
        self.provider_cfg = cfg.providers.openai_compat
        self.api_key = cfg.get_api_key("openai_compat")
        self.model = self.provider_cfg.model
        self.base_url = self.provider_cfg.base_url
        self.max_tokens = self.provider_cfg.max_tokens

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    @property
    def name(self) -> str:
        return "openai_compat"

    def is_available(self) -> bool:
        """Check if API key and base URL are present."""
        return bool(self.base_url and self.api_key)

    # --------------------------------------------------------------------- #
    # Public interface
    # --------------------------------------------------------------------- #



    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _chat(self, prompt: str) -> str:
        """Call the OpenAI-compatible chat completions endpoint."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": 0.2,
        }

        try:
            resp = self.client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"OpenAI-compatible API request failed ({self.base_url}): {exc}"
            ) from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(
                f"Unexpected response format from {self.base_url}: {data}"
            ) from exc

    @staticmethod
    def _parse_json_response(
        raw: str,
        original: List[Dict[str, Any]],
        key: str,
    ) -> List[Dict[str, Any]]:
        """Extract JSON array from *raw* and merge *key* into *original*."""
        text = raw.strip()

        # Try raw JSON first
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Look for a JSON array inside markdown fences or free text
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if not match:
                raise ValueError(
                    "Could not find JSON array in API response"
                ) from None
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Found text looking like JSON but could not parse it"
                ) from exc

        if not isinstance(parsed, list):
            raise ValueError(
                f"Expected JSON array, got {type(parsed).__name__}"
            )

        if len(parsed) != len(original):
            print(
                f"[OpenAICompatProvider] Warning: response length mismatch "
                f"({len(parsed)} vs {len(original)} items)."
            )

        result: List[Dict[str, Any]] = []
        for i, item in enumerate(original):
            merged = dict(item)
            if i < len(parsed):
                entry = parsed[i]
                if isinstance(entry, dict):
                    merged[key] = entry.get(key, "")
                elif isinstance(entry, str):
                    merged[key] = entry
                else:
                    merged[key] = str(entry)
            else:
                merged[key] = ""
            result.append(merged)
        return result