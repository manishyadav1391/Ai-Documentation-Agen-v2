"""Module section renderer."""

import json
from pathlib import Path
from typing import Any, Dict
from docx.shared import Inches, Pt, RGBColor
from manual_builder.utils import add_styled_heading, add_body_paragraph, hex_to_rgb
from manual_builder.renderers.screen import render_screen


def render_module(doc, session_dir, style, numbering):
    """
    Renders a complete recorded module from session data folder.
    Reads module_meta.json or screen meta to build module headings and summaries.
    """
    module_meta_path = session_dir / "module_meta.json"
    
    module_name = ""
    module_num = 10  # Fallback module number
    intro = ""
    features = []
    screen_order = []

    # 1. Load module metadata if it exists
    if module_meta_path.exists():
        try:
            with module_meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
            module_name = meta.get("module_name", "")
            module_num = meta.get("module_number", module_num)
            intro = meta.get("intro", "")
            features = meta.get("features", [])
            screen_order = meta.get("screen_order", [])
        except Exception as e:
            print(f"[Warning] Failed to read module_meta.json: {e}")

    # 2. Derive defaults from session folder or first screen if missing
    if not module_name:
        first_meta_path = session_dir / "screen_1_meta.json"
        if first_meta_path.exists():
            try:
                with first_meta_path.open("r", encoding="utf-8") as f:
                    first_meta = json.load(f)
                module_name = first_meta.get("screen_name") or first_meta.get("h1_text") or first_meta.get("title", "")
            except Exception:
                pass
        if not module_name:
            module_name = session_dir.name.replace("session_", "Session ").replace("_", " ").title()

    # Track current module numbering
    numbering.set_current_module(module_num)
    numbering.set_section_number(level=1, number=module_num)

    # 3. Add Module Heading (e.g., "10. Case Form")
    heading_str = f"{module_num}."
    add_styled_heading(doc, module_name, level=1, style_config=style, numbering=heading_str)

    # 4. Intro Paragraph
    if intro:
        add_body_paragraph(doc, intro, font_name=style.body_font, size_pt=style.body_size, color_hex=style.get_color("body_text"))

    # 5. Features list
    if features:
        p_feat_hdr = doc.add_paragraph()
        p_feat_hdr.paragraph_format.space_before = Pt(6)
        p_feat_hdr.paragraph_format.space_after = Pt(4)
        r_feat_hdr = p_feat_hdr.add_run(f"The {module_name} module includes features for:")
        r_feat_hdr.font.name = style.body_font
        r_feat_hdr.font.bold = True
        r_feat_hdr.font.size = Pt(style.body_size)
        r_feat_hdr.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

        for feat in features:
            p_feat = doc.add_paragraph(style="List Bullet")
            p_feat.paragraph_format.space_after = Pt(2)
            r_feat = p_feat.add_run(feat)
            r_feat.font.name = style.body_font
            r_feat.font.size = Pt(style.body_size)
            r_feat.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

    # Add space after intro blocks
    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_after = Pt(12)

    # 6. Render Screens sequentially
    if not screen_order:
        # Detect screens from filenames
        screen_files = sorted(session_dir.glob("screen_*_content.json"))
        # Parse screen indexes from names like screen_1_content.json
        for f in screen_files:
            try:
                idx = int(f.name.split("_")[1])
                screen_order.append(idx)
            except Exception:
                pass
        screen_order = sorted(list(set(screen_order)))

    for screen_idx in screen_order:
        content_path = session_dir / f"screen_{screen_idx}_content.json"
        meta_path = session_dir / f"screen_{screen_idx}_meta.json"
        
        if not content_path.exists() or not meta_path.exists():
            continue

        try:
            with content_path.open("r", encoding="utf-8") as f:
                content_data = json.load(f)
            with meta_path.open("r", encoding="utf-8") as f:
                screen_meta = json.load(f)
        except Exception as e:
            print(f"[Warning] Failed to load data for Screen {screen_idx}: {e}")
            continue

        # Skip additional state screens in main rendering loop,
        # they are rendered as sub-figures inside the main screen renderer.
        if screen_meta.get("state_of") is not None:
            continue

        print(f"  Rendering screen: {content_data.get('screen_name', f'Screen {screen_idx}')}...")
        render_screen(
            doc=doc,
            screen_index=screen_idx,
            session_dir=session_dir,
            content_data=content_data,
            screen_meta=screen_meta,
            style=style,
            numbering=numbering
        )
