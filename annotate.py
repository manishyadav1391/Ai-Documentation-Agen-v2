import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont
from config import get_config

# NCD manual color palette — matched to FR-23 and FR-24
COLORS = {
    "red": {"stroke": (215, 55, 55), "callout_bg": (255, 255, 255), "callout_border": (215, 55, 55), "text": (215, 55, 55)},
    "green": {"stroke": (95, 155, 80), "callout_bg": (255, 255, 255), "callout_border": (95, 155, 80), "text": (95, 155, 80)},
}

# Semantic role → color mapping
ROLE_COLOR = {
    "filter_form":  "red",
    "action_button":"red",
    "action_group": "red",
    "table_header": "red",
    "view_only":    "green",
}

@dataclass
class Region:
    """One annotation on the screenshot."""
    x: int
    y: int
    w: int
    h: int
    label: str
    role: str
    callout_anchor: str = "right"

def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try common system fonts; fall back to PIL default."""
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

def _wrap_text(text: str, max_chars: int = 12) -> List[str]:
    """FR-28: Wrap label to at most max_chars per line, at word boundaries."""
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

def _measure_callout(label: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int, List[str]]:
    """Return (width, height, wrapped_lines) of the callout bubble."""
    lines = _wrap_text(label)
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = font.getbbox(line)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
    padding_x, padding_y, line_gap = 14, 10, 4
    w = max(line_widths) + 2 * padding_x
    h = sum(line_heights) + line_gap * (len(lines) - 1) + 2 * padding_y
    return w, h, lines

def _rects_overlap(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int], padding: int = 10) -> bool:
    """Check whether rectangle A overlaps rectangle B."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ax1 -= padding; ay1 -= padding; ax2 += padding; ay2 += padding
    return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)

def _place_callout(region: Region, callout_w: int, callout_h: int, image_w: int, image_h: int, other_regions: List[Region] = None, gap: int = 50) -> Tuple[int, int]:
    """FR-27: Overlap-aware algorithm to place callouts without covering regions."""
    other_regions = other_regions or []
    region_rect = (region.x, region.y, region.x + region.w, region.y + region.h)
    candidates = []
    tries = [region.callout_anchor, "right", "top", "bottom", "left"]
    seen = set()

    for anchor in tries:
        if anchor in seen: continue
        seen.add(anchor)

        if anchor == "right":
            cx, cy = region.x + region.w + gap, region.y + region.h // 2 - callout_h // 2
        elif anchor == "left":
            cx, cy = region.x - callout_w - gap, region.y + region.h // 2 - callout_h // 2
        elif anchor == "top":
            cx, cy = region.x + region.w // 2 - callout_w // 2, region.y - callout_h - gap
        elif anchor == "bottom":
            cx, cy = region.x + region.w // 2 - callout_w // 2, region.y + region.h + gap
        else: continue

        cx = max(10, min(cx, image_w - callout_w - 10))
        cy = max(10, min(cy, image_h - callout_h - 10))
        callout_rect = (cx, cy, cx + callout_w, cy + callout_h)

        score = 0
        if _rects_overlap(callout_rect, region_rect, padding=5): score += 1000
        for other in other_regions:
            if other is region: continue
            other_rect = (other.x, other.y, other.x + other.w, other.y + other.h)
            if _rects_overlap(callout_rect, other_rect, padding=5): score += 100
        
        candidates.append((score, cx, cy, anchor))
        if score == 0: return cx, cy

    candidates.sort()
    _, cx, cy, _ = candidates[0]
    return cx, cy

def _draw_leader(draw: ImageDraw.ImageDraw, region: Region, callout_box: Tuple[int, int, int, int], color: Tuple):
    """FR-26: Draw a curved Bezier leader line from callout to region."""
    cx0, cy0, cx1, cy1 = callout_box
    region_cx, region_cy = region.x + region.w // 2, region.y + region.h // 2

    if region_cx < cx0: cx_out, cy_out = cx0, (cy0 + cy1) // 2
    elif region_cx > cx1: cx_out, cy_out = cx1, (cy0 + cy1) // 2
    elif region_cy < cy0: cx_out, cy_out = (cx0 + cx1) // 2, cy0
    else: cx_out, cy_out = (cx0 + cx1) // 2, cy1

    callout_cx, callout_cy = (cx0 + cx1) // 2, (cy0 + cy1) // 2
    if callout_cx < region.x: rx, ry = region.x, region.y + region.h // 2
    elif callout_cx > region.x + region.w: rx, ry = region.x + region.w, region.y + region.h // 2
    elif callout_cy < region.y: rx, ry = region.x + region.w // 2, region.y
    else: rx, ry = region.x + region.w // 2, region.y + region.h

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

def _draw_callout_bubble(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, lines: List[str], font: ImageFont.FreeTypeFont, palette: dict, border_width: int):
    """FR-25: Draw callout bubbles as rounded rectangles with colored borders."""
    radius = 12
    draw.rounded_rectangle(
        [(x, y), (x + w, y + h)],
        radius=radius, fill=palette["callout_bg"], outline=palette["callout_border"], width=border_width
    )
    line_heights = [font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines]
    total_h = sum(line_heights) + 4 * (len(lines) - 1)
    ty = y + (h - total_h) // 2

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        line_w = bbox[2] - bbox[0]
        tx = x + (w - line_w) // 2
        draw.text((tx, ty), line, fill=palette["text"], font=font)
        ty += line_heights[i] + 4

def render_annotations(session_dir: Path, screen_index: int):
    """
    Main entry point: Reads final JSON regions and screenshot, 
    renders annotations, and saves the final PNG.
    """
    config = get_config()
    
    img_path = session_dir / f"screen_{screen_index}.png"
    final_json_path = session_dir / f"screen_{screen_index}_final.json"
    output_path = session_dir / f"screen_{screen_index}_annotated.png"

    if not img_path.exists() or not final_json_path.exists():
        print(f"Missing image or final JSON data for Screen {screen_index}.")
        return

    with final_json_path.open("r", encoding="utf-8") as f:
        regions_data = json.load(f)

    # Convert dictionaries to Region dataclass objects
    regions = []
    for r in regions_data:
        bbox = r.get("bounding_box", {})
        if not bbox: continue
        regions.append(Region(
            x=int(bbox.get("x", 0)),
            y=int(bbox.get("y", 0)),
            w=int(bbox.get("width", 0)),
            h=int(bbox.get("height", 0)),
            label=r.get("label", "Unknown"),
            role=r.get("role", "view_only")
        ))

    print(f"Rendering annotations for Screen {screen_index}...")
    img = Image.open(img_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    font = _get_font(config.render.label_font_size)
    stroke_width = config.render.region_stroke_width
    border_width = config.render.callout_border_width

    for region in regions:
        color_name = ROLE_COLOR.get(region.role, "red")
        palette = COLORS[color_name]

        draw.rectangle(
            [(region.x, region.y), (region.x + region.w, region.y + region.h)],
            outline=palette["stroke"], width=stroke_width
        )
        cw, ch, lines = _measure_callout(region.label, font)
        cx, cy = _place_callout(region, cw, ch, img.width, img.height, other_regions=regions)
        _draw_leader(draw, region, (cx, cy, cx + cw, cy + ch), palette["stroke"])
        _draw_callout_bubble(draw, cx, cy, cw, ch, lines, font, palette, border_width)

    combined = Image.alpha_composite(img, overlay)
    combined.convert("RGB").save(output_path, "PNG")
    print(f"Successfully saved annotated image to {output_path.name}")