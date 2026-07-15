"""
Generic manifest-driven document builder implementation.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from docx import Document
from docx.shared import Inches, Pt, Cm

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
        """Configure page setup, document margins, standard styles, and header/footer."""
        # 1. Page Margins (from style)
        for section in self.doc.sections:
            section.top_margin = Cm(self.style.margin_cm("top"))
            section.bottom_margin = Cm(self.style.margin_cm("bottom"))
            section.left_margin = Cm(self.style.margin_cm("left"))
            section.right_margin = Cm(self.style.margin_cm("right"))

            # Set size
            pg_size = self.style.page.get("size", "A4").upper()
            if pg_size == "LETTER":
                section.page_width = Inches(8.5)
                section.page_height = Inches(11.0)
            else:  # A4 default
                section.page_width = Inches(8.27)
                section.page_height = Inches(11.69)

        # 2. Normal text style
        normal = self.doc.styles["Normal"]
        normal.font.name = self.style.body_font
        normal.font.size = Pt(self.style.body_size)
        normal.font.color.rgb = hex_to_rgb(self.style.get_color("body_text"))
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.15

        # 3. Setup document-wide headers/footers
        setup_header_footer(self.doc, self.style, self.manifest)

    def dispatch_section(self, section: SectionEntry, level: int = 1):
        """Route section rendering to the correct sub-renderer recursively without mutating state (W18)."""
        stype = section.type.lower()
        
        # Track section numbering
        # Cover, revision history, TOC and index tables don't count towards numbering
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
            render_table_of_tables(self.doc, section, self.manifest, self.style)
        elif stype == "table_of_figures":
            render_table_of_figures(self.doc, section, self.manifest, self.style)
        elif stype == "prose":
            render_prose(self.doc, section, self.manifest, self.style, heading_text=computed_heading)
        elif stype == "bullet_list":
            render_bullet_list(self.doc, section, self.manifest, self.style, heading_text=computed_heading)
        elif stype == "icon_table":
            render_icon_table(self.doc, section, self.manifest, self.style, heading_text=computed_heading)
        elif stype == "group":
            # For groups, we pass a callback that calls dispatch_section at level 2
            def nested_dispatch(sub_section):
                self.dispatch_section(sub_section, level=level + 1)
            render_group(self.doc, section, self.manifest, self.style, nested_dispatch, heading_text=computed_heading)
        elif stype == "modules":
            # Placed here for pipeline integration
            pass
        else:
            print(f"[Warning] Unknown section type: {stype}")


    def build_front_matter(self):
        """Assembles front matter (cover, revision table, TOC, preambles) from manifest."""
        for section in self.manifest.sections:
            if section.type.lower() != "modules":
                self.dispatch_section(section)

    def build_module(self, session_dir: Path):
        """Render a single module from session data."""
        render_module(self.doc, session_dir, self.style, self.numbering)

    def build_full_manual(self, ordered_session_dirs: list[Path]):
        """Builds cover, revision history, TOC, SOP, and all session modules together."""
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
