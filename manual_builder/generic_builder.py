"""
Generic manifest-driven document builder implementation.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from manual_builder.manifest_loader import ManifestConfig, SectionEntry
from manual_builder.style_loader import StyleConfig
from manual_builder.numbering import NumberingTracker
from manual_builder.utils import setup_header_footer, hex_to_rgb, add_styled_heading

# Import renderers
from manual_builder.renderers.cover import render_cover
from manual_builder.renderers.revision_history import render_revision_history
from manual_builder.renderers.toc import render_toc, render_table_of_tables, render_table_of_figures
from manual_builder.renderers.prose import render_prose
from manual_builder.renderers.bullet_list import render_bullet_list
from manual_builder.renderers.icon_table import render_icon_table
from manual_builder.renderers.group import render_group
from manual_builder.renderers.module import render_module

# Exact A4 dimensions in EMU (English Metric Units) for python-docx
_A4_WIDTH_TWIPS = 11906
_A4_HEIGHT_TWIPS = 16838
_INCH_IN_TWIPS = 1440
_A4_WIDTH_EMU = 7772400   # 11906 twips → EMU
_A4_HEIGHT_EMU = 10977600  # 16838 twips → EMU


class GenericBuilder:
    """
    Builds a professional manual by parsing client-specific static contents
    and styling configurations, and assembling session modules.
    """

    def __init__(
        self,
        manifest: ManifestConfig,
        style: StyleConfig,
        numbering_tracker: NumberingTracker,
    ):
        self.doc = Document()
        self.manifest = manifest
        self.style = style
        self.numbering = numbering_tracker
        self._setup_styles()

    def _setup_styles(self):
        """Configure page setup, document core properties, styles, and header/footer."""

        # ── G: Core document properties (title, author) ───────────────────
        core = self.doc.core_properties
        core.title = f"{self.manifest.system_name} {self.manifest.manual_title}"
        core.author = self.manifest.client_display_name
        core.last_modified_by = self.manifest.client_display_name

        # ── C: Exact A4 page setup + header/footer distances ─────────────
        for section in self.doc.sections:
            # Exact A4 twips (spec C)
            section.page_width = Pt(_A4_WIDTH_TWIPS / 20)    # twips → points → EMU internally
            section.page_height = Pt(_A4_HEIGHT_TWIPS / 20)

            # 1-inch margins (1440 twips = 72pt each)
            _margin = Pt(72)  # 1 inch
            section.top_margin = _margin
            section.bottom_margin = _margin
            section.left_margin = _margin
            section.right_margin = _margin

            # Header/footer distance (708 twips = ~35.4pt)
            section.header_distance = Pt(708 / 20)
            section.footer_distance = Pt(708 / 20)

        # ── C: Named style — Normal ───────────────────────────────────────
        normal = self.doc.styles["Normal"]
        normal.font.name = self.style.body_font          # Calibri
        normal.font.size = Pt(self.style.body_size)     # 12pt
        _body_color = self.style.get_color("body_text")
        normal.font.color.rgb = hex_to_rgb(_body_color)

        pf = normal.paragraph_format
        pf.space_after = Pt(6)
        pf.line_spacing = 1.15
        # Justified alignment
        if self.style.raw.get("layout", {}).get("body_justified", True):
            pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        # Left indent 432 twips = 0.3"
        indent_twips = self.style.raw.get("layout", {}).get("body_left_indent_twips", 0)
        if indent_twips:
            pf.left_indent = Pt(indent_twips / 20)

        # Language tag en-IN on Normal (Spec G)
        _set_lang(normal, "en-IN")

        # ── C: Named styles — Headings 1–3 ───────────────────────────────
        for level in range(1, 4):
            hcfg = self.style.heading_config(level)
            style_name = f"Heading {level}"
            try:
                h_style = self.doc.styles[style_name]
                h_style.font.name = self.style.heading_font
                h_style.font.size = Pt(hcfg["size_pt"])
                h_style.font.bold = hcfg["bold"]
                h_style.font.color.rgb = hex_to_rgb(hcfg["color"])
                h_pf = h_style.paragraph_format
                h_pf.space_before = Pt(hcfg.get("before_pt", 12))
                h_pf.space_after = Pt(hcfg.get("after_pt", 6))
                h_pf.keep_with_next = True
                _set_lang(h_style, "en-IN")
            except Exception:
                pass  # Style unavailable in minimal template

        # ── C: Named style — Caption ──────────────────────────────────────
        try:
            cap_style = self.doc.styles["Caption"]
            cap_style.font.name = self.style.body_font
            cap_style.font.size = Pt(self.style.raw.get("figures", {}).get("caption_size_pt", 9))
            cap_color = self.style.get_color(
                self.style.raw.get("figures", {}).get("caption_color", "muted")
            )
            cap_style.font.color.rgb = hex_to_rgb(cap_color)
            cap_style.font.italic = True
            cap_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap_style.paragraph_format.keep_lines_together = True
            _set_lang(cap_style, "en-IN")
        except Exception:
            pass

        # ── A3: Auto-update fields on open ───────────────────────────────
        _inject_update_fields(self.doc)

        # ── D: Document-wide headers/footers ─────────────────────────────
        setup_header_footer(self.doc, self.style, self.manifest)

    def dispatch_section(self, section: SectionEntry, level: int = 1):
        """Route section rendering to the correct sub-renderer recursively."""
        stype = section.type.lower()

        numbered_types = ["prose", "bullet_list", "icon_table", "group", "modules"]
        is_numbered = stype in numbered_types

        computed_heading = section.heading
        if is_numbered and section.heading:
            section_number = self.numbering.enter_section(level=level)
            computed_heading = f"{section_number} {section.heading}"

        if stype == "cover":
            render_cover(self.doc, section, self.manifest, self.style)
        elif stype == "revision_history":
            render_revision_history(self.doc, section, self.manifest, self.style)
        elif stype == "table_of_contents":
            render_toc(self.doc, section, self.manifest, self.style)
        elif stype == "table_of_tables":
            # D4: skip if no tables were captioned
            if self.numbering.table_count > 0:
                render_table_of_tables(self.doc, section, self.manifest, self.style)
        elif stype == "table_of_figures":
            # D4: skip if no figures were captioned
            if self.numbering.figure_count > 0:
                render_table_of_figures(self.doc, section, self.manifest, self.style)
        elif stype == "prose":
            render_prose(self.doc, section, self.manifest, self.style, heading_text=computed_heading)
        elif stype == "bullet_list":
            render_bullet_list(self.doc, section, self.manifest, self.style, heading_text=computed_heading)
        elif stype == "icon_table":
            render_icon_table(self.doc, section, self.manifest, self.style, heading_text=computed_heading)
        elif stype == "group":
            def nested_dispatch(sub_section):
                self.dispatch_section(sub_section, level=level + 1)
            render_group(self.doc, section, self.manifest, self.style, nested_dispatch, heading_text=computed_heading)
        elif stype == "modules":
            pass
        else:
            print(f"[Warning] Unknown section type: {stype}")

    def build_front_matter(self):
        """Assembles front matter from manifest."""
        for section in self.manifest.sections:
            if section.type.lower() != "modules":
                self.dispatch_section(section)

    def build_module(self, session_dir: Path):
        """Render a single module from session data."""
        render_module(self.doc, session_dir, self.style, self.numbering)

    def build_full_manual(self, ordered_session_dirs: list[Path]):
        """Builds cover, revision history, TOC, and all session modules together."""
        for section in self.manifest.sections:
            if section.type.lower() == "modules":
                for session_dir in ordered_session_dirs:
                    self.build_module(session_dir)
            else:
                self.dispatch_section(section)

    def save(self, output_path: Path):
        """Save the document to disk."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(output_path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_lang(style_obj, lang_code: str = "en-IN") -> None:
    """Set the language tag on a named paragraph style's rPr element."""
    try:
        rpr = style_obj.element.get_or_add_rPr()
        lang = OxmlElement("w:lang")
        lang.set(qn("w:val"), lang_code)
        lang.set(qn("w:eastAsia"), lang_code)
        rpr.append(lang)
    except Exception:
        pass


def _inject_update_fields(doc) -> None:
    """
    A3: Inject <w:updateFields w:val="true"/> into word/settings.xml so Word
    refreshes all fields (TOC, page numbers, SEQ) automatically on first open.
    """
    try:
        settings_el = doc.settings.element
        uf = OxmlElement("w:updateFields")
        uf.set(qn("w:val"), "true")
        settings_el.append(uf)
    except Exception as e:
        print(f"[Warning] Could not inject updateFields: {e}")
