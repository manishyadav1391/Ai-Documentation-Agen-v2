import json
from pathlib import Path
from typing import Any, Dict, List

def load_elements(elements_path: Path) -> List[Dict[str, Any]]:
    """Loads the enumerated DOM elements from the JSON file."""
    if not elements_path.exists():
        return []
    with elements_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def detect_filter_regions(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    FR-11: Detects filter regions such as forms or containers 
    with specific keywords in their ID or class.
    """
    regions = []
    keywords = ['filter', 'search', 'criteria', 'panel']
    
    for el in elements:
        tag = el.get('tag', '')
        el_id = str(el.get('id', '')).lower()
        
        # Check if it's a form or matches keyword heuristics
        if tag == 'form' or any(kw in el_id for kw in keywords):
            regions.append({
                "role": "filter_form",
                "bounding_box": el.get('bounding_box'),
                "elements_contained": [el.get('id') or el.get('name')]
            })
    return regions

def detect_table_headers(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    FR-12: Detects table headers by identifying <th> elements.
    """
    regions = []
    th_elements = [el for el in elements if el.get('tag') == 'th']
    
    if th_elements:
        # Simplified: grouping them into a single region for the table header
        # In a robust implementation, this would group by ancestor_section
        min_x = min(el['bounding_box']['x'] for el in th_elements)
        min_y = min(el['bounding_box']['y'] for el in th_elements)
        max_x = max(el['bounding_box']['x'] + el['bounding_box']['width'] for el in th_elements)
        max_y = max(el['bounding_box']['y'] + el['bounding_box']['height'] for el in th_elements)
        
        regions.append({
            "role": "table_header",
            "bounding_box": {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y},
            "elements_contained": [el.get('accessible_name') for el in th_elements]
        })
    return regions

def detect_standalone_actions(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    FR-13 & FR-16: Detects standalone buttons, skipping elements smaller than 30x20 pixels.
    """
    regions = []
    for el in elements:
        is_button = el.get('tag') == 'button' or el.get('role') == 'button'
        bbox = el.get('bounding_box', {})
        
        # Check dimensions to avoid false positives (FR-16)
        if is_button and bbox.get('width', 0) >= 30 and bbox.get('height', 0) >= 20:
            # Exclude buttons already inside a table or form (FR-13)
            if el.get('ancestor_section') not in ['table', 'form']:
                regions.append({
                    "role": "action_button",
                    "bounding_box": bbox,
                    "elements_contained": [el.get('accessible_name')]
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
        return

    regions = []
    regions.extend(detect_filter_regions(elements))
    regions.extend(detect_table_headers(elements))
    regions.extend(detect_standalone_actions(elements))
    
    if not regions:
        # Fallback: create individual regions for visible interactive elements if heuristics return 0
        for el in elements:
            tag = el.get('tag', '')
            role = el.get('role', '')
            bbox = el.get('bounding_box', {})
            name = el.get('accessible_name') or el.get('name')
            
            if (tag in ['button', 'input', 'select', 'textarea'] or role == 'button') and name:
                regions.append({
                    "role": "action_button" if (tag == 'button' or role == 'button') else "filter_form",
                    "bounding_box": bbox,
                    "elements_contained": [name]
                })
    
    # Save the detected regions
    with regions_path.open("w", encoding="utf-8") as f:
        json.dump(regions, f, indent=2)
        
    print(f"Detected {len(regions)} semantic regions. Saved to {regions_path.name}")

if __name__ == "__main__":
    # Example test run for the most recent session
    config_dir = Path("sessions")
    if config_dir.exists():
        sessions = sorted(config_dir.glob("session_*"))
        if sessions:
            latest_session = sessions[-1]
            process_screen_regions(latest_session, 1)