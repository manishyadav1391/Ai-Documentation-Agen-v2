"""Module section renderer."""

import json
from pathlib import Path
from typing import Any, Dict
from docx.shared import Inches, Pt, RGBColor
from manual_builder.utils import add_styled_heading, add_body_paragraph, hex_to_rgb, xml_safe
from manual_builder.renderers.screen import render_screen, _clean_note
from docbot.clients.profile import ClientProfile
from docbot.processing.annotate import render_annotations
from loguru import logger


def render_module(doc, session_dir, style, numbering, client_key=None):
    """
    Renders a complete recorded module from session data folder.
    Reads module_meta.json or screen meta to build module headings and summaries.

    *client_key* is the client whose manual is being assembled (its voice
    notes_block and annotation settings are used); defaults to the client
    currently selected in the app.
    """
    module_meta_path = session_dir / "module_meta.json"

    module_name = ""
    module_num = None  # assigned after the front matter if absent/colliding
    intro = ""
    features = []
    screen_order = []
    session_model = None

    # 1. Load module metadata from session.json (v3 primary source of truth)
    session_json_path = session_dir / "session.json"
    if session_json_path.exists():
        from docbot.models import SessionStore, SessionLoadError
        try:
            session_model = SessionStore.load(session_dir)
            module_name = session_model.module_name or ""
            if session_model.module_number is not None:
                module_num = session_model.module_number
            intro = session_model.module_intro or ""
            features = session_model.module_features or []
            if session_model.screens:
                screen_order = [s.index for s in session_model.screens]
        except SessionLoadError:
            # Corrupt session.json: abort rather than silently assembling from
            # stale legacy per-screen files.
            raise
        except Exception as e:
            print(f"[Warning] Failed to read session.json: {e}")

    # Fallback to legacy module_meta.json if we still lack metadata (e.g. legacy tests)
    if not module_name and module_meta_path.exists():
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

    # Session / LLM text enters the document here: strip XML-illegal characters
    module_name, intro, features = xml_safe(module_name), xml_safe(intro), xml_safe(list(features))

    # Folder-derived names come in lower case ("workflow automation")
    if module_name and module_name == module_name.lower():
        module_name = module_name.title()

    # Track current module numbering
    if numbering.mode == "continuous":
        # Increment level 1 section number dynamically
        current_section = numbering.enter_section(level=1)
        try:
            module_num = int(current_section.split(".")[0])
        except ValueError:
            module_num = 1
        numbering.set_current_module(module_num)
    else:
        # Module chapters follow the numbered front matter (and each other):
        # keep an explicit module_number only if it does not collide.
        last = numbering.last_number(level=1)
        try:
            module_num = int(module_num) if module_num is not None else None
        except (TypeError, ValueError):
            module_num = None
        if module_num is None or module_num <= last:
            module_num = last + 1
        numbering.set_current_module(module_num)
        numbering.set_section_number(level=1, number=module_num)

    # 3. Detect screens sequentially to check for single_screen layout
    if not screen_order:
        screen_files = sorted(session_dir.glob("screen_*_content.json"))
        for f in screen_files:
            try:
                idx = int(f.name.split("_")[1])
                screen_order.append(idx)
            except Exception:
                pass
        screen_order = sorted(list(set(screen_order)))

    # (screen_idx, content_dict, meta_dict). session.json is the source of truth so
    # that edits made in the Review window reach the manual; the per-screen JSON
    # files are only used for legacy sessions without session.json.
    screens_to_render = []
    if session_model is not None and session_model.screens:
        from docbot.export.content import screen_content_dict, screen_meta_dict
        for s in session_model.screens:
            if s.state_of is not None:
                continue
            screens_to_render.append((s.index, xml_safe(screen_content_dict(s)), xml_safe(screen_meta_dict(s))))
    else:
        for screen_idx in screen_order:
            content_path = session_dir / f"screen_{screen_idx}_content.json"
            meta_path = session_dir / f"screen_{screen_idx}_meta.json"
            if not content_path.exists() or not meta_path.exists():
                continue
            try:
                screen_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if screen_meta.get("state_of") is not None:
                    continue
                content_data = json.loads(content_path.read_text(encoding="utf-8"))
                screens_to_render.append((screen_idx, xml_safe(content_data), xml_safe(screen_meta)))
            except Exception as e:
                logger.warning(f"Failed to load data for Screen {screen_idx}: {e}")

    # Check for single-screen module layout under continuous mode
    single_screen = (len(screens_to_render) == 1) and (numbering.mode == "continuous")

    # Load client profile for voice rules / notes_block
    profile = None
    try:
        if not client_key:
            from config import get_config
            client_key = get_config().current_client
        profile = ClientProfile.load(client_key)
    except Exception as e:
        logger.warning(f"Could not load client profile '{client_key}': {e}")

    if not single_screen:
        # Add Module Heading (e.g., "10. Case Form")
        heading_str = f"{module_num}."
        add_styled_heading(doc, module_name, level=1, style_config=style, numbering=heading_str)

        # 4. Intro Paragraph
        if intro:
            add_body_paragraph(doc, intro, font_name=style.body_font, size_pt=style.body_size, color_hex=style.get_color("body_text"))

        # Render voice notes_block if any (strip a leading "Note:" — the label is added below)
        notes_block = _clean_note(xml_safe(profile.notes_block or "")) if profile else ""
        if notes_block:
            p_note = doc.add_paragraph()
            p_note.paragraph_format.space_before = Pt(4)
            p_note.paragraph_format.space_after = Pt(8)
            r_note_lbl = p_note.add_run("Note: ")
            r_note_lbl.font.name = style.body_font
            r_note_lbl.font.bold = True
            r_note_lbl.font.size = Pt(style.body_size)
            r_note_lbl.font.color.rgb = hex_to_rgb(style.get_color("tertiary"))
            
            r_note_val = p_note.add_run(" ".join(notes_block.split()))
            r_note_val.font.name = style.body_font
            r_note_val.font.size = Pt(style.body_size)
            r_note_val.font.color.rgb = hex_to_rgb(style.get_color("body_text"))

        # 5. Features list
        if features:
            p_feat_hdr = doc.add_paragraph()
            p_feat_hdr.paragraph_format.space_before = Pt(6)
            p_feat_hdr.paragraph_format.space_after = Pt(4)
            r_feat_hdr = p_feat_hdr.add_run(f"The {module_name} module contains the following sub-modules:")
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

    # 6. Render Screens sequentially
    for screen_idx, content_data, screen_meta in screens_to_render:
        print(f"  Rendering screen: {content_data.get('screen_name', f'Screen {screen_idx}')}...")

        # Re-render the annotated PNG so it honours the current box/callout settings
        try:
            render_annotations(session_dir, screen_idx,
                               client_profile=profile.data if profile else None)
        except Exception as e:
            logger.warning(f"Could not re-render annotations for Screen {screen_idx}: {e}")

        render_screen(
            doc=doc,
            screen_index=screen_idx,
            session_dir=session_dir,
            content_data=content_data,
            screen_meta=screen_meta,
            style=style,
            numbering=numbering,
            # Single-screen module (continuous mode): the screen itself is the
            # module's Heading 1, numbered like a module heading.
            heading_level=1 if single_screen else 2,
        )
