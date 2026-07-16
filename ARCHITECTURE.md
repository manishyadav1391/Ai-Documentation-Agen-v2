# ARCHITECTURE.md — DocBot v3

> Technical architecture reference for contributors and maintainers.

---

## System Overview

DocBot v3 is a single-process Python desktop application. It operates as a **linear pipeline** that transforms a browser recording session into a professionally formatted Word document. There is no server, no database, and no background daemon — the entire state lives in `session.json` on disk.

```
Browser Capture → Region Detection → AI Generation → Human Review → Document Assembly
```

---

## Core Data Model

All pipeline data is modelled as Pydantic v2 schemas in `docbot/models.py`. The **source of truth** is `SessionModel`, serialized as `session.json` inside the session directory.

```
SessionModel
├── module_name: str
├── module_number: Optional[int]
├── client_key: str
├── screens: list[Screen]
│   ├── index: int
│   ├── url: str
│   ├── title: str, h1: str, breadcrumb: str
│   ├── elements: list[Element]
│   │   └── BBox(x, y, width, height)
│   ├── events: list[Event]
│   │   └── kind: Literal["click","input","change","navigate",...]
│   ├── regions: list[Region]
│   │   ├── role: Literal["page_header","nav_bar","filter_form",...]
│   │   ├── label: str
│   │   ├── bbox: BBox
│   │   ├── callout_x: float | None   (manual callout position)
│   │   └── callout_y: float | None
│   ├── content: ScreenContent
│   │   ├── screen_name, purpose, navigation_sentence
│   │   ├── fields: list[FieldDetail]
│   │   ├── steps: list[Step]
│   │   └── notes: list[str]
│   ├── content_hash: Optional[str]    (LLM cache key)
│   └── figures: list[Figure]
└── _session_dir: Optional[Path]       (set after load, not persisted)
```

---

## Pipeline Stages

### Stage 1 — Browser Capture (`docbot/recorder/capture.py`)

**Input:** Start URL, client key
**Output:** `session.json` with `screens[].elements[]` and `screens[].events[]`

1. Playwright opens a headed Chromium context.
2. `injected.js` is injected into every page as an `addInitScript`. It:
   - Intercepts user events (click, input, change, navigate, keypress)
   - Stores them in `window.__docbot_events`
   - Exposes `triggerCapture()` and `triggerQuit()` via Playwright's `expose_function`
3. The writer navigates the target application.
4. **Middle-click** → calls `triggerCapture()` → `_capture_screen()`:
   - `page.evaluate()` extracts `title`, `h1`, URL, breadcrumb via the page context
   - `page.screenshot(clip=viewport_box)` captures a viewport PNG
   - `page.evaluate()` walks the DOM and returns all interactive/semantic elements with bounding boxes
   - Elements are translated from document to viewport coordinates
5. **Double middle-click** → calls `triggerQuit()` → session ends.
6. Browser auth state is saved to `sessions/state/<client>.json`.
7. `SessionStore.save(session, session_dir)` writes `session.json`.

**Key design choices:**
- Viewport-only screenshots (not full-page) to match element coordinate space.
- Element extraction uses a JS walker rather than CDP, for cross-browser portability.
- `threading.Lock` protects the shared `_state` dict between Playwright callbacks and the main polling loop.

---

### Stage 2a — Region Detection (`docbot/processing/regions.py`)

**Input:** `screen.elements: list[Element]`
**Output:** `screen.regions: list[Region]`

Heuristic rules classify DOM elements into semantic regions:

| Region Role | Detection Rule |
|---|---|
| `page_header` | `label` type element with `h1`/`h2` tag |
| `nav_bar` | ≥3 link elements in a horizontal cluster near top |
| `filter_form` | ≥2 interactive elements (input/select) grouped by bbox |
| `table_header` | `th` elements in a row |
| `action_bar` | ≥1 button elements near bottom or top |
| `section_label` | `h3`/`h4` heading elements |

Overlapping regions with IoU > 0.6 are **merged** — the union bounding box is used and elements are combined. This prevents duplicate annotations on the same UI area.

---

### Stage 2b — Step Compilation (`docbot/processing/steps.py`)

**Input:** `screen.events: list[Event]`
**Output:** `list[Step]` (deterministic skeleton, no LLM)

Rules:
- Consecutive `input`/`change` events → grouped into "Enter the following details:" parent
- `click` on button/link → "Click on the X button."
- `click` + next event `navigate` → adds "The Y page will be displayed." result step
- `keypress_enter` → "Press Enter to submit the Z."
- `navigate` (standalone) → "The Y page will be displayed."

