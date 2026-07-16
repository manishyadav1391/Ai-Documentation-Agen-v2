# Module Reference — `docbot` Package

> **API reference for all public modules in the `docbot` package.**

---

## `docbot.models`

**File:** [`docbot/models.py`](file:///c:/doc_automation_v2/docbot/models.py)

Central data schema for the entire pipeline. All models use Pydantic v2.

### Classes

---

#### `BBox`

```python
class BBox(BaseModel):
    x: float
    y: float
    width: float
    height: float
```

Bounding box in document or viewport coordinates. Used by `Element`, `Region`, and `Figure`.

---

#### `Element`

```python
class Element(BaseModel):
    id: str
    accessible_name: str
    element_class: str          # e.g., "interactive", "static_label"
    tag: str = ""               # HTML tag (input, button, h1, …)
    type: str = ""              # Element type (label, input, …)
    bounding_box: BBox
    is_visible: bool = True
    role: str = ""              # ARIA role
    value: str = ""             # Current value (for inputs)
    placeholder: str = ""
```

Represents one DOM element extracted from the browser page.

---

#### `Event`

```python
class Event(BaseModel):
    id: str
    kind: Literal["click","input","change","navigate","keypress_enter","submit"]
    target_selector: str = ""
    target_name: str = ""
    target_role: str = ""
    value_summary: str = ""     # Masked/summarised value (never PII)
    redacted: bool = False
    url_before: str = ""
    url_after: str = ""
```

One recorded user interaction. Events are collected by `injected.js` and extracted by `CaptureSession`.

---

#### `Region`

```python
class Region(BaseModel):
    id: str
    role: Literal[
        "page_header","nav_bar","filter_form","table_header",
        "action_bar","section_label","generic"
    ]
    label: str = ""
    bbox: BBox
    elements_contained: list[str] = []   # accessible_name of included elements
    callout_x: float | None = None       # Manual callout X (None = auto)
    callout_y: float | None = None       # Manual callout Y (None = auto)
    callout_number: int = 0
```

A semantic region detected from DOM elements. `callout_x`/`callout_y` are set by the Review UI when the writer manually repositions a callout bubble.

---

#### `FieldDetail`

```python
class FieldDetail(BaseModel):
    field_name: str
    utility: str        # What the field does
    information: str    # What to enter
    sample: str         # Example value
```

---

#### `Step`

```python
class Step(BaseModel):
    n: int              # Step number (1-indexed)
    text: str           # Step text (may contain **bold** markers)
    kind: Literal["action","result"] = "action"
    event_id: str = ""  # Source event ID
    crop_path: str = "" # Optional inline crop image path
```

---

#### `Figure`

```python
class Figure(BaseModel):
    index: int
    path: str           # Relative path to image file (within session dir)
    caption_note: str = ""
```

---

#### `ScreenContent`

```python
class ScreenContent(BaseModel):
    screen_name: str = ""
    purpose: str = ""
    navigation_sentence: str = ""
    region_labels: list[dict] = []
    field_details: list[FieldDetail] = []
    steps: list[Step] = []
    notes: list[str] = []
    buttons_doc: list[str] = []
    table_columns_doc: list[str] = []
    path: str = ""
```

The AI-generated documentation for one screen. Embedded in `Screen.content`.

---

#### `Screen`

```python
class Screen(BaseModel):
    index: int                          # 1-indexed screen number
    url: str = ""
    title: str = ""
    h1: str = ""
    breadcrumb: str = ""
    elements: list[Element] = []
    events: list[Event] = []
    regions: list[Region] = []
    content: ScreenContent = ScreenContent()
    content_hash: str | None = None     # LLM cache key
    figures: list[Figure] = []
    state_of: int | None = None         # If set, this screen is a sub-state of screen N
```

---

#### `SessionModel`

```python
class SessionModel(BaseModel):
    schema_version: int = 3
    module_name: str = ""
    module_number: int | None = None
    client_key: str = ""
    screens: list[Screen] = []
    _session_dir: Optional[Path] = None  # Set by SessionStore.load(); not persisted
```

The root data model for an entire recording session.

---

#### `SessionStore`

```python
class SessionStore:
    @staticmethod
    def load(session_dir: Path) -> SessionModel: ...

    @staticmethod
    def save(session: SessionModel, session_dir: Path) -> None: ...

    @staticmethod
    def latest(sessions_root: Path = Path("sessions")) -> Optional[Path]: ...
```

Static helper for reading and writing `session.json`. Handles legacy flat-file migration automatically.

---

## `docbot.recorder.capture`

**File:** [`docbot/recorder/capture.py`](file:///c:/doc_automation_v2/docbot/recorder/capture.py)

### `CaptureSession`

```python
class CaptureSession:
    def __init__(
        self,
        start_url: str,
        client_key: str,
        session_dir: Path,
        sessions_dir: Path = Path("sessions"),
        headless: bool = False,
    ) -> None: ...

    def run(self) -> SessionModel: ...
```

Orchestrates the Playwright browser session. Opens Chromium, instruments pages with `injected.js`, and processes middle-click capture gestures.

### `run_capture_session()`

```python
def run_capture_session(
    start_url: str,
    client_key: str,
    sessions_dir: Path = Path("sessions"),
    headless: bool = False,
) -> tuple[SessionModel, Path]:
```

Convenience function that creates and runs a `CaptureSession`. Returns `(session, session_dir)`.

---

## `docbot.processing.regions`

**File:** [`docbot/processing/regions.py`](file:///c:/doc_automation_v2/docbot/processing/regions.py)

### `detect_regions()`

```python
def detect_regions(elements: list[Element]) -> list[Region]:
```

Runs heuristic region detection on a list of DOM elements. Returns detected `Region` objects with bounding boxes. Overlapping regions with IoU > 0.6 are merged.

### `process_screen_regions()`

```python
def process_screen_regions(session_dir: Path, screen_index: int) -> list[Region]:
```

Convenience wrapper that loads elements from `session.json`, runs `detect_regions()`, and saves the result back to the session. Returns the detected regions.

---

## `docbot.processing.steps`

**File:** [`docbot/processing/steps.py`](file:///c:/doc_automation_v2/docbot/processing/steps.py)

### `compile_steps()`

```python
def compile_steps(events: Sequence[Event]) -> list[Step]:
```

Deterministic event-to-step compiler. Converts raw browser events into structured Step objects. No LLM call. Input/change events are grouped; click+navigate events produce action+result step pairs.

---

## `docbot.processing.generator`

**File:** [`docbot/processing/generator.py`](file:///c:/doc_automation_v2/docbot/processing/generator.py)

### `Generator`

```python
class Generator:
    def __init__(self, provider: Provider) -> None: ...

    def generate_screen(
        self,
        session: SessionModel,
        screen: Screen,
        client_profile: dict | None = None,
    ) -> ScreenDocResponse: ...

    def generate_module_intro(
        self,
        session: SessionModel,
        client_profile: dict | None = None,
    ) -> ModuleIntroResponse: ...
```

Orchestrates LLM-based documentation generation. Handles prompt assembly, content-hash caching, LLM call, response validation, and result merging.

**`ScreenDocResponse`** — schema for `generate_screen()` output:
```python
class ScreenDocResponse(BaseModel):
    screen_name: str
    purpose: str
    navigation_sentence: str
    region_labels: list[RegionLabel]    # {region_id: str, label: str}
    field_details: list[FieldDetail]
    steps: list[Step]
    notes: list[str]
    buttons_doc: list[str]
    table_columns_doc: list[str]
```

**`ModuleIntroResponse`** — schema for `generate_module_intro()` output:
```python
class ModuleIntroResponse(BaseModel):
    intro: str
    features: list[str]
```

---

## `docbot.processing.annotate`

**File:** [`docbot/processing/annotate.py`](file:///c:/doc_automation_v2/docbot/processing/annotate.py)

### `render_annotations()`

```python
def render_annotations(
    session_dir: Path,
    screen_index: int,
    regions: list[Region] | None = None,
) -> Path:
```

Renders callout overlays onto a screenshot using Pillow. Reads `screen_N.png` (or `_viewport.png`), draws colored region boxes and numbered callout bubbles, saves `screen_N_annotated.png`.

Callout positions: if `region.callout_x is not None`, uses those coordinates instead of auto-scoring.

Returns the path to the annotated PNG.

---

## `docbot.processing.crops`

**File:** [`docbot/processing/crops.py`](file:///c:/doc_automation_v2/docbot/processing/crops.py)

### `extract_crops()`

```python
def extract_crops(
    session_dir: Path,
    screen_index: int,
    steps: list[Step],
) -> list[Step]:
```

For each step that references a UI element, crops a small image patch from the screenshot around that element's bounding box. Sets `step.crop_path` to the cropped image file. Useful for inline step images in the Word document.

---

## `docbot.clients.profile`

**File:** [`docbot/clients/profile.py`](file:///c:/doc_automation_v2/docbot/clients/profile.py)

### `ClientProfile`

```python
class ClientProfile:
    key: str
    manifest: dict
    style: dict
    voice: dict
    glossary: dict[str, str]
    data: dict    # Combined: {manifest, style, voice, glossary}

    @classmethod
    def load(cls, key: str, clients_dir: Path | None = None) -> "ClientProfile": ...

    # Convenience properties
    @property def client_display_name(self) -> str: ...
    @property def system_name(self) -> str: ...
    @property def app_name(self) -> str: ...
    @property def numbering_mode(self) -> str: ...
    @property def field_style(self) -> str: ...
    @property def navigation_template(self) -> str: ...
    @property def notes_block(self) -> str: ...

    def get_color(self, key: str) -> str: ...
    def annotation_mode(self) -> str: ...
```

Loads all four per-client YAML files (`manifest.yaml`, `style.yaml`, `voice.yaml`, `glossary.yaml`) with fallback to `_default/`. Normalises the glossary (handles both list-of-dicts and flat-mapping formats).

---

## `docbot.export.qa`

**File:** [`docbot/export/qa.py`](file:///c:/doc_automation_v2/docbot/export/qa.py)

### `validate_ooxml_structure()`

```python
def validate_ooxml_structure(docx_path: Path) -> bool:
```

Validates that `fldChar` and `instrText` elements are never direct children of `<w:p>`. Microsoft Word refuses to open documents with this violation. Returns `True` if the document is valid.

### `validate_deliverable()`

```python
def validate_deliverable(docx_path: Path) -> bool:
```

Full QA gate (H1–H7):
- H1: OOXML structure
- H2: No forbidden placeholder strings (`[Client`, `Sample text`, etc.)
- H3: Revision history table has ≥1 data row
- H4: Every image paragraph followed by a Caption-style paragraph
- H5: `updateFields` present in `word/settings.xml`
- H7: python-docx round-trip succeeds

### `run_qa_check()`

```python
def run_qa_check(docx_path: Path) -> Optional[Path]:
```

Runs OOXML structural validation, then attempts to convert to PDF via LibreOffice `soffice`. If LibreOffice is available, rasterises the first 3 pages to PNG in `qa_pages/`. Returns the PDF path or `None` if LibreOffice is not installed.

---

## `docbot.logging_setup`

**File:** [`docbot/logging_setup.py`](file:///c:/doc_automation_v2/docbot/logging_setup.py)

### `setup_logging()`

```python
def setup_logging(level: str = "INFO") -> None:
```

Removes loguru's default handler and installs a coloured stderr sink at the given level. Call once at startup.

### `attach_session_log()`

```python
def attach_session_log(session_dir: Path) -> None:
```

Adds a rotating per-session DEBUG log file (`run.log`) inside `session_dir`. Replaces any previously attached session sink.

---

## `providers.base`

**File:** [`providers/base.py`](file:///c:/doc_automation_v2/providers/base.py)

### `Provider` (abstract)

```python
class Provider(ABC):
    @property @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def chat(self, prompt, *, max_tokens=8000, temperature=0.2, system=None) -> str: ...

    def chat_vision(self, prompt, images: list[Path], **kw) -> str: ...
    # Default: warns + falls back to text-only chat

    def chat_json(self, prompt, schema: Type[T], images=None, **kw) -> T: ...
    # Calls chat/chat_vision, strips fences, validates JSON, retries once on error
```

### `load_prompt()`

```python
def load_prompt(name: str, version: str = "v3", **kwargs) -> str:
```

Loads a prompt template from `prompts/{version}/{name}.txt` (with fallback to `providers/prompts/{name}.txt`) and substitutes `{key}` placeholders with `kwargs` values.

### `GenerationError`

```python
class GenerationError(RuntimeError):
    """Raised when the LLM fails to produce valid output after retries."""
```

---

## `manual_builder`

**File:** [`manual_builder/__init__.py`](file:///c:/doc_automation_v2/manual_builder/__init__.py)

### Public API

```python
from manual_builder import (
    load_manifest,      # → ManifestConfig
    load_style,         # → StyleConfig
    NumberingTracker,   # numbering state machine
    GenericBuilder,     # Word document builder
)
```

### `GenericBuilder`

```python
class GenericBuilder:
    def __init__(
        self,
        manifest: ManifestConfig,
        style: StyleConfig,
        numbering_tracker: NumberingTracker,
    ) -> None: ...

    def build_front_matter(self) -> None:
        """Renders all non-modules sections from the manifest."""

    def build_module(self, session_dir: Path) -> None:
        """Renders one session's screens into the document."""

    def build_full_manual(self, ordered_session_dirs: list[Path]) -> None:
        """Renders front matter + all modules in order."""

    def save(self, output_path: Path) -> None:
        """Saves the document to disk."""

    def dispatch_section(self, section: SectionEntry, level: int = 1) -> None:
        """Routes section rendering to the correct renderer."""
```

### `NumberingTracker`

```python
class NumberingTracker:
    def __init__(self, style_config=None, mode: str = "module_prefixed") -> None: ...

    def enter_section(self, level: int) -> str:
        """Returns section number string (e.g., '1', '10.2')"""

    def next_figure(self, module_num: int = 0) -> str:
        """Returns figure number string (mode-dependent)"""

    def next_table(self, module_num: int = 0) -> str:
        """Returns table number string"""

    def register_figure(self, number: str, caption: str) -> None: ...
    def register_table(self, number: str, caption: str) -> None: ...

    @property def figure_count(self) -> int: ...
    @property def table_count(self) -> int: ...
    @property def current_module(self) -> int: ...
```

---

## `config`

**File:** [`config.py`](file:///c:/doc_automation_v2/config.py)

### `get_config()`

```python
def get_config() -> Config:
```

Returns the singleton `Config` instance. Loads `config.yaml` and `.env` on first call.

### `Config`

```python
class Config(BaseModel):
    provider: str                  # Active provider key
    current_client: str            # Active client key
    content_dir: str = "content"
    clients_dir: str = "clients"
    styles_dir: str = "styles"
    sessions_dir: str = "sessions"
    providers: dict[str, ProviderConfig]
    render: RenderConfig
    capture: CaptureConfig
```

### `Config.get_api_key(provider_key)`

```python
def get_api_key(self, provider_key: str) -> str | None:
```

Reads the API key for the given provider from the environment variable specified in `providers[provider_key].api_key_env`.
