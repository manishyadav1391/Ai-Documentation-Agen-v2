import json
from pathlib import Path
from config import get_config
from templates.ncd.builder import NCDBuilder

def get_template_builder(template_name: str):
    """
    Factory function to return the correct document builder 
    based on the configuration setting (FR-36).
    """
    # As new templates (GSTAT, AIASL) are added, they are registered here.
    builders = {
        "ncd": NCDBuilder,
        # "gstat": GSTATBuilder,
        # "aiasl": AIASLBuilder
    }
    
    builder_class = builders.get(template_name.lower())
    if not builder_class:
        print(f"Warning: Template '{template_name}' not found. Defaulting to 'ncd'.")
        return NCDBuilder()
        
    return builder_class()

def assemble_manual(session_dir: Path):
    """
    Stage 7 (Assemble): Builds the final Word document by delegating
    the layout and formatting to the configured Client Template.
    """
    config = get_config()
    template_name = config.default_template
    print(f"\nStarting document assembly using template: '{template_name}'...")
    
    # 1. Initialize the correct client template
    builder = get_template_builder(template_name)
    
    # 2. Add boilerplate sections (FR-37)
    builder.add_cover_page(title="User Manual")
    builder.add_revision_history()
    builder.add_toc_placeholder()
    
    # 3. Iterate through all screens in the session
    screen_index = 1
    while True:
        img_path = session_dir / f"screen_{screen_index}_annotated.png"
        content_path = session_dir / f"screen_{screen_index}_content.json"
        
        # Break loop if we've run out of processed screens
        if not img_path.exists() or not content_path.exists():
            break
            
        print(f"Injecting Screen {screen_index} into document...")
        
        # Load LLM Content
        with content_path.open("r", encoding="utf-8") as f:
            content_data = json.load(f)
            
        # Delegate the section rendering to the builder (FR-38, FR-39, FR-40)
        builder.add_screen_section(screen_index, img_path, content_data)
        
        screen_index += 1
        
    # 4. Save the final document (FR-35)
    output_docx = session_dir / "manual.docx"
    builder.save(output_docx)
    print(f"\nDocument assembly complete! Saved to {output_docx.name}")

if __name__ == "__main__":
    # Test execution for the latest session
    sessions_dir = Path("sessions")
    if sessions_dir.exists():
        sessions = sorted(sessions_dir.glob("session_*"))
        if sessions:
            assemble_manual(sessions[-1])