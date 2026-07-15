"""
DocBot v3 — main pipeline entry point.

Run via the launcher UI (``python -m docbot.ui.launcher``) or directly:
    python main.py [--client <key>]
"""

import sys
import json
from pathlib import Path

from loguru import logger


from docbot.logging_setup import setup_logging, attach_session_log

# Initialise logging before anything else
setup_logging()

from config import load_config
from capture import run_capture_session
from detect_regions import process_screen_regions
from labeler import Labeler
from review_ui import open_review_ui
from annotate import render_annotations
from assemble import assemble_module


def get_provider_instance(config):
    """Instantiates the selected LLM provider based on config.yaml provider setting."""
    provider_name = getattr(config, "provider", "browser").lower()
    logger.info(f"[Provider] Using: {provider_name}")

    if provider_name == "anthropic":
        from providers.anthropic_api import AnthropicProvider
        return AnthropicProvider()
    elif provider_name in ("openai_compat", "openai"):
        from providers.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider()
    elif provider_name == "ollama":
        from providers.ollama import OllamaProvider
        return OllamaProvider()
    else:
        # Default: browser copy-paste mode
        from providers.browser import BrowserProvider
        return BrowserProvider()


def run_pipeline(client_key: str = None, start_url: str = None, module_name: str = None, module_number: int = None):
    """Executes the linear pipeline architecture with multi-screen traversal."""
    logger.info("=" * 55)
    logger.info("     Documentation Automation Bot — Pipeline Start     ")
    logger.info("=" * 55)

    config = load_config("config.yaml")
    if client_key:
        config.current_client = client_key
        logger.info(f"[Config Override] Active Client set to: {client_key}")

    provider = get_provider_instance(config)
    bot_labeler = Labeler(provider)

    # 1. Capture Phase
    logger.info("--- PHASE 1: Capture Session ---")
    run_capture_session(
        start_url=start_url or "https://google.com",
        client_key=config.current_client,
        module_name=module_name or "",
        module_number=module_number
    )


    # Locate the newly created session folder
    sessions_dir = Path(config.sessions_dir)
    sessions = sorted(sessions_dir.glob("session_*"))
    if not sessions:
        logger.error("No sessions found to process.")
        return

    latest_session = sessions[-1]
    logger.info(f"Processing session data in: {latest_session.name}")

    # Attach per-session log file
    attach_session_log(latest_session)

    # Count captured screens using the v3 SessionStore (W17)
    from docbot.models import SessionStore
    session = SessionStore.load(latest_session)
    num_screens = len(session.screens)

    if num_screens == 0:
        logger.warning("No screens were captured. Exiting.")
        return

    logger.info(f"--- PHASE 2: Processing {num_screens} Screens ---")

    # 1. Detect regions & compile steps deterministically for all screens
    from docbot.processing.regions import detect_regions
    from docbot.processing.steps import compile_steps

    for screen in session.screens:
        # Detect regions if not already done
        if not screen.regions:
            logger.info(f"Detecting regions for Screen {screen.index}…")
            screen.regions = detect_regions(screen.elements)
        
        # Compile steps from events if not already done
        if not screen.content.steps and screen.events:
            logger.info(f"Compiling event steps for Screen {screen.index}…")
            screen.content.steps = compile_steps(screen.events)

    # Save intermediate state
    SessionStore.save(session, latest_session)

    # 2. AI Pre-generation Pass (Vision-first single-call documentation)
    from docbot.processing.generator import Generator
    from docbot.clients.profile import ClientProfile

    profile = ClientProfile.load(config.current_client)
    generator = Generator(provider)

    logger.info("--- Pre-generating Documentation (AI single-call) ---")
    for screen in session.screens:
        # Avoid overwriting already generated/edited screens unless forced
        if not screen.content.screen_name or not screen.content.purpose:
            try:
                logger.info(f"Pre-generating Screen {screen.index} documentation…")
                generator.generate_screen(session, screen, client_profile=profile.data)
            except Exception as e:
                logger.warning(f"Failed to pre-generate Screen {screen.index}: {e}")

    # Save generated state
    SessionStore.save(session, latest_session)

    # Write out legacy JSON files to ensure compatibility with manual_builder/
    for screen in session.screens:
        # Write screen_N_meta.json
        meta_path = latest_session / f"screen_{screen.index}_meta.json"
        meta_data = {
            "screen_index": screen.index,
            "url": screen.url,
            "title": screen.title,
            "h1_text": screen.h1_text,
            "breadcrumb": screen.breadcrumb,
            "nav_trail": screen.nav_trail,
            "state_of": screen.state_of,
            "state_label": screen.state_label,
            "screen_name": screen.content.screen_name or screen.title or f"Screen {screen.index}"
        }
        meta_path.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")

        # Write screen_N_elements.json
        el_path = latest_session / f"screen_{screen.index}_elements.json"
        el_data = [el.model_dump() for el in screen.elements]
        el_path.write_text(json.dumps(el_data, indent=2), encoding="utf-8")

        # Write screen_N_regions.json
        r_path = latest_session / f"screen_{screen.index}_regions.json"
        r_data = [r.model_dump() for r in screen.regions if not r.deleted]
        r_path.write_text(json.dumps(r_data, indent=2), encoding="utf-8")

        # Write screen_N_content.json
        content_path = latest_session / f"screen_{screen.index}_content.json"
        legacy_content = {
            "screen_name": screen.content.screen_name,
            "purpose": screen.content.purpose,
            "navigation_instructions": screen.content.navigation_sentence,
            "field_details": [
                {
                    "field_name": f.field_name,
                    "utility": f.utility,
                    "information": f.information,
                    "sample": f.sample
                }
                for f in screen.fields
            ],
            "screen_documentation": {
                "overview": screen.content.purpose,
                "buttons": screen.content.buttons_doc,
                "table_columns": screen.content.table_columns_doc,
                "notes": screen.content.notes
            },
            "steps": [
                {
                    "n": s.n,
                    "text": s.text,
                    "kind": s.kind,
                    "crop_path": s.crop_path
                }
                for s in screen.content.steps
            ],
            "figures": [
                {"index": j + 1, "path": fig.path, "caption_note": fig.caption_note}
                for j, fig in enumerate(screen.figures)
            ]
        }
        content_path.write_text(json.dumps(legacy_content, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Open the visual review UI
    logger.info("Opening Review UI...")
    open_review_ui(latest_session, screen_index=1)

    # 4. Generate Module Introduction before Assembly
    from manual_builder import load_manifest
    _module_name = module_name
    _module_number = module_number
    if not _module_name or _module_number is None:
        try:
            manifest = load_manifest(config.current_client, content_dir=config.content_dir)
            _module_name = _module_name or manifest.system_name or manifest.client_display_name
        except Exception as e:
            logger.warning(f"Could not load manifest for module name: {e}")
            _module_name = _module_name or config.current_client

    bot_labeler.generate_module_intro(latest_session, _module_name, _module_number or 1)

    # 5. Assembly Phase
    logger.info("--- PHASE 3: Module Assembly ---")
    assemble_module(latest_session)
    logger.info("=" * 55)
    logger.info("       Module processing completed successfully!       ")
    logger.info("=" * 55)



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DocBot v3 pipeline")
    parser.add_argument("--client", type=str, default=None, help="Override active client key")
    parser.add_argument("--module-name", type=str, default=None, help="Module name for intro generation")
    parser.add_argument("--module-number", type=int, default=None, help="Module number (overrides manifest)")
    args = parser.parse_args()
    run_pipeline(
        client_key=args.client,
        module_name=args.module_name,
        module_number=args.module_number,
    )