This skeleton is passed as context to the LLM prompt to reduce hallucination.

---

### Stage 2c — AI Generation (`docbot/processing/generator.py`)

**Input:** `session: SessionModel`, `screen: Screen`, `client_profile: dict`
**Output:** `ScreenDocResponse` merged into `screen.content`

1. **Content hash check:** If `_compute_hash(PROMPT_VERSION, all_inputs) == screen.content_hash`, skip the LLM call.
2. **Prompt assembly:**
   - `load_prompt("screen_documentation", version="v3")` loads the template
   - Substitutes: `{screen_title}`, `{url}`, `{elements_summary}`, `{regions_summary}`, `{steps_skeleton}`, `{voice_rules}`, `{voice_examples}`, `{glossary}`, `{field_style}`
3. **LLM call:** `provider.chat_json(prompt, schema=ScreenDocResponse, images=[screen_png])`
   - Tries `chat_vision` first (if provider supports it); falls back to `chat`
   - On `ValidationError`: appends error to prompt, retries once
   - On second failure: raises `GenerationError`
4. **Result merge:** `_merge_result_into_screen(screen, result, content_hash)` writes all generated fields back to the Screen model.
5. **Logging:** Raw prompt and response are written to `sessions/<dir>/llm/screen_N_{hash}.json` for debugging.

**`ScreenDocResponse` schema:**
```python
class ScreenDocResponse(BaseModel):
    screen_name: str
    purpose: str
    navigation_sentence: str
    region_labels: list[RegionLabel]    # {region_id, label}
    field_details: list[FieldDetail]    # {field_name, utility, information, sample}
    steps: list[Step]                   # {n, text, kind}
    notes: list[str]
    buttons_doc: list[str]
    table_columns_doc: list[str]
```

---

### Stage 3 — Visual Review (`ui/review.py`)

**Input:** `session_dir` containing `session.json`
**Output:** Updated `session.json` (edited by writer)

`ReviewSessionUI` is a Tkinter window with:
- **Canvas** (left panel): scaled screenshot with region boxes, callout bubbles, resize handles
- **Content editor** (right panel): text fields for all `screen.content` attributes
- **Step editor**: inline step list with crop image support

**Edit modes (drag state machine):**
- `"draw"` — click+drag on empty canvas creates a new region
- `"move"` — drag inside a region box moves it
- `"resize"` — drag a handle (8 handles: nw/n/ne/e/se/s/sw/w) resizes it
- `"callout"` — drag a callout bubble repositions it

Callout positions are stored as `region.callout_x` / `region.callout_y`. When set, the annotator uses these coordinates instead of auto-scoring.

Undo: `Ctrl+Z` pops from `_undo_stack: list[list[Region]]`.

---

### Stage 4 — Annotation (`docbot/processing/annotate.py`)

**Input:** `sessions/<dir>/screen_N.png`, `screen.regions`
**Output:** `sessions/<dir>/screen_N_annotated.png`

Using Pillow:
1. Draws a semi-transparent colored overlay box for each region
2. For each region, draws a callout bubble (rounded rectangle) at:
   - `(region.callout_x, region.callout_y)` if manually set, or
   - The automatically scored candidate position (avoids other bubbles and critical UI)
3. Draws a leader line from the bubble to the region center
4. Draws a number badge (e.g., "①") inside the bubble
5. Saves as `_annotated.png`

---

### Stage 5 — Document Assembly (`manual_builder/`)

**Input:** `session_dir`, `clients/<key>/*.yaml`, `styles/<key>.yaml`
**Output:** `Final_Manuals/<client>_<system>_v<ver>_<timestamp>.docx`

```
GenericBuilder
├── _setup_styles()
│   ├── A4 page setup (exact twip dimensions)
│   ├── 1-inch margins
│   ├── Normal style (Calibri 12pt, justified, en-IN lang)
│   ├── Heading 1/2/3 styles (from style.yaml)
│   ├── Caption style (italic, centered, muted color)
│   └── updateFields in settings.xml (TOC auto-refresh)
│
├── build_front_matter()   ← for master manual
│   └── dispatch_section() per manifest section:
│       cover, revision_history, table_of_contents,
│       table_of_figures, prose, bullet_list, group
│
└── build_module(session_dir) → render_module()
    ├── Module heading (H1, numbered)
    ├── Module intro paragraph
    └── per screen: render_screen()
        ├── Screen heading (H2, numbered)
        ├── Purpose paragraph
        ├── Path breadcrumb
        ├── Navigation instruction
        ├── Screenshot in 1×1 table (0.5pt gray border)
        ├── Caption (Figure N: Name — note)
        ├── Field table (or bullet list, per style)
        ├── Steps (List Bullet, **bold** UI labels)
        └── Notes paragraphs
```

