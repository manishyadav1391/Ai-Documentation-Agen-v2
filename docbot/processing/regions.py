"""
DocBot v3 — Region detection with IoU-merge and bug fixes.

Ports detect_regions.py into docbot.processing.regions operating on
pydantic Element models instead of raw dicts.

Fixes vs v2
-----------
- W10 (double-emit): filter/form detection now groups by actual form_id
  instead of one global union; the keyword pass adds individual elements
  only if not already in a form group.
- W13 (operator precedence): detect_page_header fixed with explicit parens.
- IoU-merge: after all detectors run, regions of the same role with
  IoU > 0.6 are merged (union bbox, concatenated elements, dedup).
  Regions fully contained within a same-role region are dropped.
- Stable ids: regions assigned r1..rN after merge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from loguru import logger

from docbot.models import BBox, Element, Region


_IOu_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# Heuristic detectors
# ---------------------------------------------------------------------------

def detect_page_header(elements: Sequence[Element]) -> list[Region]:
    """Detect H1 / H2 labels as page-header landmark regions (W13 fixed)."""
    regions = []
    for el in elements:
        # W13 fix: explicit parentheses
        is_h1 = el.tag == "h1"
        is_h2_label = (el.type == "label") and (el.tag in ("h1", "h2"))
        if is_h1 or is_h2_label:
            name = el.accessible_name or el.name or ""
            if name and el.bounding_box.width > 0:
                regions.append(Region(
                    role="page_header",
                    bounding_box=el.bounding_box,
                    elements_contained=[name],
                ))
    return regions


def detect_navigation_bar(elements: Sequence[Element]) -> list[Region]:
    """Group all navigation links into a single nav-bar region."""
    nav_els = [e for e in elements if e.element_class == "navigation"]
    if not nav_els:
        return []
    nav_items = [e.accessible_name or e.name or "" for e in nav_els if e.accessible_name or e.name]
    if not nav_items:
        return []
    return [Region(
        role="navigation_bar",
        bounding_box=_union_bbox([e.bounding_box for e in nav_els]),
        elements_contained=nav_items[:10],
    )]


def detect_filter_regions(elements: Sequence[Element]) -> list[Region]:
    """
    Detect filter/search form regions.

    W10 fix: group by form_id so multiple forms don't collapse into one
    giant union bbox.  The keyword pass only adds elements NOT already
    captured in a form group.
    """
    regions = []
    keywords = {"filter", "search", "criteria", "panel", "query"}

    # Group interactive elements by their form_id
    form_buckets: dict[str, list[Element]] = {}
    for el in elements:
        if el.element_class != "interactive":
            continue
        fid = el.form_id or el.ancestor_section
        if fid in ("form", None):
            fid = "ungrouped"
        if fid:
            form_buckets.setdefault(fid, []).append(el)

    captured_ids: set[str] = set()
    for fid, els in form_buckets.items():
        bboxes = [e.bounding_box for e in els if e.bounding_box.width > 0]
        if not bboxes:
            continue
        names = [e.accessible_name or e.name or e.placeholder or "Field" for e in els]
        ub = _union_bbox(bboxes)
        ub = BBox(x=max(0.0, ub.x - 10), y=max(0.0, ub.y - 10),
                  width=ub.width + 20, height=ub.height + 20)
        regions.append(Region(
            role="filter_form",
            bounding_box=ub,
            elements_contained=[n for n in names if n],
        ))
        captured_ids.update(id(e) for e in els)

    # Keyword pass — only for elements NOT already in a form group
    for el in elements:
        if el.element_class == "navigation" or id(el) in captured_ids:
            continue
        el_id = (el.id or "").lower()
        el_name = (el.name or "").lower()
        if any(kw in el_id or kw in el_name for kw in keywords):
            name = el.accessible_name or el.name or "Filter Field"
            if el.bounding_box.width > 0:
                regions.append(Region(
                    role="filter_form",
                    bounding_box=el.bounding_box,
                    elements_contained=[name],
                ))

    return regions


def detect_table_headers(elements: Sequence[Element]) -> list[Region]:
    """Group all <th> / columnheader elements into a single table region."""
    ths = [e for e in elements if e.element_class == "table_column"]
    if not ths:
        return []
    bboxes = [e.bounding_box for e in ths if e.bounding_box.width > 0]
    if not bboxes:
        return []
    return [Region(
        role="table_header",
        bounding_box=_union_bbox(bboxes),
        elements_contained=[e.accessible_name or "" for e in ths],
    )]


def detect_standalone_actions(elements: Sequence[Element]) -> list[Region]:
    """Detect standalone action buttons not inside a form or table."""
    regions = []
    seen_labels: set[str] = set()
    for el in elements:
        is_btn = el.tag == "button" or el.role == "button"
        if not is_btn or el.bounding_box.width < 30 or el.bounding_box.height < 18:
            continue
        if el.ancestor_section in ("table", "form"):
            continue
        label = el.accessible_name or el.name or ""
        if label in seen_labels:
            continue
        seen_labels.add(label)
        regions.append(Region(
            role="action_button",
            bounding_box=el.bounding_box,
            elements_contained=[label] if label else ["Button"],
        ))
    return regions


def detect_action_columns(elements: Sequence[Element]) -> list[Region]:
    """Detect action-column buttons (edit/delete/view) inside table rows."""
    action_kw = {"edit", "delete", "remove", "view", "details", "update", "modify", "open"}
    action_els = [
        e for e in elements
        if e.ancestor_section == "table" and e.element_class == "interactive"
        and any(kw in (e.accessible_name or e.name or "").lower() for kw in action_kw)
    ]
    if not action_els:
        return []
    bboxes = [e.bounding_box for e in action_els if e.bounding_box.width > 0]
    if not bboxes:
        return []
    unique_labels = list({e.accessible_name or e.name or "Action" for e in action_els})
    return [Region(
        role="action_column",
        bounding_box=_union_bbox(bboxes),
        elements_contained=unique_labels[:8],
    )]


def detect_section_labels(elements: Sequence[Element]) -> list[Region]:
    """Detect H2/H3/H4 section headings as named sections."""
    regions = []
    for el in elements:
        if el.element_class == "static_label" and el.tag in ("h2", "h3", "h4"):
            name = el.accessible_name or el.name or ""
            if name and el.bounding_box.width > 30:
                regions.append(Region(
                    role="section_heading",
                    bounding_box=el.bounding_box,
                    elements_contained=[name],
                ))
    return regions


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def detect_regions(elements: Sequence[Element]) -> list[Region]:
    """
    Run all detectors, apply IoU-merge, assign stable ids, return regions.

    Args:
        elements: Elements from one screen (pydantic models).

    Returns:
        List of Region models with unique r1..rN ids.
    """
    raw: list[Region] = []
    raw.extend(detect_page_header(elements))
    raw.extend(detect_navigation_bar(elements))
    raw.extend(detect_filter_regions(elements))
    raw.extend(detect_table_headers(elements))
    raw.extend(detect_action_columns(elements))
    raw.extend(detect_standalone_actions(elements))
    raw.extend(detect_section_labels(elements))

    if not raw:
        # Fallback: individual regions for all meaningful elements
        seen: set[str] = set()
        for el in elements:
            name = el.accessible_name or el.name or el.placeholder
            if not name or name in seen or el.bounding_box.width == 0:
                continue
            seen.add(name)
            role = _infer_role(el)
            raw.append(Region(role=role, bounding_box=el.bounding_box,
                               elements_contained=[name]))

    merged = _iou_merge(raw)

    # Assign stable ids
    for j, r in enumerate(merged):
        r.id = f"r{j + 1}"

    return merged


def process_screen_regions(session_dir: Path, screen_index: int) -> None:
    """
    Legacy orchestrator: reads JSON files, runs detect_regions, saves output.
    Kept for backward compat with main.py / shims during transition.
    """
    logger.info(f"Detecting semantic regions for Screen {screen_index}…")

    elements_path = session_dir / f"screen_{screen_index}_elements.json"
    regions_path = session_dir / f"screen_{screen_index}_regions.json"

    if not elements_path.exists():
        logger.warning(f"No elements file for Screen {screen_index}.")
        regions_path.write_text("[]", encoding="utf-8")
        return

    try:
        raw_els = json.loads(elements_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not read elements for Screen {screen_index}: {e}")
        regions_path.write_text("[]", encoding="utf-8")
        return

    # Convert dicts → pydantic Elements
    elements: list[Element] = []
    for i, d in enumerate(raw_els):
        bbox_raw = d.get("bounding_box", {})
        elements.append(Element(
            id=d.get("id") or f"el_{i}",
            element_class=d.get("element_class", "interactive"),
            tag=d.get("tag", "input"),
            type=d.get("type"),
            role=d.get("role"),
            name=d.get("name"),
            accessible_name=d.get("accessible_name"),
            required=bool(d.get("required", False)),
            placeholder=d.get("placeholder"),
            bounding_box=BBox(**bbox_raw) if bbox_raw else BBox(),
            ancestor_section=d.get("ancestor_section"),
            form_id=d.get("form_id"),
            is_fixed=bool(d.get("is_fixed", False)),
        ))

    regions = detect_regions(elements)

    # Serialise back to JSON (legacy format)
    out = [
        {
            "id": r.id,
            "role": r.role,
            "bounding_box": r.bounding_box.model_dump(),
            "elements_contained": r.elements_contained,
            "label": r.label,
            "deleted": r.deleted,
        }
        for r in regions
    ]
    regions_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    logger.info(f"Detected {len(regions)} regions → {regions_path.name}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _union_bbox(bboxes: list[BBox]) -> BBox:
    """Return the smallest BBox that contains all *bboxes*."""
    xs = [b.x for b in bboxes]
    ys = [b.y for b in bboxes]
    x2s = [b.x + b.width for b in bboxes]
    y2s = [b.y + b.height for b in bboxes]
    return BBox(x=min(xs), y=min(ys), width=max(x2s) - min(xs), height=max(y2s) - min(ys))


def _iou_merge(regions: list[Region]) -> list[Region]:
    """
    Merge regions of the same role whose IoU > threshold.
    Drop regions fully contained within a same-role region.
    """
    if not regions:
        return []

    merged = list(regions)
    changed = True
    while changed:
        changed = False
        new_merged: list[Region] = []
        used = [False] * len(merged)

        for i in range(len(merged)):
            if used[i]:
                continue
            base = merged[i]
            combined = False
            for j in range(i + 1, len(merged)):
                if used[j]:
                    continue
                other = merged[j]
                if base.role != other.role:
                    continue
                iou = base.bounding_box.iou(other.bounding_box)
                if iou > _IOu_THRESHOLD or base.bounding_box.contains(other.bounding_box):
                    # Merge
                    union = _union_bbox([base.bounding_box, other.bounding_box])
                    all_el = list(dict.fromkeys(base.elements_contained + other.elements_contained))
                    base = Region(
                        role=base.role,
                        bounding_box=union,
                        elements_contained=all_el,
                        label=base.label or other.label,
                    )
                    used[j] = True
                    changed = True
                    combined = True
            new_merged.append(base)
            used[i] = True

        merged = new_merged

    return merged


def _infer_role(el: Element) -> str:
    if el.tag == "button" or el.role == "button":
        return "action_button"
    if el.element_class == "navigation":
        return "navigation_bar"
    if el.element_class == "static_label":
        return "section_heading"
    return "filter_form"
