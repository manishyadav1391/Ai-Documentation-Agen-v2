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
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal

from loguru import logger
from pydantic import BaseModel, field_validator, model_validator

from providers.base import Provider, load_prompt, GenerationError

if TYPE_CHECKING:
    from docbot.models import Screen, SessionModel, ScreenContent


# ---------------------------------------------------------------------------
# Response schema (pydantic v2) — matches the v3 prompt OUTPUT FORMAT
# ---------------------------------------------------------------------------

class _Lenient(BaseModel):
    """Base for LLM reply models: a ``null`` value means "use the default"."""

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


def _str_list(value: Any) -> Any:
    """Accept a bare string or a list with nulls for a ``list[str]`` field."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return value


class _RegionLabel(_Lenient):
    id: str
    label: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def _id_to_str(cls, v: Any) -> Any:
        return str(v) if isinstance(v, (int, float)) else v


class _FieldDetail(_Lenient):
    id: str
    field_name: str = ""
    utility: str = ""
    information: str = ""
    sample: str = ""


class _Step(_Lenient):
    n: int = 0
    text: str = ""
    kind: Literal["action", "result"] = "action"
    event_id: str | None = None

    @field_validator("n", mode="before")
    @classmethod
    def _parse_n(cls, v: Any) -> Any:
        if isinstance(v, str):
            m = re.match(r"\s*(\d+)", v)
            return int(m.group(1)) if m else 0
        return v

    @field_validator("kind", mode="before")
    @classmethod
    def _norm_kind(cls, v: Any) -> str:
        """Anything other than a result (note, info, '', 'Action') is an action."""
        return "result" if str(v).strip().lower() == "result" else "action"


class _DocItem(_Lenient):
    name: str = ""
    description: str = ""
    control_type: str = ""


class _DocSection(_Lenient):
    title: str = ""
    lead_in: str = ""
    items: list[_DocItem] = []


# A usable screen reply must have a non-empty value for at least one of these
_SCREEN_CONTENT_KEYS = ("screen_name", "intro", "sections", "purpose", "navigation_sentence", "steps")


class ScreenDocResponse(_Lenient):
    """Parsed LLM response for a single screen."""
    screen_name: str = ""
    screen_type: str = "other"
    intro: str = ""
    sections: list[_DocSection] = []
    purpose: str = ""
    navigation_sentence: str = ""
    regions: list[_RegionLabel] = []
    fields: list[_FieldDetail] = []
    steps: list[_Step] = []
    notes: list[str] = []
    table_columns_doc: list[str] = []
    buttons_doc: list[str] = []

    @field_validator("notes", "table_columns_doc", "buttons_doc", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> Any:
        return _str_list(v)

    @model_validator(mode="before")
    @classmethod
    def _require_content(cls, data: Any) -> Any:
        """Reject ``{}`` or a reply with none of the expected keys (it would wipe the screen)."""
        if isinstance(data, dict) and not any(data.get(k) for k in _SCREEN_CONTENT_KEYS):
            raise ValueError(
                "Reply contains none of the required keys with content: "
                + ", ".join(_SCREEN_CONTENT_KEYS)
            )
        return data


class ModuleIntroResponse(_Lenient):
    """Parsed LLM response for the module intro."""
    intro: str = ""
    features: list[str] = []

    @field_validator("features", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> Any:
        return _str_list(v)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class Generator:
    """
    Orchestrates LLM generation for all screens in a session.

    Args:
        provider: The active LLM provider instance.
    """

    _PROMPT_VERSION = "v4-1"  # bump to invalidate all caches when prompt changes

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
        progress_callback: Callable[[str], None] | None = None,
        session_dir: Path | None = None,
    ) -> ScreenDocResponse:
        """
        Generate documentation for a single screen.

        Args:
            session:        The full session model (provides module context).
            screen:         The screen to document.
            client_profile: Optional dict with voice, glossary, field_style keys.
            progress_callback: Optional callback for reporting status updates.
            session_dir:    Session folder; needed to attach the screenshot and
                            to write the llm/ prompt logs in the right place.

        Returns:
            ``ScreenDocResponse`` validated pydantic model.
        """
        if progress_callback:
            progress_callback(f"Preparing prompt context for Screen {screen.index}…")

        profile = client_profile or {}
        voice_examples = _format_voice_examples(profile.get("voice", {}))
        glossary_terms = _format_glossary(profile.get("glossary", {}))
        field_style = profile.get("style", {}).get("fields", {}).get("style", "table")
        app_name = profile.get("voice", {}).get("app_name", "Enterprise Application")
        client_display_name = profile.get("manifest", {}).get("client_display_name", app_name)
        audience = _audience(profile)
        house_style = profile.get("house_style") or _default_house_style()

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
                "element_class": el.element_class,
                "max_length": el.max_length,
                "pos": [int(el.bounding_box.x), int(el.bounding_box.y)] if el.bounding_box else None,
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
            version="v4",
            app_name=app_name,
            client_display_name=client_display_name,
            audience=audience,
            house_style=house_style,
            arrival_json=json.dumps(_arrival_context(session, screen), indent=2),
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

        if progress_callback:
            progress_callback(f"Screen {screen.index}: calling LLM ({self.provider.name})…")
        logger.info(f"[Generator] Screen {screen.index}: calling LLM ({self.provider.name})…")

        # Log the full prompt to the session LLM log
        _log_prompt(session, screen.index, prompt, session_dir)

        # Attach the screenshot (paths in the model are relative to the session dir)
        images: list[Path] = []
        shot = _screenshot_path(screen, session_dir)
        if shot is not None:
            images = [shot]

        try:
            result = self.provider.chat_json(
                prompt=prompt,
                schema=ScreenDocResponse,
                images=images or None,
                temperature=0.1,  # max_tokens: the provider's configured value
            )
        except GenerationError as e:
            logger.error(f"[Generator] Screen {screen.index}: generation failed: {e}")
            raise

        # Log the raw response
        _log_response(session, screen.index, result.model_dump_json(indent=2), session_dir)

        # Merge by id back into screen model
        _merge_result_into_screen(screen, result, content_hash)

        logger.info(
            f"[Generator] Screen {screen.index}: generated '{result.screen_name}' "
            f"({len(result.sections)} sections, {len(result.fields)} fields, "
            f"{len(result.steps)} steps, screenshot={'yes' if images else 'no'})."
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
            version="v4",
            app_name=app_name,
            client_display_name=client_display_name,
            audience=_audience(profile),
            module_name=_display_module_name(session.module_name),
            screens_json=json.dumps(screens_info, indent=2),
            voice_examples=voice_examples,
        )

        logger.info(f"[Generator] Generating module intro for '{session.module_name}'…")
        try:
            result = self.provider.chat_json(
                prompt=prompt,
                schema=ModuleIntroResponse,
                temperature=0.15,  # max_tokens: the provider's configured value
            )
        except GenerationError as e:
            logger.warning(f"[Generator] Module intro generation failed: {e}. Using fallback.")
            fallback = ModuleIntroResponse(
                intro=(
                    f"The {_display_module_name(session.module_name)} module enables users "
                    f"to manage related processes within {app_name}."
                ),
                features=[s.get("name", "") for s in screens_info if s.get("name")],
            )
            # Write into the session, but keep an existing (e.g. user-edited) intro
            if not session.module_intro:
                session.module_intro = fallback.intro
            if not session.module_features:
                session.module_features = fallback.features
            return fallback

        # Write into session model
        session.module_intro = result.intro
        session.module_features = result.features
        logger.info(f"[Generator] Module intro complete ({len(result.features)} features).")
        return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _display_module_name(name: str) -> str:
    """Folder-derived names arrive in lower case ("workflow automation")."""
    name = (name or "").strip() or "Module"
    return name.title() if name == name.lower() else name


def _audience(profile: dict) -> str:
    return (profile.get("voice", {}) or {}).get("audience") or "users"


def _default_house_style() -> str:
    try:
        return load_prompt("house_style", version="v4")
    except FileNotFoundError:
        return ""


def _screenshot_path(screen: "Screen", session_dir: Path | None) -> Path | None:
    """Resolve the screen's screenshot to an existing file (names are session-relative)."""
    for name in (screen.screenshot, screen.viewport_screenshot):
        if not name:
            continue
        p = Path(name)
        if not p.is_absolute() and session_dir is not None:
            p = Path(session_dir) / p
        if p.is_file():
            return p
    return None


