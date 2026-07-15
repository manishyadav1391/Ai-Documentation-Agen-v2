"""Browser copy-paste provider for the Documentation Automation Bot.

Implements the default workflow: write prompt to disk, open in editor,
wait for writer to paste the LLM response back, then parse.

NOTE: This is the v2 legacy provider. The v3 replacement is
``providers/browser_batch.py`` which batches all screen prompts into a
single paste per session. This module is kept as a runnable shim until
Phase 7 removes the old review_ui dependency chain.
"""

import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from config import get_config
from .base import Provider


class BrowserProvider(Provider):
    """Copy-paste provider that writes a prompt and reads a response from disk."""

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

    def chat(self, prompt: str, *, max_tokens: int = 8000,
             temperature: float = 0.2, system: str | None = None) -> str:
        """Write prompt to disk, open editor, block until writer pastes response."""
        prompt_path = self.work_dir / "llm_prompt.txt"
        response_path = self.work_dir / "llm_response.txt"

        prompt_path.write_text(prompt, encoding="utf-8")

        try:
            subprocess.Popen([self.editor, str(prompt_path)])
        except Exception as exc:
            logger.warning(f"Could not launch editor '{self.editor}': {exc}")
            logger.info(f"Please open the prompt file manually:\n  {prompt_path}")

        logger.info("=" * 60)
        logger.info(f"Prompt written to:\n  {prompt_path}")
        logger.info("Next steps:")
        logger.info("  1. Copy the prompt into your LLM (e.g., claude.ai).")
        logger.info(f"  2. Paste the response into:\n     {response_path}")
        logger.info("=" * 60)
        input("Press Enter when you have saved the response file... ")

        while not response_path.exists():
            logger.warning(f"Response file not found: {response_path}")
            logger.info("Please paste the LLM response into that file and save it.")
            cmd = input("Press Enter to retry, or type 'q' to quit: ").strip().lower()
            if cmd == "q":
                raise KeyboardInterrupt("User aborted waiting for response file.")

        return response_path.read_text(encoding="utf-8").strip()