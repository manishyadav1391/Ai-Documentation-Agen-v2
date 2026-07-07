import json
from pathlib import Path
from config import get_config
from templates.corporate.builder import CorporateBuilder

def get_template_builder(template_name: str, style_config: dict = None):
    builders = {
        "corporate": CorporateBuilder
    }
    builder_class = builders.get(template_name.lower(), CorporateBuilder)
    return builder_class(style_config)

def assemble_master_manual(ordered_session_dirs: list[Path], output_path: Path):
    """
    Combines multiple recorded modules into the final client deliverable,
    managing sequential figure numbers across modules.
    """
    config = get_config()
    style_config = config.theme.model_dump() if hasattr(config, "theme") else None
    builder = get_template_builder(config.default_template, style_config)
    
    print("=======================================================")
    print("         Generating Master Client Manual...            ")
    print("=======================================================")
    
    # 1. Master Document Boilerplate (FR-37)
    builder.add_cover_page(title="Comprehensive User Manual")
    builder.add_revision_history()
    builder.add_toc_placeholder()
    
    global_screen_counter = 1
    
    # 2. Iterate through the ordered list of modules
    for session_dir in ordered_session_dirs:
        print(f"\nProcessing module: {session_dir.name}...")
        
        # Add section divider page if using corporate layout
        if hasattr(builder, "add_divider_page"):
            # Try to read a meaningful module name from the first screen's meta
            first_meta_path = session_dir / "screen_1_meta.json"
            module_name = ""
            if first_meta_path.exists():
                try:
                    with first_meta_path.open("r", encoding="utf-8") as f:
                        first_meta = json.load(f)
                    module_name = first_meta.get("screen_name") or first_meta.get("h1_text") or first_meta.get("title", "")
                except Exception:
                    pass
            if not module_name:
                module_name = session_dir.name.replace("session_", "Session ").replace("_", " ").title()
            builder.add_divider_page(
                title=module_name,
                description=f"Detailed procedural steps and interface dictionary for the {module_name} module."
            )
        
        local_screen_index = 1
        while True:
            img_path = session_dir / f"screen_{local_screen_index}_annotated.png"
            content_path = session_dir / f"screen_{local_screen_index}_content.json"
            
            if not img_path.exists() or not content_path.exists():
                break
                
            with content_path.open("r", encoding="utf-8") as f:
                content_data = json.load(f)
                
            # Read screen meta for semantic name
            meta_path = session_dir / f"screen_{local_screen_index}_meta.json"
            screen_meta = {}
            if meta_path.exists():
                try:
                    with meta_path.open("r", encoding="utf-8") as f:
                        screen_meta = json.load(f)
                except Exception:
                    pass

            # Inject using global counter so figures number from 1 to N continuously
            builder.add_screen_section(global_screen_counter, img_path, content_data, screen_meta=screen_meta)

            local_screen_index += 1
            global_screen_counter += 1
            
    # 3. Ensure output directory exists and save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    builder.save(output_path)
    print(f"\nMaster Manual assembly complete! Saved to {output_path}")

if __name__ == "__main__":
    # Test execution: Grab all sessions in chronological order and combine them
    sessions_dir = Path("sessions")
    if sessions_dir.exists():
        all_sessions = sorted(sessions_dir.glob("session_*"))
        if all_sessions:
            master_output = Path("Final_Client_Manual.docx")
            assemble_master_manual(all_sessions, master_output)