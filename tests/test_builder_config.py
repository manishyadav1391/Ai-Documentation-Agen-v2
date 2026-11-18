"""
Builder regressions: manifest/style loading, config errors, save fallback,
table header colours, layout widths, heading levels, client note block,
corrupt session.json.
"""

import json
import re
import zipfile

import pytest
from docx import Document
from docx.shared import Inches
from PIL import Image

import master_assembler
from manual_builder import GenericBuilder, NumberingTracker, load_manifest, load_style
from manual_builder.build_error import BuildError
from manual_builder.renderers.module import render_module
from manual_builder.style_loader import StyleConfig
from manual_builder.utils import hex_to_rgb, usable_width_emu

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    monkeypatch.setenv("DOCBOT_DATA_DIR", str(root))
    (root / "clients" / "_default").mkdir(parents=True)
    (root / "content" / "_default").mkdir(parents=True)
    (root / "content" / "_default" / "manifest.yaml").write_text(
        "client_key: _default\nclient_display_name: '[Client Name]'\nsections: []\n", encoding="utf-8")
    return root


def _client(ws, key, manifest=None, style=None, voice=None, content=None):
    d = ws / "clients" / key
    (d / "content").mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (d / "manifest.yaml").write_text(manifest, encoding="utf-8")
    if style is not None:
        (d / "style.yaml").write_text(style, encoding="utf-8")
    if voice is not None:
        (d / "voice.yaml").write_text(voice, encoding="utf-8")
    for name, text in (content or {}).items():
        (d / "content" / name).parent.mkdir(parents=True, exist_ok=True)
        (d / "content" / name).write_text(text, encoding="utf-8")
    return d


def _session(path, name="Mod", screens=1):
    path.mkdir(parents=True)
    (path / "module_meta.json").write_text(json.dumps(
        {"module_name": name, "module_number": 2, "intro": "Intro.", "screen_order": list(range(1, screens + 1))}),
        encoding="utf-8")
    for i in range(1, screens + 1):
        Image.new("RGB", (2000, 1000), (255, 255, 255)).save(path / f"screen_{i}.png")
        (path / f"screen_{i}_content.json").write_text(json.dumps(
            {"screen_name": f"Screen {i}", "intro": "x",
             "figures": [{"index": 1, "path": f"screen_{i}.png", "caption_note": ""}]}), encoding="utf-8")
        (path / f"screen_{i}_meta.json").write_text("{}", encoding="utf-8")
    return path


def _xml(path):
    return zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")


BASE_MANIFEST = "client_key: acme\nclient_display_name: Acme\nsystem_name: Portal\ncover_enabled: false\n"


# ── Item 2: table header fill ───────────────────────────────────────────────

def test_table_header_colour_aliases_are_resolved(ws):
    _client(ws, "acme",
            manifest=BASE_MANIFEST + "sections:\n"
            "  - {id: rh, type: revision_history, source: rh.yaml}\n"
            "  - {id: b, type: icon_table, heading: Buttons, source: b.yaml}\n",
            style="colors:\n  table_header_bg: 'ABCDEF'\n  table_header_fg: '111111'\n"
                  "tables:\n  header_bg: table_header_bg\n  header_fg: table_header_fg\n"
                  "revision_history:\n  header_bg: table_header_bg\n",
            content={"rh.yaml": "entries: []\n",
                     "b.yaml": "columns: [Name, Description]\nrows:\n  - {name: Save, description: Saves}\n"})
    b = GenericBuilder(load_manifest("acme"), load_style("acme"), NumberingTracker(None))
    b.build_front_matter()
    out = b.save(ws / "o.docx")
    fills = set(re.findall(r'w:fill="([^"]+)"', _xml(out)))
    assert "ABCDEF" in fills
    assert not any("table" in f for f in fills)


def test_field_table_header_fill_resolved(tmp_path):
    from manual_builder.renderers.field_table import render_field_table
    style = StyleConfig(raw={"colors": {"table_header_bg": "0A0B0C"},
                             "tables": {"header_bg": "table_header_bg"}})
    doc = Document()
    render_field_table(doc, 1, [{"field_name": "Name", "utility": "u"}], style, "3-1", seq_value=1)
    fills = {el.get(W + "fill") for el in doc.element.body.iter(W + "shd")}
    assert "0A0B0C" in fills and "table_header_bg" not in fills


