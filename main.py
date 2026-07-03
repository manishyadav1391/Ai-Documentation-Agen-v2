import sys
from pathlib import Path
from config import load_config
from capture import run_capture_session
from detect_regions import process_screen_regions
from labeler import Labeler
from review_ui import open_review_ui
from annotate import render_annotations
from assemble import assemble_module

# Assume get_provider_instance loads the correct provider mapping to llm_ui.py
from providers.browser import BrowserProvider 

def get_provider_instance(config):
    """Instantiates the selected LLM provider based on config.yaml."""
    # In a full integration, this maps to the specific Provider classes.
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
    
    # Count the total number of captured screens
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
        
        # Label Regions via LLM Orchestrator[cite: 1]
        bot_labeler.label_screen_regions(latest_session, screen_index)
        
        # Open the Visual Review UI and capture the user's navigation choice
        print(f"Opening Review UI for Screen {screen_index}...")
        
        # open_review_ui now needs to return a string: 'next', 'prev', or 'quit'
        nav_action = open_review_ui(latest_session, screen_index, total_screens=num_screens)
        
        # Render the final PNG regardless of navigation direction to save state
        render_annotations(latest_session, screen_index)
        
        # Handle the navigation routing
        if nav_action == "prev" and screen_index > 1:
            screen_index -= 1
        elif nav_action == "quit":
            print("Session processing manually aborted.")
            return
        else:
            # Generate the prose and field descriptions only when moving forward
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