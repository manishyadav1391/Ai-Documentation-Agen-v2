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
from manual_builder.build_error import BuildError
from docbot.export.qa import run_qa_check, validate_ooxml_structure


def _make_output_filename(manifest, timestamp: str) -> str:
    """
    Spec G: <ClientKey>_<SystemName>_User_Manual_v<version>.docx
    Spaces replaced with underscores.
    """
    client = re.sub(r"[^A-Za-z0-9_]", "_", str(manifest.client_key).upper())
    system = re.sub(r"\s+", "_", str(manifest.system_name or manifest.manual_title or "System"))
    system = re.sub(r"[^A-Za-z0-9_]", "", system)
    version = re.sub(r"[^A-Za-z0-9._]", "", str(manifest.document_version or manifest.version or "1.0"))
    return f"{client}_{system}_User_Manual_v{version}_{timestamp}.docx"


def assemble_module(session_dir: Path):
    """
    Builds a lightweight module draft for a specific session using
    the manifest-driven GenericBuilder.
    """
    config = get_config()
    client_key = config.current_client

    logger.info(f"Building local module draft for '{client_key}' in {session_dir.name}…")

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

    # Render only the session module
    builder.build_module(session_dir)

    # Extract timestamp from session_dir name or use current time
    m = re.search(r"(\d{8}_\d{6})", session_dir.name)
    timestamp = m.group(1) if m else datetime.now().strftime("%Y%m%d_%H%M%S")

    output_filename = _make_output_filename(manifest, timestamp)

    # G: Save to Final_Manuals/ subdirectory in workspace root
    final_dir = paths.outputs_dir()
    final_dir.mkdir(parents=True, exist_ok=True)
    output_docx = final_dir / output_filename

    output_docx = builder.save(output_docx)  # may differ if the file was locked
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