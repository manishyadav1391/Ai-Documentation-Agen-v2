"""
Style loader — reads styles/<client>.yaml with validation and color resolution.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger

# Built-in colours for the standard aliases, used when a style.yaml has an
# empty/partial ``colors:`` block or an invalid hex value.
_DEFAULT_COLORS = {
    "primary": "1B365D",
    "secondary": "D97706",
    "tertiary": "C00000",
    "accent": "3B82F6",
    "table_header_bg": "1B365D",
    "table_header_fg": "FFFFFF",
    "table_zebra": "F8FAFC",
    "body_text": "333333",
    "muted": "828282",
}
_HEX_CHARS = set("0123456789abcdefABCDEF")

# Top-level style blocks that renderers treat as mappings.
_DICT_SECTIONS = ("page", "fonts", "colors", "headings", "numbering", "figures", "tables",
                  "bullets", "cover", "revision_history", "toc", "logo", "footer",
                  "annotations", "fields", "layout", "header")


def _is_hex(value: str) -> bool:
    return len(value) == 6 and all(c in _HEX_CHARS for c in value)


@dataclass
class StyleConfig:
    """Parsed and validated style configuration."""
    raw: Dict[str, Any]

    def __post_init__(self):
        # ``colors:`` with nothing under it parses as None; renderers call
        # ``.get`` on these blocks directly, so normalise to empty mappings.
        if not isinstance(self.raw, dict):
            self.raw = {}
        for key in _DICT_SECTIONS:
            if key in self.raw and not isinstance(self.raw[key], dict):
                if self.raw[key] is not None:
                    logger.warning(f"[Style] '{key}' should be a mapping; ignoring {self.raw[key]!r}.")
                self.raw[key] = {}

    # Convenience accessors with defaults
    @property
    def page(self) -> Dict[str, Any]:
        return self.raw.get("page", {})

    @property
    def fonts(self) -> Dict[str, Any]:
        return self.raw.get("fonts", {})

    @property
    def colors(self) -> Dict[str, Any]:
        return self.raw.get("colors", {})

    @property
    def headings(self) -> Dict[str, Any]:
        return self.raw.get("headings", {})

    @property
    def numbering(self) -> Dict[str, Any]:
        return self.raw.get("numbering", {})

    @property
    def figures(self) -> Dict[str, Any]:
        return self.raw.get("figures", {})

    @property
    def tables(self) -> Dict[str, Any]:
        return self.raw.get("tables", {})

    @property
    def bullets(self) -> Dict[str, Any]:
        return self.raw.get("bullets", {})

    @property
    def cover(self) -> Dict[str, Any]:
        return self.raw.get("cover", {})

    @property
    def revision_history(self) -> Dict[str, Any]:
        return self.raw.get("revision_history", {})

    @property
    def toc(self) -> Dict[str, Any]:
        return self.raw.get("toc", {})

    @property
    def logo(self) -> Dict[str, Any]:
        return self.raw.get("logo", {})

    @property
    def footer(self) -> Dict[str, Any]:
        return self.raw.get("footer", {})

    @property
    def annotations(self) -> Dict[str, Any]:
        return self.raw.get("annotations", {})

    # ── Font helpers ──────────────────────────────────────────────────────

    @property
    def body_font(self) -> str:
        return self.fonts.get("body_family", "Calibri")

    @property
    def body_size(self) -> float:
        return self.fonts.get("body_size_pt", 11)

    @property
    def heading_font(self) -> str:
        return self.fonts.get("heading_family", self.body_font)

    # ── Color resolution ──────────────────────────────────────────────────

    def get_color(self, name_or_hex: str) -> str:
        """
        Resolve a color reference.

        If *name_or_hex* matches a key in ``colors`` (e.g., ``'primary'``),
        return the hex value.  Otherwise treat it as a raw hex string.
        """
        if not name_or_hex:
            return "000000"
        name = str(name_or_hex)
        colors = self.colors
        value = str(colors[name]).lstrip("#") if name in colors else name.lstrip("#")
        if _is_hex(value):
            return value
        # Unknown alias or invalid hex (e.g. "ZZZZZZ"): fall back rather than
        # write an invalid w:fill / w:color that Word refuses to open.
        fallback = _DEFAULT_COLORS.get(name, "000000")
        if name in colors or name not in _DEFAULT_COLORS:
            logger.warning(f"[Style] Invalid colour '{value}' for '{name}'; using {fallback}.")
        return fallback

    @property
    def primary_color(self) -> str:
        return self.get_color("primary")

    @property
    def secondary_color(self) -> str:
        return self.get_color("secondary")

    @property
    def tertiary_color(self) -> str:
        return self.get_color("tertiary")

    @property
    def accent_color(self) -> str:
        return self.get_color("accent")

    @property
    def table_header_bg(self) -> str:
        return self.get_color(self.tables.get("header_bg", "table_header_bg"))

    @property
    def table_header_fg(self) -> str:
        return self.get_color(self.tables.get("header_fg", "table_header_fg"))

    # ── Heading helpers ───────────────────────────────────────────────────

    def heading_config(self, level: int) -> Dict[str, Any]:
        """Return size/bold/color config for heading level 1-4."""
        prefix = f"h{level}_"
        h = self.headings
        return {
            "size_pt": h.get(f"{prefix}size_pt", max(24 - (level - 1) * 4, 11)),
            "bold": h.get(f"{prefix}bold", True),
            "color": self.get_color(h.get(f"{prefix}color", "primary")),
            "before_pt": h.get(f"{prefix}before_pt", 18),
            "after_pt": h.get(f"{prefix}after_pt", 8),
        }

    # ── Page helpers ──────────────────────────────────────────────────────

    def margin_cm(self, side: str) -> float:
        """Return margin in cm for side (top, bottom, left, right)."""
        return self.page.get(f"margin_{side}_cm", 2.54)

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Return the raw dict for saving back to YAML."""
        return dict(self.raw)

    def save(self, path: Path):
        """Write style config back to a YAML file."""
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(self.raw, f, sort_keys=False, allow_unicode=True)


def load_style(
    client_key: str,
    styles_dir: Any = None,
) -> StyleConfig:
    """
    Load style configuration. Prioritizes the client profile folder (clients/<client_key>/style.yaml)
    before falling back to legacy styles/<client_key>.yaml or default templates.
    """
    from docbot import paths
    if styles_dir is None:
        styles_dir = paths.styles_dir()

    client_style_path = paths.clients_dir() / client_key / "style.yaml"
    if client_style_path.exists():
        style_path = client_style_path
    else:
        base = Path(styles_dir).resolve()
        client_path = base / f"{client_key}.yaml"
        default_path = base / "_default.yaml"

        if client_path.exists():
            style_path = client_path
        elif default_path.exists():
            style_path = default_path
            print(f"[Style] No style for '{client_key}', using default.")
        else:
            print(f"[Style] No style files found. Using built-in defaults.")
            return StyleConfig(raw={})

    with style_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return StyleConfig(raw=raw)

