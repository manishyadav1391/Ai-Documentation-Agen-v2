# PROMPT FOR CLAUDE UI — Generate Complete DocBot v3 Technical Documentation

Paste everything below this line into Claude.ai:

---

You are a **Staff Technical Writer and Senior Software Architect**. Your task is to write a **complete, professional technical documentation website** (as a set of Markdown files) for a Python project called **DocBot v3**.

I will give you all the information about the codebase. Write the full documentation. Do not ask clarifying questions — generate everything in one pass.

---

## PROJECT OVERVIEW

**DocBot v3** is a Python desktop application that automates the creation of professional Word (.docx) user manuals for software systems.

**Workflow:**
1. A documentation writer opens the app (Tkinter GUI launcher)
2. A headed Chromium browser opens (via Playwright) — writer navigates the target software and middle-clicks to capture screens
3. Each capture: takes a viewport screenshot + extracts DOM elements via injected JavaScript
4. After capture: heuristic region detection groups DOM elements into semantic regions
5. One LLM call per screen generates: screen name, purpose, field descriptions, steps, notes
6. A visual review/edit UI (Tkinter canvas) lets the writer correct AI output and drag callout bubbles
7. Pillow renders annotated screenshots (numbered callout bubbles + bounding boxes)
8. python-docx assembles a fully branded Word document from YAML config + session data

---

## TECH STACK

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Browser automation | Playwright (sync, pinned ==1.52.0) |
| GUI | Tkinter (stdlib) |
| Data models | Pydantic v2 |
| LLM transport | httpx (direct API calls, no SDK) |
| Image processing | Pillow |
| Word documents | python-docx ==1.1.2 |
| Config files | YAML (PyYAML) |
| Logging | loguru |
| Tests | pytest |
| OOXML validation | lxml |

---

## FOLDER STRUCTURE

```
doc_automation_v2/
├── main.py                         # Pipeline entry point — run_pipeline()
├── config.py                       # Pydantic Config + load/save helpers
├── config.yaml                     # Runtime config (provider, client, dirs)
├── .env                            # API keys (never committed)
├── .env.example                    # Template for .env
├── requirements.txt                # 10 dependencies
├── assemble.py                     # assemble_module() — single-session Word preview
├── master_assembler.py             # assemble_master_manual() — multi-session full manual
│
├── docbot/
│   ├── models.py                   # ALL Pydantic v2 data models
│   ├── logging_setup.py            # setup_logging() + attach_session_log()
│   ├── clients/
│   │   └── profile.py              # ClientProfile.load() — 4-file YAML loader
│   ├── processing/
│   │   ├── annotate.py             # Pillow: callout bubbles + bounding box overlays
│   │   ├── crops.py                # Step-inline image crop extractor
│   │   ├── generator.py            # Generator class — LLM orchestration
│   │   ├── regions.py              # Heuristic DOM region detection + IoU merge
│   │   └── steps.py               # Deterministic event→step compiler (no LLM)
│   ├── recorder/
│   │   ├── capture.py              # CaptureSession — Playwright orchestration
│   │   └── injected.js             # JS injected into every browser page
│   └── export/
│       ├── qa.py                   # OOXML validation + LibreOffice PDF QA
│       └── word_fields.py          # python-docx helpers: TOC fields, captions
│
├── manual_builder/
│   ├── generic_builder.py          # GenericBuilder class
│   ├── manifest_loader.py          # ManifestConfig dataclass + load_manifest()
│   ├── style_loader.py             # StyleConfig dataclass + load_style()
│   ├── numbering.py                # NumberingTracker (sections/figures/tables)
│   ├── utils.py                    # Word helpers
│   ├── build_error.py              # BuildError exception
│   └── renderers/
│       ├── cover.py, revision_history.py, toc.py
│       ├── prose.py, bullet_list.py, icon_table.py, group.py
│       ├── module.py               # Module-level renderer
│       ├── screen.py               # Per-screen renderer (main output)
│       └── field_table.py
│
├── providers/
│   ├── base.py                     # Abstract Provider + load_prompt() + GenerationError
│   ├── anthropic_api.py            # Anthropic Claude via httpx
│   ├── openai_compat.py            # OpenAI-compatible (Groq, Together AI)
│   ├── ollama.py                   # Ollama local/cloud
│   ├── browser.py                  # Manual copy-paste (no API key)
│   └── browser_batch.py            # Batch copy-paste mode
│
├── prompts/v3/
│   ├── screen_documentation.txt    # Main LLM prompt template
│   └── module_intro.txt
│
├── ui/
│   ├── launcher.py                 # LauncherUI — main control panel
│   ├── review.py                   # ReviewSessionUI — annotation editor (1343 lines)
│   └── style_editor.py             # StyleEditorDialog
│
├── clients/
│   ├── _default/                   # Fallback config (manifest/style/voice/glossary)
│   ├── ncd/                        # National Cooperative Database client
│   ├── ncb/                        # NCB client
│   ├── swagylab/                   # SwagyLab client
│   └── orangehrms/                 # OrangeHRMS client
│
├── sessions/                       # Runtime session data (git-ignored)
│   └── <session_dir>/
│       ├── session.json            # Primary Pydantic v2 session model
│       ├── screen_N.png / _annotated.png
│       ├── screen_N_meta.json / _content.json  (legacy compat)
│       ├── module_meta.json
│       ├── run.log
│       └── llm/                    # LLM prompt+response debug logs
│
├── Final_Manuals/                  # Output Word documents
├── tests/                          # pytest: test_chat_json, test_numbering, test_regions, test_steps
└── docs/                           # Existing analysis docs
```