# ── Item 6: ncb manifest shadowing ──────────────────────────────────────────

def test_placeholder_client_manifest_does_not_hide_legacy_manifest(ws):
    _client(ws, "ncb", manifest="client_key: _default\nclient_display_name: '[Client Name]'\nsections: []\n")
    legacy = ws / "content" / "ncb"
    legacy.mkdir(parents=True)
    (legacy / "manifest.yaml").write_text(
        "client_key: ncb\nclient_display_name: Narcotics Control Bureau\nsections: []\n", encoding="utf-8")
    m = load_manifest("ncb")
    assert m.client_display_name == "Narcotics Control Bureau"
    assert m.client_key == "ncb"
    assert m.content_dir == legacy.resolve()


def test_filled_client_manifest_still_preferred(ws):
    _client(ws, "ncb", manifest="client_key: ncb\nclient_display_name: NCB New\nsections: []\n")
    (ws / "content" / "ncb").mkdir(parents=True)
    (ws / "content" / "ncb" / "manifest.yaml").write_text("client_display_name: Old\n", encoding="utf-8")
    assert load_manifest("ncb").client_display_name == "NCB New"


# ── Item 7: notes block of the assembled client ─────────────────────────────

def test_module_note_block_uses_assembled_client_without_double_label(ws, tmp_path):
    _client(ws, "acme", voice="notes_block: |\n  Note: Acme systems need\n  a VPN.\n")
    _client(ws, "other", voice="notes_block: 'Other client note'\n")
    s = _session(tmp_path / "s")
    doc = Document()
    style = StyleConfig(raw={})
    render_module(doc, s, style, NumberingTracker(style), client_key="acme")
    texts = [p.text for p in doc.paragraphs]
    assert "Note: Acme systems need a VPN." in texts
    assert not any("Note: Note:" in t or "Other client" in t for t in texts)


# ── Items 13: locked output ─────────────────────────────────────────────────

def test_save_falls_back_to_timestamped_name_when_locked(ws, monkeypatch):
    _client(ws, "acme", manifest=BASE_MANIFEST + "sections: []\n")
    b = GenericBuilder(load_manifest("acme"), load_style("acme"), NumberingTracker(None))
    target = ws / "out" / "manual.docx"
    real_save = b.doc.save

    def save(path):
        if str(path) == str(target):
            raise PermissionError(13, "Permission denied")
        real_save(path)

    monkeypatch.setattr(b.doc, "save", save)
    out = b.save(target)
    assert out != target and out.exists()
    assert re.match(r"manual_\d{8}_\d{6}\.docx$", out.name)


# ── Item 14: tolerant config ────────────────────────────────────────────────

def test_unquoted_version_and_empty_blocks_and_bad_hex(ws, tmp_path):
    _client(ws, "acme",
            manifest=BASE_MANIFEST + "version: 1.0\nsections:\n"
            "  - {id: p, type: prose, heading: NoSource}\n"
            "  - {id: b, type: bullet_list, heading: Empty, source: ''}\n"
            "  - {id: i, type: icon_table, heading: Dir, source: sub}\n"
            "  - {id: modules, type: modules}\n",
            style="colors:\nfonts:\nheadings:\n  h1_color: ZZZZZZ\n",
            content={"sub/keep.txt": "x"})
    m = load_manifest("acme")
    assert m.version == "1.0" and m.document_version == "1.0"
    style = load_style("acme")
    assert style.colors == {} and style.fonts == {}
    assert style.get_color("primary") == "1B365D"
    assert style.heading_config(1)["color"] == "000000"
    b = GenericBuilder(m, style, NumberingTracker(style))
    b.build_full_manual([_session(tmp_path / "s")])
    out = b.save(ws / "o.docx")
    from assemble import _make_output_filename
    assert "_v1.0_" in _make_output_filename(m, "20260101_000000")
    assert "ZZZZZZ" not in _xml(out)


