"""Ollama provider for the Documentation Automation Bot.

Uses the official ``ollama`` Python package to stream chat completions
from a local or remote Ollama endpoint.
"""

import json
import re
from typing import Any, Dict, List

from ollama import Client

from config import get_config
from .base import Provider, load_prompt


class OllamaProvider(Provider):
    """Native Ollama provider using the ``ollama`` Python package."""

    def __init__(self) -> None:
        cfg = get_config()
        self.provider_cfg = cfg.providers.ollama
        self.model = self.provider_cfg.model
        self.host = self.provider_cfg.host
        self.api_key = cfg.get_api_key()

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = Client(host=self.host, headers=headers)

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """Return True if host and model are configured."""
        # Local Ollama does not strictly require an API key.
        return bool(self.host and self.model)

    # --------------------------------------------------------------------- #
    # Public interface
    # --------------------------------------------------------------------- #

    def generate_labels(
        self, regions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Send label prompt to Ollama and parse JSON response."""
        prompt = load_prompt(
            "label_regions",
            regions_json=self._to_json(regions),
        )
        raw = self._chat(prompt)
        return self._parse_json_response(raw, regions, "label")

    def generate_field_descriptions(
        self, fields: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Send field-description prompt to Ollama and parse JSON response."""
        prompt = load_prompt(
            "describe_fields",
            fields_json=self._to_json(fields),
        )
        raw = self._chat(prompt)
        return self._parse_json_response(raw, fields, "description")

    def generate_procedure_prose(self, screens: List[Dict[str, Any]]) -> str:
        """Send prose prompt to Ollama and return plain text."""
        prompt = load_prompt(
            "procedure_prose",
            screens_json=self._to_json(screens),
        )
        return self._chat(prompt)

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _chat(self, prompt: str) -> str:
        """
        Stream a single-turn chat completion and accumulate the response.
        """
        messages = [{"role": "user", "content": prompt}]
        parts: List[str] = []

        try:
            for chunk in self.client.chat(
                self.model, messages=messages, stream=True
            ):
                content = chunk.get("message", {}).get("content", "")
                if content:
                    parts.append(content)
        except Exception as exc:
            raise RuntimeError(
                f"Ollama chat failed ({self.host}, model={self.model}): {exc}"
            ) from exc

        return "".join(parts)

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
                    "Could not find JSON array in Ollama response"
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
                f"[OllamaProvider] Warning: response length mismatch "
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