---

## CORE DATA MODELS (docbot/models.py — Pydantic v2)

```python
class BBox(BaseModel):
    x: float; y: float; width: float; height: float

class Element(BaseModel):
    id: str; accessible_name: str; element_class: str
    tag: str = ""; type: str = ""; bounding_box: BBox
    is_visible: bool = True; role: str = ""; value: str = ""; placeholder: str = ""

class Event(BaseModel):
    id: str
    kind: Literal["click","input","change","navigate","keypress_enter","submit"]
    target_selector: str = ""; target_name: str = ""; target_role: str = ""
    value_summary: str = ""; redacted: bool = False
    url_before: str = ""; url_after: str = ""

class Region(BaseModel):
    id: str
    role: Literal["page_header","nav_bar","filter_form","table_header","action_bar","section_label","generic"]
    label: str = ""; bbox: BBox; elements_contained: list[str] = []
    callout_x: float | None = None   # Manual callout position — set by Review UI
    callout_y: float | None = None
    callout_number: int = 0

class FieldDetail(BaseModel):
    field_name: str; utility: str; information: str; sample: str

class Step(BaseModel):
    n: int; text: str
    kind: Literal["action","result"] = "action"
    event_id: str = ""; crop_path: str = ""

class Figure(BaseModel):
    index: int; path: str; caption_note: str = ""

class ScreenContent(BaseModel):
    screen_name: str = ""; purpose: str = ""; navigation_sentence: str = ""
    region_labels: list[dict] = []; field_details: list[FieldDetail] = []
    steps: list[Step] = []; notes: list[str] = []
    buttons_doc: list[str] = []; table_columns_doc: list[str] = []; path: str = ""

class Screen(BaseModel):
    index: int; url: str = ""; title: str = ""; h1: str = ""; breadcrumb: str = ""
    elements: list[Element] = []; events: list[Event] = []
    regions: list[Region] = []; content: ScreenContent = ScreenContent()
    content_hash: str | None = None; figures: list[Figure] = []
    state_of: int | None = None

class SessionModel(BaseModel):
    schema_version: int = 3; module_name: str = ""; module_number: int | None = None
    client_key: str = ""; screens: list[Screen] = []
    _session_dir: Optional[Path] = None  # Not persisted — set by SessionStore.load()

class SessionStore:
    @staticmethod def load(session_dir: Path) -> SessionModel: ...
    @staticmethod def save(session: SessionModel, session_dir: Path) -> None: ...
    @staticmethod def latest(sessions_root: Path) -> Optional[Path]: ...
```

---

