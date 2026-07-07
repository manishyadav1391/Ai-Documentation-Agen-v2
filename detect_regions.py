import json
from pathlib import Path
from typing import Any, Dict, List


def load_elements(elements_path: Path) -> List[Dict[str, Any]]:
    """Loads the enumerated DOM elements from the JSON file."""
    if not elements_path.exists():
        return []
    with elements_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ── Heuristic Detectors ────────────────────────────────────────────────────────

def detect_page_header(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detects the page title / H1 area as a landmark region."""
    regions = []
    for el in elements:
        if el.get("tag") == "h1" or el.get("type") == "label" and el.get("tag") in ["h1", "h2"]:
            bbox = el.get("bounding_box", {})
            text = el.get("accessible_name") or el.get("name", "")
            if text and bbox:
                regions.append({
                    "role": "page_header",
                    "bounding_box": bbox,
                    "elements_contained": [text]
                })
    return regions


def detect_navigation_bar(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Groups navigation links into a single nav-bar region."""
    nav_elements = [el for el in elements if el.get("element_class") == "navigation"]
    if not nav_elements:
        return []

    nav_items = [el.get("accessible_name") or el.get("name", "") for el in nav_elements if el.get("accessible_name") or el.get("name")]
    if not nav_items:
        return []

    # Compute bounding box that encompasses all nav links
    xs = [el["bounding_box"]["x"] for el in nav_elements if el.get("bounding_box")]
    ys = [el["bounding_box"]["y"] for el in nav_elements if el.get("bounding_box")]
    x2s = [el["bounding_box"]["x"] + el["bounding_box"]["width"] for el in nav_elements if el.get("bounding_box")]
    y2s = [el["bounding_box"]["y"] + el["bounding_box"]["height"] for el in nav_elements if el.get("bounding_box")]

    if not xs:
        return []

    return [{
        "role": "navigation_bar",
        "bounding_box": {
            "x": min(xs),
            "y": min(ys),
            "width": max(x2s) - min(xs),
            "height": max(y2s) - min(ys)
        },
        "elements_contained": nav_items[:10]   # cap at 10 items for prompt
    }]


def detect_filter_regions(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detects filter/search form regions by keyword heuristics."""
    regions = []
    keywords = ['filter', 'search', 'criteria', 'panel', 'query']

    # Group interactive form elements by ancestor_section == 'form'
    form_elements = [el for el in elements if el.get("ancestor_section") == "form" and el.get("element_class") == "interactive"]
    if form_elements:
        xs = [el["bounding_box"]["x"] for el in form_elements if el.get("bounding_box")]
        ys = [el["bounding_box"]["y"] for el in form_elements if el.get("bounding_box")]
        x2s = [el["bounding_box"]["x"] + el["bounding_box"]["width"] for el in form_elements if el.get("bounding_box")]
        y2s = [el["bounding_box"]["y"] + el["bounding_box"]["height"] for el in form_elements if el.get("bounding_box")]
        if xs:
            names = [el.get("accessible_name") or el.get("name") or el.get("placeholder") or "Field" for el in form_elements]
            regions.append({
                "role": "filter_form",
                "bounding_box": {
                    "x": max(0, min(xs) - 10),
                    "y": max(0, min(ys) - 10),
                    "width": max(x2s) - min(xs) + 20,
                    "height": max(y2s) - min(ys) + 20
                },
                "elements_contained": [n for n in names if n]
            })

    # Also detect by ID keyword matching
    for el in elements:
        el_id = str(el.get("id", "")).lower()
        el_name = str(el.get("name", "")).lower()
        if any(kw in el_id or kw in el_name for kw in keywords) and el.get("element_class") != "navigation":
            bbox = el.get("bounding_box")
            if bbox:
                regions.append({
                    "role": "filter_form",
                    "bounding_box": bbox,
                    "elements_contained": [el.get("accessible_name") or el.get("name", "Filter Field")]
                })

    return regions


def detect_table_headers(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detects table column headers and groups them into a single table region."""
    th_elements = [el for el in elements if el.get("element_class") == "table_column"]

    if not th_elements:
        return []

    min_x = min(el["bounding_box"]["x"] for el in th_elements if el.get("bounding_box"))
    min_y = min(el["bounding_box"]["y"] for el in th_elements if el.get("bounding_box"))
    max_x = max(el["bounding_box"]["x"] + el["bounding_box"]["width"] for el in th_elements if el.get("bounding_box"))
    max_y = max(el["bounding_box"]["y"] + el["bounding_box"]["height"] for el in th_elements if el.get("bounding_box"))

    return [{
        "role": "table_header",
        "bounding_box": {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y},
        "elements_contained": [el.get("accessible_name") or "" for el in th_elements]
    }]


def detect_standalone_actions(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detects standalone action buttons (not inside a form or table)."""
    regions = []
    seen_labels = set()
    for el in elements:
        is_button = el.get("tag") == "button" or el.get("role") == "button"
        bbox = el.get("bounding_box", {})
        label = el.get("accessible_name") or el.get("name") or ""

        if is_button and bbox.get("width", 0) >= 30 and bbox.get("height", 0) >= 18:
            # Exclude buttons already captured inside a form or table region
            if el.get("ancestor_section") not in ["table", "form"] and label not in seen_labels:
                seen_labels.add(label)
                regions.append({
                    "role": "action_button",
                    "bounding_box": bbox,
                    "elements_contained": [label] if label else ["Button"]
                })
    return regions


def detect_action_columns(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detects 'Actions' column buttons inside table rows (edit, delete, view icons)."""
    action_keywords = ["edit", "delete", "remove", "view", "details", "update", "modify", "open"]
    action_elements = []
    for el in elements:
        if el.get("ancestor_section") == "table" and el.get("element_class") == "interactive":
            label = (el.get("accessible_name") or el.get("name") or "").lower()
            if any(kw in label for kw in action_keywords):
                action_elements.append(el)

    if not action_elements:
        return []

    xs = [el["bounding_box"]["x"] for el in action_elements if el.get("bounding_box")]
    ys = [el["bounding_box"]["y"] for el in action_elements if el.get("bounding_box")]
    x2s = [el["bounding_box"]["x"] + el["bounding_box"]["width"] for el in action_elements if el.get("bounding_box")]
    y2s = [el["bounding_box"]["y"] + el["bounding_box"]["height"] for el in action_elements if el.get("bounding_box")]

    if not xs:
        return []

    unique_labels = list({el.get("accessible_name") or el.get("name", "Action") for el in action_elements})
    return [{
        "role": "action_column",
        "bounding_box": {"x": min(xs), "y": min(ys), "width": max(x2s) - min(xs), "height": max(y2s) - min(ys)},
        "elements_contained": unique_labels[:8]
    }]


def detect_section_labels(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detects H2/H3 section headings as named sections."""
    regions = []
    for el in elements:
        if el.get("element_class") == "static_label" and el.get("tag") in ["h2", "h3", "h4"]:
            bbox = el.get("bounding_box", {})
            text = el.get("accessible_name") or el.get("name", "")
            if text and bbox and bbox.get("width", 0) > 30:
                regions.append({
                    "role": "section_heading",
                    "bounding_box": bbox,
                    "elements_contained": [text]
                })
    return regions


def process_screen_regions(session_dir: Path, screen_index: int):
    """Orchestrates region detection for a single screen."""
    print(f"Detecting semantic regions for Screen {screen_index}...")

    elements_path = session_dir / f"screen_{screen_index}_elements.json"
    regions_path = session_dir / f"screen_{screen_index}_regions.json"

    elements = load_elements(elements_path)
    if not elements:
        print(f"No elements found for Screen {screen_index}.")
        with regions_path.open("w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return

    regions = []
    regions.extend(detect_page_header(elements))
    regions.extend(detect_navigation_bar(elements))
    regions.extend(detect_filter_regions(elements))
    regions.extend(detect_table_headers(elements))
    regions.extend(detect_action_columns(elements))
    regions.extend(detect_standalone_actions(elements))
    regions.extend(detect_section_labels(elements))

    # Fallback: if still nothing detected, create individual regions for all meaningful elements
    if not regions:
        print(f"No heuristic regions found — using element-level fallback.")
        seen = set()
        for el in elements:
            name = el.get("accessible_name") or el.get("name") or el.get("placeholder")
            if not name or name in seen:
                continue
            bbox = el.get("bounding_box", {})
            if not bbox:
                continue
            seen.add(name)

            tag = el.get("tag", "")
            ec = el.get("element_class", "")
            if tag in ["button"] or el.get("role") == "button":
                role = "action_button"
            elif ec == "navigation":
                role = "navigation_bar"
            elif ec == "static_label":
                role = "section_heading"
            else:
                role = "filter_form"

            regions.append({
                "role": role,
                "bounding_box": bbox,
                "elements_contained": [name]
            })

    # Save the detected regions
    with regions_path.open("w", encoding="utf-8") as f:
        json.dump(regions, f, indent=2)

    print(f"Detected {len(regions)} semantic regions. Saved to {regions_path.name}")


if __name__ == "__main__":
    config_dir = Path("sessions")
    if config_dir.exists():
        sessions = sorted(config_dir.glob("session_*"))
        if sessions:
            latest_session = sessions[-1]
            process_screen_regions(latest_session, 1)