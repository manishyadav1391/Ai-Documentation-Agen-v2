import sys
from pathlib import Path
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
    print(f"[Provider] Using: {provider_name}")

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


def run_pipeline():
    """Executes the linear pipeline architecture with multi-screen traversal."""
    print("=======================================================")
    print("      Documentation Automation Bot - Pipeline Start      ")
    print("=======================================================")

    config = load_config("config.yaml")
    provider = get_provider_instance(config)
    bot_labeler = Labeler(provider)

    # 1. Capture Phase
    print("\n--- PHASE 1: Capture Session ---")
    run_capture_session()

    # Locate the newly created session folder
    sessions_dir = Path(config.sessions_dir)
    sessions = sorted(sessions_dir.glob("session_*"))
    if not sessions:
        print("No sessions found to process.")
        return

    latest_session = sessions[-1]
    print(f"\nProcessing session data in: {latest_session.name}")

    # Count captured screens
    screens = list(latest_session.glob("screen_*_elements.json"))
    num_screens = len(screens)

    if num_screens == 0:
        print("No screens were captured. Exiting.")
        return

    # 2. Processing & Review Phase (Multi-Screen Loop)
    print(f"\n--- PHASE 2: Processing {num_screens} Screens ---")

    screen_index = 1
    while 1 <= screen_index <= num_screens:
        print(f"\n--- Screen {screen_index} of {num_screens} ---")

        # Detect Semantic Regions
        process_screen_regions(latest_session, screen_index)

        # Label Regions via LLM Orchestrator
        bot_labeler.label_screen_regions(latest_session, screen_index)

        # Open the Visual Review UI — it now auto-focuses
        print(f"Opening Review UI for Screen {screen_index}...")
        nav_action = open_review_ui(latest_session, screen_index, total_screens=num_screens)

        # Render the final annotated PNG regardless of navigation direction
        render_annotations(latest_session, screen_index)

        # Handle navigation routing
        if nav_action == "prev" and screen_index > 1:
            screen_index -= 1
        elif nav_action == "quit":
            print("Session processing manually aborted.")
            return
        else:
            # Generate prose and field descriptions only when moving forward
            bot_labeler.generate_screen_content(latest_session, screen_index)
            screen_index += 1

    # 3. Assembly Phase
    print("\n--- PHASE 3: Module Assembly ---")
    assemble_module(latest_session)
    print("\n=======================================================")
    print("        Module processing completed successfully!        ")
    print("=======================================================")


if __name__ == "__main__":
    run_pipeline()