## PIPELINE FLOW (main.py — run_pipeline)

```
run_pipeline(client_key, start_url, module_name, module_number)
│
├─ load_config("config.yaml") → Config
├─ get_provider_instance(config) → Provider (Anthropic|OpenAI|Ollama|Browser)
│
├─ PHASE 1: Capture
│   run_capture_session(start_url, client_key)
│   └─ CaptureSession.run()
│       ├─ sync_playwright() → Chromium headed
│       ├─ restore browser auth state from sessions/state/<client>.json
│       ├─ inject injected.js into every page (event recording + expose triggerCapture/triggerQuit)
│       ├─ LOOP: poll every 100ms for middle-click gestures
│       │   └─ _capture_screen():
│       │       ├─ page.evaluate() → title, h1, url, breadcrumb
│       │       ├─ page.screenshot(clip=viewport)  → screen_N.png
│       │       ├─ page.evaluate(DOM walker) → Element[]
│       │       └─ session.screens.append(Screen(...))
│       ├─ Double middle-click → quit
│       ├─ save browser auth state
│       └─ SessionStore.save(session, session_dir)
│
├─ PHASE 2: Processing
│   ├─ SessionStore.load(latest_session)
│   ├─ for each screen:
│   │   ├─ detect_regions(screen.elements) → Region[]   (heuristic, no LLM)
│   │   └─ compile_steps(screen.events) → Step[]        (deterministic, no LLM)
│   ├─ SessionStore.save()
│   │
│   ├─ ClientProfile.load(client_key) → {manifest, style, voice, glossary}
│   ├─ Generator(provider)
│   └─ for each screen (AI pass):
│       └─ generator.generate_screen(session, screen, client_profile=profile.data)
│           ├─ compute content hash → skip if unchanged
│           ├─ load_prompt("screen_documentation", version="v3", ...substitutions...)
│           ├─ provider.chat_json(prompt, schema=ScreenDocResponse, images=[screen.png])
│           │   ├─ strips markdown fences from response
│           │   ├─ json.loads + ScreenDocResponse.model_validate()
│           │   └─ on ValidationError: retry ONCE with error appended to prompt
│           └─ merge result into screen.content
│
├─ PHASE 3: Write legacy JSON files (screen_N_meta/elements/regions/content.json)
│
├─ PHASE 4: Review UI
│   open_review_ui(session_dir) → ReviewSessionUI (blocking Tkinter window)
│   Writer: edits text, drags callouts, resizes region boxes, Ctrl+Z undo
│
├─ PHASE 5: Module intro
│   generator.generate_module_intro(session, client_profile)
│
└─ PHASE 6: Assembly
    assemble_module(session_dir)
    └─ GenericBuilder.build_module(session_dir)
        ├─ render_annotations(session_dir, screen_index)  → screen_N_annotated.png
        └─ render_screen(doc, screen_index, ...) per screen:
            ├─ H2 heading (numbered)
            ├─ purpose paragraph
            ├─ path breadcrumb
            ├─ navigation instruction
            ├─ screenshot in 1×1 table (0.5pt border)
            ├─ Figure caption (Figure N: Name)
            ├─ field table OR bullet list
            ├─ steps (List Bullet, **bold** UI labels)
            └─ notes paragraphs
    builder.save() → Final_Manuals/<CLIENT>_<SYSTEM>_v<ver>_<ts>.docx
    validate_ooxml_structure(docx) + run_qa_check(docx)
```

---

## PROVIDER ARCHITECTURE

```python
# providers/base.py
class Provider(ABC):
    @property @abstractmethod def name(self) -> str: ...
    @abstractmethod def is_available(self) -> bool: ...
    @abstractmethod def chat(self, prompt, *, max_tokens=8000, temperature=0.2, system=None) -> str: ...
    def chat_vision(self, prompt, images: list[Path], **kw) -> str:
        # Default: text-only fallback (logs warning)
    def chat_json(self, prompt, schema: Type[T], images=None, **kw) -> T:
        # Calls chat/chat_vision → strips fences → json.loads → model_validate
        # On ValidationError: retry ONCE with error appended to prompt
        # On second failure: raise GenerationError

def load_prompt(name: str, version: str = "v3", **kwargs) -> str:
    # Searches prompts/v3/{name}.txt then providers/prompts/{name}.txt
    # Substitutes {placeholders} with kwargs

class GenerationError(RuntimeError): ...
```

