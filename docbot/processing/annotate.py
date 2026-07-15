"""
DocBot v3 — Annotated screenshot renderer.

Renders callout bubbles + leader lines on top of screenshots using the
detected region data from the session model.

Fixes vs v2
-----------
- W27: Candidate placement now tracks ALL already-placed callout rectangles
  in a ``placed`` list; new callouts score 100 points per overlap with ANY
  placed rectangle (not just with other regions).
- Style-driven: colors and mode come from ``client_profile["style"]``.
  mode: ``callouts`` | ``boxes_only`` | ``numbered_badges``
  annotations.wrap_chars: chars per callout line (default 14)
  annotations.colors: {"action_button": "red", "filter_form": "red", …}
- Falls back to default palette if style is not provided.
- Supports ``mode: numbered_badges`` for NCD (number inside badge, legend below).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from config import get_config


# Default color palette (overridable via style.yaml annotations block)
_DEFAULT_PALETTE = {
    "red": {
        "stroke": (215, 55, 55),
        "callout_bg": (255, 255, 255),
        "callout_border": (215, 55, 55),
        "text": (215, 55, 55),
    },
    "green": {
        "stroke": (95, 155, 80),
        "callout_bg": (255, 255, 255),
        "callout_border": (95, 155, 80),
        "text": (95, 155, 80),
    },
    "blue": {
        "stroke": (37, 99, 235),
        "callout_bg": (255, 255, 255),
        "callout_border": (37, 99, 235),
        "text": (37, 99, 235),
    },
}

_DEFAULT_ROLE_COLORS = {
    "filter_form": "red",
    "action_button": "red",
    "action_group": "red",
    "action_column": "red",
    "table_header": "red",
    "view_only": "green",
    "page_header": "blue",
    "navigation_bar": "blue",
    "section_heading": "blue",
}


@dataclass
class _Region:
    x: int; y: int; w: int; h: int
    label: str; role: str
    callout_anchor: str = "right"


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in [
        "arial.ttf", "Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ]:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, max_chars: int = 14) -> List[str]:
    words = text.split()
    lines, current = [], ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines or [text]


def _measure_callout(
    label: str, font: ImageFont.FreeTypeFont, max_chars: int = 14
) -> Tuple[int, int, List[str]]:
    lines = _wrap_text(label, max_chars)
    lw, lh = [], []
    for line in lines:
        bb = font.getbbox(line)
        lw.append(bb[2] - bb[0])
        lh.append(bb[3] - bb[1])
    px, py, gap = 14, 10, 4
    w = max(lw) + 2 * px
    h = sum(lh) + gap * (len(lines) - 1) + 2 * py
    return w, h, lines


def _rects_overlap(
    a: Tuple[int, int, int, int],
    b: Tuple[int, int, int, int],
    pad: int = 10,
) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ax1 -= pad; ay1 -= pad; ax2 += pad; ay2 += pad
    return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)


def _place_callout(
    region: _Region,
    callout_w: int,
    callout_h: int,
    image_w: int,
    image_h: int,
    other_regions: List[_Region],
    placed: List[Tuple[int, int, int, int]],  # W27: track placed callout rects
    gap: int = 50,
) -> Tuple[int, int]:
    """Overlap-aware callout placement (W27 fix: scores against placed callouts too)."""
    region_rect = (region.x, region.y, region.x + region.w, region.y + region.h)
    candidates = []
    tries = [region.callout_anchor, "right", "top", "bottom", "left"]
    seen: set[str] = set()

    for anchor in tries:
        if anchor in seen:
            continue
        seen.add(anchor)
        if anchor == "right":
            cx, cy = region.x + region.w + gap, region.y + region.h // 2 - callout_h // 2
        elif anchor == "left":
            cx, cy = region.x - callout_w - gap, region.y + region.h // 2 - callout_h // 2
        elif anchor == "top":
            cx, cy = region.x + region.w // 2 - callout_w // 2, region.y - callout_h - gap
        elif anchor == "bottom":
            cx, cy = region.x + region.w // 2 - callout_w // 2, region.y + region.h + gap
        else:
            continue
        cx = max(10, min(cx, image_w - callout_w - 10))
        cy = max(10, min(cy, image_h - callout_h - 10))
        callout_rect = (cx, cy, cx + callout_w, cy + callout_h)

        score = 0
        if _rects_overlap(callout_rect, region_rect, pad=5):
            score += 1000
        for other in other_regions:
            if other is region:
                continue
            other_rect = (other.x, other.y, other.x + other.w, other.y + other.h)
            if _rects_overlap(callout_rect, other_rect, pad=5):
                score += 100
        # W27: penalise overlap with already-placed callouts
        for placed_rect in placed:
            if _rects_overlap(callout_rect, placed_rect, pad=5):
                score += 100

        candidates.append((score, cx, cy, anchor))
        if score == 0:
            return cx, cy

    candidates.sort()
    _, cx, cy, _ = candidates[0]
    return cx, cy


def _draw_leader(
    draw: ImageDraw.ImageDraw,
    region: _Region,
    callout_box: Tuple[int, int, int, int],
    color: Tuple,
) -> None:
    cx0, cy0, cx1, cy1 = callout_box
    region_cx, region_cy = region.x + region.w // 2, region.y + region.h // 2
    if region_cx < cx0:
        cx_out, cy_out = cx0, (cy0 + cy1) // 2
    elif region_cx > cx1:
        cx_out, cy_out = cx1, (cy0 + cy1) // 2
    elif region_cy < cy0:
        cx_out, cy_out = (cx0 + cx1) // 2, cy0
    else:
        cx_out, cy_out = (cx0 + cx1) // 2, cy1

    callout_cx = (cx0 + cx1) // 2
    callout_cy = (cy0 + cy1) // 2
    if callout_cx < region.x:
        rx, ry = region.x, region.y + region.h // 2
    elif callout_cx > region.x + region.w:
        rx, ry = region.x + region.w, region.y + region.h // 2
    elif callout_cy < region.y:
        rx, ry = region.x + region.w // 2, region.y
    else:
        rx, ry = region.x + region.w // 2, region.y + region.h

    mid_x, mid_y = (cx_out + rx) // 2, (cy_out + ry) // 2
    dx, dy = rx - cx_out, ry - cy_out
    length = max(1, math.hypot(dx, dy))
    perp_x, perp_y = -dy / length, dx / length
    offset = min(30, length // 6)
    ctrl_x, ctrl_y = mid_x + int(perp_x * offset), mid_y + int(perp_y * offset)

    points = []
    for i in range(21):
        t = i / 20
        x = (1 - t) ** 2 * cx_out + 2 * (1 - t) * t * ctrl_x + t ** 2 * rx
        y = (1 - t) ** 2 * cy_out + 2 * (1 - t) * t * ctrl_y + t ** 2 * ry
        points.append((x, y))
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=color, width=2)


def _draw_callout_bubble(
    draw: ImageDraw.ImageDraw,
    x: int, y: int, w: int, h: int,
    lines: List[str],
    font: ImageFont.FreeTypeFont,
    palette: dict,
    border_width: int = 2,
) -> None:
    draw.rounded_rectangle(
        [(x, y), (x + w, y + h)],
        radius=12,
        fill=palette["callout_bg"],
        outline=palette["callout_border"],
        width=border_width,
    )
    lh_list = [font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines]
    total_h = sum(lh_list) + 4 * (len(lines) - 1)
    ty = y + (h - total_h) // 2
    for i, line in enumerate(lines):
        bb = font.getbbox(line)
        lw = bb[2] - bb[0]
        tx = x + (w - lw) // 2
        draw.text((tx, ty), line, fill=palette["text"], font=font)
        ty += lh_list[i] + 4


def _draw_numbered_badge(
    draw: ImageDraw.ImageDraw,
    cx: int, cy: int,
    number: int,
    font: ImageFont.FreeTypeFont,
    palette: dict,
) -> None:
    radius = 14
    draw.ellipse(
        [(cx - radius, cy - radius), (cx + radius, cy + radius)],
        fill=palette["stroke"], outline=palette["stroke"],
    )
    label = str(number)
    bb = font.getbbox(label)
    lw, lh = bb[2] - bb[0], bb[3] - bb[1]
    draw.text((cx - lw // 2, cy - lh // 2), label, fill=(255, 255, 255), font=font)


def render_annotations(
    session_dir: Path,
    screen_index: int,
    client_profile: dict | None = None,
) -> None:
    """
    Render annotated screenshot for one screen.

    Reads ``screen_{n}_regions.json`` (or equivalent in session.json),
    overlays callouts/boxes/badges, saves ``screen_{n}_annotated.png``.
    """
    cfg = get_config()

    img_path = session_dir / f"screen_{screen_index}.png"
    # Also accept viewport or full_page variants
    for variant in [
        session_dir / f"screen_{screen_index}_viewport.png",
        session_dir / f"screen_{screen_index}_full.png",
    ]:
        if variant.exists() and not img_path.exists():
            img_path = variant

    final_json_path = session_dir / f"screen_{screen_index}_final.json"
    regions_json_path = session_dir / f"screen_{screen_index}_regions.json"
    output_path = session_dir / f"screen_{screen_index}_annotated.png"

    if not img_path.exists():
        logger.warning(f"No screenshot for Screen {screen_index}; skipping annotation.")
        return

    regions_data = []
    for rpath in [final_json_path, regions_json_path]:
        if rpath.exists():
            try:
                regions_data = json.loads(rpath.read_text(encoding="utf-8"))
                break
            except Exception as e:
                logger.warning(f"Could not read regions from {rpath}: {e}")

    if not regions_data:
        logger.debug(f"No region data for Screen {screen_index}; copying raw screenshot.")
        import shutil
        shutil.copy(img_path, output_path)
        return

    # Resolve DPI scale factor from session model
    dpr = 1.0
    try:
        from docbot.models import SessionStore
        session = SessionStore.load(session_dir)
        screen = next((s for s in session.screens if s.index == screen_index), None)
        if screen:
            dpr = screen.device_pixel_ratio
    except Exception as e:
        logger.debug(f"[Annotate] Could not load session for scaling check: {e}")

    # Resolve style from client profile
    profile = client_profile or {}
    annot_style = profile.get("style", {}).get("annotations", {})
    mode = annot_style.get("mode", "callouts")
    wrap_chars = int(annot_style.get("wrap_chars", 14))
    color_map = annot_style.get("colors", _DEFAULT_ROLE_COLORS)

    label_font_size = int(cfg.render.label_font_size * dpr)
    stroke_width = int(cfg.render.region_stroke_width * dpr)
    border_width = int(cfg.render.callout_border_width * dpr)

    regions: list[_Region] = []
    for r in regions_data:
        bbox = r.get("bounding_box", {})
        if not bbox or r.get("deleted"):
            continue
        regions.append(_Region(
            x=int(bbox.get("x", 0) * dpr),
            y=int(bbox.get("y", 0) * dpr),
            w=int(bbox.get("width", 0) * dpr),
            h=int(bbox.get("height", 0) * dpr),
            label=r.get("label") or r.get("elements_contained", [""])[0] or "Region",
            role=r.get("role", "filter_form"),
        ))

    img = Image.open(img_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _get_font(label_font_size)
    small_font = _get_font(max(10, label_font_size - 4))

    placed: list[Tuple[int, int, int, int]] = []  # W27: track placed callout rects


    legend_entries: list[Tuple[int, str, dict]] = []  # (number, label, palette) for numbered_badges

    for i, region in enumerate(regions):
        color_name = color_map.get(region.role, "red")
        palette = _DEFAULT_PALETTE.get(color_name, _DEFAULT_PALETTE["red"])

        # Draw region bounding box
        draw.rectangle(
            [(region.x, region.y), (region.x + region.w, region.y + region.h)],
            outline=palette["stroke"],
            width=stroke_width,
        )

        if mode == "boxes_only":
            continue

        if mode == "numbered_badges":
            badge_cx = region.x + region.w - 14
            badge_cy = region.y + 14
            _draw_numbered_badge(draw, badge_cx, badge_cy, i + 1, small_font, palette)
            legend_entries.append((i + 1, region.label, palette))
            placed.append((badge_cx - 14, badge_cy - 14, badge_cx + 14, badge_cy + 14))
            continue

        # mode == "callouts" (default)
        cw, ch, lines = _measure_callout(region.label, font, wrap_chars)
        cx, cy = _place_callout(
            region, cw, ch, img.width, img.height,
            other_regions=regions, placed=placed, gap=50,
        )
        placed.append((cx, cy, cx + cw, cy + ch))  # W27: register this callout
        _draw_leader(draw, region, (cx, cy, cx + cw, cy + ch), palette["stroke"])
        _draw_callout_bubble(draw, cx, cy, cw, ch, lines, font, palette, border_width)

    combined = Image.alpha_composite(img, overlay).convert("RGB")

    # Draw legend for numbered_badges mode
    if mode == "numbered_badges" and legend_entries:
        from PIL import ImageFont as _IF
        legend_img = Image.new("RGB", (combined.width, 24 * len(legend_entries) + 20),
                               (255, 255, 255))
        ldraw = ImageDraw.Draw(legend_img)
        fy = 10
        for num, lbl, pal in legend_entries:
            _draw_numbered_badge(ldraw, 16, fy + 10, num, small_font, pal)
            ldraw.text((36, fy + 4), lbl, fill=pal["text"], font=small_font)
            fy += 24
        concat = Image.new("RGB", (combined.width, combined.height + legend_img.height))
        concat.paste(combined, (0, 0))
        concat.paste(legend_img, (0, combined.height))
        combined = concat

    combined.save(output_path, "PNG")
    logger.info(f"Annotated screenshot saved → {output_path.name}")
