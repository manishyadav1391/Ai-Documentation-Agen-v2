import sys
from pathlib import Path
from config import load_config
from capture import run_capture_session
from detect_regions import process_screen_regions
from labeler import Labeler
from review_ui import open_review_ui
from annotate import render_annotations
from assemble import assemble_manual

# Assuming a basic factory exists in providers to load the correct class
# For this script, we'll import the base and browser as a default fallback
from providers.base import LLMProvider
from providers.browser import BrowserProvider

def get_provider_instance(config) -> LLMProvider:
    """
    FR-21 & FR-22: Instantiates the selected LLM provider based on config.yaml.
    """
    # In a full implementation, this would dynamically route to Anthropic, OpenAI, etc.
    # We default to the BrowserProvider (claude.ai copy-paste) as specified in the SRS.
    if config.provider == "browser":
        return BrowserProvider()
    
    # Fallback
    print(f"Provider '{config.provider}' selected but module not loaded. Falling back to browser.")
    return BrowserProvider()

def run_pipeline():
    """Executes the linear pipeline architecture defined in the SRS."""
    print("=======================================================")
    print("      Documentation Automation Bot - Pipeline Start      ")
    print("=======================================================")
    
    # 1. Initialization
    config = load_config("config.yaml")
    provider = get_provider_instance(config)
    bot_labeler = Labeler(provider)
    
    # 2. Stage 1: Capture
    # We initiate the Playwright session for the user to navigate and capture screens.
    run_capture_session()
    
    # Find the most recent session folder to process
    sessions_dir = Path(config.sessions_dir)
    sessions = sorted(sessions_dir.glob("session_*"))
    if not sessions:
        print("No sessions found to process.")
        return
        
    latest_session = sessions[-1]
    print(f"\nProcessing session data in: {latest_session.name}")
    
    # Count the number of screens captured by looking at the elements JSON files
    screens = list(latest_session.glob("screen_*_elements.json"))
    num_screens = len(screens)
    
    # Loop through the linear pipeline for each screen
    for screen_index in range(1, num_screens + 1):
        print(f"\n--- Processing Screen {screen_index} of {num_screens} ---")
        
        # Stage 2: Detect
        process_screen_regions(latest_session, screen_index)
        
        # Stage 3: Label
        bot_labeler.label_screen_regions(latest_session, screen_index)
        
        # Stage 4: Review
        print(f"Opening Review UI for Screen {screen_index}...")
        open_review_ui(latest_session, screen_index)
        
        # Stage 5: Annotate
        # Ensures the final render runs just in case the user bypassed the preview button
        render_annotations(latest_session, screen_index)
        
        # Stage 6: Describe
        bot_labeler.generate_screen_content(latest_session, screen_index)
        
    # Stage 7: Assemble
    print("\n--- Final Assembly ---")
    assemble_manual(latest_session)
    print("\n=======================================================")
    print("        Pipeline execution completed successfully!       ")
    print("=======================================================")

if __name__ == "__main__":
    # Execute the full pipeline if run directly
    run_pipeline()