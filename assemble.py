from loguru import logger
from config import get_config
from manual_builder import load_manifest, load_style, NumberingTracker, GenericBuilder
from docbot.export.qa import run_qa_check

def assemble_module(session_dir: Path):
    """
    Builds a lightweight module draft for a specific session using
    the manifest-driven GenericBuilder.
    """
    config = get_config()
    client_key = config.current_client
    
    logger.info(f"Building local module draft for '{client_key}' in {session_dir.name}…")
    
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
    
    # Render only the session module
    builder.build_module(session_dir)
    
    import re
    from datetime import datetime
    
    # Extract timestamp from session_dir name or use current time
    m = re.search(r"(\d{8}_\d{6})", session_dir.name)
    timestamp = m.group(1) if m else datetime.now().strftime("%Y%m%d_%H%M%S")
    
    output_filename = f"final_{client_key}_manual_{timestamp}.docx"
    output_docx = session_dir / output_filename
    
    builder.save(output_docx)
    logger.info(f"Module assembly complete! Saved to local session: {output_docx}")
    
    # Copy to workspace root for easy user access (Issue 2)
    import shutil
    try:
        shutil.copy(output_docx, Path(output_filename))
        logger.info(f"Copied final manual to workspace root: {output_filename}")
    except Exception as e:
        logger.warning(f"Could not copy final manual to workspace root: {e}")

    # Run QA PDF check
    run_qa_check(output_docx)
