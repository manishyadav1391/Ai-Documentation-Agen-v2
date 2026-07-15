"""
DocBot v3 — Deterministic step compiler.

Converts recorded Event objects into a Step skeleton WITHOUT any LLM.
This is the "ground truth" layer (Principle P1): steps are *compiled*
from observed user actions, then *polished* by the LLM in the generator.

Rules
-----
- Consecutive ``input`` events on different fields of the same form are
  folded into a single parent step: "Enter the following details:"
  with child steps for each field.
- A ``click`` on a button/link → "Click on the <Name> button."
- A ``navigate`` event following a click → result step
  "The <title> page will be displayed." (kind=result)
- ``keypress_enter`` on an input → same as click on the submit button.
- ``submit`` without a preceding enter → "Click on the Submit button."
- ``change`` on a select → "Select <value> from the <Field> dropdown."

Step numbers are 1-indexed and reset for every call.
"""

from __future__ import annotations

from typing import Sequence

from docbot.models import Event, Step


def compile_steps(events: Sequence[Event]) -> list[Step]:
    """
    Compile a list of Steps from the recorded Event sequence.

    Args:
        events: Ordered list of events for one screen.

    Returns:
        List of Step objects suitable for LLM polishing.
    """
    steps: list[Step] = []
    n = 1
    i = 0

    while i < len(events):
        ev = events[i]

        # ── Input grouping ──────────────────────────────────────────────
        if ev.kind == "input":
            # Collect consecutive input events
            group = [ev]
            j = i + 1
            while j < len(events) and events[j].kind in ("input", "change"):
                group.append(events[j])
                j += 1

            if len(group) == 1:
                # Single field → simple step
                field_name = _field_display(ev)
                step_text = f"Enter the {field_name}."
                if ev.redacted:
                    step_text = f"Enter the {field_name}."
                steps.append(Step(n=n, text=step_text, kind="action", event_id=ev.id))
                n += 1
            else:
                # Multiple fields → group them
                steps.append(Step(
                    n=n,
                    text="Enter the following details:",
                    kind="action",
                    event_id=ev.id,
                ))
                n += 1
                for field_ev in group:
                    field_name = _field_display(field_ev)
                    steps.append(Step(
                        n=n,
                        text=f"  {field_name}.",
                        kind="action",
                        event_id=field_ev.id,
                    ))
                    n += 1

            i = j
            continue

        # ── Change (select / checkbox / radio) ──────────────────────────
        if ev.kind == "change":
            field_name = _field_display(ev)
            value = ev.value_summary or ""
            if value:
                step_text = f"Select {value!r} from the {field_name} dropdown."
            else:
                step_text = f"Select the appropriate option in the {field_name} field."
            steps.append(Step(n=n, text=step_text, kind="action", event_id=ev.id))
            n += 1
            i += 1
            continue

        # ── Click on button/link ─────────────────────────────────────────
        if ev.kind == "click":
            name = ev.target_name or "button"
            role = (ev.target_role or "").lower()
            if "button" in role or "link" in role:
                step_text = f"Click on the {name} button."
            else:
                step_text = f"Click on {name}."
            steps.append(Step(n=n, text=step_text, kind="action", event_id=ev.id))
            n += 1

            # Look-ahead: was the next event a navigation?
            if i + 1 < len(events) and events[i + 1].kind == "navigate":
                nav_ev = events[i + 1]
                page_title = nav_ev.target_name or "the next page"
                steps.append(Step(
                    n=n,
                    text=f"The {page_title} page will be displayed.",
                    kind="result",
                    event_id=nav_ev.id,
                ))
                n += 1
                i += 2   # skip the navigate we already consumed
                continue

            i += 1
            continue

        # ── Enter key (implicit submit) ──────────────────────────────────
        if ev.kind == "keypress_enter":
            name = ev.target_name or "field"
            steps.append(Step(
                n=n,
                text=f"Press Enter to submit the {name}.",
                kind="action",
                event_id=ev.id,
            ))
            n += 1
            # Look-ahead for navigation
            if i + 1 < len(events) and events[i + 1].kind == "navigate":
                nav_ev = events[i + 1]
                page_title = nav_ev.target_name or "the next page"
                steps.append(Step(
                    n=n,
                    text=f"The {page_title} page will be displayed.",
                    kind="result",
                    event_id=nav_ev.id,
                ))
                n += 1
                i += 2
                continue
            i += 1
            continue

        # ── Submit ───────────────────────────────────────────────────────
        if ev.kind == "submit":
            steps.append(Step(
                n=n,
                text="Click on the Submit button.",
                kind="action",
                event_id=ev.id,
            ))
            n += 1
            i += 1
            continue

        # ── Navigate (standalone, not after a click) ──────────────────────
        if ev.kind == "navigate":
            if ev.url_after and ev.url_before != ev.url_after:
                page_title = ev.target_name or "the next page"
                steps.append(Step(
                    n=n,
                    text=f"The {page_title} page will be displayed.",
                    kind="result",
                    event_id=ev.id,
                ))
                n += 1
            i += 1
            continue

        # ── Unknown / skip ────────────────────────────────────────────────
        i += 1

    return steps


def _field_display(ev: Event) -> str:
    """Best display name for the field referenced in an event."""
    return (ev.target_name or ev.target_selector or "field").strip()