Concrete providers: `AnthropicProvider`, `OpenAICompatProvider`, `OllamaProvider`, `BrowserProvider`, `BrowserBatchProvider`

---

## REGION DETECTION (docbot/processing/regions.py)

```python
def detect_regions(elements: list[Element]) -> list[Region]:
    # Heuristic classifiers:
    # page_header: label-type element with h1/h2 tag
    # nav_bar: ≥3 link elements in horizontal cluster near top
    # filter_form: ≥2 interactive inputs grouped by bounding box
    # table_header: th elements in a row
    # action_bar: ≥1 button elements near bottom or top
    # section_label: h3/h4 elements
    # Merge overlapping regions with IoU > 0.6 (union bbox + combined elements)
```

---

## STEP COMPILATION (docbot/processing/steps.py)

```python
def compile_steps(events: Sequence[Event]) -> list[Step]:
    # Rules (deterministic, no LLM):
    # consecutive input/change → group as "Enter the following details:" parent
    # click on button/link → "Click on the X button."
    # click + next navigate → adds "The Y page will be displayed." result step
    # keypress_enter → "Press Enter to submit the Z."
    # navigate (standalone) → "The Y page will be displayed."
```

---

## LLM AI GENERATION (docbot/processing/generator.py)

```python
class Generator:
    def __init__(self, provider: Provider): ...

    def generate_screen(self, session, screen, client_profile=None) -> ScreenDocResponse:
        # 1. Content hash check — skip if inputs unchanged
        # 2. Build prompt from template (voice rules, glossary, elements, regions, steps skeleton)
        # 3. provider.chat_json(prompt, ScreenDocResponse, images=[screenshot])
        # 4. Merge into screen.content
        # 5. Log prompt+response to sessions/<dir>/llm/

    def generate_module_intro(self, session, client_profile=None) -> ModuleIntroResponse:

# Output schemas:
class ScreenDocResponse(BaseModel):
    screen_name: str; purpose: str; navigation_sentence: str
    region_labels: list[RegionLabel]; field_details: list[FieldDetail]
    steps: list[Step]; notes: list[str]
    buttons_doc: list[str]; table_columns_doc: list[str]

class ModuleIntroResponse(BaseModel):
    intro: str; features: list[str]
```

---

## ANNOTATION RENDERING (docbot/processing/annotate.py)

```python
def render_annotations(session_dir, screen_index, regions=None) -> Path:
    # Reads screen_N.png
    # For each region:
    #   - Draws semi-transparent colored bbox overlay
    #   - Computes callout position:
    #       if region.callout_x is not None → use (callout_x, callout_y)
    #       else → auto-score candidate positions (avoids other bubbles + critical UI)
    #   - Draws rounded-rect callout bubble with number badge
    #   - Draws leader line from bubble to region center
    # Saves screen_N_annotated.png
```

---

## DOCUMENT ASSEMBLY (manual_builder/)

```python
class GenericBuilder:
    def __init__(self, manifest: ManifestConfig, style: StyleConfig, numbering: NumberingTracker): ...
    def build_front_matter(self) -> None: ...        # cover, revision history, TOC
    def build_module(self, session_dir: Path) -> None: ...  # all screens
    def build_full_manual(self, ordered_session_dirs) -> None: ...
    def save(self, output_path: Path) -> None: ...

class NumberingTracker:
    # mode: "continuous" → Figure 1,2,3… globally
    # mode: "module_prefixed" → Figure M-1, M-2… per module
    def enter_section(self, level) -> str: ...
    def next_figure(self, module_num) -> str: ...
    def next_table(self, module_num) -> str: ...
    def register_figure(self, number, caption) -> None: ...
```

**Section types in manifest:** `cover`, `revision_history`, `table_of_contents`, `table_of_figures`, `table_of_tables`, `prose`, `bullet_list`, `icon_table`, `group`, `modules`

