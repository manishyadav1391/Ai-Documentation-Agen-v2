"""
Backend regression tests: session.json is the source of truth (annotate)
and a damaged session.json is never silently replaced (SessionStore).
"""

import json

import pytest
from PIL import Image

from docbot.models import BBox, Region, Screen, SessionLoadError, SessionModel, SessionStore
from docbot.processing.annotate import render_annotations


def _profile():
    return {"style": {"annotations": {"callout_style": "bubble_label"}}}


def _red_pixels(path):
    img = Image.open(path).convert("RGB")
    data = img.tobytes()
    return sum(1 for i in range(0, len(data), 3)
               if data[i] > 180 and data[i + 1] < 120 and data[i + 2] < 120)


def _region(rid="r1", **kw):
    return Region(id=rid, role="filter_form", label="Search",
                  bounding_box=BBox(x=100, y=100, width=120, height=60), **kw)


def _write_screen(tmp_path, regions, legacy_regions=None):
    Image.new("RGB", (400, 300), (255, 255, 255)).save(tmp_path / "screen_1.png")
    if legacy_regions is not None:
        (tmp_path / "screen_1_final.json").write_text(json.dumps(legacy_regions), encoding="utf-8")
    SessionStore.save(SessionModel(screens=[Screen(index=1, regions=regions)]), tmp_path)


# --- Item 1: render_annotations reads session.json --------------------------

def test_backend_annotate_ignores_stale_legacy_file_when_region_deleted(tmp_path):
    # Legacy final.json still has the region; session.json says it was deleted
    stale = [_region().model_dump()]
    _write_screen(tmp_path, [_region(deleted=True)], legacy_regions=stale)
    render_annotations(tmp_path, 1, client_profile=_profile())
    assert _red_pixels(tmp_path / "screen_1_annotated.png") == 0


def test_backend_annotate_uses_session_regions_without_legacy_file(tmp_path):
    _write_screen(tmp_path, [_region()])
    render_annotations(tmp_path, 1, client_profile=_profile())
    assert _red_pixels(tmp_path / "screen_1_annotated.png") > 0


def test_backend_annotate_falls_back_to_legacy_without_session_json(tmp_path):
    Image.new("RGB", (400, 300), (255, 255, 255)).save(tmp_path / "screen_1.png")
    (tmp_path / "screen_1_final.json").write_text(json.dumps([_region().model_dump()]), encoding="utf-8")
    render_annotations(tmp_path, 1, client_profile=_profile())
    assert _red_pixels(tmp_path / "screen_1_annotated.png") > 0


# --- Item 15: malformed regions / style values don't crash -------------------

@pytest.mark.parametrize("bad", [
    {"id": "a", "label": "", "elements_contained": [],
     "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 20}},
    {"id": "b", "label": None, "bounding_box": {"x": 10, "y": 10, "width": 50, "height": 20}},
    {"id": "c", "label": "Neg", "bounding_box": {"x": 200, "y": 200, "width": -50, "height": -20}},
    {"id": "d", "label": "Null", "bounding_box": {"x": None, "y": 10, "width": 50, "height": None}},
    "not a dict",
])
def test_backend_annotate_survives_malformed_region(tmp_path, bad):
    Image.new("RGB", (400, 300), (255, 255, 255)).save(tmp_path / "screen_1.png")
    (tmp_path / "screen_1_final.json").write_text(json.dumps([bad]), encoding="utf-8")
    render_annotations(tmp_path, 1, client_profile=_profile())
    assert (tmp_path / "screen_1_annotated.png").exists()


def test_backend_annotate_survives_malformed_style(tmp_path):
    _write_screen(tmp_path, [_region()])
    profile = {"style": {"annotations": {
        "callout_style": "bubble_label", "callout_font_size": "big",
        "callout_padding": [5], "colors": None, "region_border_width": "x",
    }}}
    render_annotations(tmp_path, 1, client_profile=profile)
    profile["style"]["annotations"]["callout_font_size"] = 0
    render_annotations(tmp_path, 1, client_profile=profile)
    assert (tmp_path / "screen_1_annotated.png").exists()


# --- Item 2: damaged session.json -----------------------------------------

def test_backend_session_load_corrupt_raises_and_backs_up(tmp_path):
    session = SessionModel(screens=[Screen(index=1, title="Login")]).model_dump()
    session["screens"][0]["title"] = None          # one invalid value
    original = json.dumps(session)
    (tmp_path / "session.json").write_text(original, encoding="utf-8")

    with pytest.raises(SessionLoadError) as exc:
        SessionStore.load(tmp_path)

    assert "session.json.corrupt" in str(exc.value)
    assert (tmp_path / "session.json.corrupt").read_text(encoding="utf-8") == original
    # The original is untouched (nothing was overwritten)
    assert (tmp_path / "session.json").read_text(encoding="utf-8") == original


def test_backend_session_load_invalid_json_raises(tmp_path):
    (tmp_path / "session.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionLoadError):
        SessionStore.load(tmp_path)


def test_backend_session_load_missing_file_still_returns_empty(tmp_path):
    assert SessionStore.load(tmp_path).screens == []
