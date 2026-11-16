"""
Tests for the per-screen / per-client red box and callout toggles, and for
inserting screenshots as plain (editable) inline pictures.
"""

import json

from docx import Document
from docx.shared import Cm
from PIL import Image

from docbot.models import Screen, SessionModel, SessionStore
from docbot.processing.annotate import render_annotations, resolve_annotation_flags
from manual_builder.renderers.screen import _add_image_with_border
from manual_builder.style_loader import StyleConfig


def _profile(**annotations):
    return {"style": {"annotations": {"callout_style": "bubble_label", **annotations}}}


def _make_session(tmp_path, **screen_kwargs):
    Image.new("RGB", (400, 300), (255, 255, 255)).save(tmp_path / "screen_1.png")
    region = {
        "id": "r1",
        "role": "filter_form",
        "bounding_box": {"x": 100, "y": 150, "width": 120, "height": 60},
        "label": "Search",
    }
    (tmp_path / "screen_1_final.json").write_text(json.dumps([region]), encoding="utf-8")
    session = SessionModel(screens=[Screen(index=1, **screen_kwargs)])
    SessionStore.save(session, tmp_path)


def _red_pixels(img, box=None):
    img = img.convert("RGB")
    if box:
        img = img.crop(box)
    px = img.load()
    return sum(
        1
        for x in range(img.width)
        for y in range(img.height)
        if px[x, y][0] > 180 and px[x, y][1] < 120 and px[x, y][2] < 120
    )


# ── flag resolution ───────────────────────────────────────────────────────

def test_flags_default_to_on():
    assert resolve_annotation_flags(Screen(index=1), {}) == (True, True)


def test_style_default_applies_when_no_override():
    style = {"show_boxes": False, "show_callouts": True}
    assert resolve_annotation_flags(Screen(index=1), style) == (False, True)


def test_screen_override_beats_style():
    style = {"show_boxes": False, "show_callouts": False}
    screen = Screen(index=1, show_boxes=True, show_callouts=None)
    assert resolve_annotation_flags(screen, style) == (True, False)


def test_boxes_only_mode_disables_callouts():
    assert resolve_annotation_flags(None, {"mode": "boxes_only"}) == (True, False)


# ── rendering ─────────────────────────────────────────────────────────────

def test_both_off_gives_clean_screenshot(tmp_path):
    _make_session(tmp_path, show_boxes=False, show_callouts=False)
    render_annotations(tmp_path, 1, client_profile=_profile())
    out = Image.open(tmp_path / "screen_1_annotated.png")
    raw = Image.open(tmp_path / "screen_1.png")
    assert out.convert("RGB").tobytes() == raw.convert("RGB").tobytes()


def test_boxes_only_draws_box_but_no_callout(tmp_path):
    _make_session(tmp_path, show_boxes=True, show_callouts=False)
    render_annotations(tmp_path, 1, client_profile=_profile())
    out = Image.open(tmp_path / "screen_1_annotated.png")
    assert _red_pixels(out) > 0
    # Nothing red outside the region box (callout would sit above it)
    assert _red_pixels(out, box=(0, 0, 400, 140)) == 0


def test_callouts_only_draws_no_box(tmp_path):
    _make_session(tmp_path, show_boxes=False, show_callouts=True)
    render_annotations(tmp_path, 1, client_profile=_profile())
    out = Image.open(tmp_path / "screen_1_annotated.png")
    # Interior of the bottom edge of the box must stay white
    assert _red_pixels(out, box=(120, 205, 200, 212)) == 0
    assert _red_pixels(out) > 0  # callout bubble is drawn


def test_client_default_off_without_override(tmp_path):
    _make_session(tmp_path)
    render_annotations(tmp_path, 1, client_profile=_profile(show_boxes=False, show_callouts=False))
    out = Image.open(tmp_path / "screen_1_annotated.png")
    assert _red_pixels(out) == 0


# ── Word insertion ────────────────────────────────────────────────────────

def _wide_doc():
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(1)  # 21.59 - 2 = ~19.6 cm usable
    return doc


def test_screenshot_is_inline_picture_not_table(tmp_path):
    img_path = tmp_path / "shot.png"
    Image.new("RGB", (800, 500), (255, 255, 255)).save(img_path)
    doc = _wide_doc()
    style = StyleConfig(raw={"figures": {"border_enabled": True, "border_color": "CCCCCC",
                                         "border_width_pt": 0.5, "max_width_cm": 16}})
    _add_image_with_border(doc, img_path, style, alt_text="Login screen")

    assert len(doc.tables) == 0
    assert len(doc.inline_shapes) == 1
    shape = doc.inline_shapes[0]
    assert shape._inline.docPr.get("descr") == "Login screen"
    xml = shape._inline.xml
    assert "a:ln" in xml and 'val="CCCCCC"' in xml
    # 16 cm max width is honoured
    assert abs(shape.width.cm - 16) < 0.05


def test_screenshot_width_clamped_to_page(tmp_path):
    img_path = tmp_path / "shot.png"
    Image.new("RGB", (800, 500), (255, 255, 255)).save(img_path)
    doc = Document()  # Letter, 1.25" margins -> 6" usable
    style = StyleConfig(raw={"figures": {"max_width_cm": 30}})
    _add_image_with_border(doc, img_path, style)
    assert abs(doc.inline_shapes[0].width.inches - 6.0) < 0.01
