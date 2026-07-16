# CONTRIBUTING.md — DocBot v3

> Developer guide for contributors.

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- Windows (for the full UI stack) or any platform for library development
- At least one LLM API key, or use `provider: browser` for free manual mode

### Development Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd doc_automation_v2

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Install Playwright browser
playwright install chromium

# 5. Set up environment variables
copy .env.example .env
# Edit .env with your API keys
```

---

## Project Layout

```
docbot/             Core library — this is where most logic lives
  models.py         All Pydantic data models
  recorder/         Playwright capture engine
  processing/       Region detection, step compilation, AI generation, annotation
  export/           OOXML QA and Word helpers
  clients/          ClientProfile loader

manual_builder/     Word document builder (manifest-driven)
  renderers/        Per-section Word renderers

providers/          LLM provider adapters
  base.py           Abstract Provider class

ui/                 Tkinter desktop GUI
prompts/v3/         LLM prompt templates
clients/            Per-client YAML configuration
tests/              Pytest test suite
docs/               Additional documentation
```

---

## Running Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run a specific test file
pytest tests/test_regions.py -v

# Run a specific test function
pytest tests/test_steps.py::test_input_grouping -v

# Run with coverage (requires pytest-cov)
pytest tests/ --cov=docbot --cov=manual_builder --cov=providers
```

Tests should run without an LLM API key. All LLM calls are mocked in the test suite.

---

## Code Style

- **Type hints** are required on all public functions and class attributes.
- **Docstrings** (Google style) on all public functions, classes, and modules.
- **Loguru** for all logging — use `from loguru import logger`, never `print()` (except in `__main__` blocks).
- **Pydantic v2** for all data that crosses module boundaries.
- **Black** formatting (line length 100) — `pip install black && black .`
- **isort** import ordering — `pip install isort && isort .`

### Import Ordering

```python
# 1. Standard library
import json
from pathlib import Path

# 2. Third-party (alphabetical)
from loguru import logger
from pydantic import BaseModel

# 3. First-party (docbot.*, manual_builder.*, providers.*)
from docbot.models import SessionModel
```

---

## Adding a New LLM Provider

1. Create `providers/<name>.py`
2. Subclass `providers.base.Provider`
3. Implement `name`, `is_available()`, and `chat()`
4. Override `chat_vision()` if the provider supports image input
5. Register the provider in `config.py::_build_provider()` under a new key
6. Add provider config to `config.yaml` under `providers:`
7. Add a test in `tests/test_chat_json.py`

```python
from providers.base import Provider

class MyProvider(Provider):
    @property
    def name(self) -> str:
        return "MyProvider"

    def is_available(self) -> bool:
        return bool(os.getenv("MY_API_KEY"))

    def chat(self, prompt, *, max_tokens=8000, temperature=0.2, system=None) -> str:
        # Call the API and return the raw response string
        ...
```

---

## Adding a New Client

1. `mkdir clients/<client_key>`
2. Copy starter templates: `cp -r clients/_default/* clients/<client_key>/`
3. Edit the four YAML files:
   - `manifest.yaml` — client name, system name, version, sections list
   - `style.yaml` — fonts, colors, margins, annotation mode
   - `voice.yaml` — tone rules, example sentences
   - `glossary.yaml` — domain terms
4. Create `clients/<client_key>/content/revision_history.yaml` with at least one entry
5. Set `current_client: <client_key>` in `config.yaml`
6. Run the pipeline to verify

---

## Adding a New Document Section Type

1. Add the renderer in `manual_builder/renderers/<type_name>.py`
2. Implement `render_<type_name>(doc, section, manifest, style, **kwargs) -> None`
3. Import and register in `manual_builder/generic_builder.py::dispatch_section()`
4. Add the new type string to the `elif stype == ...` chain
5. Document the YAML schema for this section type in `docs/manifest_reference.md`

---

## Session Model Changes

When adding or modifying fields in `docbot/models.py`:

1. Add the field with a **default value** to ensure backward compatibility with existing `session.json` files.
2. If removing a field, add a `@model_validator(mode="before")` to strip it on load (legacy migration).
3. Bump `SCHEMA_VERSION` in `SessionModel` if the change is breaking.
4. Update `tests/` fixtures if they use the affected fields.
5. Update `docs/01_codebase_analysis_report.md` to reflect the model change.

---

## Prompt Engineering

LLM prompt templates are in `prompts/v3/`. They use `{placeholder}` substitution (not Jinja2 — just Python `str.replace()`).

When modifying prompts:
1. Increment the `PROMPT_VERSION` constant in `docbot/processing/generator.py`. This invalidates the content-hash cache, forcing all screens to be regenerated.
2. Test with at least 3 different screen types (form, table, navigation-only).
3. Verify that all `{placeholder}` names match the keyword arguments passed to `load_prompt()`.

---

## Pull Request Checklist

Before submitting a PR:

- [ ] All existing tests pass: `pytest tests/ -v`
- [ ] New functionality has tests
- [ ] Type hints added to all new public functions/methods
- [ ] Docstrings updated or added
- [ ] No `print()` statements in library code (use `logger.info/debug/warning`)
- [ ] No hardcoded paths or credentials
- [ ] `ARCHITECTURE.md` updated if the architecture changed
- [ ] `docs/` updated if new configuration options were added

---

## Security Guidelines

- **Never commit API keys** — use `.env` and environment variables
- **Never log API keys** — loguru format strings must not include provider credentials
- **Sanitise file paths** — any path derived from session data must be validated to be within the session directory
- **Validate LLM output** — always use `chat_json()` with a Pydantic schema rather than parsing raw text
- **Check `is_relative_to()`** — before opening any file whose path comes from `session.json` or `content.json`

---

## Common Pitfalls

### Tkinter + Threads

Never call Tkinter widget methods from a background thread. Use `root.after(0, callback)` or a `queue.Queue` to relay results back to the main thread.

### Playwright + `sync_playwright`

Playwright's `sync_playwright` context manager must be used inside the same thread that created it. Do not pass `Page` or `Browser` objects between threads.

### Pydantic v2 vs v1

This project uses **Pydantic v2**. Use `.model_validate()` not `.parse_obj()`, and `.model_dump()` not `.dict()`.

### `session._session_dir`

The private `_session_dir` attribute is set after construction by `SessionStore.load()` and `run_capture_session()`. Do not construct `SessionModel` directly and then access `_session_dir` — it will be `None`.
