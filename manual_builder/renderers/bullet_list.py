"""Bullet list renderer."""

from typing import Any, Dict
from docx.shared import Inches, Pt
import yaml
from manual_builder.utils import add_styled_heading, hex_to_rgb, load_yaml_file, source_file


def render_bullet_list(doc, section_entry, manifest, style, heading_text: str = None, heading_level: int = 1):
    """
    Renders bullet lists from a YAML file.
    Supports nested bullet points by checking leading spaces in YAML string items.
    """
    title = heading_text if heading_text is not None else section_entry.heading
    if title:
        add_styled_heading(doc, title, level=heading_level, style_config=style)

    list_path = source_file(section_entry, manifest, "bullet_list")
    if list_path is None:
        return

    data = load_yaml_file(list_path)
    items = (data.get("items") if isinstance(data, dict) else data) or []
    if not items:
        return

    for item in items:
        # Determine indentation level based on leading spaces
        original_str = str(item)
        stripped = original_str.lstrip()
        leading_spaces = len(original_str) - len(stripped)

        # Map leading spaces to Word list levels
        if leading_spaces >= 4:
            style_name = "List Bullet 3"
            indent_pt = 36
        elif leading_spaces >= 2:
            style_name = "List Bullet 2"
            indent_pt = 18
        else:
            style_name = "List Bullet"
            indent_pt = 0

        p = doc.add_paragraph(style=style_name)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        
        # Apply body font styling to runs
        r = p.add_run(stripped)
        r.font.name = style.body_font
        r.font.size = Pt(style.body_size)
        r.font.color.rgb = hex_to_rgb(style.get_color("body_text"))