def test_hex_to_rgb_invalid_falls_back():
    assert str(hex_to_rgb("ZZZZZZ")) == "1B365D"


# ── Item 15: config errors surfaced ─────────────────────────────────────────

def test_master_assembler_surfaces_config_error(ws, tmp_path):
    _client(ws, "acme", manifest="client_key: acme\nsections: [\n")  # invalid YAML
    with pytest.raises(BuildError, match="acme"):
        master_assembler.assemble_master_manual([], tmp_path / "x.docx", client_key="acme")


# ── Item 16: widths, first-page header, page number size ────────────────────

def test_images_and_header_tables_fit_a4_usable_width(ws, tmp_path):
    _client(ws, "acme", manifest=BASE_MANIFEST + "sections:\n  - {id: modules, type: modules}\n",
            style="layout:\n  body_left_indent_twips: 432\nfigures:\n  max_width_inches: 6.2\n")
    b = GenericBuilder(load_manifest("acme"), load_style("acme"), NumberingTracker(None))
    b.build_full_manual([_session(tmp_path / "s")])
    out = b.save(ws / "o.docx")
    doc = Document(str(out))
    usable = usable_width_emu(doc)
    extents = list(doc.element.body.iter(
        "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"))
    assert extents
    for ext in extents:
        assert int(ext.get("cx")) + int(Inches(0.3)) <= usable + 10
    sec = doc.sections[0]
    for part in (sec.header, sec.footer):
        tbl = part.tables[0]
        tblw = int(tbl._tbl.tblPr.find(W + "tblW").get(W + "w"))
        assert tblw * 635 <= usable + 635
    # no cover -> page 1 keeps header/footer
    assert sec.different_first_page_header_footer is False
    # page-number field runs carry the 8pt size
    runs = sec.footer.tables[0].cell(0, 1).paragraphs[0].runs
    field_runs = [r for r in runs if r._r.find(W + "fldChar") is not None]
    assert field_runs and all(r.font.size is not None and r.font.size.pt == 8 for r in field_runs)


def test_cover_turns_on_distinct_first_page(ws):
    _client(ws, "acme", manifest="client_key: acme\nclient_display_name: Acme\nsections:\n"
            "  - {id: cover, type: cover}\n")
    b = GenericBuilder(load_manifest("acme"), load_style("acme"), NumberingTracker(None))
    b.build_front_matter()
    assert b.doc.sections[0].different_first_page_header_footer is True


# ── Item 17: group heading levels ───────────────────────────────────────────

def test_group_subsections_use_nested_heading_levels(ws):
    _client(ws, "acme",
            manifest=BASE_MANIFEST + "sections:\n"
            "  - id: sop\n    type: group\n    heading: SOP\n    subsections:\n"
            "      - {id: b, type: icon_table, heading: Buttons, source: b.yaml}\n"
            "      - {id: c, type: prose, heading: Calendar, source: c.md}\n"
            "  - {id: t, type: icon_table, heading: Top, source: b.yaml}\n",
            content={"b.yaml": "rows:\n  - {name: A, description: B}\n", "c.md": "## Sub\nText\n"})
    b = GenericBuilder(load_manifest("acme"), load_style("acme"), NumberingTracker(None))
    b.build_front_matter()
    heads = [(p.style.name, p.text) for p in b.doc.paragraphs if p.style.name.startswith("Heading")]
    assert heads == [("Heading 1", "1 SOP"), ("Heading 2", "1.1 Buttons"), ("Heading 2", "1.2 Calendar"),
                     ("Heading 3", "Sub"), ("Heading 1", "2 Top")]


# ── Coordinator: corrupt session.json aborts the build ──────────────────────

def test_corrupt_session_json_aborts_module_render(tmp_path):
    from docbot.models import SessionLoadError
    s = _session(tmp_path / "s")
    (s / "session.json").write_text("{ not json", encoding="utf-8")
    style = StyleConfig(raw={})
    with pytest.raises(SessionLoadError):
        render_module(Document(), s, style, NumberingTracker(style), client_key="_default")
