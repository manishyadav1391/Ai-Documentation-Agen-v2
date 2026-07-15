/**
 * DocBot v3 — Event Instrumentation Script
 *
 * Injected into every page (and every new tab) via Playwright's
 * addInitScript() mechanism.  Listens for user interactions and forwards
 * them to Python via the `docbotEvent` exposed function.
 *
 * Events emitted:
 *   click          — left-click on any element
 *   input          — text entry (debounced 800ms, value redacted for sensitive fields)
 *   change         — select / checkbox / radio change
 *   submit         — form submission
 *   navigate       — popstate / hashchange (SPA navigation)
 *   keypress_enter — Enter key on an input (treated as implicit submit)
 *
 * Capture gesture triggers (forwarded as synthetic events):
 *   middle-click              → triggerCapture()
 *   Ctrl + middle-click       → triggerFullPageCapture()
 *   Shift + middle-click      → triggerStateCapture()
 *   double middle-click       → triggerQuit()
 */

(function () {
  'use strict';

  // ── Utilities ─────────────────────────────────────────────────────────────

  /**
   * Build a CSS selector for *el* that is as stable as possible.
   * Preference: id → name → aria-label + nth-of-type fallback.
   */
  function selectorFor(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) return el.tagName.toLowerCase() + '[aria-label="' + ariaLabel + '"]';
    // nth-of-type fallback
    const parent = el.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
      const nth = siblings.indexOf(el) + 1;
      return el.tagName.toLowerCase() + ':nth-of-type(' + nth + ')';
    }
    return el.tagName.toLowerCase();
  }

  /**
   * Return document-coordinate bounding box (adds scroll offsets).
   * This ensures bbox is stable regardless of scroll position at capture time.
   */
  function docBBox(el) {
    const rect = el.getBoundingClientRect();
    return {
      x: rect.x + window.scrollX,
      y: rect.y + window.scrollY,
      width: rect.width,
      height: rect.height
    };
  }

  /** Best accessible name for an element. */
  function accessibleName(el) {
    return el.getAttribute('aria-label')
      || el.getAttribute('title')
      || el.getAttribute('data-tooltip')
      || (el.innerText && el.innerText.trim().slice(0, 120))
      || el.getAttribute('placeholder')
      || (el.value && !isSensitive(el) ? el.value : null)
      || el.name
      || null;
  }

  /**
   * Return true if the field value should be redacted.
   * Matches password inputs AND fields whose name/id/type hint at sensitivity.
   */
  const SENSITIVE_RE = /password|pin|otp|cvv|captcha|secret|token/i;
  function isSensitive(el) {
    return el.type === 'password'
      || SENSITIVE_RE.test(el.name || '')
      || SENSITIVE_RE.test(el.id || '')
      || SENSITIVE_RE.test(el.getAttribute('autocomplete') || '');
  }

  /** Unique event id: 8-char hex. */
  function newId() {
    return Math.random().toString(16).slice(2, 10);
  }

  /** Emit one event to Python. */
  function emit(payload) {
    if (typeof window.docbotEvent === 'function') {
      window.docbotEvent(JSON.stringify(payload));
    }
  }

  // ── Capture gesture: middle-click with modifiers ──────────────────────────

  let _middleTimer = null;

  window.addEventListener('mousedown', function (e) {
    if (e.button !== 1) return;        // only middle-button
    e.preventDefault();

    if (e.ctrlKey) {
      // Ctrl+middle → force full-page capture (any mode)
      if (typeof window.triggerFullPageCapture === 'function') {
        window.triggerFullPageCapture();
      }
      return;
    }

    if (_middleTimer) {
      // Second click within 400ms → double-click → quit
      clearTimeout(_middleTimer);
      _middleTimer = null;
      if (typeof window.triggerQuit === 'function') {
        window.triggerQuit();
      }
    } else {
      const shiftHeld = e.shiftKey;
      _middleTimer = setTimeout(function () {
        _middleTimer = null;
        if (shiftHeld) {
          // Shift+middle → state capture (always viewport)
          if (typeof window.triggerStateCapture === 'function') {
            window.triggerStateCapture();
          }
        } else {
          // Single middle → normal capture
          if (typeof window.triggerCapture === 'function') {
            window.triggerCapture();
          }
        }
      }, 400);
    }
  }, true);

  // Keyboard shortcuts for capture actions (Issue 3)
  window.addEventListener('keydown', function (e) {
    const isAlt = e.altKey;
    const isCtrlShift = e.ctrlKey && e.shiftKey;
    if (isAlt || isCtrlShift) {
      const key = e.key.toLowerCase();
      if (key === 'c' || key === '1') {
        e.preventDefault();
        if (typeof window.triggerCapture === 'function') {
          window.triggerCapture();
        }
      } else if (key === 'f' || key === '2') {
        e.preventDefault();
        if (typeof window.triggerFullPageCapture === 'function') {
          window.triggerFullPageCapture();
        }
      } else if (key === 's' || key === '3') {
        e.preventDefault();
        if (typeof window.triggerStateCapture === 'function') {
          window.triggerStateCapture();
        }
      } else if (key === 'q' || key === '4') {
        e.preventDefault();
        if (typeof window.triggerQuit === 'function') {
          window.triggerQuit();
        }
      }
    }
  }, true);

  // ── Click events ──────────────────────────────────────────────────────────

  window.addEventListener('click', function (e) {
    if (e.button !== 0) return;
    const el = e.composedPath()[0];
    if (!el || !el.tagName) return;

    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const name = accessibleName(el);
    const bbox = docBBox(el);

    emit({
      id: newId(),
      ts: Date.now() / 1000,
      kind: 'click',
      target_selector: selectorFor(el),
      target_name: name,
      target_role: role,
      target_bbox: bbox,
      url_before: window.location.href,
      url_after: null,           // will be updated by Python after navigation
      value_summary: null,
      redacted: false,
      page_id: window.__docbotPageId || 'main'
    });
  }, true);

  // ── Input / change events (with debounce) ─────────────────────────────────

  let _inputTimers = new WeakMap();

  function handleInput(e) {
    const el = e.target;
    if (!el || !el.tagName) return;
    const sensitive = isSensitive(el);
    const tag = el.tagName.toLowerCase();
    if (!['input', 'textarea', 'select'].includes(tag)) return;

    clearTimeout(_inputTimers.get(el));
    _inputTimers.set(el, setTimeout(function () {
      emit({
        id: newId(),
        ts: Date.now() / 1000,
        kind: e.type === 'change' ? 'change' : 'input',
        target_selector: selectorFor(el),
        target_name: accessibleName(el),
        target_role: el.getAttribute('role') || tag,
        target_bbox: docBBox(el),
        url_before: window.location.href,
        url_after: null,
        value_summary: sensitive
          ? (el.value ? el.value.length + ' characters entered' : '')
          : (el.value || ''),
        redacted: sensitive,
        page_id: window.__docbotPageId || 'main'
      });
    }, 800));
  }

  window.addEventListener('input', handleInput, true);
  window.addEventListener('change', handleInput, true);

  // ── Submit ────────────────────────────────────────────────────────────────

  window.addEventListener('submit', function (e) {
    const form = e.target;
    emit({
      id: newId(),
      ts: Date.now() / 1000,
      kind: 'submit',
      target_selector: form.id ? '#' + form.id : 'form',
      target_name: form.getAttribute('aria-label') || form.id || 'Form',
      target_role: 'form',
      target_bbox: docBBox(form),
      url_before: window.location.href,
      url_after: null,
      value_summary: null,
      redacted: false,
      page_id: window.__docbotPageId || 'main'
    });
  }, true);

  // ── Enter key (implicit submit) ───────────────────────────────────────────

  window.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    const el = e.target;
    if (!el || el.tagName !== 'INPUT') return;
    emit({
      id: newId(),
      ts: Date.now() / 1000,
      kind: 'keypress_enter',
      target_selector: selectorFor(el),
      target_name: accessibleName(el),
      target_role: 'input',
      target_bbox: docBBox(el),
      url_before: window.location.href,
      url_after: null,
      value_summary: null,
      redacted: false,
      page_id: window.__docbotPageId || 'main'
    });
  }, true);

  // ── SPA navigation detection ──────────────────────────────────────────────

  function onNavigate() {
    emit({
      id: newId(),
      ts: Date.now() / 1000,
      kind: 'navigate',
      target_selector: null,
      target_name: document.title,
      target_role: null,
      target_bbox: null,
      url_before: window.__docbotLastUrl || document.referrer || null,
      url_after: window.location.href,
      value_summary: null,
      redacted: false,
      page_id: window.__docbotPageId || 'main'
    });
    window.__docbotLastUrl = window.location.href;
  }

  window.addEventListener('popstate', onNavigate);
  window.addEventListener('hashchange', onNavigate);
  window.__docbotLastUrl = window.location.href;

})();
