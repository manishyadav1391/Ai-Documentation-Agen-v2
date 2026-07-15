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
    
    output_docx = session_dir / "module_draft.docx"
    builder.save(output_docx)
    logger.info(f"Module assembly complete! Saved to {output_docx.name}")

    # Run QA PDF check
    run_qa_check(output_docx)