**Numbering modes:**
- `continuous` — figures numbered 1, 2, 3… across all modules (NCD style)
- `module_prefixed` — figures numbered M-1, M-2… per module (NCB style)

---

## Provider Architecture

All LLM providers implement `providers.base.Provider`:

```python
class Provider(ABC):
    @property @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def chat(self, prompt, *, max_tokens, temperature, system) -> str: ...

    def chat_vision(self, prompt, images, **kw) -> str:
        # Default: text-only fallback (logs warning)

    def chat_json(self, prompt, schema, images=None, **kw) -> T:
        # Calls chat/chat_vision, strips fences, validates JSON, retries once
```

Providers:
| Class | Module | Transport |
|---|---|---|
| `AnthropicProvider` | `providers.anthropic_api` | `httpx` → Anthropic Messages API |
| `OpenAICompatProvider` | `providers.openai_compat` | `httpx` → OpenAI-compatible endpoint |
| `OllamaProvider` | `providers.ollama` | `httpx` → Ollama API |
| `BrowserProvider` | `providers.browser` | `subprocess` opens Notepad (manual) |
| `BrowserBatchProvider` | `providers.browser_batch` | Session-level batch manual mode |

---

## Configuration System

```
config.yaml  →  Config (pydantic)
                 ├── provider: str
                 ├── current_client: str
                 ├── content_dir / styles_dir / sessions_dir: str
                 ├── providers: {browser, anthropic, openai_compat, ollama}
                 │     └── ProviderConfig (model, max_tokens, api_key_env, ...)
                 └── render / capture settings

clients/<key>/manifest.yaml  →  ManifestConfig (dataclass)
clients/<key>/style.yaml     →  StyleConfig (dataclass)
clients/<key>/voice.yaml     →  dict (loaded as-is into Generator prompt)
clients/<key>/glossary.yaml  →  dict[str, str] (term → definition)
```

The `get_config()` singleton loads `config.yaml` once per process and caches it. It can be reloaded with `reload_config()`.

---

## File Naming Conventions

| Pattern | Description |
|---|---|
| `sessions/session_YYYYMMDD_HHMMSS/` | Session directory (timestamped) |
| `screen_N.png` | Raw viewport screenshot (N = 1-indexed screen index) |
| `screen_N_annotated.png` | Screenshot with callout overlays |
| `screen_N_meta.json` | Legacy: title, url, breadcrumb |
| `screen_N_elements.json` | Legacy: extracted DOM elements |
| `screen_N_regions.json` | Legacy: detected regions |
| `screen_N_content.json` | Legacy: AI-generated content |
| `module_meta.json` | Legacy: module name, intro, screen order |
| `session.json` | Primary v3 session model |
| `run.log` | Per-session loguru log (DEBUG level) |
| `llm/screen_N_<hash>.json` | LLM prompt+response debugging log |
| `Final_Manuals/<CLIENT>_<SYSTEM>_User_Manual_v<ver>_<ts>.docx` | Output manual |

---

## Error Handling Philosophy

- **Pipeline failures** are logged via `loguru` and propagate as exceptions that bubble to the UI.
- **LLM failures** are retried once with the validation error appended to the prompt. Second failure raises `GenerationError`.
- **Missing YAML** files fall back to `_default/` equivalents; further fallback raises `FileNotFoundError`.
- **OOXML validation** failures are logged as errors but do not prevent file save (the file may still be manually fixable).
- **Annotation failures** are non-fatal — the pipeline continues with the unannotated screenshot.

---

## Testing

Tests live in `tests/` and use `pytest`:

```bash
pytest tests/ -v
```

| Test File | Coverage |
|---|---|
| `test_regions.py` | IoU merge, role classification, parenthesis precedence |
| `test_steps.py` | Input grouping, click+nav, change events, submit |
| `test_numbering.py` | Continuous vs. module-prefixed figure/table numbers |
| `test_chat_json.py` | JSON fence stripping, ValidationError retry logic |

---

## Known Limitations

1. **Windows-only UI** — Tkinter has native look only on Windows. Playwright works cross-platform.
2. **Synchronous pipeline** — Generation blocks the UI thread. Long sessions may appear frozen.
3. **No multi-user support** — Single session at a time; no concurrent access.
4. **Browser auth state expires** — Saved cookies may expire; writer must re-login.
5. **LLM hallucination** — The Review UI exists precisely to catch and correct AI errors before document assembly.