---

## CLIENT CONFIGURATION FILES

Each client has 4 YAML files in `clients/<key>/`:

**manifest.yaml** — metadata + sections list:
```yaml
client_key: ncd
client_display_name: "National Cooperative Database"
system_name: "NCD State Nodal Portal"
system_acronym: "NCD"; role_name: "State Nodal Officer"
manual_title: "User Manual"; version: "1.0"
audience: "State Nodal Officers"; confidentiality: "CONFIDENTIAL"
numbering_mode: continuous   # or module_prefixed
sections:
  - {id: revision_history, type: revision_history, source: revision_history.yaml}
  - {id: toc, type: table_of_contents}
  - {id: table_of_figures, type: table_of_figures}
  - {id: introduction, type: prose, heading: "Introduction", source: introduction.md}
  - {id: modules, type: modules}
```

**style.yaml** — fonts, colors, layout, annotations:
```yaml
body_font: Calibri; heading_font: Calibri; body_size: 11
colors: {primary: "1B365D", secondary: "2E6DA4", ...}
headings: {1: {size_pt:16, bold:true, color:primary}, ...}
figures: {max_width_inches:6.2, border_enabled:true, caption_size_pt:9}
fields: {style: table}    # or "bullets"
numbering: {figure_prefix: Figure, figure_format: "{fig}"}
annotations: {mode: callouts}
```

**voice.yaml** — LLM writing tone (injected into prompt):
```yaml
app_name: NCD System
tone_rules: [Use formal professional imperative, No contractions, ...]
examples: {purpose: [...], step: [...], field: [...]}
navigation_template: "Select {screen_name} option from {parent_menu}..."
notes_block: "Note: The system requires a stable internet connection..."
```

**glossary.yaml** — domain terms (injected into prompt):
```yaml
NCD: Non-Communicable Disease
HMIS: Health Management Information System
```

---

## CONFIGURATION (config.yaml + .env)

```yaml
provider: anthropic           # or openai_compat, ollama, browser
current_client: ncd
content_dir: content
clients_dir: clients
styles_dir: styles
sessions_dir: sessions
providers:
  anthropic: {api_key_env: ANTHROPIC_API_KEY, model: claude-sonnet-4-6, max_tokens: 8000}
  openai_compat: {api_key_env: OPENAI_API_KEY, base_url: https://api.groq.com/openai/v1, model: llama-3.3-70b-versatile}
  ollama: {host: https://ollama.com, model: gpt-oss:120b, api_key_env: OLLAMA_API_KEY}
  browser: {editor_command: notepad}
render: {label_font_size: 20, region_stroke_width: 3, callout_border_width: 2}
capture: {mode: viewport, scroll_capture: false}
```

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=gsk_...
OLLAMA_API_KEY=...
```

---

## QA SYSTEM (docbot/export/qa.py)

```python
def validate_ooxml_structure(docx_path) -> bool:
    # Checks fldChar/instrText are never direct children of <w:p>
    # Word refuses to open documents with this violation

def validate_deliverable(docx_path) -> bool:
    # H1: OOXML structure
    # H2: No forbidden strings ([Client, Sample text, etc.)
    # H3: Revision history table has ≥1 data row
    # H4: Every image paragraph followed by Caption-style paragraph
    # H5: updateFields in word/settings.xml (TOC auto-refresh)
    # H7: python-docx round-trip succeeds

def run_qa_check(docx_path) -> Optional[Path]:
    # Runs validate_ooxml_structure + LibreOffice PDF conversion (if installed)
    # Rasterises first 3 pages to PNG via fitz or pdf2image
