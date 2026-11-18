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
            group = _one_per_field(group)

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
            step_text = _change_text(ev)
            steps.append(Step(n=n, text=step_text, kind="action", event_id=ev.id))
            n += 1
            i += 1
            continue

        # ── Click on button/link ─────────────────────────────────────────
        if ev.kind == "click":
            name = ev.target_name or "button"
            role = (ev.target_role or "").lower()
            if "button" in role or "link" in role:
                if name.lower().endswith(" button") or name.lower() == "button":
                    step_text = f"Click on the {name}."
                else:
                    step_text = f"Click on the {name} button."
            else:
                step_text = f"Click on {name}."
            steps.append(Step(n=n, text=step_text, kind="action", event_id=ev.id))
            n += 1

            # The form submit triggered by this click is the same user action
            i = _skip_submits(events, i + 1)

            # Look-ahead: was the next event a navigation?
            if i < len(events) and events[i].kind == "navigate":
                nav_ev = events[i]
                steps.append(Step(
                    n=n,
                    text=_page_displayed(nav_ev),
                    kind="result",
                    event_id=nav_ev.id,
                ))
                n += 1
                i += 1   # skip the navigate we already consumed
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
            # The form submit triggered by Enter is the same user action
            i = _skip_submits(events, i + 1)
            # Look-ahead for navigation
            if i < len(events) and events[i].kind == "navigate":
                nav_ev = events[i]
                steps.append(Step(
                    n=n,
                    text=_page_displayed(nav_ev),
                    kind="result",
                    event_id=nav_ev.id,
                ))
                n += 1
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
                steps.append(Step(
                    n=n,
                    text=_page_displayed(ev),
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


def _page_displayed(nav_ev: Event) -> str:
    """Result sentence for a navigation ("The next page" when the title is unknown)."""
    title = (nav_ev.target_name or "").strip()
    if not title:
        return "The next page will be displayed."
    if title.lower().endswith(" page"):
        return f"The {title} will be displayed."
    return f"The {title} page will be displayed."


def _skip_submits(events: Sequence[Event], i: int) -> int:
    """Return the index of the first non-``submit`` event at or after *i*."""
    while i < len(events) and events[i].kind == "submit":
        i += 1
    return i


def _field_key(ev: Event) -> str:
    return (ev.target_selector or ev.target_name or ev.id or "").strip()


def _one_per_field(group: list[Event]) -> list[Event]:
    """Collapse repeated input events on one field (one per keystroke) to the last one."""
    last: dict[str, Event] = {}
    for ev in group:
        last[_field_key(ev)] = ev
    seen: set[str] = set()
    out: list[Event] = []
    for ev in group:
        key = _field_key(ev)
        if key not in seen:
            seen.add(key)
            out.append(last[key])
    return out


_CHECKED_VALUES = {"on", "true", "checked", "yes", "1"}
_UNCHECKED_VALUES = {"off", "false", "unchecked", "no", "0"}


def _change_text(ev: Event) -> str:
    """Step text for a ``change`` event on a select, checkbox, radio or other field."""
    field_name = _field_display(ev)
    value = (ev.value_summary or "").strip()
    role = (ev.target_role or "").lower()
    low = value.lower()
    if role in ("checkbox", "switch") or (not role and (low in _CHECKED_VALUES or low in _UNCHECKED_VALUES)):
        if low in _UNCHECKED_VALUES:
            return f"Clear the {field_name} checkbox."
        return f"Select the {field_name} checkbox."
    if role == "radio":
        if value and low not in _CHECKED_VALUES:
            return f"Select the {value} option for {field_name}."
        return f"Select the {field_name} option."
    if value and not ev.redacted:
        return f"Select {value!r} from the {field_name} dropdown."
    return f"Select the appropriate option in the {field_name} field."
