"""Screen section renderer."""

from pathlib import Path
from typing import Any, Dict
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PIL import Image as PILImage
from manual_builder.utils import add_styled_heading, add_body_paragraph, hex_to_rgb
from manual_builder.renderers.field_table import render_field_table


def render_screen(doc, screen_index, session_dir, content_data, screen_meta, style, numbering):
    """
    Renders a screen section including headings, purpose, breadcrumbs,
    screenshots, captions, field table, and action bullets.
    """
    module_num = numbering.current_module
    
    # 1. Screen Title / Name
    screen_name = (
        screen_meta.get("screen_name") or
        content_data.get("screen_name") or
        screen_meta.get("h1_text") or
        screen_meta.get("title") or
        f"Screen {screen_index}"
    )

    # Add Heading 2 for the screen (e.g., "10.1 Add Case")
    screen_number_str = numbering.enter_section(level=2)
    add_styled_heading(doc, screen_name, level=2, style_config=style, numbering=screen_number_str)

    # 2. Screen Purpose
    purpose = content_data.get("purpose")
    if not purpose and "screen_documentation" in content_data:
        purpose = content_data["screen_documentation"].get("overview")
    
    if purpose:
        add_body_paragraph(doc, purpose, font_name=style.body_font, size_pt=style.body_size, color_hex=style.get_color("body_text"))

    # 3. Path Breadcrumb
    path = content_data.get("path")
    if not path:
        path = screen_meta.get("breadcrumb")
    
    if path:
        p_path = doc.add_paragraph()
        p_path.paragraph_format.space_before = Pt(2)
        p_path.paragraph_format.space_after = Pt(6)
        r_path_lbl = p_path.add_run("Path: ")
        r_path_lbl.font.name = style.body_font
        r_path_lbl.font.bold = True
        r_path_lbl.font.size = Pt(style.body_size - 1)
        r_path_lbl.font.color.rgb = hex_to_rgb(style.get_color("secondary"))
        
        r_path_val = p_path.add_run(path)
        r_path_val.font.name = style.body_font
        r_path_val.font.size = Pt(style.body_size - 1)
        r_path_val.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

    # 4. Navigation instructions
    nav_instructions = content_data.get("navigation_instructions")
    if not nav_instructions and path:
        nav_instructions = f"Select {screen_name} option from {path.split(' >> ')[0] if ' >> ' in path else 'menu'} as shown in the image below;"
    
    if nav_instructions:
        add_body_paragraph(doc, nav_instructions, font_name=style.body_font, size_pt=style.body_size, color_hex=style.get_color("body_text"))

    # 5. Screen Figures (Screenshots)
    # Phase C introduces multiple states/figures under the screen
    figures_list = content_data.get("figures", [])
    if not figures_list:
        # Default/Fallback to a single annotated screenshot
        img_name = f"screen_{screen_index}_annotated.png"
        img_path = session_dir / img_name
        if not img_path.exists():
            img_path = session_dir / f"screen_{screen_index}.png"
        
        if img_path.exists():
            figures_list = [{"index": 1, "path": img_path.name, "caption_note": ""}]

    figure_prefix = style.numbering.get("figure_prefix", "Figure")
    
    for fig_entry in figures_list:
        fig_rel_path = fig_entry.get("path")
        fig_path = session_dir / fig_rel_path
        if not fig_path.exists():
            continue

        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_before = Pt(4)
        p_img.paragraph_format.space_after = Pt(4)

        # Fit screenshot within max boundaries
        max_w = style.figures.get("max_width_cm", 16.0) / 2.54
        max_h = 4.2  # inches
        try:
            with PILImage.open(fig_path) as img:
                img_w, img_h = img.size
            aspect = img_w / img_h
            if aspect > (max_w / max_h):
                fit_w = max_w
                fit_h = max_w / aspect
            else:
                fit_h = max_h
                fit_w = max_h * aspect
            p_img.add_run().add_picture(str(fig_path), width=Inches(fit_w), height=Inches(fit_h))
        except Exception:
            p_img.add_run().add_picture(str(fig_path), width=Inches(max_w))

        # Figure Caption
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_before = Pt(4)
        p_cap.paragraph_format.space_after = Pt(14)
        
        # Get next figure number
        fig_number_str = numbering.next_figure(module_num)
        
        r_fig = p_cap.add_run(f"{figure_prefix} {fig_number_str} ")
        r_fig.font.name = style.body_font
        r_fig.font.bold = True
        r_fig.font.size = Pt(style.figures.get("caption_size_pt", 10))
        r_fig.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

        caption_note = fig_entry.get("caption_note", "")
        fig_name = f"{screen_name} ({caption_note})" if caption_note else screen_name
        r_cap = p_cap.add_run(fig_name)
        r_cap.font.name = style.body_font
        r_cap.font.size = Pt(style.figures.get("caption_size_pt", 10))
        r_cap.font.italic = style.figures.get("caption_style", "italic") == "italic"
        r_cap.font.color.rgb = hex_to_rgb(style.get_color("muted"))

        # Register caption in tracker
        numbering.register_figure(fig_number_str, fig_name)

    # 6. Field Details Table
    field_details = content_data.get("field_details", [])
    if not field_details and "field_descriptions" in content_data:
        # Fallback to old format (transform to 4-column)
        old_fields = content_data.get("field_descriptions", [])
        field_details = []
        for f in old_fields:
            field_details.append({
                "field_name": f.get("field_name", ""),
                "utility": f.get("description", ""),
                "information": "Data input",
                "sample": "Sample text"
            })

    if field_details:
        tbl_number_str = numbering.next_table(module_num)
        render_field_table(doc, screen_index, field_details, style, tbl_number_str)
        
        # Register in tracker
        caption_text = field_details[0].get("field_name", "").split(" -> ")[0] if field_details else "Field Details"
        numbering.register_table(tbl_number_str, caption_text)

    # 7. Action items bullet list from screen_documentation
    screen_doc = content_data.get("screen_documentation", {}) or {}
    actions = []
    
    # Collect buttons
    for btn in screen_doc.get("buttons", []):
        actions.append(f"Click on the {btn} button to perform the corresponding action.")
    # Collect search criteria
    for sf in screen_doc.get("search_filters", []):
        actions.append(f"Filter records by entering details in the {sf} field.")

    if actions:
        p_act_hdr = doc.add_paragraph()
        p_act_hdr.paragraph_format.space_before = Pt(6)
        p_act_hdr.paragraph_format.space_after = Pt(4)
        r_act_hdr = p_act_hdr.add_run("User Actions / Steps:")
        r_act_hdr.font.name = style.body_font
        r_act_hdr.font.bold = True
        r_act_hdr.font.size = Pt(style.body_size)
        r_act_hdr.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

        for act in actions[:6]: # Limit to top 6 actions
            p_act = doc.add_paragraph(style="List Bullet")
            p_act.paragraph_format.space_after = Pt(2)
            r_act = p_act.add_run(act)
            r_act.font.name = style.body_font
            r_act.font.size = Pt(style.body_size)
            r_act.font.color.rgb = hex_to_rgb(style.get_color("body_text"))
            
    doc.add_page_break()
