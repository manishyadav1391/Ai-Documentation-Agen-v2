"""
Builder regressions: content that used to be silently dropped or mangled, and
bad input that used to abort the build (control characters, broken images).
"""

import json
from pathlib import Path

from docx import Document
from PIL import Image

from manual_builder.manifest_loader import SectionEntry
from manual_builder.numbering import NumberingTracker
from manual_builder.renderers.module import render_module
from manual_builder.renderers.prose import render_prose
from manual_builder.renderers.screen import _is_placeholder, render_screen
from manual_builder.style_loader import StyleConfig

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _texts(doc):
    return [p.text for p in doc.paragraphs if p.text.strip()]


def _render(tmp_path, content, style=None):
    style = style or StyleConfig(raw={})
    doc = Document()
    n = NumberingTracker(style)
    n.set_current_module(4)
    render_screen(doc, 1, tmp_path, content, {"title": "T"}, style, n)
    return doc, n


# ── Item 8: placeholder filter ──────────────────────────────────────────────

def test_is_placeholder_only_flags_real_placeholders():
    for text in ["", "  ", "[Client Name]", "[Provide a description here.]", "TODO", "tbd.",
                 "Lorem ipsum dolor sit amet", "Sample text", "Welcome to [System Name]."]:
        assert _is_placeholder(text), text
    for text in ["Click [Save] to store the record.", "Open the Data Input tab.",
                 "Enter sample text to preview the template.", "Use the Lorem field.",
                 "Values in [brackets] are optional."]:
        assert not _is_placeholder(text), text


def test_writer_layout_keeps_text_with_brackets_and_keywords(tmp_path):
    content = {
        "screen_name": "Records",
        "intro": "Click [Save] after completing the Data Input form.",
        "sections": [{"title": "Fields", "items": [
            {"name": "Notes", "description": "Enter sample text [optional]", "control_type": ""}]}],
        "notes": ["Records in [Draft] state can be edited."],
    }
    texts = _texts(_render(tmp_path, content)[0])
    assert "Click [Save] after completing the Data Input form." in texts
    assert "Notes – Enter sample text [optional]." in texts
    assert "Note: Records in [Draft] state can be edited." in texts


# ── Item 9: extra figures ───────────────────────────────────────────────────

def _png(path, color):
    Image.new("RGB", (300, 200), color).save(path)


def test_extra_figures_keep_their_own_image(tmp_path):
    _png(tmp_path / "screen_1_viewport.png", (255, 255, 255))
    _png(tmp_path / "screen_1_annotated.png", (255, 0, 0))
    _png(tmp_path / "screen_1_scroll2.png", (0, 255, 0))
    _png(tmp_path / "extra_crop.png", (0, 0, 255))
    content = {"screen_name": "S", "figures": [
        {"index": 1, "path": "screen_1_viewport.png", "caption_note": ""},
        {"index": 2, "path": "screen_1_scroll2.png", "caption_note": "scrolled"},
        {"index": 3, "path": "extra_crop.png", "caption_note": "crop"},
    ]}
    doc, n = _render(tmp_path, content)
    blobs = [doc.part.related_parts[b.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")].blob
             for b in doc.element.body.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")]
    expected = [(tmp_path / f).read_bytes()
                for f in ("screen_1_annotated.png", "screen_1_scroll2.png", "extra_crop.png")]
    assert blobs == expected
    assert n.figure_count == 3


# ── Item 10: markdown emphasis ──────────────────────────────────────────────

def _prose(tmp_path, md):
    (tmp_path / "p.md").write_text(md, encoding="utf-8")

    class _M:
        def get_source_path(self, s):
            return tmp_path / s

    doc = Document()
    render_prose(doc, SectionEntry(id="p", type="prose", source="p.md"), _M(), StyleConfig(raw={}))
    return doc


def test_prose_keeps_underscores_and_asterisks_in_names_urls_maths(tmp_path):
    md = ("Open my_file_name_v2.txt or https://example.com/a_b_c/x*y.\n"
          "Compute 2 * 3 * 4 and a*b*c.\n"
          "Set MAX_RETRY_COUNT in __init__.py.\n")
    texts = _texts(_prose(tmp_path, md))
    assert texts == ["Open my_file_name_v2.txt or https://example.com/a_b_c/x*y.",
                     "Compute 2 * 3 * 4 and a*b*c.",
                     "Set MAX_RETRY_COUNT in __init__.py."]


def test_prose_emphasis_at_word_boundaries(tmp_path):
    doc = _prose(tmp_path, "Click **Save** then _Close_ or *Cancel* and __Exit__.\n")
    p = doc.paragraphs[-1]
    assert p.text == "Click Save then Close or Cancel and Exit."
    fmt = {r.text: (bool(r.bold), bool(r.italic)) for r in p.runs}
    assert fmt["Save"] == (True, False)
    assert fmt["Close"] == (False, True)
    assert fmt["Cancel"] == (False, True)
    assert fmt["Exit"] == (True, False)


# ── Item 11: control characters ─────────────────────────────────────────────

def test_control_characters_in_session_content_are_stripped(tmp_path):
    (tmp_path / "module_meta.json").write_text(json.dumps(
        {"module_name": "Bad\x0bName", "module_number": 2, "intro": "Intro\x00 text\x1f.",
         "features": ["Feat\x08ure"], "screen_order": [1]}), encoding="utf-8")
    _png(tmp_path / "screen_1.png", (255, 255, 255))
    (tmp_path / "screen_1_content.json").write_text(json.dumps(
        {"screen_name": "Scr\x01een", "intro": "Hello\x0cworld.",
         "sections": [{"title": "T\x02", "items": [{"name": "F\x03", "description": "D\x04"}]}],
         "notes": ["N\x05ote"]}), encoding="utf-8")
    (tmp_path / "screen_1_meta.json").write_text("{}", encoding="utf-8")
    doc = Document()
    style = StyleConfig(raw={})
    render_module(doc, tmp_path, style, NumberingTracker(style), client_key="_default")
    texts = _texts(doc)
    assert "2.\tBadName" in texts
    assert "Intro text." in texts
    assert "Helloworld." in texts
    assert "F – D." in texts


def test_control_characters_in_prose_file(tmp_path):
    texts = _texts(_prose(tmp_path, "Line\x07 one\x1b.\n"))
    assert texts == ["Line one."]


# ── Item 12: broken screenshots ─────────────────────────────────────────────

def test_zero_byte_and_truncated_screenshots_are_skipped(tmp_path):
    (tmp_path / "screen_1.png").write_bytes(b"")
    _png(tmp_path / "good.png", (255, 255, 255))
    data = (tmp_path / "good.png").read_bytes()
    (tmp_path / "trunc.png").write_bytes(data[: len(data) // 2])
    content = {"screen_name": "S", "figures": [
        {"index": 1, "path": "screen_1.png", "caption_note": ""},
        {"index": 2, "path": "trunc.png", "caption_note": "t"},
        {"index": 3, "path": "good.png", "caption_note": "g"},
    ]}
    doc, n = _render(tmp_path, content)
    texts = _texts(doc)
    assert any("screen_1.png could not be read" in t for t in texts)
    assert any("trunc.png could not be read" in t for t in texts)
    assert n.figure_count == 1  # only the good image is numbered
    assert len(list(doc.element.body.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"))) == 1
