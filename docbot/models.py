"""
DocBot v3 — typed session data model.

Everything the pipeline reads and writes is expressed here.
A ``SessionModel`` is the single source of truth for a recording session;
it is serialised as ``session.json`` in the session directory.

Migration
---------
Call ``migrate_legacy(session_dir)`` to convert old ``screen_N_*.json``
files into a ``session.json``.  Existing sessions remain usable without
any manual intervention.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from loguru import logger
from pydantic import BaseModel, Field as PydanticField, model_validator


# ---------------------------------------------------------------------------
# Primitive shapes
# ---------------------------------------------------------------------------

class BBox(BaseModel):
    """Bounding box in document coordinates (CSS pixels, scroll-adjusted)."""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    def iou(self, other: "BBox") -> float:
        """Intersection over Union with another BBox."""
        ix1 = max(self.x, other.x)
        iy1 = max(self.y, other.y)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)
        inter_w = max(0.0, ix2 - ix1)
        inter_h = max(0.0, iy2 - iy1)
        inter = inter_w * inter_h
        union = self.width * self.height + other.width * other.height - inter
        return inter / union if union > 0 else 0.0

    def contains(self, other: "BBox") -> bool:
        """Return True if *other* is fully contained in self."""
        return (
            self.x <= other.x and self.y <= other.y
            and self.x2 >= other.x2 and self.y2 >= other.y2
        )


# ---------------------------------------------------------------------------
# DOM element
# ---------------------------------------------------------------------------

class Element(BaseModel):
    """A single DOM element extracted from the page."""
    id: str = ""
    element_class: str = "interactive"    # interactive | navigation | static_label | table_column
    tag: str = "input"
    type: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    accessible_name: Optional[str] = None
    required: bool = False
    placeholder: Optional[str] = None
    pattern: Optional[str] = None
    max_length: Optional[int] = None
    bounding_box: BBox = PydanticField(default_factory=BBox)
    ancestor_section: Optional[str] = None
    form_id: Optional[str] = None          # closest form's id/name
    is_fixed: bool = False                 # position:fixed or sticky


# ---------------------------------------------------------------------------
# Recorded event
# ---------------------------------------------------------------------------

class Event(BaseModel):
    """A single recorded user interaction."""
    id: str = PydanticField(default_factory=lambda: str(uuid.uuid4())[:8])
    ts: float = PydanticField(default_factory=lambda: datetime.now().timestamp())
    kind: Literal["click", "input", "change", "submit", "navigate", "keypress_enter"] = "click"
    target_selector: Optional[str] = None
    target_name: Optional[str] = None
    target_role: Optional[str] = None
    target_bbox: Optional[BBox] = None
    value_summary: Optional[str] = None
    redacted: bool = False
    url_before: Optional[str] = None
    url_after: Optional[str] = None
    screenshot_before: Optional[str] = None   # relative path in session dir
    screenshot_after: Optional[str] = None    # relative path in session dir
    page_id: str = "main"                     # for multi-tab tracking


# ---------------------------------------------------------------------------
# Detected region
# ---------------------------------------------------------------------------

class Region(BaseModel):
    """A semantic region on a screen (form section, nav bar, table, etc.)."""
    id: str = ""
    role: str = "filter_form"
    bounding_box: BBox = PydanticField(default_factory=BBox)
    elements_contained: list[str] = PydanticField(default_factory=list)
    label: str = ""
    deleted: bool = False


# ---------------------------------------------------------------------------
# Field detail (LLM-populated)
# ---------------------------------------------------------------------------

class FieldDetail(BaseModel):
    """Documentation for one interactive form field."""
    id: str = ""                # echoes Element.id
    element_id: str = ""
    field_name: str = ""
    utility: str = ""
    information: str = ""
    sample: str = ""
    section_label: str = ""


# ---------------------------------------------------------------------------
# Step (either compiled from events or LLM-polished)
# ---------------------------------------------------------------------------

class Step(BaseModel):
    """One numbered step in the screen's procedure."""
    n: int
    text: str
    kind: Literal["action", "result"] = "action"
    event_id: Optional[str] = None
    crop_path: Optional[str] = None      # inline image for NCD style


# ---------------------------------------------------------------------------
# Figure (screenshot / scroll segment / state capture)
# ---------------------------------------------------------------------------

class Figure(BaseModel):
    """One figure (screenshot segment) for a screen."""
    index: int
    path: str                            # relative path in session dir
    caption_note: str = ""
    source: Literal["viewport", "full_page"] = "viewport"
    scroll_y: float = 0.0               # scroll position at capture time
    content_hash: str = ""              # for deduplication of sticky headers


# ---------------------------------------------------------------------------
# Screen-level LLM content (what the generator writes)
# ---------------------------------------------------------------------------

