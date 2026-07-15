"""
Manual assembly entry point.

Spec G: Output goes to Final_Manuals/<ClientKey>_<SystemName>_User_Manual_v<version>.docx
"""

from pathlib import Path
import re
import shutil
from datetime import datetime

from loguru import logger
from config import get_config
from manual_builder import load_manifest, load_style, NumberingTracker, GenericBuilder
from docbot.export.qa import run_qa_check, validate_ooxml_structure


def _make_output_filename(manifest, timestamp: str) -> str:
    """
    Spec G: <ClientKey>_<SystemName>_User_Manual_v<version>.docx
    Spaces replaced with underscores.
    """
    client = re.sub(r"[^A-Za-z0-9_]", "_", manifest.client_key.upper())
    system = re.sub(r"\s+", "_", manifest.system_name or manifest.manual_title or "System")
    system = re.sub(r"[^A-Za-z0-9_]", "", system)
    version = re.sub(r"[^A-Za-z0-9._]", "", manifest.document_version or manifest.version or "1.0")
    return f"{client}_{system}_User_Manual_v{version}_{timestamp}.docx"


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

    # Extract timestamp from session_dir name or use current time
    m = re.search(r"(\d{8}_\d{6})", session_dir.name)
    timestamp = m.group(1) if m else datetime.now().strftime("%Y%m%d_%H%M%S")

    output_filename = _make_output_filename(manifest, timestamp)

    # G: Save to Final_Manuals/ subdirectory in workspace root
    final_dir = Path("Final_Manuals")
    final_dir.mkdir(parents=True, exist_ok=True)
    output_docx = final_dir / output_filename

    builder.save(output_docx)
    logger.info(f"Module assembly complete! Saved to: {output_docx}")

    # Also copy to session dir for backwards compatibility
    try:
        shutil.copy(output_docx, session_dir / output_filename)
    except Exception:
        pass

    # H: Run OOXML structural validation + QA check
    validate_ooxml_structure(output_docx)
    run_qa_check(output_docx)

    return output_docx


def assemble_master(session_dirs: list, client_key: str = None):
    """
    Builds the full master client manual from multiple session directories.
    """
    config = get_config()
    if client_key is None:
        client_key = config.current_client

    logger.info(f"Assembling master manual for '{client_key}' from {len(session_dirs)} session(s)…")

    try:
        manifest = load_manifest(client_key, content_dir=config.content_dir)
        style = load_style(client_key, styles_dir=config.styles_dir)
    except Exception as e:
        logger.error(f"Failed to load config for '{client_key}': {e}")
        raise

    numbering_mode = getattr(manifest, "numbering_mode", "module_prefixed")
    numbering = NumberingTracker(style, mode=numbering_mode)
    builder = GenericBuilder(manifest, style, numbering)

    builder.build_full_manual(ordered_session_dirs=[Path(d) for d in session_dirs])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = _make_output_filename(manifest, timestamp)

    final_dir = Path("Final_Manuals")
    final_dir.mkdir(parents=True, exist_ok=True)
    output_docx = final_dir / output_filename

    builder.save(output_docx)
    logger.info(f"Master manual saved to: {output_docx}")

    # H: Run OOXML structural validation + QA
    validate_ooxml_structure(output_docx)
    run_qa_check(output_docx)

    return output_docx