"""
Screen section renderer.

Changes (Spec E, F):
- E2: keep_with_next on image paragraph, keep_lines_together on caption.
- E3: 6.2" width, scale by height for tall captures, 0.5pt gray native picture border
      (plain inline picture, no wrapper table, so it stays editable in Word).
- E4: Removed empty spacer paragraphs between sections.
- F1: Bullet field format: bold field name, en-dash, sentence-case description.
      Lead-in: "Enter the following details:"
- F2: Steps as numbered list (List Number style), bold UI labels in step text.
- F4: Caption format: "Figure N: Screen Name — caption_note" (colon form).
- F5: Skip/flag LLM-generated placeholder text in fields and purpose.
"""

from pathlib import Path
from typing import Any, Dict, List

from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PIL import Image as PILImage

from manual_builder.utils import add_styled_heading, add_body_paragraph, hex_to_rgb
from manual_builder.renderers.field_table import render_field_table
from docbot.export.word_fields import add_caption

# Spec F5: LLM placeholder strings that must never reach the deliverable
_PLACEHOLDER_STRINGS = {"sample text", "data input", "lorem ipsum", "lorem", "["}


def _is_placeholder(text: str) -> bool:
    """Return True if the text looks like unresolved placeholder content."""
    if not text:
        return True
    lower = text.strip().lower()
    return any(p in lower for p in _PLACEHOLDER_STRINGS)


def _usable_width_inches(doc, fallback: float = 6.2) -> float:
    """Text width of the last section (page width minus left/right margins)."""
    try:
        sec = doc.sections[-1]
        return (sec.page_width - sec.left_margin - sec.right_margin) / 914400
    except Exception:
        return fallback


def _figure_limit_inches(figures_cfg: dict, key: str, default: float) -> float:
    """Read ``<key>_cm`` (style.yaml) with fallback to legacy ``<key>_inches``."""
    if figures_cfg.get(f"{key}_cm") is not None:
        return float(figures_cfg[f"{key}_cm"]) / 2.54
    return float(figures_cfg.get(f"{key}_inches", default))


def _add_picture_outline(inline_shape, color_hex: str, width_pt: float) -> None:
    """Give an inline picture a native Word picture border (Picture Format > Picture Border)."""
    from docx.oxml import OxmlElement

    spPr = inline_shape._inline.graphic.graphicData.pic.spPr
    ln = OxmlElement("a:ln")
    ln.set("w", str(int(width_pt * 12700)))  # 12700 EMU per pt
    fill = OxmlElement("a:solidFill")
    clr = OxmlElement("a:srgbClr")
    clr.set("val", color_hex.upper())
    fill.append(clr)
    ln.append(fill)
    spPr.append(ln)


def _add_image_with_border(doc, img_path: Path, style, alt_text: str = "") -> None:
    """
    E3: Insert screenshot as a plain inline picture in a centred paragraph so it
    stays freely editable in Word (resize, crop, wrap, replace). The optional
    thin border is a native picture outline rather than a wrapper table.
    Also sets keep_with_next on the image paragraph.
    """
    figures_cfg = style.raw.get("figures", {})
    max_w = min(_figure_limit_inches(figures_cfg, "max_width", 6.2), _usable_width_inches(doc))
    max_h = _figure_limit_inches(figures_cfg, "max_height", 7.5)

    # Determine render dimensions preserving aspect ratio
    fit_w, fit_h = max_w, max_w  # fallback
    try:
        with PILImage.open(img_path) as img:
            orig_w, orig_h = img.size
        aspect = orig_w / orig_h
        if orig_h / orig_w > 1.5:
            # Tall full-page capture: scale by height
            fit_h = min(max_h, max_w / aspect)
            fit_w = fit_h * aspect
        else:
            # Normal screenshot: scale by width
            fit_w = min(max_w, max_h * aspect)
            fit_h = fit_w / aspect
        # Safety caps
        if fit_h > max_h:
            fit_h = max_h
            fit_w = fit_h * aspect
        if fit_w > max_w:
            fit_w = max_w
            fit_h = fit_w / aspect
    except Exception:
        fit_w, fit_h = max_w, max_w / 1.5

    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.space_before = Pt(4)
    p_img.paragraph_format.space_after = Pt(4)
    p_img.paragraph_format.keep_with_next = True  # E2
    run = p_img.add_run()
    try:
        shape = run.add_picture(str(img_path), width=Inches(fit_w), height=Inches(fit_h))
    except Exception:
        shape = run.add_picture(str(img_path), width=Inches(fit_w))

    if alt_text:
        shape._inline.docPr.set("descr", alt_text)

    if figures_cfg.get("border_enabled", True):
        border_color = str(figures_cfg.get("border_color", "AAAAAA")).lstrip("#")
        border_pt = float(figures_cfg.get("border_width_pt", figures_cfg.get("border_pt", 0.5)))
        _add_picture_outline(shape, border_color, border_pt)