def _arrival_context(session: "SessionModel", screen: "Screen") -> dict:
    """How the user got to this screen: previous screen + what was clicked there."""
    screens = list(session.screens)
    if screen.state_of is not None:
        prev = next((s for s in screens if s.index == screen.state_of), None)
    else:
        earlier = [s for s in screens if s.index < screen.index and s.state_of is None]
        prev = earlier[-1] if earlier else None
    info: dict = {"menu_trail": screen.nav_trail, "breadcrumb": screen.breadcrumb}
    if screen.state_of is not None:
        info["note"] = f"This is a state of the parent screen ({screen.state_label or 'dialog/pop-up'})."
    if prev is None:
        info["previous_screen"] = None
        return info
    info["previous_screen"] = prev.content.screen_name or prev.title or f"Screen {prev.index}"
    clicks = [e for e in prev.events if e.kind in ("click", "submit", "navigate") and e.target_name]
    if clicks:
        last = clicks[-1]
        info["clicked_on_previous_screen"] = {"name": last.target_name, "role": last.target_role}
    return info


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


def _log_dir_for(session: "SessionModel", session_dir: Path | None) -> Path:
    if session_dir is not None:
        return Path(session_dir) / "llm"
    from docbot import paths
    return paths.sessions_dir() / session.session_id / "llm"


