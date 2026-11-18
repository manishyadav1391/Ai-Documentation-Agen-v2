"""
Builder regressions: caption numbering (SEQ cached value + per-module reset),
Table of Figures emission, numbering_mode, module/section number collisions.
"""

import json
import re
import zipfile

import pytest
from docx import Document
from PIL import Image

from manual_builder import GenericBuilder, NumberingTracker, load_manifest, load_style
from manual_builder.renderers.module import render_module
from manual_builder.style_loader import StyleConfig

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _session(path, name, number, screens):
    """Legacy-layout session: module_meta.json + screen_N_{content,meta}.json + PNGs."""
    path.mkdir(parents=True)
    meta = {"module_name": name, "screen_order": list(range(1, screens + 1))}
    if number is not None:
        meta["module_number"] = number
    (path / "module_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    for i in range(1, screens + 1):
        Image.new("RGB", (300, 200), (255, 255, 255)).save(path / f"screen_{i}.png")
        content = {"screen_name": f"{name} Screen {i}", "intro": "Intro text.",
                   "figures": [{"index": 1, "path": f"screen_{i}.png", "caption_note": ""}]}
        (path / f"screen_{i}_content.json").write_text(json.dumps(content), encoding="utf-8")
        (path / f"screen_{i}_meta.json").write_text(json.dumps({"title": f"S{i}"}), encoding="utf-8")
    return path


def _ptext(p_el):
    """Paragraph text with field instructions shown as {…}."""
    out = []
    for el in p_el.iter():
        if el.tag == W + "t":
            out.append(el.text or "")
        elif el.tag == W + "instrText":
            out.append("{" + (el.text or "").strip() + "}")
    return "".join(out)


def _captions(doc):
    return [_ptext(p._p) for p in doc.paragraphs if p.style is not None and p.style.name == "Caption"]


def _headings(doc, level=None):
    names = {f"Heading {level}"} if level else {f"Heading {i}" for i in range(1, 5)}
    return [p.text for p in doc.paragraphs if p.style is not None and p.style.name in names]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """Isolated DocBot workspace with one client 'acme'."""
    root = tmp_path / "ws"
    monkeypatch.setenv("DOCBOT_DATA_DIR", str(root))
    client = root / "clients" / "acme"
    (client / "content").mkdir(parents=True)
    (client / "content" / "intro.md").write_text("Hello.", encoding="utf-8")
    (client / "voice.yaml").write_text("notes_block: ''\n", encoding="utf-8")
    (client / "style.yaml").write_text("colors:\n  table_header_bg: '123456'\n", encoding="utf-8")
    return root


def _manifest(ws, mode=None, extra_sections=""):
    text = (
        "client_key: acme\nclient_display_name: Acme\nsystem_name: Portal\ncover_enabled: false\n"
        + (f"numbering_mode: {mode}\n" if mode else "")
        + "sections:\n"
        "  - {id: toc, type: table_of_contents}\n"
        "  - {id: tot, type: table_of_tables, heading: Table of Tables}\n"
        "  - {id: tof, type: table_of_figures, heading: Table of Figures}\n"
        "  - {id: intro, type: prose, heading: Introduction, source: intro.md}\n"
        + extra_sections
        + "  - {id: modules, type: modules}\n"
    )
    (ws / "clients" / "acme" / "manifest.yaml").write_text(text, encoding="utf-8")


def _build(ws, sessions, out_name="out.docx"):
    manifest = load_manifest("acme")
    style = load_style("acme")
    builder = GenericBuilder(manifest, style, NumberingTracker(style, mode=manifest.numbering_mode))
    builder.build_full_manual(sessions)
    out = builder.save(ws / out_name)
    return Document(str(out)), out


# ── Item 1: captions ────────────────────────────────────────────────────────

def test_caption_cached_value_matches_tracker_and_resets_per_module(ws, tmp_path):
    _manifest(ws)  # module_prefixed (default)
    a = _session(tmp_path / "a", "Alpha", None, 3)
    b = _session(tmp_path / "b", "Beta", None, 2)
    doc, _ = _build(ws, [a, b])
    caps = _captions(doc)
    # Front matter "1 Introduction" -> modules are chapters 2 and 3
    assert caps == [
        "Figure 2-{SEQ Figure \\* ARABIC \\r 1}1 Alpha Screen 1",
        "Figure 2-{SEQ Figure \\* ARABIC}2 Alpha Screen 2",
        "Figure 2-{SEQ Figure \\* ARABIC}3 Alpha Screen 3",
        "Figure 3-{SEQ Figure \\* ARABIC \\r 1}1 Beta Screen 1",
        "Figure 3-{SEQ Figure \\* ARABIC}2 Beta Screen 2",
    ]


def test_caption_continuous_mode_counts_across_modules(ws, tmp_path):
    _manifest(ws, mode="continuous")
    a = _session(tmp_path / "a", "Alpha", None, 2)
    b = _session(tmp_path / "b", "Beta", None, 2)
    doc, _ = _build(ws, [a, b])
    caps = _captions(doc)
    cached = [re.search(r"\}(\d+) ", c).group(1) for c in caps]
    assert cached == ["1", "2", "3", "4"]
    assert not any("\\r" in c for c in caps)


# ── Item 3: Table of Figures ────────────────────────────────────────────────

def test_table_of_figures_emitted_when_figures_exist_and_tot_dropped(ws, tmp_path):
    _manifest(ws)
    doc, out = _build(ws, [_session(tmp_path / "a", "Alpha", None, 1)])
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert 'TOC \\h \\z \\c "Figure"' in xml
    assert '\\c "Table"' not in xml  # no table captions -> TOT removed
    h1 = _headings(doc, 1)
    assert "Table of Figures" in h1 and "Table of Tables" not in h1
    assert "Table of Contents" in h1  # neighbouring blocks untouched


def test_table_of_figures_dropped_without_figures(ws):
    _manifest(ws)
    manifest, style = load_manifest("acme"), load_style("acme")
    builder = GenericBuilder(manifest, style, NumberingTracker(style))
    builder.build_front_matter()
    out = builder.save(ws / "fm.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert '\\c "Figure"' not in xml
    assert "Introduction" in xml


# ── Item 4: numbering_mode ──────────────────────────────────────────────────

def test_manifest_numbering_mode_is_read(ws):
    _manifest(ws, mode="continuous")
    assert load_manifest("acme").numbering_mode == "continuous"
    _manifest(ws)
    assert load_manifest("acme").numbering_mode == "module_prefixed"


def test_continuous_mode_with_module_figure_format_does_not_crash():
    style = StyleConfig(raw={"numbering": {"figure_format": "{module}-{fig}",
                                           "table_format": "{module}-{tbl}"}})
    n = NumberingTracker(style, mode="continuous")
    assert n.next_figure(3) == "1"
    assert n.next_figure(3) == "2"
    assert n.next_table(3) == "1"


def test_single_screen_module_gets_heading_1_in_continuous_mode(ws, tmp_path):
    _manifest(ws, mode="continuous")
    a = _session(tmp_path / "a", "Alpha", None, 2)
    solo = _session(tmp_path / "solo", "Solo", None, 1)
    doc, _ = _build(ws, [a, solo])
    h1 = _headings(doc, 1)
    assert "2.\tAlpha" in h1
    assert "3.\tSolo Screen 1" in h1  # the single screen is the module's H1
    assert "3.1\tSolo Screen 1" not in _headings(doc, 2)


# ── Item 5: section number collisions ───────────────────────────────────────

def test_module_numbers_follow_front_matter_and_never_collide(ws, tmp_path):
    _manifest(ws)
    a = _session(tmp_path / "a", "Alpha", None, 1)   # no number
    b = _session(tmp_path / "b", "Beta", None, 1)    # no number
    c = _session(tmp_path / "c", "Gamma", 1, 1)      # collides with "1 Introduction"
    d = _session(tmp_path / "d", "Delta", 10, 1)     # free explicit number is kept
    doc, _ = _build(ws, [a, b, c, d])
    h1 = _headings(doc, 1)
    assert h1[-5:] == ["1 Introduction", "2.\tAlpha", "3.\tBeta", "4.\tGamma", "10.\tDelta"]


def test_explicit_module_number_kept_in_standalone_draft(tmp_path):
    s = _session(tmp_path / "a", "Alpha", 7, 1)
    style = StyleConfig(raw={})
    doc = Document()
    render_module(doc, s, style, NumberingTracker(style), client_key="_default")
    assert _headings(doc, 1) == ["7.\tAlpha"]
    assert _captions(doc)[0].startswith("Figure 7-")
