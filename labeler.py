"""
labeler.py — v3 compatibility shim.

The Labeler class has been replaced by the Generator in
``docbot.processing.generator``.  This shim provides a thin Labeler
adapter that forwards calls to Generator so main.py continues to work
unchanged during the transition period.

Deprecated: Will be removed in Phase 7.
"""

import warnings
import json
from pathlib import Path

from loguru import logger

warnings.warn(
    "labeler.py is a compatibility shim. "
    "Use docbot.processing.generator.Generator directly.",
    DeprecationWarning,
    stacklevel=2,
)


class Labeler:
    """
    Thin compatibility adapter around the v3 Generator.

    Accepts the same Provider argument as before, but internally delegates
    to ``docbot.processing.generator.Generator``.
    """

    def __init__(self, provider) -> None:
        from docbot.processing.generator import Generator
        self.provider = provider
        self._gen = Generator(provider)
        logger.warning(
            "Labeler is deprecated. Switch callers to Generator(provider).generate_screen(…)."
        )

    def switch_provider(self, new_provider) -> None:
        from docbot.processing.generator import Generator
        self.provider = new_provider
        self._gen = Generator(new_provider)
        logger.info("Switched LLM provider for this session.")

    def label_screen_regions(self, session_dir: Path, screen_index: int) -> None:
        """Compat stub — region labelling is now done inside generate_screen()."""
        logger.debug(f"label_screen_regions({screen_index}) is a no-op in v3 (merged into generate_screen).")

    def generate_screen_content(self, session_dir: Path, screen_index: int) -> None:
        """
        Generate full documentation for one screen (v3 path).

        Reads the session.json / legacy flat files, runs the Generator,
        and writes the result back to screen_N_content.json for the old
        export path compatibility.
        """
        from docbot.models import SessionStore
        session = SessionStore.load(session_dir)

        # Find the screen
        screen = next(
            (s for s in session.screens if s.index == screen_index), None
        )
        if screen is None:
            logger.warning(f"Screen {screen_index} not found in session model.")
            return

        try:
            result = self._gen.generate_screen(session, screen)
        except Exception as e:
            logger.error(f"Screen {screen_index} generation failed: {e}")
            return

        # Write legacy content JSON for compatibility with generic_builder
        content_path = session_dir / f"screen_{screen_index}_content.json"
        legacy = {
            "screen_name": result.screen_name,
            "purpose": result.purpose,
            "navigation_instructions": result.navigation_sentence,
            "field_details": [
                {
                    "field_name": f.field_name,
                    "utility": f.utility,
                    "information": f.information,
                    "sample": f.sample,
                }
                for f in result.fields
            ],
            "screen_documentation": {
                "overview": result.purpose,
                "buttons": result.buttons_doc,
                "table_columns": result.table_columns_doc,
                "notes": result.notes,
            },
            "steps": [
                {
                    "n": s.n,
                    "text": s.text,
                    "kind": s.kind,
                    "crop_path": s.crop_path,
                }
                for s in result.steps
            ],
            "figures": [
                {"index": j + 1, "path": fig.path, "caption_note": fig.caption_note}
                for j, fig in enumerate(screen.figures)
            ],
        }

        content_path.write_text(json.dumps(legacy, indent=2, ensure_ascii=False), encoding="utf-8")

        # Persist updated session model
        SessionStore.save(session, session_dir)
        logger.info(f"Screen {screen_index} content saved to {content_path.name}")

    def generate_module_intro(
        self,
        session_dir: Path,
        module_name: str = "",
        module_number: int | None = None,
    ) -> None:
        """Generate module intro and write to module_meta.json (legacy compat)."""
        from docbot.models import SessionStore
        session = SessionStore.load(session_dir)

        if module_name:
            session.module_name = module_name
        if module_number is not None:
            session.module_number = module_number

        try:
            result = self._gen.generate_module_intro(session)
        except Exception as e:
            logger.error(f"Module intro generation failed: {e}")
            return

        # Write legacy module_meta.json
        meta_path = session_dir / "module_meta.json"
        screen_order = [s.index for s in session.screens if s.state_of is None]
        meta = {
            "module_name": session.module_name,
            "module_number": session.module_number or 1,
            "intro": result.intro,
            "features": result.features,
            "screen_order": screen_order,
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        SessionStore.save(session, session_dir)
        logger.info(f"Module intro written to {meta_path.name}")