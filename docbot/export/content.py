"""
Convert a ``Screen`` (session.json) into the dicts the Word renderers consume.

``session.json`` is the single source of truth: the Review window edits it, and
the builder reads it through these helpers. The legacy ``screen_N_content.json``
/ ``screen_N_meta.json`` files are still written from the same dicts for
backwards compatibility, but the builder no longer depends on them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docbot.models import Screen


def screen_meta_dict(screen: "Screen") -> dict:
    return {
        "screen_index": screen.index,
        "url": screen.url,
        "title": screen.title,
        "h1_text": screen.h1_text,
        "breadcrumb": screen.breadcrumb,
        "nav_trail": screen.nav_trail,
        "state_of": screen.state_of,
        "state_label": screen.state_label,
        "screen_name": screen.content.screen_name or screen.title or f"Screen {screen.index}",
    }


def screen_content_dict(screen: "Screen") -> dict:
    c = screen.content
    return {
        "screen_name": c.screen_name,
        "intro": c.intro,
        "sections": [sec.model_dump() for sec in c.sections],
        "purpose": c.purpose,
        "navigation_instructions": c.navigation_sentence,
        "field_details": [
            {
                "field_name": f.field_name,
                "utility": f.utility,
                "information": f.information,
                "sample": f.sample,
            }
            for f in screen.fields
        ],
        "screen_documentation": {
            "overview": c.purpose,
            "buttons": c.buttons_doc,
            "table_columns": c.table_columns_doc,
            "notes": c.notes,
        },
        "steps": [
            {"n": s.n, "text": s.text, "kind": s.kind, "crop_path": s.crop_path}
            for s in c.steps
        ],
        "figures": [
            {"index": j + 1, "path": fig.path, "caption_note": fig.caption_note}
            for j, fig in enumerate(screen.figures)
        ],
    }
