import json
from pathlib import Path
from typing import List, Dict, Any
from providers.base import LLMProvider, RegionForLabeling, FieldForDescribing
from config import get_config


class Labeler:
    """
    Orchestrates LLM provider calls for region labels and document prose.
    Injects application name, page title, and breadcrumb context into every prompt.
    """
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def switch_provider(self, new_provider: LLMProvider):
        """
        FR-22: Allows switching the active LLM provider mid-session.
        Called by main.py or the UI if the user changes their settings.
        """
        self.provider = new_provider
        print("Switched LLM provider for this session.")

    def _load_meta(self, session_dir: Path, screen_index: int) -> Dict[str, Any]:
        """Loads the screen meta file and returns it as a dict."""
        meta_path = session_dir / f"screen_{screen_index}_meta.json"
        if meta_path.exists():
            try:
                with meta_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _get_context(self, session_dir: Path, screen_index: int):
        """Returns (app_name, page_title, breadcrumb, screen_name) from config + meta."""
        cfg = get_config()
        app_name = getattr(cfg.theme, "app_name", "") or getattr(cfg.theme, "company_name", "")
        meta = self._load_meta(session_dir, screen_index)
        page_title = meta.get("h1_text") or meta.get("title", "")
        breadcrumb = meta.get("breadcrumb", "")
        screen_name = meta.get("screen_name", "")
        return app_name, page_title, breadcrumb, screen_name

    def label_screen_regions(self, session_dir: Path, screen_index: int):
        """
        Stage 3 (Label): Reads detected regions, asks the LLM to assign
        human-readable labels, and saves them to screen_N_labeled.json.
        Also writes the suggested screen_title back to meta.json if no name exists.
        """
        print(f"\nLabeling regions for Screen {screen_index}...")

        regions_path = session_dir / f"screen_{screen_index}_regions.json"
        labeled_path = session_dir / f"screen_{screen_index}_labeled.json"
        meta_path = session_dir / f"screen_{screen_index}_meta.json"

        if labeled_path.exists():
            print(f"Labels already exist for Screen {screen_index}. Skipping LLM labeling.")
            return

        if not regions_path.exists():
            print(f"No regions file found for Screen {screen_index}.")
            return

        with regions_path.open("r", encoding="utf-8") as f:
            regions_data: List[Dict[str, Any]] = json.load(f)

        if not regions_data:
            print("No regions detected to label.")
            with labeled_path.open("w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
            return

        # Prepare dataclasses for the provider interface
        regions_for_labeling = [
            RegionForLabeling(
                role=r.get("role", "unknown"),
                candidate_labels=r.get("elements_contained", [])
            )
            for r in regions_data
        ]

        # Get page context for rich prompts
        app_name, page_title, breadcrumb, screen_name = self._get_context(session_dir, screen_index)

        if hasattr(self.provider, "work_dir"):
            self.provider.work_dir = session_dir

        # Use label_regions_with_title to also get the LLM's screen name suggestion
        labels, suggested_title = self.provider.label_regions_with_title(
            regions_for_labeling,
            app_name=app_name, page_title=page_title, breadcrumb=breadcrumb
        )

        # Merge labels back into the JSON payload
        for i, r in enumerate(regions_data):
            r["label"] = labels[i] if i < len(labels) else f"Unknown Region {i + 1}"

        with labeled_path.open("w", encoding="utf-8") as f:
            json.dump(regions_data, f, indent=2)

        # If the screen has no name yet, write the LLM-suggested title to meta
        if suggested_title and meta_path.exists():
            try:
                with meta_path.open("r", encoding="utf-8") as f:
                    meta = json.load(f)
                if not meta.get("screen_name"):
                    meta["screen_name"] = suggested_title
                    with meta_path.open("w", encoding="utf-8") as f:
                        json.dump(meta, f, indent=2)
                    print(f"Auto-assigned screen name: \"{suggested_title}\"")
            except Exception:
                pass

        print(f"Assigned labels to {len(regions_data)} regions. Saved to {labeled_path.name}")

    def generate_screen_content(self, session_dir: Path, screen_index: int):
        """
        Stage 6 (Describe): Generates field descriptions and narrative prose
        using the final writer-reviewed regions and DOM elements.
        """
        print(f"\nGenerating field descriptions and prose for Screen {screen_index}...")

        elements_path = session_dir / f"screen_{screen_index}_elements.json"
        final_regions_path = session_dir / f"screen_{screen_index}_final.json"
        content_path = session_dir / f"screen_{screen_index}_content.json"

        if content_path.exists():
            print(f"Content already exists for Screen {screen_index}. Skipping generation.")
            return

        if not elements_path.exists() or not final_regions_path.exists():
            print(f"Required data missing to generate content for Screen {screen_index}.")
            return

        with elements_path.open("r", encoding="utf-8") as f:
            elements_data = json.load(f)

        with final_regions_path.open("r", encoding="utf-8") as f:
            final_regions_data = json.load(f)

        # Get context for prompts
        app_name, page_title, breadcrumb, screen_name = self._get_context(session_dir, screen_index)

        # Prepare form fields — skip REDACTED / navigation / static labels
        fields_for_describing = []
        for el in elements_data:
            # Only describe interactive form input fields
            if el.get("element_class") not in ["interactive", None]:
                continue
            if el.get("tag") not in ["input", "select", "textarea"]:
                continue
            # Skip REDACTED password fields
            if el.get("accessible_name") == "[REDACTED]":
                continue

            el_bbox = el.get("bounding_box", {})
            section_name = "Form Field"

            for r in final_regions_data:
                r_bbox = r.get("bounding_box", {})
                if el_bbox and r_bbox:
                    el_cx = el_bbox.get("x", 0) + el_bbox.get("width", 0) / 2
                    el_cy = el_bbox.get("y", 0) + el_bbox.get("height", 0) / 2
                    rx, ry = r_bbox.get("x", 0), r_bbox.get("y", 0)
                    rw, rh = r_bbox.get("width", 0), r_bbox.get("height", 0)
                    if rx <= el_cx <= rx + rw and ry <= el_cy <= ry + rh:
                        section_name = r.get("label", "Form Field")
                        break

            field_label = el.get("accessible_name") or el.get("placeholder") or el.get("name") or "Unnamed Field"
            fields_for_describing.append(
                FieldForDescribing(
                    name=f"{section_name} -> {field_label}",
                    type=el.get("type") or "text",
                    required=el.get("required", False),
                    placeholder=el.get("placeholder"),
                    validation=el.get("pattern")
                )
            )

        descriptions = []
        if fields_for_describing:
            if hasattr(self.provider, "work_dir"):
                self.provider.work_dir = session_dir
            descriptions = self.provider.describe_fields(
                fields_for_describing,
                app_name=app_name, page_title=page_title, screen_name=screen_name
            )

        field_content = []
        for i, f_desc in enumerate(fields_for_describing):
            field_content.append({
                "field_name": f_desc.name,
                "description": descriptions[i] if i < len(descriptions) else ""
            })

        # Build action sequence from final reviewed regions
        actions = []
        for r in final_regions_data:
            role = r.get("role", "")
            label = r.get("label", "")
            if role in ["action_button", "action_column"]:
                actions.append({"action": "Click", "target": label})
            elif role in ["filter_form"]:
                actions.append({"action": "Fill in details in", "target": label})
            elif role in ["table_header", "view_only"]:
                actions.append({"action": "Review data in", "target": label})
            elif role == "navigation_bar":
                actions.append({"action": "Navigate using", "target": label})
            elif role in ["page_header", "section_heading"]:
                actions.append({"action": "Refer to section", "target": label})
            else:
                actions.append({"action": "Interact with", "target": label})

        if not actions:
            actions = [{"action": "Navigate and interact with", "target": "screen elements"}]

        prose = self.provider.procedure_prose(
            actions, context="User operation",
            app_name=app_name, screen_name=screen_name,
            page_title=page_title, breadcrumb=breadcrumb
        )

        content_data = {
            "field_descriptions": field_content,
            "procedure_prose": prose,
            "screen_name": screen_name,
            "page_title": page_title
        }

        with content_path.open("w", encoding="utf-8") as f:
            json.dump(content_data, f, indent=2)

        print(f"Content generation complete. Saved to {content_path.name}")