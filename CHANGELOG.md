# CHANGELOG.md — DocBot v3

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v3.x — Current] — In Development

### Added
- `callout_x` / `callout_y` fields on `Region` model — manual callout positioning in review UI
- Draggable callout bubbles in `ReviewSessionUI` (8 resize handles + move/draw/callout drag modes)
- Handle-based region box editing (resize any of 8 handles, drag to move)
- Right-click context menu (edit / delete / reset callout) on regions
- Arrow key nudge for selected region (Shift+Arrows = resize)
- `Ctrl+Z` undo stack for move/resize/callout/draw/delete operations
- Live cursor position and selected region info in status bar
- Per-session `run.log` file via `docbot.logging_setup.attach_session_log()`
- `validate_deliverable()` in `docbot/export/qa.py` — full H1–H7 QA check suite
- `validate_ooxml_structure()` — verifies `fldChar`/`instrText` are never bare children of `<w:p>`
- `NumberingTracker.mode = "continuous"` for NCD-style sequential figure numbering
- `clients/<key>/` directory structure for per-client manifest/style/voice/glossary configuration
- `ClientProfile.load()` — unified loader for all four per-client YAML files
- Module-level section numbering in `NumberingTracker.enter_section()`
- `render_field_table()` — field details as a styled Word table (alternative to bullet list)
- `_add_image_with_border()` in `screen.py` — screenshots wrapped in a 1×1 table with 0.5pt border
- `_strip_fences()` in `providers/base.py` — strips markdown code fences from LLM output
- Content-hash caching in `Generator.generate_screen()` — skips LLM if inputs unchanged
- `llm/` directory per session for prompt+response debugging logs
- `docbot/processing/steps.py` — deterministic step compiler (no LLM)
- `assemble.py::assemble_module()` — single-module Word preview
- `master_assembler.py::assemble_master_manual()` — multi-session master manual

### Changed
- Core implementation moved from root-level files to `docbot.*` package (v2→v3 migration)
- `Labeler` replaced by `Generator` as primary AI generation class
- `process_screen_regions()` replaced by `detect_regions()` + `process_screen_regions()` wrapper
- Screen content now stored in `session.json` (`screen.content`) rather than flat `screen_N_content.json` only
- Provider interface standardised: `chat()` → `chat_vision()` → `chat_json()` hierarchy
- Prompt templates moved from `providers/prompts/` to `prompts/v3/`

### Deprecated
- `capture.py` root-level shim (use `docbot.recorder.capture` directly)
- `annotate.py` root-level shim (use `docbot.processing.annotate` directly)
- `detect_regions.py` root-level shim (use `docbot.processing.regions` directly)
- `review_ui.py` root-level shim (use `ui.review` directly)
- `labeler.py` shim class (use `docbot.processing.generator.Generator` directly)

---

## [v2.x — Legacy]

### Key Features (v2)
- Browser-based capture using Playwright
- `Labeler` class for LLM-based region labelling and documentation generation
- Flat JSON file storage per screen (`screen_N_meta.json`, `screen_N_content.json`, etc.)
- Word document assembly using `manual_builder` (first generation)
- Providers: Anthropic, OpenAI-compatible, Ollama, Browser copy-paste

---

## Security Notes

- **2026-07**: An Ollama API key was inadvertently committed to the repository in a previous version. All affected credentials have been rotated. See `.env.example` for the security notice.
