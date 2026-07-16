# Architectural Review Report — DocBot v3

> **Project:** `c:\doc_automation_v2`
> **Reviewed:** 2026-07-16

---

## Table of Contents

1. [Architecture Strengths](#1-architecture-strengths)
2. [Critical Issues](#2-critical-issues)
3. [High-Priority Issues](#3-high-priority-issues)
4. [Medium-Priority Issues](#4-medium-priority-issues)
5. [Low-Priority / Future Considerations](#5-low-priority--future-considerations)
6. [Recommended Refactoring Roadmap](#6-recommended-refactoring-roadmap)

---

## 1. Architecture Strengths

### 1.1 Clean Separation of Concerns

The three primary concerns — capture, AI generation, and document assembly — are well-separated:

- `docbot/recorder/` owns browser interaction
- `docbot/processing/` owns all data transformation (regions, steps, AI generation, annotation)
- `manual_builder/` owns document rendering (no business logic, pure Word assembly)
- `providers/` owns LLM transport (pure I/O, no document logic)

### 1.2 Pydantic v2 Data Contracts

All session data is modelled with strict Pydantic v2 schemas (`SessionModel`, `Screen`, `Region`, `Element`, `Step`, `FieldDetail`, `BBox`). This catches data errors early, produces clean JSON serialization, and makes the entire pipeline data contract explicit and testable.

### 1.3 Provider Abstraction

`providers.base.Provider` is a clean abstract base with a single mandatory method (`chat()`). All LLM-specific details are encapsulated behind a uniform `chat()` / `chat_vision()` / `chat_json()` interface. Adding a new provider requires only a new subclass.

### 1.4 Content-Hash Caching

`Generator.generate_screen()` computes a hash of the prompt inputs and skips the LLM call if the hash matches the stored `content_hash`. This is pragmatic caching for an interactive workflow where the user may re-run generation without changing inputs.

### 1.5 Manifest-Driven Document Builder

The manifest/style/voice/glossary YAML system means **zero code changes are required** to onboard a new client or document brand. The `GenericBuilder` is a generic engine.

### 1.6 Deterministic Step Compiler

`docbot/processing/steps.py` produces a step skeleton from raw browser events _without_ an LLM call. This means: (a) steps are always coherent even without AI, and (b) the LLM has a structured foundation to polish rather than hallucinate from scratch.

### 1.7 OOXML Quality Gate

`docbot/export/qa.py` includes an automated OOXML structural validation pass that catches `fldChar`/`instrText` element placement errors that would cause Microsoft Word to refuse to open the document. This is a non-trivial safeguard.

---

## 2. Critical Issues

### 2.1 Blocking UI — Pipeline Runs on Main Thread

| Severity | Impact |
|---|---|
| **Critical** | Application appears frozen during 30–300s AI generation |

`run_pipeline()` is called synchronously on the Tkinter main thread. During AI generation (which can take 30+ seconds per screen × N screens), the UI is completely frozen — no button responses, no progress updates beyond the manually-incremented progress label.

**Recommended fix:**
Run the pipeline in a `threading.Thread`. Communicate progress back to Tkinter using a thread-safe queue + `root.after()` polling, or use `root.after()` with small chunked tasks.

```python
# Current (problematic):
self._run_pipeline()

# Recommended:
thread = threading.Thread(target=self._run_pipeline, daemon=True)
thread.start()
```

---

### 2.2 No Error Recovery — Any Step Failure Aborts the Entire Pipeline

| Severity | Impact |
|---|---|
| **Critical** | A single LLM timeout or network error loses all captured work |

The main pipeline in `main.py` has no checkpointing or partial-failure recovery. If the LLM call for screen 8 (of 15) fails, the user must restart from screen 1.

**Recommended fix:**
- Mark each screen with a `generation_status: Literal["pending", "done", "failed"]` field.
- In the generation loop, skip screens already marked `"done"` (already partially implemented via content-hash caching).
- Catch per-screen exceptions and mark `"failed"` rather than propagating.
- Allow the Review UI to trigger re-generation of individual failed screens.

---

### 2.3 `lxml` Missing from `requirements.txt`

| Severity | Impact |
|---|---|
| **Critical** | QA validation silently fails or crashes on clean installs |

`docbot/export/qa.py` imports `from lxml import etree` for OOXML validation. `lxml` is not listed in `requirements.txt`. Fresh environments without `lxml` will either silently skip QA (if the import is wrapped in try/except) or crash.

**Recommended fix:**
Add `lxml>=4.9,<6` to `requirements.txt`.

---

## 3. High-Priority Issues

### 3.1 Compatibility Shims Still Active

| Severity | Priority |
|---|---|
| High | Execute Phase 7 shim removal |

Five root-level shim files (`capture.py`, `annotate.py`, `detect_regions.py`, `review_ui.py`, `labeler.py`) each emit `DeprecationWarning` on every import. This pollutes log output and can confuse contributors.

**Recommended fix:**
- Update `main.py` to import directly from `docbot.*` and `ui.*`.
- Delete the five shim files.

---

### 3.2 Session Directory Encoded Implicitly Via `_session_dir` Private Attribute

| Severity | Priority |
|---|---|
| High | Data integrity risk |

`SessionModel` has a private `_session_dir: Optional[Path] = None` field that is set after construction in `run_capture_session()`. Several pipeline steps depend on `session._session_dir` being set. If it's `None` (e.g., if `SessionModel` is constructed elsewhere), the pipeline silently uses fallback logic that may write to the wrong directory.

**Recommended fix:**
`session_dir` should be a **first-class public field** on `SessionModel`, required at construction time (with a `model_validator` to ensure it is always set before use).

---

### 3.3 Legacy JSON Files Written After AI Generation (Redundant I/O)

| Severity | Priority |
|---|---|
| High | Performance + maintenance burden |

`main.py` writes `screen_N_meta.json`, `screen_N_elements.json`, `screen_N_regions.json`, `screen_N_content.json` after AI generation. These are _read back_ by `manual_builder/renderers/module.py` instead of reading from `session.json` directly.

This creates:
- Redundant disk I/O (session.json → legacy files → document)
- Duplication of data that can diverge
- A maintenance burden when fields are added to `SessionModel`

**Recommended fix:**
Have `render_module()` read `SessionStore.load(session_dir)` directly from `session.json`. Eliminate the intermediate legacy JSON files. Keep them only as a temporary debugging aid if needed.

---

### 3.4 Hardcoded Font Path Probing in `annotate.py`

| Severity | Priority |
|---|---|
| High | Cross-platform failure risk |

`docbot/processing/annotate.py::_get_font()` probes OS-specific font file paths (Windows: `C:\Windows\Fonts\calibri.ttf` etc.). On systems where these fonts don't exist (Linux CI, Docker), Pillow falls back to a bitmap default font that produces visually poor annotations.

**Recommended fix:**
- Bundle a minimal fallback font (e.g., OpenSans or DejaVu) in `docbot/processing/fonts/`.
- Use `importlib.resources` to load it as a package resource.
- Remove the hard-coded path list.

---

### 3.5 `config.yaml` Contains Production Secrets Path Configuration (Security)

| Severity | Priority |
|---|---|
| High | Security |

`config.yaml` contains `api_key_env: OLLAMA_API_KEY` which is committed to version control. While the actual key value comes from `.env`, committing the Ollama model name `gpt-oss:120b` and host URL `https://ollama.com` to the repository may not be desirable.

More critically, the `.env.example` itself states: *"A previous version of this repository inadvertently committed an Ollama API key."*

**Recommended fix:**
- Confirm the compromised key has been rotated.
- Add a `git secrets` or `pre-commit` hook to prevent future secret leakage.
- Optionally move provider configuration out of the committed `config.yaml` into a `.env`-only or secret management system.

---

## 4. Medium-Priority Issues

### 4.1 `ui/review.py` is 1,343 Lines — God Class

| Severity | Priority |
|---|---|
| Medium | Maintainability |

`ReviewSessionUI` is a monolithic 1,343-line class handling: layout building, canvas rendering, drag state machines (4 modes), keyboard shortcuts, undo stack, region editing, screen navigation, content editing, AI regeneration, and annotation export.

**Recommended fix:**
Extract into sub-components:
- `CanvasController` — drag/resize/callout state machine
- `RegionEditor` — region list panel + edit dialog
- `ContentEditor` — text fields panel
- `ToolbarController` — button actions and menu

---

### 4.2 `Labeler.generate_screen_content()` Writes Legacy JSON With Hardcoded Field Mapping

| Severity | Priority |
|---|---|
| Medium | Tech debt |

`labeler.py:79–116` converts `ScreenDocResponse` into a hardcoded legacy JSON format (`navigation_instructions`, `field_details`, `screen_documentation`). If `ScreenDocResponse` fields are ever renamed, this mapping silently breaks.

**Status:** This is the shim to be deleted in Phase 7. Priority is low once Phase 7 is executed.

---

### 4.3 No Validation That `clients/<key>/voice.yaml` Matches Generator Schema

| Severity | Priority |
|---|---|
| Medium | Data quality |

`Generator._format_voice_examples()` reads `voice.get("examples", {})` and `voice.get("tone_rules", [])`. If a new voice.yaml has a typo in a key, the LLM prompt silently degrades (empty sections instead of an error).

**Recommended fix:**
Add a `VoiceConfig` Pydantic model and validate `voice.yaml` against it at `ClientProfile.load()` time.

---

### 4.4 NumberingTracker `mode` Must Match Manifest `numbering_mode` — No Validation

| Severity | Priority |
|---|---|
| Medium | Data integrity |

`assemble.py:49` does `numbering_mode = getattr(manifest, "numbering_mode", "module_prefixed")`. If the YAML has a typo (`contiuous` instead of `continuous`), it silently falls back to `module_prefixed` instead of raising an error.

**Recommended fix:**
Add `numbering_mode: Literal["continuous", "module_prefixed"] = "module_prefixed"` to `ManifestConfig` so Pydantic validates the value.

---

### 4.5 `screen.py` Uses `session_dir / fig_rel_path` Without Sanitisation

| Severity | Priority |
|---|---|
| Medium | Security / Path traversal |

`render_screen()` in `screen.py:206` builds `fig_path = session_dir / fig_rel_path` where `fig_rel_path` comes from `content_data["figures"][i]["path"]`. If a malformed or malicious `session.json` contains a path like `../../etc/passwd`, PIL would attempt to open that file.

**Recommended fix:**
Validate that `fig_path.resolve().is_relative_to(session_dir.resolve())` before opening.

---

### 4.6 `chat_json()` Retry Logic Stores Error in Class Variable `_last_validation_error`

| Severity | Priority |
|---|---|
| Medium | Thread safety |

`Provider._last_validation_error` is a class-level variable (defined at line 228 of `providers/base.py`). In a multi-threaded scenario (even future async), two concurrent `chat_json()` calls could overwrite each other's error state, causing the retry prompt to contain the wrong error.

**Recommended fix:**
Change `_last_validation_error` to a local variable passed between the loop iterations.

---

## 5. Low-Priority / Future Considerations

### 5.1 Playwright Pinned to Exact Version `==1.52.0`

Playwright releases frequently (monthly). The pinned version will become out-of-date. Consider using `>=1.52.0,<2` with a tested upper bound.

### 5.2 No `setup.py` / `pyproject.toml`

The project has no package metadata file. This makes it harder to install as a library or run in isolated environments. Consider adding a minimal `pyproject.toml`.

### 5.3 No Type Stubs for `tkinter`

`ui/*.py` files use tkinter without type annotations. Adding `tkinter-stubs` and running `mypy` would catch widget attribute errors.

### 5.4 `config.yaml::provider: ollama` Points to Cloud Endpoint

The configured Ollama host is `https://ollama.com` (cloud) rather than `http://localhost:11434` (local). The model is `gpt-oss:120b` — an unusual name for Ollama. This suggests a custom cloud Ollama instance. Ensure the deployment environment has access to this endpoint.

### 5.5 `injected.js` Not Validated or Tested

The JavaScript injected into every captured page is a critical piece of the capture pipeline (event recording, element extraction). It has no automated tests. A JS error in `injected.js` would silently produce empty captures. Consider a Playwright-based integration test.

---

## 6. Recommended Refactoring Roadmap

| Priority | Item | Effort |
|---|---|---|
| 1 | Add `lxml` to `requirements.txt` | Trivial |
| 2 | Remove 5 deprecated shim files; update `main.py` imports | Small |
| 3 | Run pipeline in background thread (non-blocking UI) | Medium |
| 4 | Promote `session_dir` to first-class field on `SessionModel` | Small |
| 5 | Have `render_module()` read `session.json` directly (eliminate legacy JSON) | Medium |
| 6 | Bundle a fallback font in `docbot/processing/fonts/` | Small |
| 7 | Add `lxml` + rotate compromised API key; add `pre-commit` secret scanner | Small |
| 8 | Add per-screen error recovery (`generation_status` field) | Medium |
| 9 | Validate `voice.yaml` and `numbering_mode` with Pydantic | Small |
| 10 | Sanitise `fig_path` in `screen.py` (path traversal guard) | Small |
| 11 | Fix `_last_validation_error` thread-safety in `Provider.chat_json()` | Small |
| 12 | Split `ui/review.py` into sub-components | Large |
| 13 | Add `pyproject.toml` with package metadata | Small |
| 14 | Add integration test for `injected.js` | Medium |
