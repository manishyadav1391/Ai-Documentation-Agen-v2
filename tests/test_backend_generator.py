"""
Backend regression tests: LLM reply parsing (providers.base) and merging
into the screen model (generator).
"""

import json

import pytest

from docbot.models import BBox, DocItem, DocSection, Region, Screen, ScreenContent, SessionModel, Step
from docbot.processing.generator import Generator, ScreenDocResponse
from providers.base import GenerationError, Provider


GOOD = {
    "screen_name": "Login", "intro": "Intro.", "purpose": "P.", "navigation_sentence": "N.",
    "sections": [{"title": "Fields", "lead_in": "", "items": [
        {"name": "User", "description": "Enter.", "control_type": "Text"}]}],
    "regions": [{"id": "r1", "label": "Header"}],
    "steps": [{"n": 1, "text": "Do.", "kind": "action"}],
    "notes": [],
}


class Fake(Provider):
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    @property
    def name(self):
        return "fake"

    def is_available(self):
        return True

    def chat(self, prompt, *, max_tokens=None, temperature=0.2, system=None):
        self.calls.append({"max_tokens": max_tokens})
        r = self.replies.pop(0) if self.replies else "{}"
        if isinstance(r, BaseException):
            raise r
        return r


def _screen():
    return Screen(
        index=1,
        regions=[Region(id="r1", label="Old header", bounding_box=BBox(width=10, height=10))],
        content=ScreenContent(
            screen_name="Existing", intro="Existing intro.", purpose="Existing purpose.",
            sections=[DocSection(title="S", items=[DocItem(name="A")])],
            steps=[Step(n=1, text="Skeleton step.")],
        ),
    )


def _generate(replies, screen=None):
    screen = screen or _screen()
    session = SessionModel(module_name="Mod", screens=[screen])
    provider = Fake(replies)
    return Generator(provider), session, screen, provider


# --- Item 6 / 7: tolerant JSON extraction ----------------------------------

G = json.dumps(GOOD)


@pytest.mark.parametrize("raw", [
    "Here is the JSON:\n```json\n" + G + "\n```",
    "```json\n" + G + "\n```\nHope this helps!",
    "<think>let me think {about it}</think>\n" + G,
    "﻿" + G,
    "```JSON\n" + G + "\n```",
])
def test_backend_chat_json_tolerates_wrapping(raw):
    provider = Fake([raw])
    res = provider.chat_json("p", ScreenDocResponse)
    assert res.screen_name == "Login"
    assert len(provider.calls) == 1


def test_backend_chat_json_null_content_retries_instead_of_crashing():
    class NullFake(Fake):
        def chat(self, prompt, **kw):
            self.calls.append(kw)
            return None if len(self.calls) == 1 else G
    provider = NullFake([])
    assert provider.chat_json("p", ScreenDocResponse).screen_name == "Login"
    assert len(provider.calls) == 2


# --- Item 3: empty / keyless replies are rejected ---------------------------

@pytest.mark.parametrize("reply", ["{}", json.dumps({"name": "x", "description": "y"})])
def test_backend_empty_reply_rejected_and_screen_untouched(reply):
    gen, session, screen, provider = _generate([reply, reply])
    before = screen.content.model_dump()
    with pytest.raises(GenerationError):
        gen.generate_screen(session, screen)
    assert screen.content.model_dump() == before


# --- Item 8: nulls / odd step kinds are normalised; hash set last ------------

def test_backend_nulls_and_step_kinds_normalised():
    reply = dict(GOOD)
    reply.update({
        "screen_name": None, "intro": None, "notes": None, "lead_in": None,
        "regions": [{"id": "r1", "label": None}, {"id": 2, "label": "Two"}],
        "steps": [{"n": "1.", "text": "a", "kind": "note"},
                  {"text": "b", "kind": "Result "},
                  {"n": 3, "text": "c", "kind": None}],
    })
    reply["sections"] = [{"title": "T", "lead_in": None,
                          "items": [{"name": "X", "description": None, "control_type": None}]}]
    gen, session, screen, provider = _generate([json.dumps(reply)])
    gen.generate_screen(session, screen)

    c = screen.content
    assert len(provider.calls) == 1
    assert c.screen_name == "Existing"          # null keeps existing value
    assert c.intro == "Existing intro."
    assert [(s.n, s.kind) for s in c.steps] == [(1, "action"), (2, "result"), (3, "action")]
    assert c.sections[0].items[0].control_type == ""
    assert screen.regions[0].label == "Old header"   # null label never wipes
    assert c.content_hash


def test_backend_failed_merge_leaves_no_hash(monkeypatch):
    gen, session, screen, provider = _generate([G])

    def boom(*a, **k):
        raise RuntimeError("merge failed")
    monkeypatch.setattr("docbot.models.Step", boom)
    with pytest.raises(RuntimeError):
        gen.generate_screen(session, screen)
    assert screen.content.content_hash == ""
    assert screen.content.intro == "Existing intro."   # nothing half-written


# --- Item 4: configured max_tokens is used ----------------------------------

def test_backend_generator_does_not_override_max_tokens():
    gen, session, screen, provider = _generate([G, json.dumps({"intro": "I", "features": ["f"]})])
    gen.generate_screen(session, screen)
    gen.generate_module_intro(session)
    assert [c["max_tokens"] for c in provider.calls] == [None, None]


# --- Item 9: module intro fallback is written to the session ----------------

def test_backend_module_intro_fallback_assigned():
    gen, session, screen, provider = _generate([RuntimeError("down")])
    res = gen.generate_module_intro(session)
    assert session.module_intro == res.intro
    assert "Mod" in session.module_intro
    assert session.module_features == ["Existing"]


def test_backend_module_intro_fallback_keeps_existing_intro():
    gen, session, screen, provider = _generate([RuntimeError("down")])
    session.module_intro = "User-written intro."
    gen.generate_module_intro(session)
    assert session.module_intro == "User-written intro."
