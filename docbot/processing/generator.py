"""
docbot.processing.generator — v3 screen documentation generator.

Replaces the old Labeler class with a single-call-per-screen LLM interface.
The generator reads from the Session model, calls the provider once per
screen (vision-capable or text-only), and writes results back into the model.

Key design decisions
--------------------
- ONE LLM call per screen, returning a fully-structured JSON object.
- Merging by ``id`` (not index) — so a dropped/reordered field cannot
  corrupt adjacent fields (fixes W11).
- Content-hash caching: only regenerate when the prompt inputs change.
- Vision is conditional: images passed when provider.chat_vision is
  overridden AND a screenshot file exists. Text-only path always works.
- ``generate_module_intro`` produces the module preamble paragraph.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel

from providers.base import Provider, load_prompt, GenerationError

if TYPE_CHECKING:
    from docbot.models import Screen, SessionModel, ScreenContent


# ---------------------------------------------------------------------------
# Response schema (pydantic v2) — matches the v3 prompt OUTPUT FORMAT
# ---------------------------------------------------------------------------

class _RegionLabel(BaseModel):
    id: str
    label: str


class _FieldDetail(BaseModel):
    id: str
    field_name: str = ""
    utility: str = ""
    information: str = ""
    sample: str = ""


class _Step(BaseModel):
    n: int
    text: str
    kind: str = "action"
    event_id: str | None = None


class ScreenDocResponse(BaseModel):
    """Parsed LLM response for a single screen."""
    screen_name: str = ""
    screen_type: str = "other"
    purpose: str = ""
    navigation_sentence: str = ""
    regions: list[_RegionLabel] = []
    fields: list[_FieldDetail] = []
    steps: list[_Step] = []
    notes: list[str] = []
    table_columns_doc: list[str] = []
    buttons_doc: list[str] = []


class ModuleIntroResponse(BaseModel):
    """Parsed LLM response for the module intro."""
    intro: str = ""
    features: list[str] = []


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class Generator:
    """
    Orchestrates LLM generation for all screens in a session.

    Args:
        provider: The active LLM provider instance.
    """

    _PROMPT_VERSION = "v3-1"  # bump to invalidate all caches when prompt changes

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate_screen(
        self,
        session: "SessionModel",
        screen: "Screen",
        client_profile: dict | None = None,
    ) -> ScreenDocResponse:
        """
        Generate documentation for a single screen.

        Args:
            session:        The full session model (provides module context).
            screen:         The screen to document.
            client_profile: Optional dict with voice, glossary, field_style keys.

        Returns:
            ``ScreenDocResponse`` validated pydantic model.
        """
        profile = client_profile or {}
        voice_examples = _format_voice_examples(profile.get("voice", {}))
        glossary_terms = _format_glossary(profile.get("glossary", {}))
        field_style = profile.get("style", {}).get("fields", {}).get("style", "table")
        app_name = profile.get("voice", {}).get("app_name", "Enterprise Application")
        client_display_name = profile.get("manifest", {}).get("client_display_name", app_name)

        # Build context objects for the prompt
        screen_context = {
            "url": screen.url,
            "title": screen.title,
            "h1_text": screen.h1_text,
            "breadcrumb": screen.breadcrumb,
            "nav_trail": screen.nav_trail,
            "screen_index": screen.index,
            "module_name": session.module_name,
        }

        # Prepare element list (only meaningful interactive + nav + static)
        elements_with_ids = [
            {
                "id": el.id or f"el_{i}",
                "tag": el.tag,
                "type": el.type,
                "role": el.role,
                "accessible_name": el.accessible_name,
                "required": el.required,
                "placeholder": el.placeholder,
                "ancestor_section": el.ancestor_section,
                "bounding_box": el.bounding_box.model_dump() if el.bounding_box else None,
            }
            for i, el in enumerate(screen.elements)
        ]

        # Prepare region list with ids
        regions_with_ids = [
            {
                "id": r.id,
                "role": r.role,
                "elements_contained": r.elements_contained,
                "bounding_box": r.bounding_box.model_dump() if r.bounding_box else None,
            }
            for r in screen.regions
            if not r.deleted
        ]

        # Prepare events list (pre-compiled skeleton steps from steps.py)
        events_list = [
            {
                "id": ev.id,
                "kind": ev.kind,
                "target_name": ev.target_name,
                "target_role": ev.target_role,
                "value_summary": ev.value_summary if not ev.redacted else "<redacted>",
                "url_before": ev.url_before,
                "url_after": ev.url_after,
            }
            for ev in screen.events
        ]

        prompt = load_prompt(
            "screen_documentation",
            version="v3",
            app_name=app_name,
            client_display_name=client_display_name,
            screen_context_json=json.dumps(screen_context, indent=2),
            elements_json=json.dumps(elements_with_ids, indent=2),
            regions_json=json.dumps(regions_with_ids, indent=2),
            events_json=json.dumps(events_list, indent=2) if events_list else "[]",
            voice_examples=voice_examples,
            glossary_terms=glossary_terms,
            field_style=field_style,
        )

        # Content-hash caching
        content_hash = _compute_hash(self._PROMPT_VERSION, prompt)
        if screen.content.content_hash == content_hash:
            logger.info(
                f"[Generator] Screen {screen.index}: cache hit (hash={content_hash[:8]}). "
                "Skipping LLM call."
            )
            # Return the cached content re-parsed into the response schema
            return _content_to_response(screen.content)

        logger.info(f"[Generator] Screen {screen.index}: calling LLM ({self.provider.name})…")

        # Log the full prompt to the session LLM log
        _log_prompt(session, screen.index, prompt)

        # Determine if we can pass a screenshot
        images: list[Path] = []
        if screen.screenshot and Path(screen.screenshot).exists():
            images = [Path(screen.screenshot)]

        try:
            result = self.provider.chat_json(
                prompt=prompt,
                schema=ScreenDocResponse,
                images=images or None,
                max_tokens=8000,
                temperature=0.1,
            )
        except GenerationError as e:
            logger.error(f"[Generator] Screen {screen.index}: generation failed: {e}")
            raise

        # Log the raw response
        _log_response(session, screen.index, result.model_dump_json(indent=2))

        # Merge by id back into screen model
        _merge_result_into_screen(screen, result, content_hash)

        logger.info(
            f"[Generator] Screen {screen.index}: generated '{result.screen_name}' "
            f"({len(result.fields)} fields, {len(result.steps)} steps)."
        )
        return result

    def generate_module_intro(
        self,
        session: "SessionModel",
        client_profile: dict | None = None,
    ) -> ModuleIntroResponse:
        """
        Generate the module introduction paragraph and feature bullets.

        Args:
            session:        The full session model.
            client_profile: Optional dict with voice keys.

        Returns:
            ``ModuleIntroResponse`` pydantic model.
        """
        profile = client_profile or {}
        voice_examples = _format_voice_examples(profile.get("voice", {}))
        app_name = profile.get("voice", {}).get("app_name", "Enterprise Application")
        client_display_name = profile.get("manifest", {}).get("client_display_name", app_name)

        screens_info = [
            {"name": s.content.screen_name or s.title, "purpose": s.content.purpose}
            for s in session.screens
            if s.state_of is None  # skip state captures
        ]

        prompt = load_prompt(
            "module_intro",
            version="v3",
            app_name=app_name,
            client_display_name=client_display_name,
            module_name=session.module_name or "Module",
            screens_json=json.dumps(screens_info, indent=2),
            voice_examples=voice_examples,
        )

        logger.info(f"[Generator] Generating module intro for '{session.module_name}'…")
        try:
            result = self.provider.chat_json(
                prompt=prompt,
                schema=ModuleIntroResponse,
                max_tokens=2000,
                temperature=0.15,
            )
        except GenerationError as e:
            logger.warning(f"[Generator] Module intro generation failed: {e}. Using fallback.")
            return ModuleIntroResponse(
                intro=(
                    f"The {session.module_name} module enables users to manage related "
                    f"processes within {app_name}."
                ),
                features=[s.get("name", "") for s in screens_info],
            )

        # Write into session model
        session.module_intro = result.intro
        session.module_features = result.features
        logger.info(f"[Generator] Module intro complete ({len(result.features)} features).")
        return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _format_voice_examples(voice: dict) -> str:
    if not voice:
        return "(No specific voice guidelines provided.)"
    lines = []
    tone_rules = voice.get("tone_rules", [])
    if tone_rules:
        lines.append("Tone rules:")
        for rule in tone_rules:
            lines.append(f"  - {rule}")
    examples = voice.get("examples", {})
    if examples.get("purpose"):
        lines.append("\nExample purpose sentences:")
        for ex in examples["purpose"]:
            lines.append(f'  "{ex}"')
    if examples.get("step"):
        lines.append("\nExample step sentences:")
        for ex in examples["step"]:
            lines.append(f'  "{ex}"')
    if examples.get("field"):
        lines.append("\nExample field bullets:")
        for ex in examples["field"]:
            lines.append(f'  "{ex}"')
    nav_template = voice.get("navigation_template")
    if nav_template:
        lines.append(f'\nNavigation template: "{nav_template}"')
    return "\n".join(lines) if lines else "(No specific voice guidelines provided.)"


def _format_glossary(glossary: dict) -> str:
    if not glossary:
        return "(No glossary terms defined.)"
    lines = [f'  - "{k}": {v}' for k, v in glossary.items()]
    return "\n".join(lines)


def _compute_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
    return h.hexdigest()


def _log_prompt(session: "SessionModel", screen_index: int, prompt: str) -> None:
    try:
        from pathlib import Path
        import datetime
        session_dir = Path(f"sessions/{session.session_id}")
        log_dir = session_dir / "llm"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%H%M%S")
        (log_dir / f"screen_{screen_index}_{ts}_prompt.txt").write_text(prompt, encoding="utf-8")
    except Exception as e:
        logger.debug(f"Could not write prompt log: {e}")


def _log_response(session: "SessionModel", screen_index: int, response: str) -> None:
    try:
        from pathlib import Path
        import datetime
        session_dir = Path(f"sessions/{session.session_id}")
        log_dir = session_dir / "llm"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%H%M%S")
        (log_dir / f"screen_{screen_index}_{ts}_response.json").write_text(response, encoding="utf-8")
    except Exception as e:
        logger.debug(f"Could not write response log: {e}")


def _merge_result_into_screen(
    screen: "Screen",
    result: ScreenDocResponse,
    content_hash: str,
) -> None:
    """Merge LLM result by id into the screen model."""
    from docbot.models import Field, Step, Region, ScreenContent

    # Update content fields
    screen.content.screen_name = result.screen_name or screen.content.screen_name
    screen.content.purpose = result.purpose
    screen.content.navigation_sentence = result.navigation_sentence
    screen.content.notes = result.notes
    screen.content.buttons_doc = result.buttons_doc
    screen.content.table_columns_doc = result.table_columns_doc
    screen.content.content_hash = content_hash

    # Merge steps (replace skeleton with LLM-polished version)
    screen.content.steps = [
        Step(
            n=s.n,
            text=s.text,
            kind=s.kind,  # type: ignore[arg-type]
            event_id=s.event_id,
        )
        for s in result.steps
    ]

    # Merge region labels by id
    region_map = {r.id: r for r in screen.regions}
    for r_label in result.regions:
        if r_label.id in region_map:
            region_map[r_label.id].label = r_label.label

    # Merge field details by id
    field_map = {f.id: f for f in screen.fields}
    for f_detail in result.fields:
        if f_detail.id in field_map:
            field = field_map[f_detail.id]
            field.field_name = f_detail.field_name or field.field_name
            field.utility = f_detail.utility
            field.information = f_detail.information
            field.sample = f_detail.sample  # empty string → skip in export


def _content_to_response(content: "ScreenContent") -> ScreenDocResponse:
    """Re-wrap cached ScreenContent as a ScreenDocResponse for uniform return type."""
    return ScreenDocResponse(
        screen_name=content.screen_name,
        purpose=content.purpose,
        navigation_sentence=content.navigation_sentence,
        steps=[_Step(n=s.n, text=s.text, kind=s.kind, event_id=s.event_id)
               for s in content.steps],
        notes=content.notes,
        buttons_doc=content.buttons_doc,
        table_columns_doc=content.table_columns_doc,
    )
