import json
from pathlib import Path
from config import get_config
from templates.corporate.builder import CorporateBuilder

def get_template_builder(template_name: str, style_config: dict = None):
    """Factory to return the correct document builder."""
    builders = {
        "corporate": CorporateBuilder
    }
    builder_class = builders.get(template_name.lower(), CorporateBuilder)
    return builder_class(style_config)

def assemble_module(session_dir: Path):
    """
    Builds a lightweight module draft for a specific session.
    Omits the master cover page, TOC, and revision history.
    """
    config = get_config()
    template_name = config.default_template
    style_config = config.theme.model_dump() if hasattr(config, "theme") else None
    builder = get_template_builder(template_name, style_config)
    
    print(f"\nAssembling local module draft using template: '{template_name}'...")
    
    draft_title = f"Module Draft: {session_dir.name.replace('session_', 'Session ').replace('_', ' ').title()}"
    draft_desc = "This is a lightweight local module draft containing screen annotation details, procedural instructions, and the interface element dictionary."
    if hasattr(builder, "add_draft_title"):
        builder.add_draft_title(draft_title, draft_desc)
    
    screen_index = 1
    while True:
        img_path = session_dir / f"screen_{screen_index}_annotated.png"
        content_path = session_dir / f"screen_{screen_index}_content.json"
        
        if not img_path.exists() or not content_path.exists():
            break
            
        print(f"Injecting Screen {screen_index} into module...")
        
        with content_path.open("r", encoding="utf-8") as f:
            content_data = json.load(f)
            
        # Load meta for semantic screen name
        meta_path = session_dir / f"screen_{screen_index}_meta.json"
        screen_meta = {}
        if meta_path.exists():
            try:
                with meta_path.open("r", encoding="utf-8") as f:
                    screen_meta = json.load(f)
            except Exception:
                pass

        builder.add_screen_section(screen_index, img_path, content_data, screen_meta=screen_meta)
        screen_index += 1
        
    output_docx = session_dir / "module_draft.docx"
    # Ensure parent directory exists
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    builder.save(output_docx)
    print(f"Module assembly complete! Saved to {output_docx.name}")