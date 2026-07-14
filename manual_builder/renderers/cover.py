"""Cover renderer for the manual builder."""

import datetime
from pathlib import Path
from typing import Any, Dict
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from manual_builder.utils import set_cell_background, set_cell_margins, set_table_borders, remove_table_borders, hex_to_rgb, add_bottom_border


def render_cover(doc, section_entry, manifest, style):
    """
    Renders a premium client-specific cover page using style configuration and cover.yaml.
    Cover page has no header/footer.
    """
    # Load cover details
    cover_path = manifest.get_source_path(section_entry.source)
    import yaml
    if cover_path.exists():
        with cover_path.open("r", encoding="utf-8") as f:
            cover_data = yaml.safe_load(f) or {}
    else:
        cover_data = {}

    title = cover_data.get("title", manifest.manual_title)
    subtitle = cover_data.get("subtitle", manifest.system_name)
    subtitle_2 = cover_data.get("subtitle_2", "User Manual")
    subtitle_3 = cover_data.get("subtitle_3", "")
    subtitle_4 = cover_data.get("subtitle_4", manifest.client_display_name)
    version_label = cover_data.get("version_label", "Version")
    version_value = cover_data.get("version_value", manifest.version)
    illustration_path_str = cover_data.get("illustration", "")

    # Retrieve cover style parameters
    cover_style = style.cover
    layout = cover_style.get("layout", "centered")
    accent_bar_color = cover_style.get("accent_bar_color", "primary")
    accent_bar_width_cm = cover_style.get("accent_bar_width_cm", 1.0)
    title_size_pt = cover_style.get("title_size_pt", 32)
    title_color_name = cover_style.get("title_color", "primary")
    subtitle_size_pt = cover_style.get("subtitle_size_pt", 18)
    subtitle_color_name = cover_style.get("subtitle_color", "muted")
    version_position = cover_style.get("version_position", "bottom_right")
    illustration_max_width_cm = cover_style.get("illustration_max_width_cm", 10.0)

    # 1. Decorative top/left accent bar (if layout requires it)
    if layout == "left_accent_bar":
        # Create a layout table: 1 row, 2 columns. Column 1 is accent bar, Column 2 is contents.
        # But in python-docx, adding a page-wide sidebar is easiest by formatting margins or using a table.
        # Let's use a nice accent table at the top as a header bar instead, similar to the original corporate builder.
        accent_table = doc.add_table(rows=1, cols=1)
        accent_table.autofit = False
        accent_table.columns[0].width = Inches(6.5)
        accent_cell = accent_table.cell(0, 0)
        set_cell_background(accent_cell, style.get_color(accent_bar_color))
        set_cell_margins(accent_cell, top=200, bottom=200, left=150, right=150)
        accent_p = accent_cell.paragraphs[0]
        accent_p.paragraph_format.space_after = Pt(0)
    elif layout == "full_bleed":
        # Full bleed layout (colored cover page background)
        # Note: True full bleed background in Word requires modifying page background XML,
        # which is extremely complex. Instead we shade a large single-cell table spanning the page.
        # For simplicity, we fallback to a centered layout with colored titles/accents.
        pass

    # Spacing
    for _ in range(3):
        doc.add_paragraph()

    # Client Logo
    logo_path_str = style.logo.get("path", "")
    logo_path = Path(logo_path_str) if logo_path_str else None
    if logo_path and logo_path.exists():
        p_logo = doc.add_paragraph()
        p_logo.alignment = WD_ALIGN_PARAGRAPH.LEFT
        try:
            p_logo.add_run().add_picture(str(logo_path), height=Inches(1.1))
        except Exception:
            pass

    doc.add_paragraph()  # spacer

    # Subtitle 3 & 4 (e.g. "For", "Narcotics Control Bureau" in secondary color)
    if subtitle_3 or subtitle_4:
        p_for = doc.add_paragraph()
        p_for.alignment = WD_ALIGN_PARAGRAPH.CENTER if layout == "centered" else WD_ALIGN_PARAGRAPH.LEFT
        if subtitle_3:
            r_for_lbl = p_for.add_run(subtitle_3 + "\n")
            r_for_lbl.font.name = style.heading_font
            r_for_lbl.font.size = Pt(subtitle_size_pt - 4)
            r_for_lbl.font.italic = True
            r_for_lbl.font.color.rgb = hex_to_rgb(style.get_color("secondary"))
        if subtitle_4:
            r_for_val = p_for.add_run(subtitle_4.upper())
            r_for_val.font.name = style.heading_font
            r_for_val.font.size = Pt(subtitle_size_pt - 2)
            r_for_val.font.bold = True
            r_for_val.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

    # Title
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER if layout == "centered" else WD_ALIGN_PARAGRAPH.LEFT
    r_title = p_title.add_run(title)
    r_title.font.name = style.heading_font
    r_title.font.size = Pt(title_size_pt)
    r_title.font.bold = True
    r_title.font.color.rgb = hex_to_rgb(style.get_color(title_color_name))
    add_bottom_border(p_title, color_hex=style.get_color("secondary"), sz=18)

    # Subtitle (System full name + acronym)
    if subtitle:
        p_sub = doc.add_paragraph()
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER if layout == "centered" else WD_ALIGN_PARAGRAPH.LEFT
        r_sub = p_sub.add_run(subtitle)
        r_sub.font.name = style.heading_font
        r_sub.font.size = Pt(subtitle_size_pt)
        r_sub.font.italic = True
        r_sub.font.color.rgb = hex_to_rgb(style.get_color(subtitle_color_name))

    # Subtitle 2 (User Manual)
    if subtitle_2:
        p_sub2 = doc.add_paragraph()
        p_sub2.alignment = WD_ALIGN_PARAGRAPH.CENTER if layout == "centered" else WD_ALIGN_PARAGRAPH.LEFT
        r_sub2 = p_sub2.add_run(subtitle_2)
        r_sub2.font.name = style.heading_font
        r_sub2.font.size = Pt(subtitle_size_pt - 2)
        r_sub2.font.bold = True
        r_sub2.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

    # Illustration (If selected/configured by user)
    if illustration_path_str:
        ill_path = Path(illustration_path_str)
        if not ill_path.is_absolute() and manifest:
            ill_path = manifest.get_source_path(illustration_path_str)
        if ill_path.exists():
            p_ill = doc.add_paragraph()
            p_ill.alignment = WD_ALIGN_PARAGRAPH.CENTER
            try:
                p_ill.add_run().add_picture(str(ill_path), width=Inches(illustration_max_width_cm / 2.54))
            except Exception:
                pass

    # Push metadata block to bottom
    for _ in range(8):
        doc.add_paragraph()

    # Bottom line
    p_line = doc.add_paragraph()
    p_line.alignment = WD_ALIGN_PARAGRAPH.CENTER if layout == "centered" else WD_ALIGN_PARAGRAPH.LEFT
    add_bottom_border(p_line, color_hex=style.primary_color, sz=12)
    p_line.paragraph_format.space_after = Pt(8)

    # Metadata / Version block
    meta_table = doc.add_table(rows=1, cols=2)
    meta_table.autofit = False
    meta_table.columns[0].width = Inches(3.25)
    meta_table.columns[1].width = Inches(3.25)
    set_table_borders(meta_table, "E2E8F0")

    left_cell = meta_table.cell(0, 0)
    set_cell_background(left_cell, "F8FAFC")
    set_cell_margins(left_cell, top=120, bottom=120, left=150, right=150)
    p_left = left_cell.paragraphs[0]
    p_left.paragraph_format.line_spacing = 1.5

    metadata_items = [
        (f"DOCUMENT {version_label.upper()}", version_value),
        ("PUBLISHED DATE", datetime.datetime.now().strftime("%d-%m-%Y")),
        ("GENERATED BY", "Documentation Automation Bot v2"),
    ]

    for label, val in metadata_items:
        r_lbl = p_left.add_run(f"{label}:\n")
        r_lbl.font.name = style.body_font
        r_lbl.font.size = Pt(8.5)
        r_lbl.font.bold = True
        r_lbl.font.color.rgb = RGBColor(100, 100, 100)
        r_val = p_left.add_run(f"{val}\n\n")
        r_val.font.name = style.body_font
        r_val.font.size = Pt(9.5)
        r_val.font.color.rgb = RGBColor(40, 40, 40)

    right_cell = meta_table.cell(0, 1)
    set_cell_background(right_cell, style.primary_color)
    set_cell_margins(right_cell, top=120, bottom=120, left=150, right=150)
    p_right = right_cell.paragraphs[0]
    p_right.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_right.paragraph_format.space_before = Pt(24)

    r_conf = p_right.add_run("CONFIDENTIAL")
    r_conf.font.name = style.heading_font
    r_conf.font.size = Pt(11)
    r_conf.font.bold = True
    r_conf.font.color.rgb = RGBColor(255, 255, 255)

    doc.add_page_break()
