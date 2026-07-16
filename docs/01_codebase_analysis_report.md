# Codebase Analysis Report — DocBot v3

> **Project:** `c:\doc_automation_v2`
> **Analyzed:** 2026-07-16
> **Analyzer:** Staff Software Engineer / Architect

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Architecture Overview](#2-project-architecture-overview)
3. [Folder Structure](#3-folder-structure)
4. [Module Map & Dependency Graph](#4-module-map--dependency-graph)
5. [Import Graph](#5-import-graph)
6. [Call Graph — Main Pipeline](#6-call-graph--main-pipeline)
7. [Runtime Flow](#7-runtime-flow)
8. [Data Flow](#8-data-flow)
9. [Configuration Files](#9-configuration-files)
10. [Environment Variables](#10-environment-variables)
11. [Third-Party Integrations](#11-third-party-integrations)
12. [Authentication Flow](#12-authentication-flow)
13. [Background Jobs](#13-background-jobs)

---

## 1. Executive Summary

DocBot v3 is a **Python desktop application** that automates the creation of professional user-manual Word documents (`.docx`) for software systems. The system orchestrates:

1. **Browser-based capture** (Playwright headed Chromium) — the writer navigates a target web application and triggers captures by middle-clicking.
2. **AI-driven documentation generation** — one LLM call per screen produces screen names, purpose statements, field descriptions, procedure steps, and region labels.
3. **Visual review and editing** — a Tkinter GUI lets the writer correct AI output, drag callout bubbles, and resize annotation regions.
4. **Manifest-driven Word document assembly** — a `python-docx` builder reads per-client YAML configuration and session data to produce a fully-branded, numbered, QA-validated `.docx`.

The codebase is currently in a **v2→v3 migration** state. Several compatibility shims exist at the root level (`capture.py`, `annotate.py`, `detect_regions.py`, `review_ui.py`, `labeler.py`) that re-export from the correct `docbot.*` package locations while emitting `DeprecationWarning`. These shims are intended for removal in Phase 7/8.

---

## 2. Project Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      ui/launcher.py                             │
│                   (Tkinter Control Panel)                        │
└────────────┬────────────────────────────┬───────────────────────┘
             │ run_pipeline()              │ assemble_master_manual()
             ▼                            ▼
┌────────────────────┐         ┌──────────────────────┐
│     main.py        │         │  master_assembler.py  │
│ (Linear Pipeline)  │         │ (Multi-session build) │
└──────┬─────────────┘         └──────────┬───────────┘
       │                                   │
       ├─ Phase 1: Capture                 │
       │  docbot/recorder/capture.py       │
       │  (Playwright + injected.js)       │
       │                                   │
       ├─ Phase 2a: Region Detection       │
       │  docbot/processing/regions.py     │
       │                                   │
       ├─ Phase 2b: Step Compilation       │    ┌────────────────────────┐
       │  docbot/processing/steps.py       │    │  manual_builder/       │
       │                                   │    │  generic_builder.py    │
       ├─ Phase 2c: AI Documentation       │    │  (GenericBuilder)      │
       │  docbot/processing/generator.py   │    └────────┬───────────────┘
       │  → providers/{anthropic,openai,   │             │ renders
       │    ollama,browser}.py             │    ┌────────▼───────────────┐
       │                                   │    │  manual_builder/       │
       ├─ Phase 3: Visual Review           │    │  renderers/screen.py   │
       │  ui/review.py                     │    │  (screen sections)     │
       │  + docbot/processing/annotate.py  │    └────────────────────────┘
       │                                   │
       └─ Phase 4: Assembly                │
          assemble.py (single module)  ────┘
          → Final_Manuals/*.docx
          → docbot/export/qa.py
```

**Key design principles:**
- **Session-centric**: All pipeline data lives in `session.json` (pydantic `SessionModel`). Legacy flat JSON files are written as a compatibility layer.
- **One LLM call per screen**: Reduces latency and cost vs. separate calls per field/region.
- **Content-hash caching**: Screens are not re-generated if their prompt inputs haven't changed.
- **Manifest-driven output**: Document structure, branding, and voice are fully externalised to per-client YAML — no hardcoded content.

---

## 3. Folder Structure

```
c:\doc_automation_v2\
│
├── main.py                         # Pipeline entry point (run_pipeline)
├── config.py                       # Pydantic Config models, load/save helpers
├── config.yaml                     # Runtime-editable application config
├── .env                            # Secret API keys (git-ignored)
├── .env.example                    # Template for .env
├── requirements.txt                # 9 third-party dependencies
├── assemble.py                     # Single-module + master assembly entry points
├── master_assembler.py             # Multi-session master manual assembler
│
├── annotate.py                     # DEPRECATED SHIM → docbot.processing.annotate
├── capture.py                      # DEPRECATED SHIM → docbot.recorder.capture
├── detect_regions.py               # DEPRECATED SHIM → docbot.processing.regions
├── review_ui.py                    # DEPRECATED SHIM → ui.review
├── labeler.py                      # DEPRECATED SHIM → docbot.processing.generator
│
├── docbot/                         # Core library package
│   ├── models.py                   # ALL pydantic v2 data models
│   ├── logging_setup.py            # Loguru setup (console + per-session file)
│   ├── clients/
│   │   └── profile.py              # ClientProfile: loads 4 YAML files per client
│   ├── processing/
│   │   ├── annotate.py             # Pillow: callout bubbles + leader lines on PNG
│   │   ├── crops.py                # Extracts step-inline crop images
│   │   ├── generator.py            # LLM orchestrator (Generator class)
│   │   ├── regions.py              # Heuristic DOM region detectors + IoU merge
│   │   └── steps.py               # Deterministic event-to-step compiler
│   ├── recorder/
│   │   ├── capture.py              # CaptureSession (Playwright orchestration)
│   │   └── injected.js             # JS injected into every browser page
│   └── export/
│       ├── qa.py                   # OOXML validation + LibreOffice PDF QA
│       ├── word_fields.py          # python-docx helpers: TOC fields, captions
│       └── renderers/              # (sub-package, used internally by export)
│
├── manual_builder/                 # Manifest-driven Word doc builder
│   ├── __init__.py                 # Public API
│   ├── generic_builder.py          # GenericBuilder class
│   ├── manifest_loader.py          # ManifestConfig dataclass + loader
│   ├── style_loader.py             # StyleConfig dataclass + loader
│   ├── numbering.py                # NumberingTracker (sections/figures/tables)
│   ├── utils.py                    # Word helpers (header/footer, borders, colors)
│   ├── build_error.py              # BuildError exception
│   └── renderers/
│       ├── cover.py                # Cover page
│       ├── revision_history.py     # Revision history table
│       ├── toc.py                  # TOC / Table of Figures / Table of Tables
│       ├── prose.py                # Free text prose section
│       ├── bullet_list.py          # Bulleted list section
│       ├── icon_table.py           # Icon + description table
│       ├── group.py                # Grouped nested sections
│       ├── module.py               # Module-level renderer
│       ├── screen.py               # Per-screen: heading, purpose, screenshot, fields, steps
│       └── field_table.py          # Field detail table
│
├── providers/                      # LLM provider adapters
│   ├── base.py                     # Abstract Provider + load_prompt + GenerationError
│   ├── anthropic_api.py            # Anthropic Claude API
│   ├── openai_compat.py            # OpenAI-compatible endpoints (Groq, etc.)
│   ├── ollama.py                   # Ollama local/cloud
│   ├── browser.py                  # Manual copy-paste (no API key)
│   └── browser_batch.py            # Batch copy-paste mode
│
├── prompts/v3/                     # LLM prompt templates (v3)
│   ├── screen_documentation.txt
│   └── module_intro.txt
│
├── ui/                             # Desktop GUI
│   ├── launcher.py                 # LauncherUI (main control panel)
│   ├── review.py                   # ReviewSessionUI (annotation editor, 1343 lines)
│   └── style_editor.py             # StyleEditorDialog (advanced style editing)
│
├── clients/                        # Per-client configuration
│   ├── _default/                   # Fallback defaults (manifest/style/voice/glossary)
│   ├── ncd/                        # National Cooperative Database
│   ├── ncb/                        # NCB
│   ├── swagylab/                   # SwagyLab
│   └── orangehrms/                 # OrangeHRMS
│
├── styles/                         # Legacy global style YAMLs (being superseded)
├── sessions/                       # Runtime session data (git-ignored)
│   ├── <session_dir>/session.json  # Primary session model
│   ├── <session_dir>/screen_N_*.png
│   ├── <session_dir>/screen_N_*.json (legacy)
│   ├── <session_dir>/run.log
│   └── state/<client>.json         # Saved browser auth (cookies)
├── Final_Manuals/                  # Output Word documents
├── tests/                          # Pytest suite (4 test files)
├── llm_ui.py                       # ORPHAN - standalone LLM UI, not imported
├── manual_builder.zip              # ARTIFACT - archived old version
└── v3 changes                      # Plain-text change log
```

---

## 4. Module Map & Dependency Graph

```
ui.launcher ──────────────────────────────────────────────────────┐
    ├── main.run_pipeline()                                        │
    │       ├── capture.py (SHIM) → docbot.recorder.capture       │
    │       │       ├── playwright (sync_playwright)               │
    │       │       ├── docbot.models (SessionModel, Screen…)      │
    │       │       └── injected.js                                │
    │       ├── detect_regions.py (SHIM) → docbot.processing.regions
    │       │       └── docbot.models (Element, BBox, Region)      │
    │       ├── docbot.processing.steps                            │
    │       │       └── docbot.models (Event, Step)                │
    │       ├── labeler.py (SHIM) → docbot.processing.generator    │
    │       │       ├── providers.base (Provider, load_prompt)     │
    │       │       │       ├── providers.anthropic_api            │
    │       │       │       ├── providers.openai_compat            │
    │       │       │       ├── providers.ollama                   │
    │       │       │       └── providers.browser                  │
    │       │       └── docbot.models                              │
    │       ├── review_ui.py (SHIM) → ui.review                   │
    │       │       ├── docbot.models                              │
    │       │       ├── docbot.processing.annotate                 │
    │       │       │       ├── PIL (Pillow)                       │
    │       │       │       └── config                             │
    │       │       ├── docbot.processing.generator                │
    │       │       └── docbot.processing.crops                    │
    │       └── assemble.py                                        │
    │               └── manual_builder (GenericBuilder)            │
    │                       ├── manifest_loader                    │
    │                       ├── style_loader                       │
    │                       ├── numbering                          │
    │                       └── renderers.screen → docbot.export.* │
    ├── master_assembler.assemble_master_manual()                  │
    ├── config (get_config, save_config)                           │
    ├── docbot.clients.profile.ClientProfile                       │
    └── ui.style_editor.StyleEditorDialog                         ─┘
```

---

## 5. Import Graph

| Module | Key Direct Imports |
|---|---|
| `main.py` | `config`, `capture` (shim), `detect_regions` (shim), `labeler` (shim), `review_ui` (shim), `annotate` (shim), `assemble`, `docbot.models`, `docbot.processing.regions`, `docbot.processing.steps`, `docbot.processing.generator`, `docbot.clients.profile`, `manual_builder` |
| `docbot.models` | `pydantic`, `loguru`, `json`, `os`, `tempfile`, `uuid`, `datetime`, `pathlib`, `hashlib` |
| `docbot.recorder.capture` | `playwright.sync_api`, `config`, `docbot.logging_setup`, `docbot.models` |
| `docbot.processing.generator` | `providers.base`, `docbot.models`, `hashlib`, `json`, `loguru` |
| `docbot.processing.regions` | `docbot.models`, `loguru`, `json`, `pathlib` |
| `docbot.processing.steps` | `docbot.models` |
| `docbot.processing.annotate` | `config`, `PIL`, `loguru`, `json`, `math`, `dataclasses` |
| `docbot.processing.crops` | `PIL`, `docbot.models`, `pathlib`, `loguru` |
| `docbot.clients.profile` | `yaml`, `loguru`, `pathlib` |
| `docbot.export.qa` | `lxml.etree`, `docx`, `loguru`, `subprocess`, `shutil`, `zipfile` |
| `docbot.export.word_fields` | `python-docx`, `docx.oxml`, `docx.oxml.ns` |
| `providers.base` | `abc`, `json`, `re`, `pydantic`, `loguru`, `pathlib` |
| `providers.anthropic_api` | `providers.base`, `httpx` |
| `providers.openai_compat` | `providers.base`, `httpx` |
| `providers.ollama` | `providers.base`, `httpx` |
| `providers.browser` | `providers.base`, `subprocess` |
| `manual_builder.generic_builder` | `python-docx`, `manual_builder.*`, `docbot.export.*` |
| `manual_builder.renderers.screen` | `python-docx`, `PIL`, `manual_builder.utils`, `docbot.export.word_fields` |
| `ui.launcher` | `main`, `master_assembler`, `config`, `docbot.clients.profile`, `ui.style_editor`, `tkinter`, `yaml`, `pathlib` |
| `ui.review` | `docbot.models`, `docbot.processing.generator`, `docbot.processing.annotate`, `docbot.processing.crops`, `config`, `PIL`, `tkinter` |
| `config.py` | `pydantic`, `yaml`, `dotenv`, `loguru`, `os`, `pathlib` |

---

## 6. Call Graph — Main Pipeline

```
run_pipeline(client_key, start_url, module_name, module_number)
│
├─ load_config("config.yaml") → Config
├─ get_provider_instance(config) → Provider
│   └─ AnthropicProvider() | OpenAICompatProvider() | OllamaProvider() | BrowserProvider()
├─ Labeler(provider)  [DEPRECATED SHIM wrapping Generator]
│
├─ run_capture_session(start_url, client_key, ...)
│   └─ CaptureSession.run()
│       ├─ sync_playwright() → Chromium headed
│       ├─ context.storage_state restore (auth)
│       ├─ context.on("page", _setup_page)   # instrument every page
│       │   ├─ page.add_init_script(_JS_HOOK) # inject event recorder
│       │   └─ page.expose_function(triggerCapture, triggerQuit, ...)
│       ├─ LOOP: page.wait_for_timeout(100) + _process_pending_captures()
│       │   └─ _capture_screen(page, ...)
│       │       ├─ page.evaluate(_PAGE_CONTEXT_JS) → title, h1, breadcrumb, url
│       │       ├─ page.screenshot(path=..., clip=vp_box)  # viewport PNG
│       │       ├─ page.evaluate(_DOM_EXTRACT_JS) → raw_els
│       │       ├─ Filter/translate elements to viewport space (FIX-2)
│       │       └─ session.screens.append(Screen(...))
│       ├─ context.storage_state save (auth)
│       └─ SessionStore.save(session, session_dir)
│
├─ SessionStore.load(latest_session) → SessionModel
│
├─ LOOP per screen:
│   ├─ detect_regions(screen.elements) → list[Region]
│   └─ compile_steps(screen.events) → list[Step]
├─ SessionStore.save(session, latest_session)
│
├─ ClientProfile.load(config.current_client)
├─ Generator(provider)
│
├─ LOOP per screen (AI generation):
│   └─ generator.generate_screen(session, screen, client_profile=profile.data)
│       ├─ _format_voice_examples(voice) → str
│       ├─ _format_glossary(glossary) → str
│       ├─ load_prompt("screen_documentation", version="v3", ...) → str
│       ├─ _compute_hash(PROMPT_VERSION, prompt) → content_hash
│       ├─ [cache check] → if hash matches, skip LLM
│       ├─ provider.chat_json(prompt, schema=ScreenDocResponse, images=...)
│       │   ├─ provider.chat_vision(prompt, images) | provider.chat(prompt)
│       │   ├─ _strip_fences(raw) → text
│       │   ├─ json.loads(text) → data
│       │   └─ ScreenDocResponse.model_validate(data)  [retry once on error]
│       ├─ _log_prompt() + _log_response() → llm/ directory
│       └─ _merge_result_into_screen(screen, result, content_hash)
│
├─ SessionStore.save(session, latest_session)
├─ LOOP: write legacy screen_N_*.json files
│
├─ open_review_ui(latest_session, screen_index=1)
│   └─ ReviewSessionUI(root, session_dir, initial_idx)
│       └─ [blocking Tkinter window — writer edits content]
│
├─ bot_labeler.generate_module_intro(latest_session, module_name, module_number)
│   └─ generator.generate_module_intro(session)
│       └─ provider.chat_json(module_intro prompt, schema=ModuleIntroResponse)
│
└─ assemble_module(latest_session)
    ├─ load_manifest(client_key) → ManifestConfig
    ├─ load_style(client_key) → StyleConfig
    ├─ NumberingTracker(style, mode)
    ├─ GenericBuilder(manifest, style, numbering)
    │   ├─ _setup_styles() [page, Normal, Headings, Caption styles]
    │   └─ build_module(session_dir)
    │       └─ render_module(doc, session_dir, style, numbering)
    │           ├─ render_annotations(session_dir, screen_index)
    │           │   └─ Pillow: open PNG, draw boxes/callouts, save _annotated.png
    │           └─ render_screen(doc, screen_index, session_dir, content, meta, style, numbering)
    │               ├─ add_styled_heading (screen name, level 2)
    │               ├─ add_body_paragraph (purpose)
    │               ├─ path breadcrumb run
    │               ├─ navigation instruction paragraph
    │               ├─ _add_image_with_border (screenshot in 1×1 border table)
    │               ├─ add_caption (Figure N: Name)
    │               ├─ render_field_table | bullet fields
    │               ├─ steps (List Bullet paragraphs with **bold** markers)
    │               └─ notes paragraphs
    ├─ builder.save(output_docx) → Final_Manuals/*.docx
    ├─ validate_ooxml_structure(output_docx)
    └─ run_qa_check(output_docx)
        └─ LibreOffice soffice --headless --convert-to pdf (optional)
```

---

## 7. Runtime Flow

| Step | Actor | Action |
|---|---|---|
| 1 | Writer | Runs `python ui/launcher.py` |
| 2 | LauncherUI | Tkinter window opens; writer selects client, provider, URL, module name |
| 3 | LauncherUI | Calls `run_pipeline()`; window iconifies |
| 4 | CaptureSession | Opens headed Chromium, navigates to start URL |
| 5 | Writer | Navigates target application, performs actions |
| 6 | injected.js | Records every click/input/change/navigate event |
| 7 | Writer | Middle-clicks to capture a screen |
| 8 | CaptureSession | Captures viewport PNG, extracts DOM elements |
| 9 | Writer | Double middle-clicks to quit capture |
| 10 | CaptureSession | Saves auth state, closes browser, saves `session.json` |
| 11 | main.py | Loads session, runs region detection and step compilation |
| 12 | Generator | Calls LLM for each screen (with progress window) |
| 13 | main.py | Saves session, writes legacy JSON files |
| 14 | ReviewSessionUI | Opens Tkinter editor; writer reviews/edits content |
| 15 | Writer | Closes Review UI |
| 16 | Labeler | Generates module introduction via LLM |
| 17 | assemble_module | GenericBuilder creates `*.docx` → `Final_Manuals/` |
| 18 | qa.py | OOXML structural validation; LibreOffice PDF (if installed) |
| 19 | LauncherUI | Shows success dialog; `Final_Manuals/` folder opens |
| 20 | Writer | Uses LauncherUI to select sessions and assemble master manual |

---

## 8. Data Flow

```
Playwright Browser
  ├── Screenshots (PNG files) ──────────────────────────────────────────────────┐
  └── DOM Extraction (JS)                                                        │
        └── Elements[] (BBox, tag, role, name, …)                               │
        └── Events[] (click, input, navigate, …)                                │
              │                                                                  │
              ▼                                                                  │
         SessionModel (session.json)                                             │
              ├── SessionStore.save() ─── sessions/<dir>/session.json            │
              │                                                                  │
              ├── detect_regions(elements) → Region[]                            │
              ├── compile_steps(events) → Step[] (skeleton)                      │
              │                                                                  │
              ├── Generator.generate_screen() ────────────────────┐              │
              │     Prompt inputs:                                 │              │
              │       url, title, h1, elements[], regions[],       │              │
              │       events[], voice, glossary, field_style       │              │
              │                                LLM call            │              │
              │     ScreenDocResponse:          ─────────────────► │              │
              │       screen_name, purpose,                        │              │
              │       navigation_sentence,                         │              │
              │       region_labels[], field_details[],            │              │
              │       steps[], notes[]           ◄─────────────── │              │
              │                                                     │              │
              ├── Merged back into Screen.content / fields / regions              │
              │                                                                  │
              ├── Legacy JSON export:                                             │
              │     screen_N_meta.json                                            │
              │     screen_N_elements.json                                        │
              │     screen_N_regions.json                                         │
              │     screen_N_content.json                                         │
              │                                                                  │
              └── ReviewSessionUI (edit session in place)                        │
                                                                                 │
         docbot.processing.annotate.render_annotations()                         │
              Reads: screen_N_regions.json + screen_N.png  ◄────────────────────┘
              Writes: screen_N_annotated.png
                │
                ▼
         manual_builder.renderers.screen.render_screen()
              Reads: screen_N_content.json + screen_N_annotated.png
                │
                ▼
         GenericBuilder.save() → Final_Manuals/<client>_<system>_v<ver>.docx
```

---

## 9. Configuration Files

| File | Format | Runtime-editable? | Purpose |
|---|---|---|---|
| `config.yaml` | YAML | Yes (UI saves back) | Provider, client, dirs, render params |
| `.env` | dotenv | Manual | API keys for LLM providers |
| `clients/<key>/manifest.yaml` | YAML | Via text editor | Client name, system, version, sections |
| `clients/<key>/style.yaml` | YAML | Via StyleEditorDialog | Fonts, colors, margins, annotations mode |
| `clients/<key>/voice.yaml` | YAML | Via text editor | Tone rules, example sentences, nav template |
| `clients/<key>/glossary.yaml` | YAML | Via text editor | Domain terms |
| `clients/<key>/content/revision_history.yaml` | YAML | Via text editor | Document change log |
| `prompts/v3/*.txt` | Text | Manual | LLM prompt templates with `{placeholders}` |
| `sessions/state/<client>.json` | JSON | Auto (Playwright) | Saved browser auth state (cookies/localStorage) |

---

## 10. Environment Variables

| Variable | Required for | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | `provider: anthropic` | Authenticates to Anthropic Messages API |
| `OPENAI_API_KEY` | `provider: openai_compat` | Authenticates to OpenAI / Groq / Together AI |
| `OLLAMA_API_KEY` | `provider: ollama` (cloud) | Authenticates to Ollama cloud endpoint |

> [!CAUTION]
> The `.env.example` warns that a **previous git commit exposed an Ollama API key**. If you have access to the git history, treat any such key as compromised and rotate it immediately via your provider's dashboard.

---

## 11. Third-Party Integrations

| Library | Version | Role in System |
|---|---|---|
| `playwright==1.52.0` | Pinned | Headed Chromium for web capture; JS injection; event recording |
| `python-docx==1.1.2` | Pinned | Word document creation, paragraph/run/table manipulation |
| `pydantic>=2.0,<3` | Flexible | Data validation for all session models, config, LLM responses |
| `PyYAML>=6.0,<7` | Flexible | Parsing all YAML configuration files |
| `python-dotenv>=1.0,<2` | Flexible | Loading `.env` for API key injection |
| `httpx>=0.28,<1` | Flexible | HTTP client used by Ollama and OpenAI-compat providers |
| `Pillow>=10.0,<13` | Flexible | Screenshot annotation (callout bubbles, bounding boxes, badges) |
| `loguru>=0.7,<1` | Flexible | Structured logging to console (coloured) and per-session file |
| `pytest>=8.0,<9` | Dev | Test runner |
| `tkinter` (stdlib) | stdlib | Desktop GUI (Launcher, Review UI, Style Editor) |
| `lxml` | Implicit via docx | OOXML XML validation in `qa.py` |
| `LibreOffice soffice` | System/Optional | PDF generation for QA; rasterisation |
| `fitz` / `pdf2image` | System/Optional | PDF page rasterisation for visual QA |

---

## 12. Authentication Flow

DocBot **does not implement its own authentication**. It manages authentication for the **target application** being documented:

```
First run (no saved state):
  1. Playwright opens fresh unauthenticated browser context
  2. Writer manually logs into target application
  3. After session ends → context.storage_state() → sessions/state/<client>.json

Subsequent runs (saved state exists):
  1. Playwright opens context with storage_state=<client>.json
  2. Cookies/localStorage restore → writer already logged in
  3. If state expired → logged out; writer logs in again → state overwritten
```

**LLM API authentication:**
- Keys are read from environment variables at call time via `config.get_api_key()`
- Keys are **never stored** in session data, models, or logs
- The `Config` object only stores the *name* of the environment variable (`api_key_env`), not the key value

---

## 13. Background Jobs

DocBot is a **single-process, synchronous application** with no background queues, async tasks, or scheduled jobs.

The only concurrency is:

| Mechanism | Where | Purpose |
|---|---|---|
| `threading.Lock` | `docbot.recorder.capture.CaptureSession` | Protects `_state` dict from simultaneous writes by Playwright callbacks and the main polling loop |
| Tkinter event loop | `ui/launcher.py`, `ui/review.py` | Tkinter's mainloop runs all GUI updates |
| Manual `update()` calls | `main.py` loading window | Forces Tkinter to refresh the progress window during AI generation (blocking loop) |

There is no Celery, asyncio, threading for the pipeline proper, or any background file watcher.
