"""
DocBot v3 — Client profile loader (Phase 6).

Loads the four per-client YAML files from ``clients/<key>/`` with
automatic fallback to ``clients/_default/`` for any missing file.

Profile structure
-----------------
``ClientProfile.data`` contains four merged dicts:

  "manifest" : client_key, client_display_name, system_name, version, sections…
  "style"    : page, fonts, colors, headings, numbering, figures, tables,
               bullets, cover, footer, annotations…
  "voice"    : app_name, tone_rules, examples, navigation_template, notes_block…
  "glossary" : term → definition mapping

Usage
-----
::

    profile = ClientProfile.load("ncd")
    app_name = profile.voice.get("app_name", "App")
    style = profile.style
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from docbot import paths
_DEFAULT_KEY = "_default"


class ClientProfile:
    """
    Loaded and merged client profile data.

    Attributes:
        key:      Client key string (e.g. "ncd", "ncb").
        manifest: Manifest YAML contents.
        style:    Style YAML contents.
        voice:    Voice YAML contents.
        glossary: Glossary YAML contents (term → definition).
        data:     Combined dict ``{manifest, style, voice, glossary}``.
    """

    def __init__(
        self,
        key: str,
        manifest: dict,
        style: dict,
        voice: dict,
        glossary: dict,
    ) -> None:
        self.key = key
        self.manifest = manifest
        self.style = style
        self.voice = voice
        self.glossary = glossary
        self.data = {
            "manifest": manifest,
            "style": style,
            "voice": voice,
            "glossary": glossary,
        }

    @classmethod
    def load(cls, key: str, clients_dir: Path | str | None = None) -> "ClientProfile":
        """
        Load a client profile, falling back to ``_default`` for any missing file.

        Args:
            key:         Client key (folder name under ``clients/``).
            clients_dir: Override the default ``clients/`` directory.

        Returns:
            ``ClientProfile`` instance.
        """
        base = Path(clients_dir) if clients_dir else paths.clients_dir()
        client_dir = base / key
        default_dir = base / _DEFAULT_KEY

        manifest = _load_yaml(client_dir / "manifest.yaml", default_dir / "manifest.yaml")
        style = _load_yaml(client_dir / "style.yaml", default_dir / "style.yaml")
        voice = _load_yaml(client_dir / "voice.yaml", default_dir / "voice.yaml")
        glossary = _load_yaml(client_dir / "glossary.yaml", default_dir / "glossary.yaml")

        # Also try legacy content/<key>/ location for manifest
        if not manifest and (base.parent / "content" / key / "manifest.yaml").exists():
            legacy_manifest = _load_yaml(
                base.parent / "content" / key / "manifest.yaml", {}
            )
            manifest = legacy_manifest
            logger.debug(f"[ClientProfile] Loaded manifest from legacy content/{key}/")

        # Normalise glossary (YAML list of dicts OR a flat mapping)
        if isinstance(glossary, list):
            glossary = {
                entry.get("term", ""): entry.get("definition", "")
                for entry in glossary
                if isinstance(entry, dict)
            }
        glossary = glossary or {}

        logger.info(f"[ClientProfile] Loaded profile for '{key}'.")
        return cls(key=key, manifest=manifest, style=style, voice=voice, glossary=glossary)

    # ------------------------------------------------------------------ #
    # Convenience accessors
    # ------------------------------------------------------------------ #

    @property
    def client_display_name(self) -> str:
        return self.manifest.get("client_display_name", "[Client Name]")

    @property
    def system_name(self) -> str:
        return self.manifest.get("system_name", self.manifest.get("client_display_name", ""))

    @property
    def app_name(self) -> str:
        return self.voice.get("app_name", self.system_name or "Enterprise Application")

    @property
    def numbering_mode(self) -> str:
        """Return ``"continuous"`` or ``"module_prefixed"``."""
        return self.manifest.get("numbering_mode", "module_prefixed")

    @property
    def field_style(self) -> str:
        """Return ``"table"`` or ``"bullets"``."""
        return self.style.get("fields", {}).get("style", "table")

    @property
    def navigation_template(self) -> str:
        return self.voice.get("navigation_template", "Navigate to {screen_name}.")

    @property
    def notes_block(self) -> str:
        return self.voice.get("notes_block", "")

    def get_color(self, key: str) -> str:
        """Resolve a color alias from the style (e.g. 'primary' → '1B365D')."""
        colors = self.style.get("colors", {})
        val = colors.get(key, "333333")
        # May be an alias to another color
        resolved = colors.get(val, val)
        return resolved.lstrip("#")

    def annotation_mode(self) -> str:
        return self.style.get("annotations", {}).get("mode", "callouts")


def _load_yaml(primary: Path | dict, fallback: Path | dict | None = None) -> dict:
    """Load YAML from *primary*, falling back to *fallback* if missing/invalid."""
    if isinstance(primary, dict):
        return primary
    if isinstance(primary, Path) and primary.exists():
        try:
            result = yaml.safe_load(primary.read_text(encoding="utf-8")) or {}
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.warning(f"Could not parse YAML {primary}: {e}")

    if fallback is None:
        return {}
    if isinstance(fallback, dict):
        return fallback
    if isinstance(fallback, Path) and fallback.exists():
        try:
            result = yaml.safe_load(fallback.read_text(encoding="utf-8")) or {}
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.warning(f"Could not parse fallback YAML {fallback}: {e}")
    return {}
