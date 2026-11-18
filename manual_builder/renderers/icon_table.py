"""Icon and Button reference table renderer."""

from pathlib import Path
from typing import Any, Dict
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import yaml
from manual_builder.utils import (
    add_styled_heading, set_cell_background, set_cell_margins, set_table_borders, hex_to_rgb,
    load_yaml_file, source_file, scaled_widths, set_table_width,
)


def render_icon_table(doc, section_entry, manifest, style, heading_text: str = None, heading_level: int = 2):
    """
    Renders reference tables for buttons/icons.
    If icons/images are skipped or not found, renders a clean text-based table instead.
    """
    title = heading_text if heading_text is not None else section_entry.heading
    if title:
        add_styled_heading(doc, title, level=heading_level, style_config=style)

    table_path = source_file(section_entry, manifest, "icon_table")
    if table_path is None:
        return

    data = load_yaml_file(table_path)
    if not isinstance(data, dict):
        data = {}

    columns = data.get("columns", ["Name", "Description"])
    rows = data.get("rows", [])
    if not rows:
        return

    num_cols = len(columns)
    table = doc.add_table(rows=1 + len(rows), cols=num_cols)
    table.autofit = False

    # Apply style borders
    border_color = style.tables.get("border_color", "CCCCCC")
    set_table_borders(table, border_color)

    # Set column widths based on column count
    # (scaled down to the section's usable width, e.g. 6.27" on A4)
    if num_cols == 3:
        set_table_width(table, scaled_widths(doc, [1.5, 1.8, 3.2]))  # Button/Icon | Name | Description
    elif num_cols == 2:
        set_table_width(table, scaled_widths(doc, [2.2, 4.3]))
    else:
        set_table_width(table, scaled_widths(doc, [6.5 / num_cols] * num_cols))

    # Render Header
    # Values may be colour aliases ("table_header_bg") — resolve before writing w:fill
    hdr_bg = style.get_color(style.tables.get("header_bg") or style.table_header_bg)
    hdr_fg = style.get_color(style.tables.get("header_fg") or style.table_header_fg)
    hdr_bold = style.tables.get("header_bold", True)

    hdr_cells = table.rows[0].cells
    for idx, col_name in enumerate(columns):
        hdr_cells[idx].text = col_name
        set_cell_background(hdr_cells[idx], hdr_bg)
        set_cell_margins(hdr_cells[idx], top=100, bottom=100, left=120, right=120)
        p = hdr_cells[idx].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        if p.runs:
            r = p.runs[0]
            r.font.name = style.heading_font
            r.font.size = Pt(9.5)
            r.font.bold = hdr_bold
            r.font.color.rgb = hex_to_rgb(hdr_fg)

    # Render Rows
    for r_idx, row_data in enumerate(rows):
        row_cells = table.rows[r_idx + 1].cells
        
        # Determine cell values based on columns structure
        cell_values = []
        if num_cols == 3:
            # First column is placeholder for the button/icon
            cell_values.append("") 
            cell_values.append(str(row_data.get("name", "")))
            cell_values.append(str(row_data.get("description", "")))
        else:
            cell_values.append(str(row_data.get("name", "")))
            cell_values.append(str(row_data.get("description", "")))

        # Fill text
        for idx, val in enumerate(cell_values):
            row_cells[idx].text = val

        # Handle button/icon picture if path exists (otherwise remains blank text)
        if num_cols == 3 and "icon" in row_data:
            icon_path_str = row_data["icon"]
            if icon_path_str:
                icon_path = Path(icon_path_str)
                if not icon_path.is_absolute() and manifest:
                    icon_path = manifest.get_source_path(icon_path_str)
                if icon_path.exists():
                    p_img = row_cells[0].paragraphs[0]
                    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    try:
                        p_img.add_run().add_picture(str(icon_path), height=Inches(0.25))
                    except Exception:
                        # Fallback to name in first col if img fails
                        row_cells[0].text = f"[{row_data.get('name', 'Icon')}]"

        # Apply cell shading and fonts
        zebra_striping = style.tables.get("zebra_striping", True)
        zebra_color = style.get_color(style.tables.get("zebra_color", "table_zebra"))
        fill_color = zebra_color if (zebra_striping and r_idx % 2 == 1) else "FFFFFF"

        for idx, cell in enumerate(row_cells):
            set_cell_background(cell, fill_color)
            set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
            p = cell.paragraphs[0]
            if p.runs:
                r = p.runs[0]
                r.font.name = style.body_font
                r.font.size = Pt(9)
                r.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

    # Spacer after table
    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(8)