def _log_prompt(session: "SessionModel", screen_index: int, prompt: str,
                session_dir: Path | None = None) -> None:
    try:
        import datetime
        log_dir = _log_dir_for(session, session_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%H%M%S")
        (log_dir / f"screen_{screen_index}_{ts}_prompt.txt").write_text(prompt, encoding="utf-8")
    except Exception as e:
        logger.debug(f"Could not write prompt log: {e}")


def _log_response(session: "SessionModel", screen_index: int, response: str,
                  session_dir: Path | None = None) -> None:
    try:
        import datetime
        log_dir = _log_dir_for(session, session_dir)
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
    """
    Merge LLM result by id into the screen model.

    Only keys present in the reply are applied (a missing / null key keeps
    the existing value).  All values are converted before anything is
    assigned, so a bad value cannot leave the screen half-written, and
    ``content_hash`` is set last.
    """
    from docbot.models import DocItem, DocSection, Step

    present = result.model_fields_set
    content = screen.content

    # Build every new value before touching the screen
    updates: dict = {}
    if "screen_name" in present and result.screen_name.strip():
        updates["screen_name"] = result.screen_name
    for key in ("intro", "purpose", "navigation_sentence"):
        if key in present:
            updates[key] = getattr(result, key)
    if "sections" in present:
        updates["sections"] = [
            DocSection(
                title=sec.title,
                lead_in=sec.lead_in,
                items=[DocItem(**it.model_dump()) for it in sec.items if it.name.strip()],
            )
            for sec in result.sections
            if any(it.name.strip() for it in sec.items)
        ]
    for key in ("notes", "buttons_doc", "table_columns_doc"):
        if key in present:
            updates[key] = list(getattr(result, key))
    if "steps" in present:
        llm_steps = [st for st in result.steps if st.text.strip()]
        # Replace the skeleton with the LLM-polished version
        updates["steps"] = [
            Step(n=st.n if st.n > 0 else pos, text=st.text, kind=st.kind, event_id=st.event_id)
            for pos, st in enumerate(llm_steps, start=1)
        ]
    region_labels = {r.id: r.label for r in result.regions if r.label.strip()}

    # Apply
    for key, value in updates.items():
        setattr(content, key, value)

    # Merge region labels by id (an empty label never wipes an existing one)
    for region in screen.regions:
        if region.id in region_labels:
            region.label = region_labels[region.id]

    # Merge field details by id
    field_map = {f.id: f for f in screen.fields}
    for f_detail in result.fields:
        if f_detail.id in field_map:
            field = field_map[f_detail.id]
            field.field_name = f_detail.field_name or field.field_name
            field.utility = f_detail.utility
            field.information = f_detail.information
            field.sample = f_detail.sample  # empty string → skip in export

    content.content_hash = content_hash


def _content_to_response(content: "ScreenContent") -> ScreenDocResponse:
    """Re-wrap cached ScreenContent as a ScreenDocResponse for uniform return type."""
    # model_construct: cached content is trusted and may legitimately be empty
    return ScreenDocResponse.model_construct(
        screen_name=content.screen_name,
        intro=content.intro,
        sections=[_DocSection(**sec.model_dump()) for sec in content.sections],
        purpose=content.purpose,
        navigation_sentence=content.navigation_sentence,
        steps=[_Step(n=s.n, text=s.text, kind=s.kind, event_id=s.event_id)
               for s in content.steps],
        notes=content.notes,
        buttons_doc=content.buttons_doc,
        table_columns_doc=content.table_columns_doc,
    )
