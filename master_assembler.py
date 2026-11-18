import json
from pathlib import Path
from loguru import logger
from config import get_config
from manual_builder import load_manifest, load_style, NumberingTracker, GenericBuilder
from manual_builder.build_error import BuildError
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
    
    from docbot import paths
    # Load client metadata and styling
    # Missing files already fall back to _default inside the loaders; anything
    # raised here is a real configuration error (bad YAML etc.) — surface it
    # instead of building a _default manual that fails later for another reason.
    try:
        manifest = load_manifest(client_key)
        style = load_style(client_key)
    except Exception as e:
        logger.error(f"Failed to load manifest/style for client '{client_key}': {e}")
        raise BuildError(f"Could not load configuration for client '{client_key}': {e}") from e

    numbering_mode = getattr(manifest, "numbering_mode", "module_prefixed")
    numbering = NumberingTracker(style, mode=numbering_mode)
    builder = GenericBuilder(manifest, style, numbering)

    
    # Render all parts (front matter + all modules)
    builder.build_full_manual(ordered_session_dirs)
        
    # Ensure output directory exists and save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = builder.save(output_path)  # may differ if the file was locked
    logger.info(f"Master Manual assembly complete! Saved to {output_path}")

    # Run QA check
    run_qa_check(output_path)
    return output_path

if __name__ == "__main__":
    from docbot import paths
    from datetime import datetime
    config = get_config()
    client_key = config.current_client
    # Test execution: Grab all sessions in chronological order and combine them
    sessions_dir = paths.sessions_dir()
    if sessions_dir.exists():
        all_sessions = sorted(sessions_dir.glob("session_*"))
        if all_sessions:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            master_output = paths.outputs_dir() / f"{client_key}_{timestamp}.docx"
            assemble_master_manual(all_sessions, master_output)