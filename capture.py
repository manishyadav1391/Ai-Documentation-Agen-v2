import json
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page
from config import get_config

def setup_session_dir() -> Path:
    """Creates a timestamped folder for the current session."""
    config = get_config()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = config.sessions_path / f"session_{timestamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir

def force_render_lazy_content(page: Page):
    """Scrolls the page to the bottom and back up to trigger lazy loading."""
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

def extract_dom_elements(page: Page) -> list[dict]:
    """
    Injects JavaScript to extract interactive DOM elements.
    Excludes hidden elements and those with zero dimensions.
    """
    js_script = """
    () => {
        // Target interactive elements and table cells
        const selectors = 'button, a, input, select, textarea, th, td, [role="button"], [role="link"]';
        const elements = document.querySelectorAll(selectors);
        const data = [];
        
        elements.forEach(el => {
            const style = window.getComputedStyle(el);
            // Skip hidden elements
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
            
            const rect = el.getBoundingClientRect();
            // Skip zero-dimension elements
            if (rect.width === 0 || rect.height === 0) return;
            
            // Redact password fields
            let value = el.value || null;
            const isPassword = el.type === 'password' || (el.name && el.name.match(/password|pin|otp|cvv/i));
            if (isPassword) value = '[REDACTED]';
            
            data.push({
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                role: el.getAttribute('role'),
                name: el.name || el.getAttribute('name'),
                id: el.id,
                required: el.required || false,
                max_length: el.getAttribute('maxlength') || null,
                pattern: el.pattern || null,
                placeholder: el.placeholder || null,
                accessible_name: el.getAttribute('aria-label') || el.innerText || value,
                bounding_box: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                ancestor_section: el.closest('form, table, div[role="region"]')?.tagName.toLowerCase() || null
            });
        });
        return data;
    }
    """
    return page.evaluate(js_script)

def capture_screen(page: Page, session_dir: Path, screen_index: int):
    """Executes the capture sequence for a single screen."""
    print(f"\nCapturing Screen {screen_index}...")
    
    force_render_lazy_content(page)
    
    # Generate file paths
    img_path = session_dir / f"screen_{screen_index}.png"
    elements_path = session_dir / f"screen_{screen_index}_elements.json"
    meta_path = session_dir / f"screen_{screen_index}_meta.json"
    
    # 1. Capture full-page screenshot
    page.screenshot(path=img_path, full_page=True)
    
    # 2. Extract DOM
    elements = extract_dom_elements(page)
    with elements_path.open("w", encoding="utf-8") as f:
        json.dump(elements, f, indent=2)
        
    # 3. Save Metadata
    meta = {
        "url": page.url,
        "title": page.title(),
        "viewport": page.viewport_size,
        "timestamp": datetime.now().isoformat()
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        
    print(f"Captured {len(elements)} interactive elements.")
    print(f"Saved artifacts to {session_dir.name}/")

def run_capture_session(start_url: str = "https://google.com"):
    """Main loop for the capture session."""
    session_dir = setup_session_dir()
    
    with sync_playwright() as p:
        # Launch headed browser so the writer can navigate manually
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        
        page.goto(start_url)
        print("\nBrowser launched. Navigate to your target module and log in if necessary.")
        
        screen_index = 1
        while True:
            cmd = input("\nPress [Enter] to capture current screen, or type 'q' to quit: ").strip().lower()
            if cmd == 'q':
                break
            
            capture_screen(page, session_dir, screen_index)
            screen_index += 1
            
        print(f"\nSession complete. Data saved in {session_dir}")
        browser.close()

if __name__ == "__main__":
    run_capture_session()