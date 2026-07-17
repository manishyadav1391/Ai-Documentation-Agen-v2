"""
DocBot v3 — main pipeline entry point.

Run via the launcher UI (``python -m docbot.ui.launcher``) or directly:
    python main.py [--client <key>]
"""

import sys
import json
from pathlib import Path

from loguru import logger


from docbot import paths
from docbot.logging_setup import setup_logging, attach_session_log

# Initialise logging before anything else
setup_logging()

from config import load_config
from docbot.recorder.capture import run_capture_session
from docbot.processing.generator import Generator
from ui.review import open_review_ui
from docbot.processing.annotate import render_annotations
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


def run_pipeline(
    client_key: str = None,
    start_url: str = None,
    module_name: str = None,
    module_number: int = None,
    progress_callback: Callable[[str], None] | None = None,
    cancel_event: Any = None,
):
    """Executes the linear pipeline architecture with multi-screen traversal."""
    def update_progress(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    update_progress("Starting pipeline...")
    if cancel_event and cancel_event.is_set():
        raise KeyboardInterrupt("Pipeline cancelled.")

    config = load_config()
    if client_key:
        config.current_client = client_key
        logger.info(f"[Config Override] Active Client set to: {client_key}")

    provider = get_provider_instance(config)

    # 1. Capture Phase
    update_progress("--- PHASE 1: Capture Session ---")
    session_model = run_capture_session(
        start_url=start_url or "https://google.com",
        client_key=config.current_client,
        module_name=module_name or "",
        module_number=module_number,
        progress_callback=progress_callback
    )

    if cancel_event and cancel_event.is_set():
        raise KeyboardInterrupt("Pipeline cancelled.")

    # Locate the newly created session folder (Issue 2)
    latest_session = getattr(session_model, "_session_dir", None)
    if not latest_session:
        sessions_dir = paths.sessions_dir()
        sessions = sorted(sessions_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        sessions = [s for s in sessions if s.is_dir() and not s.name.startswith(".")]
        if not sessions:
            logger.error("No sessions found to process.")
            return
        latest_session = sessions[-1]

    update_progress(f"Processing session data in: {latest_session.name}")

    # Attach per-session log file
    attach_session_log(latest_session)

    # Count captured screens using the v3 SessionStore (W17)
    from docbot.models import SessionStore
    session = SessionStore.load(latest_session)
    num_screens = len(session.screens)

    if num_screens == 0:
        logger.warning("No screens were captured. Exiting.")
        return

    update_progress(f"--- PHASE 2: Processing {num_screens} Screens ---")

    # 1. Detect regions & compile steps deterministically for all screens
    from docbot.processing.regions import detect_regions
    from docbot.processing.steps import compile_steps

    for screen in session.screens:
        if cancel_event and cancel_event.is_set():
            raise KeyboardInterrupt("Pipeline cancelled.")
        # Detect regions if not already done
        if not screen.regions:
            update_progress(f"Detecting regions for Screen {screen.index}…")
            screen.regions = detect_regions(screen.elements)
        
        # Compile steps from events if not already done
        if not screen.content.steps and screen.events:
            update_progress(f"Compiling event steps for Screen {screen.index}…")
            screen.content.steps = compile_steps(screen.events)

    # Save intermediate state
    SessionStore.save(session, latest_session)

    # 2. AI Pre-generation Pass (Vision-first single-call documentation)
    from docbot.clients.profile import ClientProfile

    profile = ClientProfile.load(config.current_client)
    generator = Generator(provider)

    update_progress("--- Pre-generating Documentation (AI single-call) ---")

    num_success = 0
    for idx, screen in enumerate(session.screens):
        if cancel_event and cancel_event.is_set():
            raise KeyboardInterrupt("Pipeline cancelled.")
        
        # Avoid overwriting already generated/edited screens unless forced
        if not screen.content.screen_name or not screen.content.purpose:
            try:
                update_progress(f"Screen {screen.index} of {num_screens}: pre-generating...")
                generator.generate_screen(session, screen, client_profile=profile.data, progress_callback=progress_callback)
                num_success += 1
            except Exception as e:
                logger.error(f"Failed to pre-generate Screen {screen.index}: {e}")
                err_msg = str(e)
                if "generation failed" in err_msg.lower() or "validationerror" in err_msg.lower() or "json" in err_msg.lower():
                    err_msg = "Could not parse or validate AI response."
                if not screen.content.notes:
                    screen.content.notes = []
                screen.content.notes.append(f"GENERATION FAILED: {err_msg}")
                screen.content.screen_name = screen.content.screen_name or f"Screen {screen.index} (Failed)"
                screen.content.purpose = screen.content.purpose or "AI generation failed."
        else:
            num_success += 1

    if num_success < num_screens:
        update_progress(f"{num_success} of {num_screens} screens generated; open Review UI to retry failed screens.")
    else:
        update_progress(f"All {num_screens} screens successfully generated.")

    if cancel_event and cancel_event.is_set():
        raise KeyboardInterrupt("Pipeline cancelled.")

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
    update_progress("Opening Review UI...")
    if progress_callback:
        progress_callback(f"REQUEST_REVIEW_UI:{latest_session.resolve()}")
    else:
        open_review_ui(latest_session, screen_index=1)

    if cancel_event and cancel_event.is_set():
        raise KeyboardInterrupt("Pipeline cancelled.")

    # 4. Generate Module Introduction before Assembly
    from manual_builder import load_manifest
    _module_name = module_name
    _module_number = module_number
    if not _module_name or _module_number is None:
        try:
            manifest = load_manifest(config.current_client)
            _module_name = _module_name or manifest.system_name or manifest.client_display_name
        except Exception as e:
            logger.warning(f"Could not load manifest for module name: {e}")
            _module_name = _module_name or config.current_client

    # Generate module intro directly via Generator (no shim)
    _session_for_intro = SessionStore.load(latest_session)
    _session_for_intro.module_name = _module_name or _session_for_intro.module_name
    _session_for_intro.module_number = _module_number or _session_for_intro.module_number or 1
    try:
        generator.generate_module_intro(_session_for_intro, client_profile=profile.data)
        SessionStore.save(_session_for_intro, latest_session)
    except Exception as e:
        logger.warning(f"Module intro generation failed: {e}")

    if cancel_event and cancel_event.is_set():
        raise KeyboardInterrupt("Pipeline cancelled.")

    # 5. Assembly Phase
    update_progress("--- PHASE 3: Module Assembly ---")
    assemble_module(latest_session)
    update_progress("Module processing completed successfully!")



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