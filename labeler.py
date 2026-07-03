import json
from pathlib import Path
from typing import List, Dict, Any
from providers.base import LLMProvider, RegionForLabeling, FieldForDescribing

class Labeler:
    """
    Orchestrates LLM provider calls for region labels and document prose.
    """
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def switch_provider(self, new_provider: LLMProvider):
        """
        FR-22: Allows switching the active LLM provider mid-session.
        Called by main.py or the UI if the user changes their settings.
        """
        self.provider = new_provider
        print(f"Switched LLM provider for this session.")

    def label_screen_regions(self, session_dir: Path, screen_index: int):
        """
        Stage 3 (Label): Reads detected regions, asks the LLM to assign 
        human-readable labels, and saves them to screen_N_labeled.json.
        """
        print(f"\nLabeling regions for Screen {screen_index}...")
        
        regions_path = session_dir / f"screen_{screen_index}_regions.json"
        labeled_path = session_dir / f"screen_{screen_index}_labeled.json"
        
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
        regions_for_labeling = []
        for r in regions_data:
            candidates = r.get("elements_contained", [])
            regions_for_labeling.append(
                RegionForLabeling(
                    role=r.get("role", "unknown"), 
                    candidate_labels=candidates
                )
            )

        # Execute provider call (Browser copy-paste or API)
        if hasattr(self.provider, "work_dir"):
            self.provider.work_dir = session_dir
        labels = self.provider.label_regions(regions_for_labeling)

        # Merge generated labels back into the JSON payload
        for i, r in enumerate(regions_data):
            r["label"] = labels[i] if i < len(labels) else f"Unknown Region {i+1}"

        with labeled_path.open("w", encoding="utf-8") as f:
            json.dump(regions_data, f, indent=2)
            
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
        
        if not elements_path.exists() or not final_regions_path.exists():
            print(f"Required data missing to generate content for Screen {screen_index}.")
            return
            
        with elements_path.open("r", encoding="utf-8") as f:
            elements_data = json.load(f)
            
        with final_regions_path.open("r", encoding="utf-8") as f:
            final_regions_data = json.load(f)

        # Prepare form fields for description generation
        fields_for_describing = []
        for el in elements_data:
            if el.get("tag") in ["input", "select", "textarea"]:
                fields_for_describing.append(
                    FieldForDescribing(
                        name=el.get("accessible_name") or el.get("name") or "Unnamed Field",
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
            descriptions = self.provider.describe_fields(fields_for_describing)
        
        field_content = []
        for i, f_desc in enumerate(fields_for_describing):
            field_content.append({
                "field_name": f_desc.name,
                "description": descriptions[i] if i < len(descriptions) else ""
            })

        # Placeholder for procedure actions mapping
        actions = [{"action": "Navigate and interact", "target": "Screen elements"}] 
        prose = self.provider.procedure_prose(actions, context="User operation")

        content_data = {
            "field_descriptions": field_content,
            "procedure_prose": prose
        }

        with content_path.open("w", encoding="utf-8") as f:
            json.dump(content_data, f, indent=2)
            
        print(f"Content generation complete. Saved to {content_path.name}")