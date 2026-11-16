"""
Tests for the writer-style screen layout and for the builder reading session.json
(so that edits made in the Review window reach the manual).
"""

from docx import Document
from PIL import Image

from docbot.models import DocItem, DocSection, Screen, SessionModel, SessionStore, Step
from manual_builder.numbering import NumberingTracker
from manual_builder.renderers.module import render_module
from manual_builder.renderers.screen import _clean_label, render_screen
from manual_builder.style_loader import StyleConfig


def _style(**layout):
    return StyleConfig(raw={"layout": layout} if layout else {})


def _texts(doc):
    return [p.text for p in doc.paragraphs if p.text.strip()]


def _render(tmp_path, content, style=None):
    doc = Document()
    numbering = NumberingTracker(style or _style(), mode="module_prefixed")
    numbering.set_current_module(4)
    render_screen(doc, 1, tmp_path, content, {"title": "Tenders"}, style or _style(), numbering)
    return _texts(doc)


def test_sections_render_as_name_dash_description_type(tmp_path):
    content = {
        "screen_name": "Tender Management",
        "intro": "Click Quick Management → Tender Management from the left navigation panel.",
        "sections": [{"title": "Search Filters", "lead_in": "", "items": [
            {"name": "Language", "description": "Select the language", "control_type": "Dropdown"},
        ]}],
        "steps": [],
        "notes": ["Note: Deleted tenders cannot be restored"],
    }
    texts = _render(tmp_path, content)
    assert "Click Quick Management → Tender Management from the left navigation panel." in texts
    assert "Search Filters" in texts
    assert "Language – Select the language. (Dropdown)" in texts
    assert "Note: Deleted tenders cannot be restored." in texts  # no "Note: Note:"
    assert not any(t.startswith("Steps:") or t.startswith("Path:") for t in texts)


def test_generic_navigation_filler_is_dropped(tmp_path):
    content = {
        "screen_name": "Users",
        "purpose": "The Users page displays all user accounts.",
        "navigation_instructions": "Navigate to Users from the main menu.",
        "field_details": [{"field_name": "Name", "utility": "Enter the user name"}],
    }
    texts = _render(tmp_path, content)
    assert texts[1] == "The Users page displays all user accounts."
    assert "Name – Enter the user name." in texts  # legacy fields still documented


def test_procedure_is_numbered_with_results_unnumbered(tmp_path):
    content = {
        "screen_name": "Login",
        "steps": [
            {"n": 1, "text": "Enter the email address", "kind": "action"},
            {"n": 2, "text": "Click Login", "kind": "action"},
            {"n": 3, "text": "The Dashboard page will be displayed", "kind": "result"},
        ],
    }
    texts = _render(tmp_path, content)
    assert "1.\tEnter the email address." in texts
    assert "2.\tClick Login." in texts
    assert "The Dashboard page will be displayed." in texts


def test_legacy_layout_still_available(tmp_path):
    content = {"screen_name": "Login", "steps": [{"n": 1, "text": "Click Login", "kind": "action"}]}
    texts = _render(tmp_path, content, style=_style(screen_layout="legacy"))
    assert "Steps:" in texts


def test_clean_label():
    assert _clean_label("ASSIGNED USER TYPE") == "Assigned User Type"
    assert _clean_label("NCD ID") == "NCD ID"
    assert _clean_label("Search workflows...") == "Search workflows"


def test_builder_uses_session_json_edits(tmp_path):
    Image.new("RGB", (200, 100), (255, 255, 255)).save(tmp_path / "screen_1.png")
    screen = Screen(index=1, screenshot="screen_1.png")
    screen.content.screen_name = "Users"
    screen.content.intro = "Edited in Review: the Users page lists all accounts."
    screen.content.sections = [DocSection(title="Buttons", items=[
        DocItem(name="Add User", description="Click to add a user", control_type="Button")])]
    screen.content.steps = [Step(n=1, text="Click Add User", kind="action")]
    SessionStore.save(SessionModel(module_name="User Management", module_number=3,
                                   screens=[screen]), tmp_path)
    # A stale legacy content file must NOT win over session.json
    (tmp_path / "screen_1_content.json").write_text('{"screen_name": "OLD", "intro": "OLD TEXT"}',
                                                     encoding="utf-8")

    doc = Document()
    style = _style()
    render_module(doc, tmp_path, style, NumberingTracker(style, mode="module_prefixed"))
    texts = _texts(doc)
    assert "Edited in Review: the Users page lists all accounts." in texts
    assert "Add User – Click to add a user. (Button)" in texts
    assert not any("OLD TEXT" in t for t in texts)
