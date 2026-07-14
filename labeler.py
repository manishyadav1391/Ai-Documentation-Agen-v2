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
        meta_path = session_dir / f"screen_{screen_index}_meta.json"

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
        
        # Load screen meta
        screen_meta = self._load_meta(session_dir, screen_index)

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

        rich_field_details = []
        if fields_for_describing:
            if hasattr(self.provider, "work_dir"):
                self.provider.work_dir = session_dir
            rich_field_details = self.provider.describe_fields_rich(
                fields_for_describing,
                app_name=app_name, page_title=page_title, screen_name=screen_name
            )

        # Retain backward compatibility legacy key
        legacy_field_content = []
        for f in rich_field_details:
            legacy_field_content.append({
                "field_name": f.get("field_name", ""),
                "description": f.get("utility", "")
            })

        # Build grouped control lists for structured documentation generation
        control_groups = {
            "navigation": [],
            "search_filters": [],
            "buttons": [],
            "table_columns": [],
            "form_fields": [],
            "tabs": [],
            "additional_features": []
        }

        for r in final_regions_data:
            role = r.get("role", "")
            labels = [lbl for lbl in r.get("elements_contained", []) if lbl]

            if role == "navigation_bar":
                control_groups["navigation"].extend(labels)
            elif role == "filter_form":
                control_groups["search_filters"].extend(labels)
            elif role in ["action_button", "action_column"]:
                control_groups["buttons"].extend(labels)
            elif role == "table_header":
                control_groups["table_columns"].extend(labels)
            elif role == "section_heading":
                control_groups["additional_features"].extend(labels)
            elif role == "page_header":
                control_groups["additional_features"].extend(labels)
            else:
                control_groups["additional_features"].extend(labels)

        if not control_groups["navigation"] and breadcrumb:
            control_groups["navigation"].append(breadcrumb)

        # Use screen type hints when available
        screen_type_value = "unknown"
        if screen_name:
            title_lower = screen_name.lower()
            if any(term in title_lower for term in ["login", "sign in"]):
                screen_type_value = "login"
            elif any(term in title_lower for term in ["dashboard", "home"]):
                screen_type_value = "dashboard"
            elif any(term in title_lower for term in ["report", "list", "grid"]):
                screen_type_value = "report"
            elif any(term in title_lower for term in ["form", "create", "add", "edit"]):
                screen_type_value = "form"
            elif any(term in title_lower for term in ["search", "filter"]):
                screen_type_value = "search"

        if hasattr(self.provider, "work_dir"):
            self.provider.work_dir = session_dir
        documentation = self.provider.generate_screen_documentation(
            control_groups,
            app_name=app_name,
            page_title=page_title,
            screen_name=screen_name,
            breadcrumb=breadcrumb,
            screen_type=screen_type_value
        )

        # 8. Generate Screen Purpose via LLM
        screen_context = {
            "url": screen_meta.get("url", ""),
            "title": page_title,
            "breadcrumb": breadcrumb,
            "regions": [r.get("label", "") for r in final_regions_data if not r.get("deleted")]
        }
        purpose_sentence = ""
        try:
            purpose_sentence = self.provider.generate_screen_purpose(screen_context)
        except Exception as e:
            print(f"[Warning] Failed to generate screen purpose: {e}")
            purpose_sentence = f"The {screen_name} screen allows users to interact with form fields and submit data."

        # 9. Generate Deterministic Path Breadcrumbs
        nav_trail = screen_meta.get("nav_trail", [])
        breadcrumb_path = self.generate_screen_path(nav_trail, screen_name)

        # 10. Assemble figures array
        figures_array = []
        # Find all figures for this screen (handling Phase C multiple states)
        figures_array.append({
            "index": 1,
            "path": f"screen_{screen_index}_annotated.png",
            "caption_note": ""
        })
        # Check if there are other states
        for state_file in sorted(session_dir.glob(f"screen_{screen_index}_state_*_annotated.png")):
            state_num = state_file.name.split("_state_")[1].split("_")[0]
            # Try to load state meta to get state_label
            state_label = ""
            state_meta_path = session_dir / f"screen_{screen_index}_state_{state_num}_meta.json"
            if state_meta_path.exists():
                try:
                    with state_meta_path.open("r", encoding="utf-8") as f:
                        s_meta = json.load(f)
                    state_label = s_meta.get("state_label", "")
                except Exception:
                    pass
            if not state_label:
                state_label = f"State {state_num}"
            figures_array.append({
                "index": len(figures_array) + 1,
                "path": state_file.name,
                "caption_note": state_label
            })

        content_data = {
            "field_descriptions": legacy_field_content,
            "field_details": rich_field_details,
            "screen_documentation": documentation,
            "screen_name": screen_name,
            "page_title": page_title,
            "purpose": purpose_sentence,
            "path": breadcrumb_path,
            "navigation_instructions": f"Select {screen_name} option from {breadcrumb_path.split(' >> ')[0] if ' >> ' in breadcrumb_path else 'menu'} as shown in the image below;",
            "figures": figures_array
        }

        with content_path.open("w", encoding="utf-8") as f:
            json.dump(content_data, f, indent=2)

        print(f"Content generation complete. Saved to {content_path.name}")

    def generate_screen_path(self, nav_trail: list[str], screen_name: str) -> str:
        """Deterministic breadcrumb generation: 'Path: menu >> submenu >> screen_name'."""
        if not nav_trail:
            return screen_name
        # Filter out empty or None values
        clean_trail = [t for t in nav_trail if t]
        if screen_name not in clean_trail:
            clean_trail.append(screen_name)
        return " >> ".join(clean_trail)

    def generate_module_intro(self, session_dir: Path, module_name: str, module_number: int):
        """Generates the module intro paragraph and feature bullet list based on screens in session."""
        print(f"\nGenerating module introduction for module: {module_name}...")
        module_meta_path = session_dir / "module_meta.json"

        # Gather screens and their purposes
        screen_info = []
        screen_files = sorted(session_dir.glob("screen_*_content.json"))
        for f in screen_files:
            try:
                with f.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                # Skip state screens (only process primary screens)
                idx = int(f.name.split("_")[1])
                meta_path = session_dir / f"screen_{idx}_meta.json"
                if meta_path.exists():
                    with meta_path.open("r", encoding="utf-8") as m_file:
                        meta = json.load(m_file)
                    if meta.get("state_of") is not None:
                        continue
                screen_info.append({
                    "name": data.get("screen_name", ""),
                    "purpose": data.get("purpose", "")
                })
            except Exception:
                pass

        if not screen_info:
            print("No screens found to generate module intro.")
            return

        try:
            if hasattr(self.provider, "work_dir"):
                self.provider.work_dir = session_dir
            intro_data = self.provider.generate_module_intro(module_name, screen_info)
        except Exception as e:
            print(f"[Warning] Failed to generate module intro via LLM: {e}")
            # Fallback
            intro_data = {
                "intro": f"The {module_name} module in the application enables users to manage processes. Users can perform transactions, view lists, and enter data.",
                "features": [s.get("name", "") for s in screen_info]
            }

        module_meta = {
            "module_name": module_name,
            "module_number": module_number,
            "intro": intro_data.get("intro", ""),
            "features": intro_data.get("features", []),
            "screen_order": [int(f.name.split("_")[1]) for f in screen_files if "state" not in f.name]
        }

        with module_meta_path.open("w", encoding="utf-8") as f:
            json.dump(module_meta, f, indent=2)
        print(f"Module introduction saved to module_meta.json")