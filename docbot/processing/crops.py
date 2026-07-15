"""
DocBot v3 — Element crop extractor.

For every recorded click event that has a bounding box, crops a small
region of the nearest screenshot and saves it as an inline image.

These crops are used by the NCD export style to show the exact button
or field the user clicked on, inline within the step text (Principle P5).

Crop size: element bbox + 6px padding on each side.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from docbot.models import Event, Screen, SessionModel


_PADDING = 6   # pixels of padding around the cropped element


def extract_crops(
    session: SessionModel,
    screen: Screen,
    session_dir: Path,
) -> None:
    """
    For each click/keypress_enter event on *screen* that has a bbox,
    crop the element region from the nearest event screenshot and attach
    ``crop_path`` to the corresponding step.

    Modifies ``screen.content.steps`` in-place.

    Args:
        session:     The full session model (for context).
        screen:      The screen whose events to process.
        session_dir: Path to the session directory for reading/writing PNGs.
    """
    try:
        from PIL import Image as PILImage
    except ImportError:
        logger.warning("[Crops] Pillow not available; skipping crop extraction.")
        return

    crops_dir = session_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    # Build an event_id → event lookup
    ev_map = {ev.id: ev for ev in screen.events}

    for step in screen.content.steps:
        if not step.event_id:
            continue
        ev = ev_map.get(step.event_id)
        if not ev:
            continue
        if ev.kind not in ("click", "keypress_enter"):
            continue
        if not ev.target_bbox:
            continue

        # Find the nearest screenshot to crop from
        screenshot_path = _find_screenshot(ev, screen, session_dir)
        if not screenshot_path or not screenshot_path.exists():
            continue

        bbox = ev.target_bbox
        # Use viewport coordinates (bbox is in document coords; for viewport screenshots
        # we need to subtract the scroll_y of the segment — but for simplicity here we
        # use the raw document coords which work for full-page screenshots)
        x1 = max(0, int(bbox.x) - _PADDING)
        y1 = max(0, int(bbox.y) - _PADDING)
        x2 = int(bbox.x + bbox.width) + _PADDING
        y2 = int(bbox.y + bbox.height) + _PADDING

        crop_name = f"crop_{screen.index}_{step.event_id}.png"
        crop_path = crops_dir / crop_name

        if crop_path.exists():
            step.crop_path = str(crop_path.relative_to(session_dir))
            continue

        try:
            with PILImage.open(screenshot_path) as img:
                # Clamp to image dimensions
                x2 = min(x2, img.width)
                y2 = min(y2, img.height)
                if x2 <= x1 or y2 <= y1:
                    continue
                cropped = img.crop((x1, y1, x2, y2))
                cropped.save(str(crop_path), "PNG")
            step.crop_path = f"crops/{crop_name}"
            logger.debug(f"Crop saved: {crop_name} ({x2 - x1}×{y2 - y1}px)")
        except Exception as e:
            logger.warning(f"Could not create crop for event {ev.id}: {e}")


def _find_screenshot(ev: Event, screen: Screen, session_dir: Path) -> Path | None:
    """Find the best screenshot for cropping the element in *ev*."""
    # Prefer event's own 'after' screenshot
    if ev.screenshot_after:
        p = session_dir / ev.screenshot_after
        if p.exists():
            return p
    # Fall back to screen's primary screenshot
    if screen.screenshot:
        p = session_dir / screen.screenshot
        if p.exists():
            return p
    # Last resort: any figure path
    for fig in screen.figures:
        p = session_dir / fig.path
        if p.exists():
            return p
    return None
