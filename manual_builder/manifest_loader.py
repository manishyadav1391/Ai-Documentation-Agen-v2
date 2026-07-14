"""
Manifest loader — reads content/<client>/manifest.yaml and resolves source paths.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


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

    def get_source_path(self, source: str) -> Path:
        """Resolve a source path relative to the client content dir."""
        return self.content_dir / source


def _parse_section(raw: Dict[str, Any]) -> SectionEntry:
    """Parse a single section entry from the manifest YAML."""
    subsections = []
    if "subsections" in raw:
        subsections = [_parse_section(s) for s in raw["subsections"]]

    return SectionEntry(
        id=raw.get("id", ""),
        type=raw.get("type", ""),
        heading=raw.get("heading", ""),
        source=raw.get("source", ""),
        subsections=subsections,
    )


def load_manifest(
    client_key: str,
    content_dir: str = "content",
) -> ManifestConfig:
    """
    Load and parse content/<client_key>/manifest.yaml.

    Falls back to content/_default/manifest.yaml if the client folder
    doesn't have a manifest.

    Args:
        client_key: The client folder name (e.g. 'ncb').
        content_dir: Root content directory (default: 'content').

    Returns:
        A ManifestConfig with resolved paths.

    Raises:
        FileNotFoundError: If neither client nor default manifest exists.
    """
    base = Path(content_dir).resolve()
    client_path = base / client_key / "manifest.yaml"
    default_path = base / "_default" / "manifest.yaml"

    if client_path.exists():
        manifest_path = client_path
        resolved_content_dir = base / client_key
    elif default_path.exists():
        manifest_path = default_path
        resolved_content_dir = base / "_default"
    else:
        raise FileNotFoundError(
            f"No manifest found for client '{client_key}' "
            f"(looked at {client_path} and {default_path})"
        )

    with manifest_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    sections = [_parse_section(s) for s in raw.get("sections", [])]

    return ManifestConfig(
        client_key=raw.get("client_key", client_key),
        client_display_name=raw.get("client_display_name", client_key),
        system_name=raw.get("system_name", ""),
        system_acronym=raw.get("system_acronym", ""),
        role_name=raw.get("role_name", ""),
        manual_title=raw.get("manual_title", "User Manual"),
        version=raw.get("version", "1.0"),
        sections=sections,
        content_dir=resolved_content_dir,
    )


def get_available_clients(content_dir: str = "content") -> List[str]:
    """Return a list of client keys that have manifest.yaml files."""
    base = Path(content_dir).resolve()
    clients = []
    if base.exists():
        for child in sorted(base.iterdir()):
            if child.is_dir() and child.name != "_default":
                if (child / "manifest.yaml").exists():
                    clients.append(child.name)
    return clients
