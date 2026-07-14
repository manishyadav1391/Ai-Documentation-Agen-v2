"""Revision history renderer."""

from typing import Any, Dict
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from manual_builder.utils import set_cell_background, set_cell_margins, set_table_borders, hex_to_rgb, add_styled_heading


def render_revision_history(doc, section_entry, manifest, style):
    """
    Renders the 6-column revision history table as defined in revision_history.yaml.
    Columns: Revision No | Revision Date | Revision By | Approved Date | Approved By | Description
    """
    # Add section heading
    add_styled_heading(doc, section_entry.heading or "Revision History", level=1, style_config=style)

    # Load data
    history_path = manifest.get_source_path(section_entry.source)
    import yaml
    if history_path.exists():
        with history_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    entries = data.get("entries", [])
    if not entries:
        # Placeholder entry if empty
        entries = [{
            "revision": "1.0",
            "date": "",
            "by": "",
            "approved_date": "",
            "approved_by": "",
            "description": "Initial version"
        }]

    # Create table (rows = header + data rows, cols = 6)
    table = doc.add_table(rows=1 + len(entries), cols=6)
    table.autofit = False
    
    # Configure borders
    border_color = style.revision_history.get("border_color", "CCCCCC")
    set_table_borders(table, border_color)

    # Set column widths
    table.columns[0].width = Inches(0.8)  # Rev No
    table.columns[1].width = Inches(1.0)  # Date
    table.columns[2].width = Inches(1.1)  # By
    table.columns[3].width = Inches(1.1)  # Approved Date
    table.columns[4].width = Inches(1.1)  # Approved By
    table.columns[5].width = Inches(1.4)  # Description

    # Headers
    headers = [
        "Revision No", "Revision Date", "Revision By",
        "Approved Date", "Approved By", "Description"
    ]
    
    hdr_bg = style.revision_history.get("header_bg", style.table_header_bg)
    hdr_fg = style.revision_history.get("header_fg", style.table_header_fg)

    hdr_cells = table.rows[0].cells
    for idx, text in enumerate(headers):
        hdr_cells[idx].text = text
        set_cell_background(hdr_cells[idx], hdr_bg)
        set_cell_margins(hdr_cells[idx], top=100, bottom=100, left=120, right=120)
        p = hdr_cells[idx].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        if p.runs:
            r = p.runs[0]
            r.font.name = style.heading_font
            r.font.size = Pt(9.5)
            r.font.bold = True
            r.font.color.rgb = hex_to_rgb(hdr_fg)

    # Fill data rows
    for r_idx, entry in enumerate(entries):
        row_cells = table.rows[r_idx + 1].cells
        
        # Populate each cell
        row_cells[0].text = str(entry.get("revision", ""))
        row_cells[1].text = str(entry.get("date", ""))
        row_cells[2].text = str(entry.get("by", ""))
        row_cells[3].text = str(entry.get("approved_date", ""))
        row_cells[4].text = str(entry.get("approved_by", ""))
        row_cells[5].text = str(entry.get("description", ""))

        # Style cells
        fill_color = "F8FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for idx, cell in enumerate(row_cells):
            set_cell_background(cell, fill_color)
            set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
            p = cell.paragraphs[0]
            if p.runs:
                r = p.runs[0]
                r.font.name = style.body_font
                r.font.size = Pt(9)
                r.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

    # Add space after table
    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(8)
    
    # Page break
    doc.add_page_break()
