"""Screen section renderer."""

from pathlib import Path
from typing import Any, Dict
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PIL import Image as PILImage
from manual_builder.utils import add_styled_heading, add_body_paragraph, hex_to_rgb
from manual_builder.renderers.field_table import render_field_table
from docbot.export.word_fields import add_caption


def render_screen(doc, screen_index, session_dir, content_data, screen_meta, style, numbering):
    """
    Renders a screen section including headings, purpose, breadcrumbs,
    screenshots, captions, field list (table or bullets), steps (with crops),
    notes and action bullets.
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

    # NCD rule: if the module has exactly one screen and numbering mode is continuous,
    # render_module may have already set it or handled it. But by default:
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
        # Prioritize annotated screen image if it exists (Issue 6)
        if fig_entry.get("index") == 1 or fig_rel_path.startswith("screen_"):
            annotated_name = f"screen_{screen_index}_annotated.png"
            if (session_dir / annotated_name).exists():
                fig_rel_path = annotated_name

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

        # W4 Figure Caption using native SEQ fields
        caption_note = fig_entry.get("caption_note", "")
        fig_name = f"{screen_name} ({caption_note})" if caption_note else screen_name
        
        fig_number_str = numbering.next_figure(module_num)
        
        add_caption(
            doc,
            prefix=figure_prefix,
            caption_text=fig_name,
            style_cfg=style,
            seq_name="Figure",
            module_num=module_num if numbering.mode == "module_prefixed" else None,
            font_size_pt=style.figures.get("caption_size_pt", 10),
        )

        # Register caption in tracker
        numbering.register_figure(fig_number_str, fig_name)

    # 6. Field Details (Table vs Bullets)
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

    # Read configuration for field presentation style (bullets vs table)
    field_style = style.raw.get("fields", {}).get("style", "table")

    if field_details:
        if field_style == "bullets":
            p_fld_hdr = doc.add_paragraph()
            p_fld_hdr.paragraph_format.space_before = Pt(6)
            p_fld_hdr.paragraph_format.space_after = Pt(4)
            r_fld_hdr = p_fld_hdr.add_run("Field Descriptions:")
            r_fld_hdr.font.name = style.body_font
            r_fld_hdr.font.bold = True
            r_fld_hdr.font.size = Pt(style.body_size)
            r_fld_hdr.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

            for f in field_details:
                raw_name = f.get("field_name", "")
                display_name = raw_name.split(" -> ")[-1] if " -> " in raw_name else raw_name
                utility = f.get("utility", "")
                # Skip empty fields or placeholders
                if not display_name or utility == "Data input":
                    continue
                
                # Format: "{name} — {utility}"
                bullet_fmt = style.raw.get("fields", {}).get("bullet_format", "{name} — {utility}")
                bullet_text = bullet_fmt.format(name=display_name, utility=utility)
                
                p_bullet = doc.add_paragraph(style="List Bullet")
                p_bullet.paragraph_format.space_after = Pt(2)
                r_bullet = p_bullet.add_run(bullet_text)
                r_bullet.font.name = style.body_font
                r_bullet.font.size = Pt(style.body_size)
                r_bullet.font.color.rgb = hex_to_rgb(style.get_color("body_text"))
        else:
            tbl_number_str = numbering.next_table(module_num)
            render_field_table(doc, screen_index, field_details, style, tbl_number_str)
            # Register in tracker
            caption_text = field_details[0].get("field_name", "").split(" -> ")[0] if field_details else "Field Details"
            numbering.register_table(tbl_number_str, caption_text)

    # 7. Action items / steps (Ground truth compiled steps)
    steps_list = content_data.get("steps", [])
    if steps_list:
        p_act_hdr = doc.add_paragraph()
        p_act_hdr.paragraph_format.space_before = Pt(6)
        p_act_hdr.paragraph_format.space_after = Pt(4)
        r_act_hdr = p_act_hdr.add_run("User Actions / Steps:")
        r_act_hdr.font.name = style.body_font
        r_act_hdr.font.bold = True
        r_act_hdr.font.size = Pt(style.body_size)
        r_act_hdr.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

        for step in steps_list:
            text = step.get("text", "")
            crop_path_rel = step.get("crop_path")
            crop_file = session_dir / crop_path_rel if crop_path_rel else None
            
            p_act = doc.add_paragraph(style="List Bullet")
            p_act.paragraph_format.space_after = Pt(2)
            
            r_act = p_act.add_run(text)
            r_act.font.name = style.body_font
            r_act.font.size = Pt(style.body_size)
            r_act.font.color.rgb = hex_to_rgb(style.get_color("body_text"))
            
            if crop_file and crop_file.exists():
                p_act.add_run(" ")
                try:
                    # Render the small crop inline (0.25 inches height)
                    p_act.add_run().add_picture(str(crop_file), height=Inches(0.25))
                except Exception:
                    pass
    else:
        # Fallback to old dynamic button/search filter text builder
        screen_doc = content_data.get("screen_documentation", {}) or {}
        actions = []
        for btn in screen_doc.get("buttons", []):
            actions.append(f"Click on the {btn} button to perform the corresponding action.")
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

            for act in actions[:6]:
                p_act = doc.add_paragraph(style="List Bullet")
                p_act.paragraph_format.space_after = Pt(2)
                r_act = p_act.add_run(act)
                r_act.font.name = style.body_font
                r_act.font.size = Pt(style.body_size)
                r_act.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

    # 8. Notes list
    notes = content_data.get("notes") or (content_data.get("screen_documentation", {}) or {}).get("notes", [])
    if notes:
        for note in notes:
            p_note = doc.add_paragraph()
            p_note.paragraph_format.space_before = Pt(4)
            p_note.paragraph_format.space_after = Pt(4)
            r_note_lbl = p_note.add_run("Note: ")
            r_note_lbl.font.name = style.body_font
            r_note_lbl.font.bold = True
            r_note_lbl.font.size = Pt(style.body_size)
            r_note_lbl.font.color.rgb = hex_to_rgb(style.get_color("tertiary"))
            
            r_note_val = p_note.add_run(note)
            r_note_val.font.name = style.body_font
            r_note_val.font.size = Pt(style.body_size)
            r_note_val.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

    # Configurable page break per screen (continuous flow for NCD, page break for NCB)
    page_break = style.raw.get("layout", {}).get("page_break_per_screen", True)
    if page_break:
        doc.add_page_break()
