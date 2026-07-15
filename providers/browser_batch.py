"""Browser-batch provider for DocBot v3.

Instead of N separate copy-paste round-trips (one per screen), this
provider batches ALL screen prompts for a session into ONE combined file.
The writer pastes it once into claude.ai, saves the response, and the
provider parses per-prompt responses from the delimiters.

Protocol
--------
Batch prompt file (``sessions/<s>/llm_batch_prompt.txt``):

    ===== DOCBOT BATCH PROMPT =====
    Paste this entire file into your AI (claude.ai).
    The AI must respond using the same delimiters shown below.
    ===============================

    ===== PROMPT screen_1 =====
    <prompt text>
    ===== END PROMPT screen_1 =====

    ===== PROMPT screen_2 =====
    …

Response file (``sessions/<s>/llm_batch_response.txt``):

    ===== RESPONSE screen_1 =====
    <response text>
    ===== END RESPONSE screen_1 =====

    ===== RESPONSE screen_2 =====
    …

Single-screen ``chat()`` (e.g. module intro) writes/reads a
``llm_single_prompt.txt`` / ``llm_single_response.txt`` pair.
"""

import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from config import get_config
from .base import Provider


_BATCH_HEADER = """\
===== DOCBOT BATCH PROMPT =====
Paste this entire file into claude.ai (or your preferred AI).
The AI MUST respond using the EXACT same delimiters shown below.
Each response block must begin with ===== RESPONSE <id> ===== and end with
===== END RESPONSE <id> =====

Return ALL blocks. Do NOT skip any.
===============================

"""

_SINGLE_HEADER = """\
===== DOCBOT SINGLE PROMPT =====
Paste this prompt into your AI, then save the response to:
  {response_path}
================================

"""


class BrowserBatchProvider(Provider):
    """
    Session-level batch provider: collects prompts and flushes as one file.

    Usage::

        provider = BrowserBatchProvider(session_dir)
        provider.queue("screen_1", prompt_1)
        provider.queue("screen_2", prompt_2)
        responses = provider.flush()   # blocks for one copy-paste
        text_1 = responses["screen_1"]
        text_2 = responses["screen_2"]
    """

    def __init__(self, session_dir: Path | None = None) -> None:
        self.session_dir: Path = session_dir or Path(".")
        cfg = get_config()
        self.editor = cfg.providers.browser.editor_command
        self._queue: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "browser_batch"

    def is_available(self) -> bool:
        return True

    # ------------------------------------------------------------------ #
    # Batch API
    # ------------------------------------------------------------------ #

    def queue(self, prompt_id: str, prompt: str) -> None:
        """Add a named prompt to the batch queue."""
        self._queue[prompt_id] = prompt
        logger.debug(f"[BrowserBatch] Queued prompt '{prompt_id}' ({len(prompt)} chars).")

    def flush(self) -> dict[str, str]:
        """
        Write the batch file, open the editor, block for one paste,
        then parse and return per-id responses.

        Returns:
            dict mapping prompt_id → response text.

        Raises:
            KeyboardInterrupt: If the writer types 'q' to abort.
        """
        if not self._queue:
            logger.warning("[BrowserBatch] flush() called with empty queue; nothing to do.")
            return {}

        batch_path = self.session_dir / "llm_batch_prompt.txt"
        response_path = self.session_dir / "llm_batch_response.txt"

        # Build batch file
        lines = [_BATCH_HEADER]
        for pid, prompt in self._queue.items():
            lines.append(f"===== PROMPT {pid} =====\n")
            lines.append(prompt)
            lines.append(f"\n===== END PROMPT {pid} =====\n\n")

        batch_path.write_text("".join(lines), encoding="utf-8")
        self._open_editor(batch_path)

        logger.info("=" * 60)
        logger.info(f"Batch prompt ({len(self._queue)} screens) written to:\n  {batch_path}")
        logger.info("Steps:")
        logger.info("  1. Copy the ENTIRE file into claude.ai.")
        logger.info("  2. Copy the AI response into:")
        logger.info(f"     {response_path}")
        logger.info("  3. Press Enter here when done.")
        logger.info("=" * 60)

        self._wait_for_file(response_path)

        responses = self._parse_batch_response(response_path)
        self._queue.clear()
        return responses

    # ------------------------------------------------------------------ #
    # Single-prompt Provider interface (for module intro etc.)
    # ------------------------------------------------------------------ #

    def chat(self, prompt: str, *, max_tokens: int = 8000,
             temperature: float = 0.2, system: str | None = None) -> str:
        """Write a single prompt and wait for a response file."""
        prompt_path = self.session_dir / "llm_single_prompt.txt"
        response_path = self.session_dir / "llm_single_response.txt"

        header = _SINGLE_HEADER.format(response_path=response_path)
        full_prompt = header + (f"System: {system}\n\n" if system else "") + prompt
        prompt_path.write_text(full_prompt, encoding="utf-8")
        self._open_editor(prompt_path)

        logger.info("=" * 60)
        logger.info(f"Single prompt written to:\n  {prompt_path}")
        logger.info(f"Save the AI response to:\n  {response_path}")
        logger.info("=" * 60)

        self._wait_for_file(response_path)
        return response_path.read_text(encoding="utf-8").strip()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _open_editor(self, path: Path) -> None:
        try:
            subprocess.Popen([self.editor, str(path)])
        except Exception as e:
            logger.warning(f"Could not open editor '{self.editor}': {e}")

    def _wait_for_file(self, path: Path) -> None:
        input("Press Enter when you have saved the response file… ")
        while not path.exists():
            logger.warning(f"Response file not found: {path}")
            cmd = input("Press Enter to retry, or type 'q' to quit: ").strip().lower()
            if cmd == "q":
                raise KeyboardInterrupt("User aborted waiting for response file.")

    @staticmethod
    def _parse_batch_response(response_path: Path) -> dict[str, str]:
        """Parse ``===== RESPONSE <id> =====`` blocks from response file."""
        text = response_path.read_text(encoding="utf-8")
        results: dict[str, str] = {}
        import re
        pattern = re.compile(
            r"=====\s*RESPONSE\s+(\S+)\s*=====\s*\n(.*?)\n=====\s*END RESPONSE\s+\1\s*=====",
            re.DOTALL,
        )
        for match in pattern.finditer(text):
            pid, content = match.group(1), match.group(2).strip()
            results[pid] = content
        if not results:
            logger.warning(
                "[BrowserBatch] No delimited response blocks found in response file. "
                "The AI may not have followed the delimiter format — returning raw text as 'raw'."
            )
            results["raw"] = text.strip()
        return results
