"""
Provider base layer for DocBot v3.

Defines the abstract interface every LLM provider must implement.
Providers are pure transport — no UI imports, no tkinter, no config UI.

Interface summary
-----------------
- ``chat(prompt, *, max_tokens, temperature, system)`` → str
- ``chat_vision(prompt, images, **kw)`` → str  (default: text-only fallback)
- ``chat_json(prompt, schema, images, **kw)`` → BaseModel instance
  (strips fences, validates, retries once on ValidationError)

Helper
------
- ``load_prompt(name, version, **kwargs)`` — load from ``prompts/{version}/``
"""

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Type, TypeVar

from loguru import logger
from pydantic import BaseModel, ValidationError

# Root of the project (one directory up from providers/)
_REPO_ROOT = Path(__file__).resolve().parent.parent

T = TypeVar("T", bound=BaseModel)


class GenerationError(RuntimeError):
    """Raised when the LLM fails to produce valid output after retries."""


def load_prompt(name: str, version: str = "v3", **kwargs: Any) -> str:
    """
    Load a prompt template and substitute ``{key}`` placeholders.

    Search order:
    1. ``prompts/{version}/{name}.txt``  (v3 default)
    2. ``providers/prompts/{name}.txt``  (legacy v2 fallback)

    Args:
        name:    Template name without extension (e.g. ``screen_documentation``).
        version: Prompt version directory (default ``"v3"``).
        **kwargs: Placeholder substitutions.

    Returns:
        Fully populated prompt string.

    Raises:
        FileNotFoundError: If the template cannot be found in either location.
    """
    candidates = [
        _REPO_ROOT / "prompts" / version / f"{name}.txt",
        _REPO_ROOT / "providers" / "prompts" / f"{name}.txt",
    ]
    for path in candidates:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            for k, v in kwargs.items():
                text = text.replace(f"{{{k}}}", str(v))
            return text

    raise FileNotFoundError(
        f"Prompt template '{name}' not found. Searched:\n" +
        "\n".join(f"  {p}" for p in candidates)
    )


class Provider(ABC):
    """
    Abstract interface for all LLM-assisted generation backends.

    Concrete implementations:
    - BrowserProvider      — copy-paste to claude.ai
    - BrowserBatchProvider — session-level batch (1 paste per session)
    - AnthropicProvider    — Anthropic Messages API
    - OpenAICompatProvider — OpenAI-compatible endpoint (Groq, etc.)
    - OllamaProvider       — Ollama local / cloud via httpx
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if the provider is configured and ready.

        For API providers: API key is present.
        For browser modes: always True.
        """
        ...

    @abstractmethod
    def chat(
        self,
        prompt: str,
        *,
        max_tokens: int = 8000,
        temperature: float = 0.2,
        system: str | None = None,
    ) -> str:
        """
        Send a text prompt and return the model's response as a string.

        Args:
            prompt:      The user message content.
            max_tokens:  Maximum response tokens (default 8000).
            temperature: Sampling temperature (default 0.2).
            system:      Optional system-level instruction.

        Returns:
            Raw response text from the model.
        """
        ...

    def chat_vision(
        self,
        prompt: str,
        images: list[Path],
        **kw,
    ) -> str:
        """
        Send a prompt with images and return the model's response.

        Default implementation: logs a warning and falls back to text-only
        ``chat()``. Override in providers that support vision.

        Args:
            prompt: The user message.
            images: List of PNG file paths to include.
            **kw:   Forwarded to ``chat()`` (max_tokens, temperature, system).

        Returns:
            Raw response text from the model.
        """
        logger.warning(
            f"[{self.name}] chat_vision called but not implemented for this provider. "
            "Falling back to text-only chat (screenshots omitted)."
        )
        return self.chat(prompt, **kw)

    def chat_json(
        self,
        prompt: str,
        schema: Type[T],
        images: list[Path] | None = None,
        **kw,
    ) -> T:
        """
        Call the model and parse the response as a pydantic v2 model.

        Steps:
        1. Call ``chat_vision`` (with images) or ``chat`` (without).
        2. Strip markdown fences (```json … ```).
        3. ``json.loads`` + ``schema.model_validate``.
        4. On ``ValidationError``: retry ONCE, appending the error details
           to the prompt ("Your previous output failed validation: …").
        5. On second failure: raise ``GenerationError``.

        Args:
            prompt: The user prompt.
            schema: A pydantic BaseModel subclass to validate against.
            images: Optional list of PNG paths (forwarded to chat_vision).
            **kw:   max_tokens, temperature, system — forwarded to chat.

        Returns:
            A validated instance of *schema*.

        Raises:
            GenerationError: If the model fails to produce valid JSON twice.
        """
        for attempt in range(2):
            current_prompt = prompt
            if attempt == 1:
                # Append validation error context for the retry
                current_prompt = (
                    f"{prompt}\n\n"
                    f"Your previous output failed JSON validation with this error:\n"
                    f"  {self._last_validation_error}\n"
                    f"Return ONLY the corrected JSON object. No markdown, no explanation."
                )

            try:
                if images:
                    raw = self.chat_vision(current_prompt, images, **kw)
                else:
                    raw = self.chat(current_prompt, **kw)
            except Exception as exc:
                raise GenerationError(
                    f"[{self.name}] chat call failed on attempt {attempt + 1}: {exc}"
                ) from exc

            # Strip fences
            text = _strip_fences(raw)

            try:
                data = json.loads(text)
                return schema.model_validate(data)
            except json.JSONDecodeError as e:
                self._last_validation_error = f"JSON parse error: {e} — raw snippet: {text[:300]}"
                logger.warning(
                    f"[{self.name}] JSON decode failed on attempt {attempt + 1}: {e}"
                )
            except ValidationError as e:
                self._last_validation_error = str(e)
                logger.warning(
                    f"[{self.name}] Pydantic validation failed on attempt {attempt + 1}: {e}"
                )

        raise GenerationError(
            f"[{self.name}] Failed to produce valid JSON matching {schema.__name__} "
            f"after 2 attempts. Last error: {self._last_validation_error}"
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    _last_validation_error: str = ""

    @staticmethod
    def _to_json(data: Any) -> str:
        """Pretty-print a Python object as compact JSON."""
        return json.dumps(data, indent=2, ensure_ascii=False)


# Alias for backward compatibility with any remaining legacy imports
LLMProvider = Provider


def _strip_fences(text: str) -> str:
    """
    Remove markdown code fences from LLM output.

    Handles:
    - ```json\\n…\\n```
    - ```\\n…\\n```
    - Inline leading/trailing whitespace
    """
    text = text.strip()
    # Match ```<optional lang>\\n...\\n```
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Also strip single-backtick wraps
    if text.startswith("`") and text.endswith("`"):
        return text[1:-1].strip()
    return text