class ScreenContent(BaseModel):
    """LLM-generated content for a screen."""
    screen_name: str = ""
    purpose: str = ""
    navigation_sentence: str = ""
    path: str = ""
    steps: list[Step] = PydanticField(default_factory=list)
    notes: list[str] = PydanticField(default_factory=list)
    buttons_doc: list[str] = PydanticField(default_factory=list)
    table_columns_doc: list[str] = PydanticField(default_factory=list)
    content_hash: str = ""              # sha256 of prompt inputs for cache


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

class Screen(BaseModel):
    """One captured screen (or state) within a session."""
    index: int
    state_of: Optional[int] = None      # parent screen index, or None
    state_label: str = ""
    url: str = ""
    title: str = ""
    h1_text: str = ""
    breadcrumb: str = ""
    nav_trail: list[str] = PydanticField(default_factory=list)
    screenshot: str = ""                # primary (full_page or viewport) path
    viewport_screenshot: str = ""       # viewport path if mode=="both"
    device_pixel_ratio: float = 1.0
    elements: list[Element] = PydanticField(default_factory=list)
    events: list[Event] = PydanticField(default_factory=list)
    regions: list[Region] = PydanticField(default_factory=list)
    fields: list[FieldDetail] = PydanticField(default_factory=list)
    figures: list[Figure] = PydanticField(default_factory=list)
    content: ScreenContent = PydanticField(default_factory=ScreenContent)
    reviewed: bool = False


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SessionModel(BaseModel):
    """The top-level session document — one per recording session."""
    schema_version: int = 1
    session_id: str = PydanticField(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    client_key: str = "default"
    module_name: str = ""
    module_number: Optional[int] = None
    module_intro: str = ""
    module_features: list[str] = PydanticField(default_factory=list)
    start_url: str = ""
    created_at: str = PydanticField(default_factory=lambda: datetime.now().isoformat())
    screens: list[Screen] = PydanticField(default_factory=list)


# ---------------------------------------------------------------------------
# Session store (load / save with atomic write)
# ---------------------------------------------------------------------------

class SessionStore:
    """Loads and saves ``session.json`` with atomic tmp-then-rename writes."""

    FILENAME = "session.json"

    @classmethod
    def load(cls, session_dir: Path) -> SessionModel:
        """Load ``session.json`` from *session_dir*, or return empty model."""
        path = session_dir / cls.FILENAME
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return SessionModel.model_validate(data)
            except Exception as e:
                logger.warning(f"Could not parse {path}: {e}. Starting fresh.")
        # Auto-migrate from legacy flat files if present
        return migrate_legacy(session_dir)

    @classmethod
    def save(cls, model: SessionModel, session_dir: Path) -> None:
        """Atomically write *model* to ``session.json`` in *session_dir*."""
        session_dir.mkdir(parents=True, exist_ok=True)
        target = session_dir / cls.FILENAME
        data = model.model_dump_json(indent=2)
        # Write to temp file then rename for atomicity
        fd, tmp_path = tempfile.mkstemp(
            dir=session_dir, prefix=".session_tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.debug(f"session.json saved ({len(data)} bytes) → {target}")


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------

def migrate_legacy(session_dir: Path) -> SessionModel:
    """
    Convert old ``screen_N_*.json`` flat files into a ``SessionModel``.

    This is a best-effort conversion; existing annotated PNGs and content
    are preserved by referencing their existing paths.

    Args:
        session_dir: Path to the session folder.

    Returns:
        A populated ``SessionModel`` (not yet saved to disk).
    """
    session_dir = Path(session_dir)
    meta_files = sorted(session_dir.glob("screen_*_meta.json"))

    if not meta_files:
        # Nothing to migrate; return a blank session
        logger.debug(f"[migrate_legacy] No legacy files found in {session_dir}.")
        return SessionModel(
            session_id=session_dir.name.replace("session_", ""),
        )

    logger.info(f"[migrate_legacy] Migrating {len(meta_files)} legacy screens in {session_dir.name}…")

    session = SessionModel(
        session_id=session_dir.name.replace("session_", ""),
    )

    for meta_path in meta_files:
        # Parse screen index from filename e.g. screen_1_meta.json → 1
        parts = meta_path.stem.split("_")
        try:
            idx = int(parts[1])
        except (IndexError, ValueError):
            continue

        # Skip state files (handled as figures)
        is_state = "state" in meta_path.stem
        if is_state:
            continue

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[migrate_legacy] Could not read {meta_path}: {e}")
            continue

        screen = Screen(
            index=idx,
            url=meta.get("url", ""),
            title=meta.get("title", ""),
            h1_text=meta.get("h1_text", ""),
            breadcrumb=meta.get("breadcrumb", ""),
            nav_trail=meta.get("nav_trail", []),
            state_of=meta.get("state_of"),
            state_label=meta.get("state_label", ""),
        )

        # Elements
        el_path = session_dir / f"screen_{idx}_elements.json"
        if el_path.exists():
            try:
                raw_els = json.loads(el_path.read_text(encoding="utf-8"))
                for i, el_dict in enumerate(raw_els):
                    bbox_raw = el_dict.get("bounding_box", {})
                    screen.elements.append(Element(
                        id=el_dict.get("id") or f"el_{i}",
                        element_class=el_dict.get("element_class", "interactive"),
                        tag=el_dict.get("tag", "input"),
                        type=el_dict.get("type"),
                        role=el_dict.get("role"),
                        name=el_dict.get("name"),
                        accessible_name=el_dict.get("accessible_name"),
                        required=bool(el_dict.get("required", False)),
                        placeholder=el_dict.get("placeholder"),
                        pattern=el_dict.get("pattern"),
                        bounding_box=BBox(**bbox_raw) if bbox_raw else BBox(),
                        ancestor_section=el_dict.get("ancestor_section"),
                    ))
            except Exception as e:
                logger.warning(f"[migrate_legacy] Could not read elements for screen {idx}: {e}")

        # Regions (from _final.json if available, else _regions.json)
        for regions_file in [
            session_dir / f"screen_{idx}_final.json",
            session_dir / f"screen_{idx}_regions.json",
        ]:
            if regions_file.exists():
                try:
                    raw_regions = json.loads(regions_file.read_text(encoding="utf-8"))
                    for j, r in enumerate(raw_regions):
                        bbox_raw = r.get("bounding_box", {})
                        screen.regions.append(Region(
                            id=f"r{j + 1}",
                            role=r.get("role", "filter_form"),
                            bounding_box=BBox(**bbox_raw) if bbox_raw else BBox(),
                            elements_contained=r.get("elements_contained", []),
                            label=r.get("label", ""),
                            deleted=bool(r.get("deleted", False)),
                        ))
                    break
                except Exception as e:
                    logger.warning(f"[migrate_legacy] Could not read regions for screen {idx}: {e}")

        # Content
        content_path = session_dir / f"screen_{idx}_content.json"
        if content_path.exists():
            try:
                content_raw = json.loads(content_path.read_text(encoding="utf-8"))
                screen_doc = content_raw.get("screen_documentation", {}) or {}
                screen.content = ScreenContent(
                    screen_name=(
                        meta.get("screen_name")
                        or content_raw.get("screen_name")
                        or ""
                    ),
                    purpose=content_raw.get("purpose", ""),
                    navigation_sentence=content_raw.get("navigation_instructions", ""),
                    path=content_raw.get("path", ""),
                    notes=screen_doc.get("notes", []),
                    buttons_doc=screen_doc.get("buttons", []),
                    table_columns_doc=screen_doc.get("table_columns", []),
                )
                # Migrate field_details
                for fd in content_raw.get("field_details", []):
                    screen.fields.append(PydanticField(
                        id=fd.get("field_name", "").replace(" ", "_")[:20] or f"f{len(screen.fields)}",
                        element_id="",
                        field_name=fd.get("field_name", ""),
                        utility=fd.get("utility", fd.get("description", "")),
                        information=fd.get("information", ""),
                        sample=fd.get("sample", ""),
                    ))
            except Exception as e:
                logger.warning(f"[migrate_legacy] Could not read content for screen {idx}: {e}")

        # Figures
        annot_path = session_dir / f"screen_{idx}_annotated.png"
        raw_path = session_dir / f"screen_{idx}.png"
        fig_path = annot_path if annot_path.exists() else raw_path
        if fig_path.exists():
            screen.screenshot = fig_path.name
            screen.figures.append(Figure(index=1, path=fig_path.name))

        # State sub-figures
        for state_file in sorted(session_dir.glob(f"screen_{idx}_state_*_annotated.png")):
            state_num_str = state_file.name.split("_state_")[1].split("_")[0]
            state_label = ""
            state_meta_p = session_dir / f"screen_{idx}_state_{state_num_str}_meta.json"
            if state_meta_p.exists():
                try:
                    sm = json.loads(state_meta_p.read_text(encoding="utf-8"))
                    state_label = sm.get("state_label", "")
                except Exception:
                    pass
            screen.figures.append(Figure(
                index=len(screen.figures) + 1,
                path=state_file.name,
                caption_note=state_label or f"State {state_num_str}",
            ))

        session.screens.append(screen)

    # Sort by index
    session.screens.sort(key=lambda s: s.index)
    logger.info(f"[migrate_legacy] Migration complete: {len(session.screens)} screens.")
    return session
