"""
Manifest loader — reads clients/<client>/manifest.yaml and resolves source paths.
"""

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from loguru import logger

_NUMBERING_MODES = ("module_prefixed", "continuous")


@dataclass
class SectionEntry:
    """One section in the manifest."""
    id: str
    type: str
    heading: str = ""
    source: str = ""
    subsections: List["SectionEntry"] = field(default_factory=list)


@dataclass
class ManifestConfig:
    """Parsed manifest with all metadata and resolved source paths."""
    client_key: str
    client_display_name: str
    system_name: str
    system_acronym: str
    role_name: str
    manual_title: str
    version: str
    sections: List[SectionEntry]
    content_dir: Path  # absolute path to client's content folder

    # Extended fields (Section B spec)
    audience: str = ""
    document_version: str = ""
    confidentiality: str = ""
    prepared_by: str = ""
    reviewed_by: str = ""
    approved_by: str = ""
    cover_enabled: bool = True
    # "module_prefixed" (Figure 10-1, NCB) or "continuous" (Figure 1, 2, … NCD)
    numbering_mode: str = "module_prefixed"

    def get_source_path(self, source: str) -> Path:
        """Resolve a source path relative to the client content dir."""
        return self.content_dir / source

    def require(self, field_name: str, renderer: str = "renderer") -> str:
        """
        Return the named field value, or raise BuildError if it is empty.
        Ensures no bracket placeholders reach a deliverable (Spec B2).
        """
        from manual_builder.build_error import BuildError
        value = getattr(self, field_name, "")
        if not value or str(value).strip().startswith("["):
            raise BuildError(
                f"manifest field '{field_name}' is required by the {renderer} "
                f"but is empty or contains a placeholder. "
                f"Set it in clients/{self.client_key}/manifest.yaml."
            )
        return str(value)


def _text(value: Any, default: str = "") -> str:
    """YAML scalars may arrive as numbers (``version: 1.0``) or null."""
    if value is None:
        return default
    return str(value)


def _parse_section(raw: Dict[str, Any]) -> SectionEntry:
    """Parse a single section entry from the manifest YAML."""
    subsections = [_parse_section(s) for s in (raw.get("subsections") or []) if isinstance(s, dict)]

    return SectionEntry(
        id=_text(raw.get("id")),
        type=_text(raw.get("type")),
        heading=_text(raw.get("heading")),
        source=_text(raw.get("source")),
        subsections=subsections,
    )


def _is_placeholder_manifest(path: Path) -> bool:
    """True for an unfilled template copy (e.g. client_display_name '[Client Name]')."""
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception:
        return False
    name = _text(raw.get("client_display_name")).strip()
    return not name or name.startswith("[")


def load_manifest(
    client_key: str,
    content_dir: Any = None,
) -> ManifestConfig:
    """
    Load and parse clients/<client_key>/manifest.yaml (preferred) or
    content/<client_key>/manifest.yaml.

    Falls back to content/_default/manifest.yaml if the client folder
    doesn't have a manifest.

    Args:
        client_key: The client folder name (e.g. 'ncd').
        content_dir: Root content directory (default: None, resolves to paths.content_dir()).

    Returns:
        A ManifestConfig with resolved paths.

    Raises:
        FileNotFoundError: If neither client nor default manifest exists.
    """
    from docbot import paths
    if content_dir is None:
        content_dir = paths.content_dir()
    # Prefer clients/<key>/manifest.yaml over legacy content/<key>/manifest.yaml
    client_root = paths.clients_dir() / client_key
    client_manifest = client_root / "manifest.yaml"

    base = Path(content_dir).resolve()
    legacy_path = base / client_key / "manifest.yaml"
    default_path = base / "_default" / "manifest.yaml"

    # A clients/<key>/manifest.yaml that is still the unfilled _default template
    # must not hide a real legacy content/<key>/manifest.yaml (NCB).
    if client_manifest.exists() and legacy_path.exists() and _is_placeholder_manifest(client_manifest) \
            and not _is_placeholder_manifest(legacy_path):
        logger.warning(f"{client_manifest} is an unfilled template; using {legacy_path} instead.")
        manifest_path = legacy_path
        resolved_content_dir = base / client_key
    elif client_manifest.exists():
        manifest_path = client_manifest
        # Content lives under clients/<key>/content/ if present, else legacy content/<key>/
        content_sub = client_root / "content"
        resolved_content_dir = content_sub if content_sub.exists() else (base / client_key)
    elif legacy_path.exists():
        manifest_path = legacy_path
        resolved_content_dir = base / client_key
    elif default_path.exists():
        manifest_path = default_path
        resolved_content_dir = base / "_default"
    else:
        raise FileNotFoundError(
            f"No manifest found for client '{client_key}' "
            f"(looked at {client_manifest}, {legacy_path}, and {default_path})"
        )

    from manual_builder.utils import xml_safe
    with manifest_path.open("r", encoding="utf-8") as f:
        raw = xml_safe(yaml.safe_load(f) or {})
    if not isinstance(raw, dict):
        raise ValueError(f"{manifest_path} must contain a YAML mapping")

    sections = [_parse_section(s) for s in (raw.get("sections") or []) if isinstance(s, dict)]

    # A template copied from _default keeps "client_key: _default"; the folder
    # it lives in is the real key.
    key = _text(raw.get("client_key"), client_key) or client_key
    if key == "_default" and client_key != "_default" and manifest_path != default_path:
        key = client_key

    mode = _text(raw.get("numbering_mode"), "module_prefixed").strip().lower() or "module_prefixed"
    if mode not in _NUMBERING_MODES:
        logger.warning(f"Unknown numbering_mode '{mode}' in {manifest_path}; using module_prefixed.")
        mode = "module_prefixed"

    version = _text(raw.get("version"), "1.0") or "1.0"
    cover_enabled = raw.get("cover_enabled", True)
    if isinstance(cover_enabled, str):
        cover_enabled = cover_enabled.strip().lower() not in ("false", "no", "0", "off")

    return ManifestConfig(
        client_key=key,
        client_display_name=_text(raw.get("client_display_name"), client_key),
        system_name=_text(raw.get("system_name")),
        system_acronym=_text(raw.get("system_acronym")),
        role_name=_text(raw.get("role_name")),
        manual_title=_text(raw.get("manual_title"), "User Manual") or "User Manual",
        version=version,
        sections=sections,
        content_dir=resolved_content_dir,
        # Extended spec B fields
        audience=_text(raw.get("audience")),
        document_version=_text(raw.get("document_version"), version) or version,
        confidentiality=_text(raw.get("confidentiality")),
        prepared_by=_text(raw.get("prepared_by")),
        reviewed_by=_text(raw.get("reviewed_by")),
        approved_by=_text(raw.get("approved_by")),
        cover_enabled=bool(cover_enabled),
        numbering_mode=mode,
    )


def get_available_clients(content_dir: Any = None) -> List[str]:
    """Return a list of client keys that have manifest.yaml files."""
    from docbot import paths
    if content_dir is None:
        content_dir = paths.content_dir()
    found = set()

    # Check clients/ directory first
    clients_root = paths.clients_dir()
    if clients_root.exists():
        for child in sorted(clients_root.iterdir()):
            if child.is_dir() and child.name != "_default":
                if (child / "manifest.yaml").exists():
                    found.add(child.name)

    # Also check legacy content/ directory
    base = Path(content_dir).resolve()
    if base.exists():
        for child in sorted(base.iterdir()):
            if child.is_dir() and child.name != "_default":
                if (child / "manifest.yaml").exists():
                    found.add(child.name)

    return sorted(found)
