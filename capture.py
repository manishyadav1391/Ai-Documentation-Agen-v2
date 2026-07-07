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
    """Injects JavaScript to extract ALL meaningful DOM elements — interactive AND static."""
    js_script = """
    () => {
        const data = [];

        // ── 1. INTERACTIVE ELEMENTS ────────────────────────────────────────────
        const interactive = 'button, input, select, textarea, [role="button"], [role="switch"], [role="checkbox"], [role="radio"], [role="combobox"], [role="listbox"], [role="menuitem"], [role="tab"]';
        document.querySelectorAll(interactive).forEach(el => {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;

            let value = el.value || null;
            const isPassword = el.type === 'password' || (el.name && el.name.match(/password|pin|otp|cvv/i));
            if (isPassword) value = '[REDACTED]';

            // Derive the best accessible name available
            const ariaLabel = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('data-tooltip') || null;
            const innerText = el.innerText ? el.innerText.trim().slice(0, 120) : null;
            const accessible_name = ariaLabel || innerText || el.getAttribute('placeholder') || value || el.name || null;

            data.push({
                element_class: 'interactive',
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                role: el.getAttribute('role'),
                name: el.name || el.getAttribute('name'),
                id: el.id,
                required: el.required || false,
                max_length: el.getAttribute('maxlength') || null,
                pattern: el.pattern || null,
                placeholder: el.placeholder || null,
                accessible_name: accessible_name,
                bounding_box: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                ancestor_section: el.closest('form, table, [role="dialog"], [role="main"]')?.tagName.toLowerCase() || null
            });
        });

        // ── 2. NAVIGATION LINKS ────────────────────────────────────────────────
        const navSelectors = 'nav a, header a, [role="navigation"] a, .sidebar a, .menu a, .navbar a, aside a';
        document.querySelectorAll(navSelectors).forEach(el => {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            const rect = el.getBoundingClientRect();
            if (rect.width < 5 || rect.height < 5) return;
            const text = el.innerText ? el.innerText.trim() : null;
            if (!text || text.length < 2) return;
            data.push({
                element_class: 'navigation',
                tag: 'a',
                type: 'nav_link',
                role: 'link',
                name: text,
                id: el.id,
                required: false,
                max_length: null,
                pattern: null,
                placeholder: null,
                accessible_name: text,
                bounding_box: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                ancestor_section: 'navigation'
            });
        });

        // ── 3. PAGE HEADINGS & LABELS ──────────────────────────────────────────
        const staticSelectors = 'h1, h2, h3, h4, label, .page-title, .card-title, .section-title, [class*="heading"], [class*="title"], caption';
        document.querySelectorAll(staticSelectors).forEach(el => {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            const rect = el.getBoundingClientRect();
            if (rect.width < 5 || rect.height < 5) return;
            const text = el.innerText ? el.innerText.trim().slice(0, 200) : null;
            if (!text || text.length < 2) return;
            data.push({
                element_class: 'static_label',
                tag: el.tagName.toLowerCase(),
                type: 'label',
                role: 'heading',
                name: text,
                id: el.id,
                required: false,
                max_length: null,
                pattern: null,
                placeholder: null,
                accessible_name: text,
                bounding_box: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                ancestor_section: el.closest('form, table, section, main, div[role="main"]')?.tagName.toLowerCase() || null
            });
        });

        // ── 4. TABLE HEADERS ───────────────────────────────────────────────────
        document.querySelectorAll('th, [role="columnheader"]').forEach(el => {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;
            const text = el.innerText ? el.innerText.trim() : null;
            if (!text) return;
            data.push({
                element_class: 'table_column',
                tag: 'th',
                type: 'column_header',
                role: 'columnheader',
                name: text,
                id: el.id,
                required: false,
                max_length: null,
                pattern: null,
                placeholder: null,
                accessible_name: text,
                bounding_box: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                ancestor_section: 'table'
            });
        });

        return data;
    }
    """
    return page.evaluate(js_script)

def extract_page_context(page: Page) -> dict:
    """Extracts high-level page metadata: title, H1, visible body summary."""
    js_context = """
    () => {
        const h1 = document.querySelector('h1');
        const pageTitle = document.title || '';
        const h1Text = h1 ? h1.innerText.trim() : '';

        // Breadcrumb detection
        const breadcrumb = document.querySelector('[aria-label="breadcrumb"], .breadcrumb, nav ol, nav ul.breadcrumb');
        const breadcrumbText = breadcrumb ? breadcrumb.innerText.trim().replace(/\\n/g, ' > ').slice(0, 200) : '';

        // Active tab/section detection
        const activeTab = document.querySelector('[role="tab"][aria-selected="true"], .nav-tab.active, .tab-item.active');
        const activeTabText = activeTab ? activeTab.innerText.trim() : '';

        return {
            page_title: pageTitle,
            h1_text: h1Text,
            breadcrumb: breadcrumbText,
            active_tab: activeTabText,
            url: window.location.href
        };
    }
    """
    try:
        return page.evaluate(js_context)
    except Exception:
        return {"page_title": page.title(), "h1_text": "", "breadcrumb": "", "active_tab": "", "url": page.url}

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

    # Save rich page context alongside legacy meta
    context = extract_page_context(page)
    meta = {
        "url": page.url,
        "title": page.title(),
        "h1_text": context.get("h1_text", ""),
        "breadcrumb": context.get("breadcrumb", ""),
        "active_tab": context.get("active_tab", ""),
        "viewport": page.viewport_size,
        "timestamp": datetime.now().isoformat(),
        "screen_name": ""   # placeholder — filled by review UI
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        
    interactive_count = sum(1 for e in elements if e.get("element_class") == "interactive")
    static_count = len(elements) - interactive_count
    print(f"Captured {interactive_count} interactive + {static_count} static elements for Screen {screen_index}.")

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