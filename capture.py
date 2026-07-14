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
    """Extracts high-level page metadata: title, H1, visible body summary, nav trail, siblings."""
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

        // Calculate navigation trail
        const navTrail = [];
        if (breadcrumbText) {
            breadcrumbText.split(' > ').forEach(part => {
                const cleanPart = part.trim();
                if (cleanPart && !navTrail.includes(cleanPart)) {
                    navTrail.push(cleanPart);
                }
            });
        }
        
        // Find visible siblings of the active menu link
        const siblingScreens = [];
        const activeMenu = document.querySelector('.sidebar .active, .menu .active')?.closest('ul, ol');
        if (activeMenu) {
            activeMenu.querySelectorAll('a').forEach(link => {
                const text = link.innerText.trim();
                if (text && !siblingScreens.includes(text)) {
                    siblingScreens.push(text);
                }
            });
        }

        return {
            page_title: pageTitle,
            h1_text: h1Text,
            breadcrumb: breadcrumbText,
            active_tab: activeTabText,
            url: window.location.href,
            nav_trail: navTrail,
            sibling_screens: siblingScreens
        };
    }
    """
    try:
        return page.evaluate(js_context)
    except Exception:
        return {"page_title": page.title(), "h1_text": "", "breadcrumb": "", "active_tab": "", "url": page.url, "nav_trail": [], "sibling_screens": []}

def capture_screen(page: Page, session_dir: Path, screen_index: int, state_of: int = None, state_label: str = None):
    """Executes the capture sequence for a single screen or screen state."""
    if state_of is not None:
        # Determine the next state index for the parent screen
        existing_states = list(session_dir.glob(f"screen_{state_of}_state_*_elements.json"))
        state_idx = len(existing_states) + 1
        img_name = f"screen_{state_of}_state_{state_idx}.png"
        elements_name = f"screen_{state_of}_state_{state_idx}_elements.json"
        meta_name = f"screen_{state_of}_state_{state_idx}_meta.json"
        print(f"\n[State Capture Triggered] Processing State {state_idx} for Screen {state_of}...")
    else:
        img_name = f"screen_{screen_index}.png"
        elements_name = f"screen_{screen_index}_elements.json"
        meta_name = f"screen_{screen_index}_meta.json"
        print(f"\n[Capture Triggered] Processing Screen {screen_index}...")
    
    force_render_lazy_content(page)
    
    img_path = session_dir / img_name
    elements_path = session_dir / elements_name
    meta_path = session_dir / meta_name
    
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
        "screen_name": "",   # placeholder — filled by review UI
        "nav_trail": context.get("nav_trail", []),
        "sibling_screens": context.get("sibling_screens", []),
        "state_of": state_of,
        "state_label": state_label
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        
    interactive_count = sum(1 for e in elements if e.get("element_class") == "interactive")
    static_count = len(elements) - interactive_count
    if state_of is not None:
        print(f"Captured state {state_idx} ({interactive_count} interactive + {static_count} static elements) for Screen {state_of}.")
    else:
        print(f"Captured screen {screen_index} ({interactive_count} interactive + {static_count} static elements).")

def setup_mouse_triggers(page: Page, session_dir: Path, app_state: dict):
    """Injects a smart global mouse listener inside the browser context."""
    
    def python_capture():
        app_state["capture_requested"] = True

    def python_state_capture():
        app_state["state_capture_requested"] = True

    def python_quit():
        print("\n[Quit Triggered] Double middle-click detected. Ending capture session...")
        app_state["quit"] = True

    # Expose Python functions to the browser
    page.expose_function("triggerPythonCapture", python_capture)
    page.expose_function("triggerPythonStateCapture", python_state_capture)
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
                    if (e.shiftKey) {
                        window.triggerPythonStateCapture();
                    } else {
                        window.triggerPythonCapture();
                    }
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
    app_state = {
        "index": 1,
        "quit": False,
        "capture_requested": False,
        "state_capture_requested": False
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        
        setup_mouse_triggers(page, session_dir, app_state)
        page.goto(start_url)
        
        print("\n=======================================================")
        print("Browser Active. Controls:")
        print("  * SINGLE Middle-Click: Capture the current screen.")
        print("  * SHIFT + Middle-Click: Capture as additional state of last screen.")
        print("  * DOUBLE Middle-Click: Quit and process the manual.")
        print("=======================================================")
        
        # Non-blocking loop: keeps the script alive but yields to Playwright's event loop
        while not app_state["quit"]:
            if app_state["capture_requested"]:
                app_state["capture_requested"] = False
                capture_screen(page, session_dir, app_state["index"])
                app_state["index"] += 1
                
            elif app_state["state_capture_requested"]:
                app_state["state_capture_requested"] = False
                parent_idx = app_state["index"] - 1
                if parent_idx >= 1:
                    # Retrieve prompt or default label
                    state_lbl = f"State {len(list(session_dir.glob(f'screen_{parent_idx}_state_*_elements.json'))) + 1}"
                    capture_screen(page, session_dir, app_state["index"], state_of=parent_idx, state_label=state_lbl)
                else:
                    print("Cannot capture state: No main screens have been captured yet.")
                    
            # Check every 100ms. This prevents the terminal from hanging.
            page.wait_for_timeout(100) 
                
        print(f"\nSession closed. Data saved in {session_dir.name}")
        browser.close()

if __name__ == "__main__":
    run_capture_session()