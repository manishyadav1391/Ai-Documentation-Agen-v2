"""
DocBot v3 — Playwright capture session.

Runs a headed Chromium browser, instruments every page/tab with the
event hook script, and handles the writer's middle-click gestures.

CHANGE LOG (visible-area capture fix)
-------------------------------------
FIX-1  Middle-click now captures EXACTLY what is visible on the monitor
       at the writer's CURRENT scroll position. The lazy-render
       scroll-to-bottom/scroll-to-top dance is now done ONLY for
       full-page captures (it was resetting the view to the top of the
       page before every screenshot).
FIX-2  In viewport captures, elements are FILTERED to those visible in
       the viewport and their bounding boxes are TRANSLATED into
       viewport coordinates (bbox_document - scroll). Regions, labels
       and annotations therefore cover ONLY the visible area and align
       pixel-perfect with the screenshot. (Fixed/sticky elements work
       too: the JS added scroll to their rects, so the same subtraction
       lands them correctly.)
FIX-3  Scroll segmentation (seg1/seg2) only runs when
       capture.scroll_capture is true AND mode is viewport. Set
       scroll_capture: false in config.yaml to disable it entirely.

Gesture table (unchanged):
  Middle-click          → capture VISIBLE screen (configured mode)
  Ctrl + Middle-click   → force FULL-PAGE for this capture
  Shift + Middle-click  → capture as state of previous screen (always viewport)
  Double Middle-click   → quit session and start processing
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.sync_api import sync_playwright, Page

from config import get_config
from docbot.logging_setup import attach_session_log
from docbot.models import (
    BBox, Element, Event, Figure, Screen, SessionModel, SessionStore,
)

# Load injected.js once at import time
_JS_HOOK = (Path(__file__).parent / "injected.js").read_text(encoding="utf-8")

# DOM extraction JS — run on each capture to get current page elements.
# Coordinates are DOCUMENT coordinates (rect + scroll); for viewport
# captures they are translated to viewport space in Python (FIX-2).
_DOM_EXTRACT_JS = """
() => {
  const data = [];
  const scrollX = window.scrollX, scrollY = window.scrollY;

  // 1. Interactive elements
  const interactive = 'button, input, select, textarea, [role="button"], [role="switch"], [role="checkbox"], [role="radio"], [role="combobox"], [role="listbox"], [role="menuitem"], [role="tab"]';
  document.querySelectorAll(interactive).forEach((el, i) => {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    const ariaLabel = el.getAttribute('aria-label') || el.getAttribute('title') || null;
    const innerText = el.innerText ? el.innerText.trim().slice(0, 120) : null;
    const accessible_name = ariaLabel || innerText || el.getAttribute('placeholder') || el.name || null;
    const pos = window.getComputedStyle(el).position;
    const form = el.closest('form');
    const formId = form ? (form.id || form.getAttribute('name') || 'form_' + Array.from(document.forms).indexOf(form)) : null;

    data.push({
      element_class: 'interactive',
      tag: el.tagName.toLowerCase(),
      type: el.type || null,
      role: el.getAttribute('role'),
      name: el.name || el.getAttribute('name'),
      id: el.id || ('el_' + i),
      required: el.required || false,
      max_length: el.getAttribute('maxlength') ? parseInt(el.getAttribute('maxlength')) : null,
      pattern: el.pattern || null,
      placeholder: el.placeholder || null,
      accessible_name: accessible_name,
      bounding_box: {x: rect.x + scrollX, y: rect.y + scrollY, width: rect.width, height: rect.height},
      ancestor_section: el.closest('form, table, [role="dialog"], [role="main"]')?.tagName.toLowerCase() || null,
      form_id: formId,
      is_fixed: (pos === 'fixed' || pos === 'sticky')
    });
  });

  // 2. Navigation links
  const navSel = [
    'nav a', 'header a', '[role="navigation"] a', '.sidebar a', '.menu a', '.navbar a', 'aside a',
    '[class*="sidebar"] a', '[class*="sidenav"] a', '[class*="side-nav"] a', '[class*="nav-menu"] a',
    '[id*="sidebar"] a', '[id*="sidenav"] a', 'ul.nav a', '.nav-item a', 'a.nav-link',
    '[role="menubar"] a', '[role="tree"] a', '[role="treeitem"]',
    '[class*="left-panel"] a', '[class*="leftpanel"] a', '[class*="left-menu"] a'
  ].join(', ');
  document.querySelectorAll(navSel).forEach((el, i) => {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
    const rect = el.getBoundingClientRect();
    if (rect.width < 5 || rect.height < 5) return;
    const text = el.innerText ? el.innerText.trim() : null;
    if (!text || text.length < 2) return;
    const pos = window.getComputedStyle(el).position;
    data.push({
      element_class: 'navigation', tag: 'a', type: 'nav_link', role: 'link',
      name: text, id: el.id || ('nav_' + i), required: false, max_length: null,
      pattern: null, placeholder: null, accessible_name: text,
      bounding_box: {x: rect.x + scrollX, y: rect.y + scrollY, width: rect.width, height: rect.height},
      ancestor_section: 'navigation', form_id: null,
      is_fixed: (pos === 'fixed' || pos === 'sticky')
    });
  });

  // 3. Page headings & labels
  document.querySelectorAll('h1, h2, h3, h4, label, .page-title, .card-title, .section-title, caption').forEach((el, i) => {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
    const rect = el.getBoundingClientRect();
    if (rect.width < 5 || rect.height < 5) return;
    const text = el.innerText ? el.innerText.trim().slice(0, 200) : null;
    if (!text || text.length < 2) return;
    data.push({
      element_class: 'static_label', tag: el.tagName.toLowerCase(), type: 'label',
      role: 'heading', name: text, id: el.id || ('lbl_' + i), required: false,
      max_length: null, pattern: null, placeholder: null, accessible_name: text,
      bounding_box: {x: rect.x + scrollX, y: rect.y + scrollY, width: rect.width, height: rect.height},
      ancestor_section: el.closest('form, table, section, main, div[role="main"]')?.tagName.toLowerCase() || null,
      form_id: null, is_fixed: false
    });
  });

  // 4. Table headers
  document.querySelectorAll('th, [role="columnheader"]').forEach((el, i) => {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const text = el.innerText ? el.innerText.trim() : null;
    if (!text) return;
    data.push({
      element_class: 'table_column', tag: 'th', type: 'column_header',
      role: 'columnheader', name: text, id: el.id || ('th_' + i), required: false,
      max_length: null, pattern: null, placeholder: null, accessible_name: text,
      bounding_box: {x: rect.x + scrollX, y: rect.y + scrollY, width: rect.width, height: rect.height},
      ancestor_section: 'table', form_id: null, is_fixed: false
    });
  });

  return data;
}
"""

_PAGE_CONTEXT_JS = """
() => {
  const h1 = document.querySelector('h1');
  const breadcrumb = document.querySelector('[aria-label="breadcrumb"], .breadcrumb, nav ol');
  const breadcrumbText = breadcrumb ? breadcrumb.innerText.trim().replace(/\\n/g, ' > ').slice(0, 200) : '';
  const navTrail = breadcrumbText ? breadcrumbText.split(' > ').filter(Boolean) : [];
  return {
    page_title: document.title || '',
    h1_text: h1 ? h1.innerText.trim() : '',
    breadcrumb: breadcrumbText,
    url: window.location.href,
    nav_trail: navTrail,
    device_pixel_ratio: window.devicePixelRatio || 1.0
  };
}
"""

# Viewport geometry at THIS INSTANT (current scroll position)
_VIEWPORT_BOX_JS = """
() => ({
    x: window.scrollX,
    y: window.scrollY,
    width: window.innerWidth,
    height: window.innerHeight
})
"""


class CaptureSession:
    """Manages a single recording session from start to close."""

    def __init__(
        self,
        start_url: str,
        client_key: str,
        module_name: str = "",
        module_number: int | None = None,
        session_dir: Path | None = None,
    ) -> None:
        cfg = get_config()
        self.cfg = cfg
        self.capture_mode = cfg.capture.mode          # viewport | full_page | both
        self.scroll_capture = cfg.capture.scroll_capture

        # Session model
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = ts
        if session_dir is None:
            clean_module = "".join(c if c.isalnum() else "_" for c in module_name).strip("_")
            prefix = f"{clean_module}_{ts}" if clean_module else f"session_{ts}"
            session_dir = cfg.sessions_path / prefix

        session_dir.mkdir(parents=True, exist_ok=True)
        self.session_dir = session_dir

        attach_session_log(session_dir)

        self.session = SessionModel(
            session_id=session_id,
            client_key=client_key,
            module_name=module_name,
            module_number=module_number,
            start_url=start_url,
        )

        # Mutable state (shared between browser callbacks and main loop)
        self._state: dict[str, Any] = {
            "capture_requested": False,
            "full_page_capture_requested": False,
            "state_capture_requested": False,
            "quit": False,
            "screen_index": 1,
            "pending_events": [],
            "last_viewport_screenshot": None,
        }
        self._lock = threading.Lock()
        self._pages: dict[str, Page] = {}

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #

    def run(self) -> SessionModel:
        """Launch browser, record, return the completed session model."""
        logger.info(f"Starting capture session → {self.session_dir.name}")
        logger.info(f"Start URL: {self.session.start_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--start-maximized"],
            )
            context = browser.new_context(
                no_viewport=True,
            )
            # Restore saved auth state if available
            state_path = self.cfg.sessions_path / "state" / f"{self.session.client_key}.json"
            if state_path.exists():
                try:
                    context = browser.new_context(
                        no_viewport=True,
                        storage_state=str(state_path),
                    )
                    logger.info(f"Restored auth state from {state_path.name}")
                except Exception as e:
                    logger.warning(f"Could not restore auth state: {e}")

            # Instrument every new page / tab (W9 multi-tab fix)
            context.on("page", self._setup_page)

            page = context.new_page()
            page.goto(self.session.start_url)

            logger.info("=" * 55)
            logger.info("Browser active. Controls:")
            logger.info("  Capture VISIBLE screen → Middle-click  OR  Alt + C  OR  Ctrl + Shift + C")
            logger.info("  Force FULL page        → Ctrl+Middle-click  OR  Alt + F  OR  Ctrl + Shift + F")
            logger.info("  Capture state          → Shift+Middle-click  OR  Alt + S  OR  Ctrl + Shift + S")
            logger.info("  Quit & Process         → Double Middle-click  OR  Alt + Q  OR  Ctrl + Shift + Q")
            logger.info("=" * 55)

            # Event loop — non-blocking poll
            while not self._state["quit"]:
                page.wait_for_timeout(100)
                self._process_pending_captures(page)

            # Save auth state for next session
            state_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                context.storage_state(path=str(state_path))
                logger.info(f"Auth state saved to {state_path.name}")
            except Exception as e:
                logger.warning(f"Could not save auth state: {e}")

            browser.close()

        SessionStore.save(self.session, self.session_dir)
        logger.info(
            f"Session closed. {len(self.session.screens)} screens captured. "
            f"Data in: {self.session_dir.name}"
        )
        return self.session

    # ------------------------------------------------------------------ #
    # Page setup (called for every new page / tab)
    # ------------------------------------------------------------------ #

    def _setup_page(self, page: Page) -> None:
        """Instrument a page with event hooks and gesture triggers."""
        page_id = str(uuid.uuid4())[:8]
        self._pages[page_id] = page

        page.add_init_script(f"window.__docbotPageId = '{page_id}';")
        page.add_init_script(_JS_HOOK)
        try:
            page.evaluate(_JS_HOOK)
        except Exception:
            pass  # add_init_script covers future navigations

        page.expose_function("docbotEvent", self._on_js_event)
        page.expose_function("triggerCapture", self._on_capture)
        page.expose_function("triggerFullPageCapture", self._on_full_page_capture)
        page.expose_function("triggerStateCapture", self._on_state_capture)
        page.expose_function("triggerQuit", self._on_quit)

        logger.debug(f"Page {page_id} instrumented.")

    # ------------------------------------------------------------------ #
    # JS → Python callbacks
    # ------------------------------------------------------------------ #

    def _on_js_event(self, raw_json: str) -> None:
        with self._lock:
            self._state["pending_events"].append(raw_json)

    def _on_capture(self) -> None:
        with self._lock:
            self._state["capture_requested"] = True

    def _on_full_page_capture(self) -> None:
        with self._lock:
            self._state["full_page_capture_requested"] = True

    def _on_state_capture(self) -> None:
        with self._lock:
            self._state["state_capture_requested"] = True

    def _on_quit(self) -> None:
        logger.info("Quit triggered by double middle-click.")
        with self._lock:
            self._state["quit"] = True

    # ------------------------------------------------------------------ #
    # Capture logic
    # ------------------------------------------------------------------ #

    def _process_pending_captures(self, page: Page) -> None:
        with self._lock:
            do_capture = self._state.pop("capture_requested", False)
            do_full = self._state.pop("full_page_capture_requested", False)
            do_state = self._state.pop("state_capture_requested", False)
            pending_events = self._state["pending_events"][:]
            self._state["pending_events"].clear()

        if pending_events and self.session.screens:
            self._flush_events(pending_events, self.session.screens[-1])

        if do_full:
            self._capture_screen(page, force_full_page=True)
        elif do_state:
            self._capture_screen(page, is_state=True)
        elif do_capture:
            self._capture_screen(page)

    def _flush_events(self, raw_events: list[str], screen: Screen) -> None:
        import json as _json
        for raw in raw_events:
            try:
                data = _json.loads(raw)
                bbox_raw = data.get("target_bbox")
                screen.events.append(Event(
                    id=data.get("id", str(uuid.uuid4())[:8]),
                    ts=float(data.get("ts", 0)),
                    kind=data.get("kind", "click"),
                    target_selector=data.get("target_selector"),
                    target_name=data.get("target_name"),
                    target_role=data.get("target_role"),
                    target_bbox=BBox(**bbox_raw) if bbox_raw else None,
                    value_summary=data.get("value_summary"),
                    redacted=bool(data.get("redacted", False)),
                    url_before=data.get("url_before"),
                    url_after=data.get("url_after"),
                    page_id=data.get("page_id", "main"),
                ))
            except Exception as e:
                logger.warning(f"Could not parse event: {e}")

    def _capture_screen(
        self,
        page: Page,
        is_state: bool = False,
        force_full_page: bool = False,
    ) -> None:
        """Execute a full capture sequence for one screen or state."""
        idx = self._state["screen_index"]
        parent_idx = None
        state_num = None

        if is_state:
            if not self.session.screens:
                logger.warning("Cannot capture state: no main screens captured yet.")
                return
            parent_idx = self.session.screens[-1].index
            state_num = sum(1 for s in self.session.screens if s.state_of == parent_idx) + 1
            logger.info(f"Capturing state {state_num} for Screen {parent_idx}…")
        else:
            logger.info(f"Capturing Screen {idx}…")

        # Determine the mode for this capture.
        # States are ALWAYS viewport (capture exactly what the writer sees).
        if is_state:
            mode = "viewport"
        elif force_full_page:
            mode = "full_page"
        else:
            mode = self.capture_mode

        # ------------------------------------------------------------------
        # FIX-1: lazy-render scroll dance ONLY for full-page captures.
        # For viewport captures we must NOT touch the scroll position —
        # the writer middle-clicked on what they are LOOKING AT right now.
        # ------------------------------------------------------------------
        if mode in ("full_page", "both"):
            try:
                original_scroll = page.evaluate("({x: window.scrollX, y: window.scrollY})")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(400)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(400)
                # Restore the writer's original position so 'both' mode
                # viewport shot (and their browsing) is unaffected.
                page.evaluate(
                    f"window.scrollTo({original_scroll['x']}, {original_scroll['y']})"
                )
                page.wait_for_timeout(200)
            except Exception:
                pass

        # Page context
        try:
            ctx = _get_page_context(page)
        except Exception as e:
            logger.warning(f"Could not get page context: {e}")
            ctx = {"page_title": page.title(), "h1_text": "", "breadcrumb": "", "url": page.url,
                   "nav_trail": [], "device_pixel_ratio": 1.0}

        screen = Screen(
            index=idx if not is_state else (len(self.session.screens) + 100),
            state_of=parent_idx,
            state_label=f"State {state_num}" if is_state else "",
            url=ctx.get("url", page.url),
            title=ctx.get("page_title", page.title()),
            h1_text=ctx.get("h1_text", ""),
            breadcrumb=ctx.get("breadcrumb", ""),
            nav_trail=ctx.get("nav_trail", []),
            device_pixel_ratio=float(ctx.get("device_pixel_ratio", 1.0)),
        )

        if is_state:
            base = f"screen_{parent_idx}_state_{state_num}"
        else:
            base = f"screen_{idx}"

        figures: list[Figure] = []

        # Viewport geometry AT THE CURRENT SCROLL POSITION — used both to
        # clip the screenshot and to filter/translate elements (FIX-2).
        try:
            vp_box = page.evaluate(_VIEWPORT_BOX_JS)
        except Exception:
            vp_box = {"x": 0, "y": 0, "width": 1280, "height": 720}

        # --- Full-page screenshot ---
        if mode in ("full_page", "both"):
            fp_name = f"{base}_full.png"
            fp_path = self.session_dir / fp_name
            try:
                page.screenshot(path=str(fp_path), full_page=True)
                screen.screenshot = fp_name
                figures.append(Figure(index=len(figures) + 1, path=fp_name,
                                      source="full_page", scroll_y=0.0))
                logger.debug(f"Full-page screenshot → {fp_name}")
            except Exception as e:
                logger.warning(f"Full-page screenshot failed: {e}")

        # --- Viewport screenshot (exactly what is on the monitor) ---
        if mode in ("viewport", "both"):
            vp_name = f"{base}_viewport.png"
            vp_path = self.session_dir / vp_name
            try:
                page.screenshot(path=str(vp_path), clip=vp_box)
                if mode == "viewport":
                    screen.screenshot = vp_name
                screen.viewport_screenshot = vp_name
                figures.append(Figure(index=len(figures) + 1, path=vp_name,
                                      source="viewport",
                                      scroll_y=float(vp_box.get("y", 0))))
                logger.debug(
                    f"Viewport screenshot at scroll y={vp_box.get('y', 0)} → {vp_name}"
                )

                # FIX-3: scroll segments ONLY if explicitly enabled in config.
                if mode == "viewport" and self.scroll_capture and not is_state:
                    scroll_figures = self._scroll_capture(page, base, len(figures), vp_box)
                    figures.extend(scroll_figures)

            except Exception as e:
                logger.warning(f"Viewport screenshot failed: {e}")

        screen.figures = figures

        # --- DOM extraction ---
        try:
            raw_els = page.evaluate(_DOM_EXTRACT_JS)
        except Exception as e:
            logger.warning(f"DOM extraction failed for screen {idx}: {e}")
            raw_els = []

        # ------------------------------------------------------------------
        # FIX-2: for viewport captures, keep ONLY elements visible in the
        # viewport and translate their coordinates into viewport space so
        # regions / labels / annotations match the screenshot exactly.
        # Full-page captures keep document coordinates (unchanged behavior).
        # ------------------------------------------------------------------
        viewport_space = (mode == "viewport")
        sx = float(vp_box.get("x", 0))
        sy = float(vp_box.get("y", 0))
        vw = float(vp_box.get("width", 0))
        vh = float(vp_box.get("height", 0))

        kept, dropped = 0, 0
        for el_dict in raw_els:
            bbox_raw = el_dict.get("bounding_box", {}) or {}
            bx = float(bbox_raw.get("x", 0))
            by = float(bbox_raw.get("y", 0))
            bw = float(bbox_raw.get("width", 0))
            bh = float(bbox_raw.get("height", 0))

            if viewport_space:
                # Visibility test: element rect must intersect the viewport rect.
                # (JS stored doc coords = rect + scroll for ALL elements,
                #  including fixed/sticky, so one uniform test/translation works.)
                inter_x = max(0.0, min(bx + bw, sx + vw) - max(bx, sx))
                inter_y = max(0.0, min(by + bh, sy + vh) - max(by, sy))
                if inter_x <= 0 or inter_y <= 0:
                    dropped += 1
                    continue
                # Require at least 40% of the element to be visible so
                # half-cut elements at the edges don't produce clipped boxes.
                if bw * bh > 0 and (inter_x * inter_y) / (bw * bh) < 0.40:
                    dropped += 1
                    continue
                # Translate document coords → viewport (screenshot) coords,
                # clamped to the image bounds.
                nx = max(0.0, bx - sx)
                ny = max(0.0, by - sy)
                nw = min(bw, vw - nx)
                nh = min(bh, vh - ny)
                bbox = BBox(x=nx, y=ny, width=nw, height=nh)
            else:
                bbox = BBox(x=bx, y=by, width=bw, height=bh)

            screen.elements.append(Element(
                id=el_dict.get("id", ""),
                element_class=el_dict.get("element_class", "interactive"),
                tag=el_dict.get("tag", "input"),
                type=el_dict.get("type"),
                role=el_dict.get("role"),
                name=el_dict.get("name"),
                accessible_name=el_dict.get("accessible_name"),
                required=bool(el_dict.get("required", False)),
                placeholder=el_dict.get("placeholder"),
                pattern=el_dict.get("pattern"),
                max_length=el_dict.get("max_length"),
                bounding_box=bbox,
                ancestor_section=el_dict.get("ancestor_section"),
                form_id=el_dict.get("form_id"),
                is_fixed=bool(el_dict.get("is_fixed", False)),
            ))
            kept += 1

        self.session.screens.append(screen)
        if getattr(self, "progress_callback", None):
            self.progress_callback(f"SCREEN_CAPTURED:{len(self.session.screens)}")

        if not is_state:
            self._state["screen_index"] += 1

        interactive_count = sum(1 for e in screen.elements if e.element_class == "interactive")
        if viewport_space:
            logger.info(
                f"Screen {idx} captured (visible area only): {kept} elements kept, "
                f"{dropped} off-screen elements excluded, "
                f"{interactive_count} interactive, {len(screen.figures)} figure(s)."
            )
        else:
            logger.info(
                f"Screen {idx} captured (full page): {interactive_count} interactive "
                f"elements, {len(screen.figures)} figure(s)."
            )

    def _scroll_capture(
        self, page: Page, base: str, fig_offset: int, vp_box: dict
    ) -> list[Figure]:
        """
        OPTIONAL scroll segmentation (config: capture.scroll_capture).
        Starts from the writer's CURRENT position and captures downward.
        Restores the original scroll position when done.
        NOTE: elements for segments are not extracted; segments are
        illustration-only "(continued)" figures.
        """
        try:
            viewport_h = int(vp_box.get("height") or page.evaluate("window.innerHeight"))
            start_y = int(vp_box.get("y", 0))
            page_h = page.evaluate("document.body.scrollHeight")
        except Exception:
            return []

        remaining = page_h - (start_y + viewport_h)
        if remaining <= viewport_h * 0.6:
            return []

        logger.debug(f"Scroll capture: page_h={page_h}, viewport_h={viewport_h}, start_y={start_y}")
        figures: list[Figure] = []
        overlap = int(viewport_h * 0.10)
        step = viewport_h - overlap
        scroll_y = start_y + step
        seg_idx = 1
        seen_hashes: set[str] = set()

        while scroll_y < page_h:
            try:
                page.evaluate(f"window.scrollTo(0, {scroll_y})")
                page.wait_for_timeout(300)
                seg_name = f"{base}_seg{seg_idx}.png"
                seg_path = self.session_dir / seg_name
                page.screenshot(path=str(seg_path), full_page=False)

                img_hash = hashlib.md5(seg_path.read_bytes()).hexdigest()[:12]
                if img_hash not in seen_hashes:
                    seen_hashes.add(img_hash)
                    figures.append(Figure(
                        index=fig_offset + len(figures) + 1,
                        path=seg_name,
                        caption_note="(continued)",
                        source="viewport",
                        scroll_y=float(scroll_y),
                        content_hash=img_hash,
                    ))
                    logger.debug(f"Scroll segment {seg_idx} → {seg_name}")
                else:
                    seg_path.unlink(missing_ok=True)
                    logger.debug(f"Scroll segment {seg_idx} deduplicated (sticky header).")

            except Exception as e:
                logger.warning(f"Scroll segment {seg_idx} failed: {e}")
                break

            scroll_y += step
            seg_idx += 1

        # Restore the writer's original scroll position (not top!)
        try:
            page.evaluate(f"window.scrollTo(0, {start_y})")
        except Exception:
            pass

        return figures


def _get_page_context(page: Page) -> dict:
    try:
        return page.evaluate(_PAGE_CONTEXT_JS)
    except Exception as e:
        logger.warning(f"Page context extraction failed: {e}")
        return {"page_title": page.title(), "h1_text": "", "breadcrumb": "",
                "url": page.url, "nav_trail": [], "device_pixel_ratio": 1.0}


def run_capture_session(
    start_url: str = "https://google.com",
    client_key: str = "default",
    module_name: str = "",
    module_number: int | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> SessionModel:
    """Convenience entry point called from main.py / launcher."""
    cfg = get_config()
    client_key = client_key or cfg.current_client
    session = CaptureSession(
        start_url=start_url,
        client_key=client_key,
        module_name=module_name,
        module_number=module_number,
    )
    session.progress_callback = progress_callback
    model = session.run()
    model._session_dir = session.session_dir
    return model