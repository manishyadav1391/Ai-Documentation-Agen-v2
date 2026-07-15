import json
from pathlib import Path
from loguru import logger
from config import get_config
from manual_builder import load_manifest, load_style, NumberingTracker, GenericBuilder
from docbot.export.qa import run_qa_check

def assemble_master_manual(ordered_session_dirs: list[Path], output_path: Path, client_key: str = None):
    """
    Combines multiple recorded modules into the final client deliverable,
    managing sequential figure numbers across modules.
    """
    config = get_config()
    if client_key is None:
        client_key = config.current_client

    logger.info("=" * 55)
    logger.info(f"    Generating Master Client Manual: '{client_key}'    ")
    logger.info("=" * 55)
    
    # Load client metadata and styling
    try:
        manifest = load_manifest(client_key, content_dir=config.content_dir)
        style = load_style(client_key, styles_dir=config.styles_dir)
    except Exception as e:
        logger.warning(f"Failed to load config for '{client_key}': {e}. Using defaults.")
        manifest = load_manifest("_default", content_dir=config.content_dir)
        style = load_style("_default", styles_dir=config.styles_dir)

    numbering_mode = getattr(manifest, "numbering_mode", "module_prefixed")
    numbering = NumberingTracker(style, mode=numbering_mode)
    builder = GenericBuilder(manifest, style, numbering)

    
    # Render all parts (front matter + all modules)
    builder.build_full_manual(ordered_session_dirs)
        
    # Ensure output directory exists and save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    builder.save(output_path)
    logger.info(f"Master Manual assembly complete! Saved to {output_path}")

    # Run QA check
    run_qa_check(output_path)

if __name__ == "__main__":
    # Test execution: Grab all sessions in chronological order and combine them
    sessions_dir = Path("sessions")
    if sessions_dir.exists():
        all_sessions = sorted(sessions_dir.glob("session_*"))
        if all_sessions:
            master_output = Path("Final_Manuals/Final_Client_Manual.docx")
            assemble_master_manual(all_sessions, master_output)