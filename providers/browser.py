"""Browser copy-paste provider for the Documentation Automation Bot.

Implements the default workflow: write prompt to disk, open in editor,
wait for writer to paste the LLM response back, then parse and merge.
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from config import get_config
from .base import Provider, load_prompt


class BrowserProvider(Provider):
    """Copy-paste provider that writes prompts and reads responses from disk."""

    def __init__(self, work_dir: Path = Path(".")) -> None:
        self.work_dir = work_dir
        cfg = get_config()
        self.editor = cfg.providers.browser.editor_command

    @property
    def name(self) -> str:
        return "browser"

    def is_available(self) -> bool:
        """Always available; no API key or network call required."""
        return True

    # --------------------------------------------------------------------- #
    # Public interface
    # --------------------------------------------------------------------- #



    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _write_and_wait(
        self, prompt: str, prompt_path: Path, response_path: Path
    ) -> None:
        """Write *prompt* to disk, open editor, block until writer responds."""
        prompt_path.write_text(prompt, encoding="utf-8")

        # Launch the configured editor (Notepad by default)
        try:
            subprocess.Popen([self.editor, str(prompt_path)])
        except Exception as exc:  # pragma: no cover
            print(
                f"[BrowserProvider] Could not launch editor '{self.editor}': {exc}"
            )
            print(f"Please open the prompt file manually:\n  {prompt_path}")

        print(f"\n{'=' * 60}")
        print(f"Prompt written to:\n  {prompt_path}")
        print("Next steps:")
        print("  1. Copy the prompt into your LLM (e.g., claude.ai).")
        print(f"  2. Paste the response into:\n     {response_path}")
        print(f"{'=' * 60}")
        input("Press Enter when you have saved the response file... ")
        while not response_path.exists():
            print(f"\n[WARNING] Response file not found: {response_path}")
            print("Please paste the LLM response into that file and save it.")
            cmd = input("Press Enter to try again, or type 'q' to quit: ").strip().lower()
            if cmd == 'q':
                raise KeyboardInterrupt("User aborted waiting for response file.")

    @staticmethod
    def _parse_json_response(
        response_path: Path,
        original: List[Dict[str, Any]],
        key: str,
    ) -> List[Dict[str, Any]]:
        """Read *response_path*, extract JSON array, merge *key* into *original*."""
        text = response_path.read_text(encoding="utf-8")

        # Try raw JSON first
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Look for a JSON array inside markdown fences or free text
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if not match:
                raise ValueError(
                    f"Could not find JSON array in {response_path}"
                ) from None
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Found text looking like JSON but could not parse it in "
                    f"{response_path}"
                ) from exc

        if not isinstance(parsed, list):
            raise ValueError(
                f"Expected JSON array in {response_path}, got "
                f"{type(parsed).__name__}"
            )

        if len(parsed) != len(original):
            print(
                f"[BrowserProvider] Warning: response length mismatch "
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

    @staticmethod
    def _parse_text_response(response_path: Path) -> str:
        """Return the raw text of a plain-text response file."""
        return response_path.read_text(encoding="utf-8").strip()