def render_screen(doc, screen_index, session_dir, content_data, screen_meta, style, numbering):
    """
    Renders a screen section including headings, purpose, breadcrumbs,
    screenshots, captions, field list (bullets), steps, notes.
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

    screen_number_str = numbering.enter_section(level=2)
    add_styled_heading(doc, screen_name, level=2, style_config=style, numbering=screen_number_str)

    layout = (style.raw.get("layout", {}) or {}).get("screen_layout", "writer")
    if layout == "writer":
        _render_writer_body(doc, screen_index, session_dir, content_data, screen_meta,
                            style, numbering, screen_name, module_num)
        if (style.raw.get("layout", {}) or {}).get("page_break_per_screen", False):
            doc.add_page_break()
        return

    # 2. Screen Purpose (F5: skip placeholder)
    purpose = content_data.get("purpose")
    if not purpose and "screen_documentation" in content_data:
        purpose = content_data["screen_documentation"].get("overview")

    if purpose and not _is_placeholder(purpose):
        add_body_paragraph(
            doc, purpose,
            font_name=style.body_font, size_pt=style.body_size,
            color_hex=style.get_color("body_text"),
        )

    # 3. Path Breadcrumb
    path = content_data.get("path") or screen_meta.get("breadcrumb")
    if path:
        p_path = doc.add_paragraph()
        p_path.paragraph_format.space_before = Pt(2)
        p_path.paragraph_format.space_after = Pt(4)
        r_lbl = p_path.add_run("Path: ")
        r_lbl.font.name = style.body_font
        r_lbl.font.bold = True
        r_lbl.font.size = Pt(style.body_size - 1)
        r_lbl.font.color.rgb = hex_to_rgb(style.get_color("secondary"))
        r_val = p_path.add_run(path)
        r_val.font.name = style.body_font
        r_val.font.size = Pt(style.body_size - 1)
        r_val.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

    # 4. Navigation instructions
    nav_instructions = content_data.get("navigation_instructions")
    if not nav_instructions and path:
        nav_instructions = (
            f"Select {screen_name} option from "
            f"{path.split(' >> ')[0] if ' >> ' in path else 'menu'} as shown in the image below."
        )
    if nav_instructions and not _is_placeholder(nav_instructions):
        add_body_paragraph(
            doc, nav_instructions,
            font_name=style.body_font, size_pt=style.body_size,
            color_hex=style.get_color("body_text"),
        )

    # 5. Screen Figures (Screenshots)
    _render_figures(doc, screen_index, session_dir, content_data, style, numbering,
                    screen_name, module_num)

    # 6. Field Details (Bullets — spec F1)
    field_details = content_data.get("field_details", [])
    if not field_details and "field_descriptions" in content_data:
        old_fields = content_data.get("field_descriptions", [])
        field_details = [
            {
                "field_name": f.get("field_name", ""),
                "utility": f.get("description", ""),
                "information": "",
                "sample": "",
            }
            for f in old_fields
        ]

    field_style = style.raw.get("fields", {}).get("style", "table")

    if field_details:
        if field_style == "bullets":
            # F1: Lead-in sentence
            lead_in = style.raw.get("fields", {}).get("lead_in", "Enter the following details:")
            p_hdr = doc.add_paragraph()
            p_hdr.paragraph_format.space_before = Pt(6)
            p_hdr.paragraph_format.space_after = Pt(2)
            r_hdr = p_hdr.add_run(lead_in)
            r_hdr.font.name = style.body_font
            r_hdr.font.bold = True
            r_hdr.font.size = Pt(style.body_size)
            r_hdr.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

            for f in field_details:
                raw_name = f.get("field_name", "")
                display_name = raw_name.split(" -> ")[-1] if " -> " in raw_name else raw_name
                utility = f.get("utility", "")

                # F5: skip placeholder utilities
                if not display_name or _is_placeholder(utility):
                    continue

                p_bullet = doc.add_paragraph(style="List Bullet")
                p_bullet.paragraph_format.space_after = Pt(2)

                # F1: bold field name
                r_name = p_bullet.add_run(display_name)
                r_name.font.name = style.body_font
                r_name.font.bold = True
                r_name.font.size = Pt(style.body_size)
                r_name.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

                # en-dash separator
                r_sep = p_bullet.add_run(" \u2013 ")
                r_sep.font.name = style.body_font
                r_sep.font.size = Pt(style.body_size)
                r_sep.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

                # description (sentence case, ending with period if missing)
                desc = utility.strip()
                if desc and not desc.endswith("."):
                    desc += "."
                r_desc = p_bullet.add_run(desc)
                r_desc.font.name = style.body_font
                r_desc.font.size = Pt(style.body_size)
                r_desc.font.color.rgb = hex_to_rgb(style.get_color("body_text"))
        else:
            tbl_number_str = numbering.next_table(module_num)
            render_field_table(doc, screen_index, field_details, style, tbl_number_str)
            caption_text = (
                field_details[0].get("field_name", "").split(" -> ")[0]
                if field_details else "Field Details"
            )
            numbering.register_table(tbl_number_str, caption_text)

    # 7. Steps (F2: numbered list, bold UI labels)
    steps_list = content_data.get("steps", [])
    if steps_list:
        p_act_hdr = doc.add_paragraph()
        p_act_hdr.paragraph_format.space_before = Pt(6)
        p_act_hdr.paragraph_format.space_after = Pt(2)
        r_act_hdr = p_act_hdr.add_run("Steps:")
        r_act_hdr.font.name = style.body_font
        r_act_hdr.font.bold = True
        r_act_hdr.font.size = Pt(style.body_size)
        r_act_hdr.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

        for step in steps_list:
            text = step.get("text", "")
            crop_path_rel = step.get("crop_path")
            crop_file = session_dir / crop_path_rel if crop_path_rel else None

            # Use bullet list instead of numbered list
            p_act = doc.add_paragraph(style="List Bullet")
            p_act.paragraph_format.space_after = Pt(2)

            # F2: Bold **text between asterisks** or <bold> markers
            _add_step_text_with_bold(p_act, text, style)

            if crop_file and crop_file.exists():
                try:
                    p_act.add_run(" ").add_picture(str(crop_file), height=Inches(0.25))
                except Exception:
                    pass
    else:
        # Fallback button/filter text
        screen_doc = content_data.get("screen_documentation", {}) or {}
        actions = []
        for btn in screen_doc.get("buttons", []):
            actions.append(f"Click the **{btn}** button to perform the corresponding action.")
        for sf in screen_doc.get("search_filters", []):
            actions.append(f"Filter records by entering details in the **{sf}** field.")

        if actions:
            p_act_hdr = doc.add_paragraph()
            p_act_hdr.paragraph_format.space_before = Pt(6)
            p_act_hdr.paragraph_format.space_after = Pt(2)
            r_act_hdr = p_act_hdr.add_run("Steps:")
            r_act_hdr.font.name = style.body_font
            r_act_hdr.font.bold = True
            r_act_hdr.font.size = Pt(style.body_size)
            r_act_hdr.font.color.rgb = hex_to_rgb(style.get_color("secondary"))

            for act in actions[:6]:
                p_act = doc.add_paragraph(style="List Bullet")
                p_act.paragraph_format.space_after = Pt(2)
                _add_step_text_with_bold(p_act, act, style)

    # 8. Notes list (F3)
    notes = content_data.get("notes") or (content_data.get("screen_documentation", {}) or {}).get("notes", [])
    if notes:
        for note in notes:
            if not note or _is_placeholder(note):
                continue
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

    # E1: Configurable page break per screen
    page_break = style.raw.get("layout", {}).get("page_break_per_screen", False)
    if page_break:
        doc.add_page_break()



def _render_figures(doc, screen_index, session_dir, content_data, style, numbering,
                    screen_name, module_num) -> None:
    """Screenshot(s) + numbered captions for one screen (shared by both layouts)."""
    figures_list = content_data.get("figures", [])
    if not figures_list:
        img_name = f"screen_{screen_index}_annotated.png"
        img_path = session_dir / img_name
        if not img_path.exists():
            img_path = session_dir / f"screen_{screen_index}.png"
        if img_path.exists():
            figures_list = [{"index": 1, "path": img_path.name, "caption_note": ""}]

    figure_prefix = style.numbering.get("figure_prefix", "Figure")

    for fig_entry in figures_list:
        fig_rel_path = fig_entry.get("path", "")
        # Prefer annotated image when it exists
        if fig_entry.get("index") == 1 or (fig_rel_path and fig_rel_path.startswith("screen_")):
            annotated_name = f"screen_{screen_index}_annotated.png"
            if (session_dir / annotated_name).exists():
                fig_rel_path = annotated_name

        fig_path = session_dir / fig_rel_path
        if not fig_path.exists():
            continue

        # F4: caption format "Figure N: Screen Name — caption_note"
        caption_note = fig_entry.get("caption_note", "")
        if caption_note:
            fig_caption = f"{screen_name} \u2014 {caption_note}"
        else:
            fig_caption = screen_name

        # E2/E3: image with optional border; keep_with_next set inside helper
        _add_image_with_border(doc, fig_path, style, alt_text=fig_caption)

        fig_number_str = numbering.next_figure(module_num)

        # E2: Caption paragraph gets keep_lines_together
        # add_caption handles paragraph creation — we patch it after
        add_caption(
            doc,
            prefix=figure_prefix,
            caption_text=fig_caption,
            style_cfg=style,
            seq_name="Figure",
            module_num=module_num if numbering.mode == "module_prefixed" else None,
            font_size_pt=style.raw.get("figures", {}).get("caption_size_pt", 9),
        )
        # Apply keep_lines_together to the just-added caption paragraph (E2)
        try:
            doc.paragraphs[-1].paragraph_format.keep_lines_together = True
        except Exception:
            pass

        numbering.register_figure(fig_number_str, fig_caption)



# ---------------------------------------------------------------------------
# Writer layout (house style of the reference manuals)
# ---------------------------------------------------------------------------

_GENERIC_NAV_PREFIXES = ("navigate to ", "select ")


def _clean_note(note: str) -> str:
    text = (note or "").strip()
    while text.lower().startswith("note:"):
        text = text[5:].strip()
    return text


def _clean_label(name: str) -> str:
    """Safety net for on-screen labels: drop placeholder ellipses, de-shout CAPS headers."""
    name = (name or "").strip()
    if name.endswith(("...", "…")):
        name = name.rstrip(".…").strip()
    words = name.split()
    if words and name.isupper() and any(len(w) > 3 for w in words):
        # "ASSIGNED USER TYPE" -> "Assigned User Type"; keep short acronyms (ID, URL, OTP)
        name = " ".join(w if len(w.strip(".")) <= 3 else w.capitalize() for w in words)
    return name


def _sentence(text: str) -> str:
    text = (text or "").strip()
    if text and text[-1] not in ".!?:":
        text += "."
    return text


def _writer_intro(content_data: dict, screen_meta: dict) -> str:
    """Opening paragraph: AI intro, else navigation + purpose (no generic filler)."""
    intro = (content_data.get("intro") or "").strip()
    if intro and not _is_placeholder(intro):
        return intro
    parts = []
    nav = (content_data.get("navigation_instructions") or "").strip()
    if nav and not nav.lower().startswith(_GENERIC_NAV_PREFIXES) and not _is_placeholder(nav):
        parts.append(_sentence(nav))
    purpose = (content_data.get("purpose") or "").strip()
    if purpose and not _is_placeholder(purpose):
        parts.append(_sentence(purpose))
    return " ".join(parts)


def _writer_sections(content_data: dict) -> list:
    """AI sections, or a single 'Fields' section built from legacy field details."""
    sections = content_data.get("sections") or []
    if sections:
        return sections
    items = []
    for f in content_data.get("field_details", []) or []:
        name = f.get("field_name", "")
        name = name.split(" -> ")[-1] if " -> " in name else name
        desc = f.get("utility", "")
        if name and desc and not _is_placeholder(desc):
            items.append({"name": name, "description": desc, "control_type": ""})
    return [{"title": "Fields", "lead_in": "", "items": items}] if items else []


def _run(paragraph, text, style, bold=False, color_key="body_text"):
    r = paragraph.add_run(text)
    r.font.name = style.body_font
    r.font.size = Pt(style.body_size)
    r.font.bold = bold
    r.font.color.rgb = hex_to_rgb(style.get_color(color_key))
    return r


def _render_writer_body(doc, screen_index, session_dir, content_data, screen_meta,
                        style, numbering, screen_name, module_num) -> None:
    fields_cfg = style.raw.get("fields", {}) or {}
    show_type = fields_cfg.get("show_control_type", True)

    # 1. Opening paragraph (navigation + what the page allows)
    intro = _writer_intro(content_data, screen_meta)
    if intro:
        add_body_paragraph(doc, intro, font_name=style.body_font, size_pt=style.body_size,
                           color_hex=style.get_color("body_text"))

    # 2. Screenshot + caption
    _render_figures(doc, screen_index, session_dir, content_data, style, numbering,
                    screen_name, module_num)

    # 3. Grouped element lists: "Name – Description. (Type)"
    for sec in _writer_sections(content_data):
        items = [it for it in sec.get("items", []) if (it.get("name") or "").strip()]
        if not items:
            continue
        title = (sec.get("title") or "").strip()
        # A one-item section named like its item ("Pagination") needs no sub-heading
        if len(items) == 1 and _clean_label(items[0]["name"]).lower() == title.lower():
            title = ""
        if title:
            p_t = doc.add_paragraph()
            p_t.paragraph_format.space_before = Pt(8)
            p_t.paragraph_format.space_after = Pt(2)
            p_t.paragraph_format.keep_with_next = True
            _run(p_t, title, style, bold=True, color_key="secondary")
        lead_in = (sec.get("lead_in") or "").strip()
        if lead_in:
            p_l = doc.add_paragraph()
            p_l.paragraph_format.space_after = Pt(2)
            p_l.paragraph_format.keep_with_next = True
            _run(p_l, lead_in, style)
        for it in items:
            p_b = doc.add_paragraph(style="List Bullet")
            p_b.paragraph_format.space_after = Pt(2)
            _run(p_b, _clean_label(it["name"]), style, bold=True)
            desc = _sentence(it.get("description", ""))
            if desc:
                _run(p_b, " \u2013 " + desc, style)
            ctype = (it.get("control_type") or "").strip()
            if show_type and ctype:
                _run(p_b, f" ({ctype})", style)

    # 4. Procedure — only when the AI found a real task flow
    steps = [st for st in content_data.get("steps", []) or [] if (st.get("text") or "").strip()]
    if steps:
        p_h = doc.add_paragraph()
        p_h.paragraph_format.space_before = Pt(8)
        p_h.paragraph_format.space_after = Pt(2)
        p_h.paragraph_format.keep_with_next = True
        _run(p_h, fields_cfg.get("procedure_lead_in", "Perform the following steps:"), style,
             bold=True, color_key="secondary")
        n = 0
        for st in steps:
            p_s = doc.add_paragraph()
            p_s.paragraph_format.space_after = Pt(2)
            p_s.paragraph_format.left_indent = Inches(0.35)
            if st.get("kind") == "result":
                _add_step_text_with_bold(p_s, _sentence(st["text"]), style)
            else:
                n += 1
                p_s.paragraph_format.first_line_indent = Inches(-0.25)
                _run(p_s, f"{n}.\t", style)
                _add_step_text_with_bold(p_s, _sentence(st["text"]), style)
            crop_rel = st.get("crop_path")
            crop_file = session_dir / crop_rel if crop_rel else None
            if crop_file and crop_file.exists():
                try:
                    p_s.add_run(" ").add_picture(str(crop_file), height=Inches(0.22))
                except Exception:
                    pass

    # 5. Notes
    notes = content_data.get("notes") or (content_data.get("screen_documentation", {}) or {}).get("notes", [])
    for note in notes or []:
        text = _clean_note(note)
        if not text or _is_placeholder(text):
            continue
        p_n = doc.add_paragraph()
        p_n.paragraph_format.space_before = Pt(6)
        p_n.paragraph_format.space_after = Pt(4)
        _run(p_n, "Note: ", style, bold=True, color_key="tertiary")
        _run(p_n, _sentence(text), style)

def _add_step_text_with_bold(paragraph, text: str, style) -> None:
    """
    F2: Render step text, bolding any token wrapped in **…** (markdown-like bold).
    Adds runs with alternating bold/normal formatting.
    """
    import re
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            r = paragraph.add_run(part[2:-2])
            r.bold = True
        else:
            r = paragraph.add_run(part)
            r.bold = False
        r.font.name = style.body_font
        r.font.size = Pt(style.body_size)
        r.font.color.rgb = hex_to_rgb(style.get_color("body_text"))
