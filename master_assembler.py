import json
from pathlib import Path
from config import get_config
from templates.ncd.builder import NCDBuilder

def get_template_builder(template_name: str):
    builders = {"ncd": NCDBuilder}
    builder_class = builders.get(template_name.lower(), NCDBuilder)
    return builder_class()

def assemble_master_manual(ordered_session_dirs: list[Path], output_path: Path):
    """
    Combines multiple recorded modules into the final client deliverable,
    managing sequential figure numbers across modules.
    """
    config = get_config()
    builder = get_template_builder(config.default_template)
    
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
        
        local_screen_index = 1
        while True:
            img_path = session_dir / f"screen_{local_screen_index}_annotated.png"
            content_path = session_dir / f"screen_{local_screen_index}_content.json"
            
            if not img_path.exists() or not content_path.exists():
                break
                
            with content_path.open("r", encoding="utf-8") as f:
                content_data = json.load(f)
                
            # Inject using global counter so figures number from 1 to N continuously
            builder.add_screen_section(global_screen_counter, img_path, content_data)
            
            local_screen_index += 1
            global_screen_counter += 1
            
    # 3. Save Master File
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