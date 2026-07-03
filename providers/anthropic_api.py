"""Anthropic API provider for the Documentation Automation Bot.

Uses Anthropic's native ``/v1/messages`` endpoint via ``httpx``.
"""

import json
import re
from typing import Any, Dict, List

import httpx

from config import get_config
from .base import Provider, load_prompt


class AnthropicProvider(Provider):
    """HTTP provider for Anthropic's native Messages API."""

    def __init__(self) -> None:
        cfg = get_config()
        self.provider_cfg = cfg.providers.anthropic
        self.api_key = cfg.get_api_key()
        self.model = self.provider_cfg.model
        self.max_tokens = self.provider_cfg.max_tokens

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
        }

        self.client = httpx.Client(
            base_url="https://api.anthropic.com",
            headers=headers,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        """Check if API key is present."""
        return bool(self.api_key)

    # --------------------------------------------------------------------- #
    # Public interface
    # --------------------------------------------------------------------- #

    def generate_labels(
        self, regions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Send label prompt and parse JSON response."""
        prompt = load_prompt(
            "label_regions",
            regions_json=self._to_json(regions),
        )
        raw = self._chat(prompt)
        return self._parse_json_response(raw, regions, "label")

    def generate_field_descriptions(
        self, fields: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Send field-description prompt and parse JSON response."""
        prompt = load_prompt(
            "describe_fields",
            fields_json=self._to_json(fields),
        )
        raw = self._chat(prompt)
        return self._parse_json_response(raw, fields, "description")

    def generate_procedure_prose(self, screens: List[Dict[str, Any]]) -> str:
        """Send prose prompt and return plain text."""
        prompt = load_prompt(
            "procedure_prose",
            screens_json=self._to_json(screens),
        )
        return self._chat(prompt)

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _chat(self, prompt: str) -> str:
        """Call Anthropic Messages API."""
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            resp = self.client.post("/v1/messages", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Anthropic API request failed: {exc}"
            ) from exc

        try:
            # Anthropic returns content as a list of blocks
            return data["content"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise ValueError(
                f"Unexpected Anthropic response format: {data}"
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
                    "Could not find JSON array in Anthropic response"
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
                f"[AnthropicProvider] Warning: response length mismatch "
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