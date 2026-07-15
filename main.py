"""
DocBot v3 — main pipeline entry point.

Run via the launcher UI (``python -m docbot.ui.launcher``) or directly:
    python main.py [--client <key>]
"""

import sys
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


def run_pipeline(client_key: str = None, module_name: str = None, module_number: int = None):
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
    run_capture_session()

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

    # Count captured screens
    screens = list(latest_session.glob("screen_*_elements.json"))
    num_screens = len(screens)

    if num_screens == 0:
        logger.warning("No screens were captured. Exiting.")
        return

    # 2. Processing & Review Phase (Multi-Screen Loop)
    logger.info(f"--- PHASE 2: Processing {num_screens} Screens ---")

    screen_index = 1
    while 1 <= screen_index <= num_screens:
        logger.info(f"--- Screen {screen_index} of {num_screens} ---")

        # Detect Semantic Regions
        process_screen_regions(latest_session, screen_index)

        # Label Regions via LLM Orchestrator
        bot_labeler.label_screen_regions(latest_session, screen_index)

        # Open the Visual Review UI
        logger.info(f"Opening Review UI for Screen {screen_index}...")
        nav_action = open_review_ui(latest_session, screen_index, total_screens=num_screens)

        # Render the final annotated PNG
        render_annotations(latest_session, screen_index)

        # Handle navigation routing
        if nav_action == "prev" and screen_index > 1:
            screen_index -= 1
        elif nav_action == "quit":
            logger.info("Session processing manually aborted.")
            return
        else:
            # Generate prose and field descriptions only when moving forward
            bot_labeler.generate_screen_content(latest_session, screen_index)
            screen_index += 1

    # Generate Module Introduction before Assembly
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

    # 3. Assembly Phase
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