```

---

## TESTS (tests/)

4 test files, 8 tests total:
- `test_regions.py` — IoU merge, role classification, parenthesis precedence
- `test_steps.py` — input grouping, click+navigate, change events
- `test_numbering.py` — continuous vs module-prefixed figure/table numbers
- `test_chat_json.py` — JSON fence stripping, ValidationError retry logic

---

## KEY DESIGN DECISIONS

1. **One LLM call per screen** (not per field/region) — reduces cost and latency
2. **Content-hash caching** — Generator skips LLM if prompt inputs unchanged
3. **Deterministic steps first** — steps.py compiles steps from events WITHOUT LLM; Generator only polishes
4. **Session.json is source of truth** — legacy flat JSON files written only for backward compat with manual_builder renderers
5. **Manifest-driven document** — zero code changes to onboard new client
6. **IoU merge** — prevents duplicate callouts on same UI area
7. **Manual callout override** — `region.callout_x/y` bypasses auto-scoring when writer drags bubble

---

## NOW GENERATE THE FOLLOWING DOCUMENTATION

Write all of the following as professional, complete Markdown documents. Use proper headings, tables, code blocks, and diagrams where helpful. Be thorough — these are the only docs for this project.

### Document 1: `docs/getting-started.md`
Complete installation + first run guide. Include: prerequisites, virtualenv setup, pip install, playwright install, .env setup, config.yaml configuration, first recording walkthrough (step by step), first assembly walkthrough. Include a troubleshooting section.

### Document 2: `docs/user-guide.md`
Full user manual for the documentation writer. Cover: the launcher UI, recording a module (middle-click gestures), what happens during AI generation, using the Review UI (editing text, dragging callouts, resizing boxes, undo), assembling a module, assembling the master manual. Use numbered steps. Include a "Tips & Tricks" section.

### Document 3: `docs/provider-guide.md`
How to configure and use each LLM provider: Anthropic, OpenAI-compatible (Groq, Together AI), Ollama (local and cloud), and Browser (manual copy-paste). Include: API key setup, config.yaml settings, known limitations, cost estimates, when to use each. Also document how to add a brand new provider (step by step with code example).

### Document 4: `docs/client-onboarding.md`
How to onboard a new client from scratch. Step-by-step: create the directory, copy defaults, fill in all 4 YAML files with field-by-field explanation and examples, create revision history, test the config. Include a full worked example (invent a realistic client "ABC Health"). Cover color palette best practices, font choices, voice tone examples for different industries.

### Document 5: `docs/prompt-engineering.md`
How the LLM prompts work. Cover: the prompt template system (`load_prompt()`), what variables are injected, how voice.yaml and glossary.yaml feed into the prompt, how to tune prompts for better output, the `PROMPT_VERSION` cache invalidation mechanism, how to write good `tone_rules` and `examples` in voice.yaml, common LLM output problems and how to fix them in the prompt.

### Document 6: `docs/session-data-reference.md`
Complete reference for the session data format. Cover: `session.json` schema (all fields), legacy JSON files and why they exist, the `sessions/state/<client>.json` auth file, the `llm/` debug log format, the `run.log` format. Include example JSON snippets for each file.

### Document 7: `docs/troubleshooting.md`
Comprehensive troubleshooting guide. Cover at minimum: browser won't open, Playwright not installed, session has 0 screens, AI generation produces empty content, API key errors (each provider), Word document won't open in Microsoft Word, fonts not found, LibreOffice PDF not generated, Review UI doesn't load, assembly fails with BuildError, OOXML validation errors, callout bubbles in wrong position, fields are "sample text" placeholders, module intro not generated. For each problem: symptom, cause, fix.

### Document 8: `docs/architecture-deep-dive.md`
Deep technical architecture document for contributors. Cover: complete call graph (as ASCII), Pydantic data model diagram, how region IoU merge works (algorithm), how content-hash caching works, how the Provider retry mechanism works, how the Review UI drag state machine works (4 modes: draw/move/resize/callout), how the NumberingTracker works for both modes, how the manifest `sections` list maps to renderer dispatch, OOXML validation approach, security model (auth state, API keys, path traversal guards).

---

## OUTPUT FORMAT

For each document:
- Start with `# Document N: <filename>` as a header
- Then the full Markdown content
- Use `---` between documents
- Use realistic, specific examples (not "foo/bar" placeholders)
- Every code block must have a language tag
- Tables for all reference information
- Bold key terms on first use
- Keep a consistent "you" voice (addressing the documentation writer/developer)

Generate all 8 documents now.
