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
    page.wait_for_timeout(500)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)

def extract_dom_elements(page: Page) -> list[dict]:
    """Injects JavaScript to extract interactive DOM elements."""
    js_script = """
    () => {
        const selectors = 'button, a, input, select, textarea, th, td, [role="button"], [role="link"]';
        const elements = document.querySelectorAll(selectors);
        const data = [];
        
        elements.forEach(el => {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
            
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;
            
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
    print(f"\n[Capture Triggered] Processing Screen {screen_index}...")
    
    force_render_lazy_content(page)
    
    img_path = session_dir / f"screen_{screen_index}.png"
    elements_path = session_dir / f"screen_{screen_index}_elements.json"
    meta_path = session_dir / f"screen_{screen_index}_meta.json"
    
    page.screenshot(path=img_path, full_page=True)
    
    elements = extract_dom_elements(page)
    with elements_path.open("w", encoding="utf-8") as f:
        json.dump(elements, f, indent=2)
        
    meta = {
        "url": page.url,
        "title": page.title(),
        "viewport": page.viewport_size,
        "timestamp": datetime.now().isoformat()
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        
    print(f"Captured {len(elements)} interactive elements for Screen {screen_index}.")

def setup_mouse_triggers(page: Page, session_dir: Path, app_state: dict):
    """Injects a smart global mouse listener inside the browser context."""
    
    def python_capture():
        app_state["capture_requested"] = True

    def python_quit():
        print("\n[Quit Triggered] Double middle-click detected. Ending capture session...")
        app_state["quit"] = True

    # Expose both Python functions to the browser
    page.expose_function("triggerPythonCapture", python_capture)
    page.expose_function("triggerPythonQuit", python_quit)

    # JS logic: Uses a 400ms timer to differentiate single vs double clicks
    init_script = """
    let middleClickTimer = null;
    
    window.addEventListener('mousedown', (e) => {
        if (e.button === 1) { 
            e.preventDefault(); 
            
            if (middleClickTimer) {
                // Timer is active: this is a DOUBLE click
                clearTimeout(middleClickTimer);
                middleClickTimer = null;
                window.triggerPythonQuit();
            } else {
                // Timer is not active: wait 400ms to see if it's a SINGLE click
                middleClickTimer = setTimeout(() => {
                    window.triggerPythonCapture();
                    middleClickTimer = null;
                }, 400); 
            }
        }
    }, true);
    """
    
    page.add_init_script(init_script)
    page.evaluate(init_script)

def run_capture_session(start_url: str = "https://google.com"):
    """Main loop for the capture session."""
    session_dir = setup_session_dir()
    
    # We use a state dictionary so the exposed functions can modify these values
    app_state = {"index": 1, "quit": False, "capture_requested": False}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        
        setup_mouse_triggers(page, session_dir, app_state)
        page.goto(start_url)
        
        print("\n=======================================================")
        print("Browser Active. Controls:")
        print("  * SINGLE Middle-Click: Capture the current screen.")
        print("  * DOUBLE Middle-Click: Quit and process the manual.")
        print("=======================================================")
        
        # Non-blocking loop: keeps the script alive but yields to Playwright's event loop
        while not app_state["quit"]:
            if app_state["capture_requested"]:
                app_state["capture_requested"] = False
                capture_screen(page, session_dir, app_state["index"])
                app_state["index"] += 1
            # Check every 100ms. This prevents the terminal from hanging.
            page.wait_for_timeout(100) 
                
        print(f"\nSession closed. Data saved in {session_dir.name}")
        browser.close()

if __name__ == "__main__":
    run_capture_session()