# Dead Code Detection Report — DocBot v3

> **Project:** `c:\doc_automation_v2`
> **Analyzed:** 2026-07-16

---

## Table of Contents

1. [Deprecated Compatibility Shims](#1-deprecated-compatibility-shims)
2. [Orphaned Files](#2-orphaned-files)
3. [Duplicate / Redundant Logic](#3-duplicate--redundant-logic)
4. [Commented-Out Code & Debug Artifacts](#4-commented-out-code--debug-artifacts)
5. [Obsolete Assets](#5-obsolete-assets)
6. [Unused Dependencies](#6-unused-dependencies)
7. [Circular Dependency Check](#7-circular-dependency-check)
8. [Summary Table](#8-summary-table)

---

## 1. Deprecated Compatibility Shims

These root-level files exist solely to re-export from their new `docbot.*` locations. Each file emits a `DeprecationWarning` at import time and has a docstring saying it will be removed in Phase 7/8. They add noise on every pipeline run.

---

### `capture.py`

| Attribute | Value |
|---|---|
| **File** | `c:\doc_automation_v2\capture.py` |
| **Why unused** | Shim re-exporting `run_capture_session` / `CaptureSession` from `docbot.recorder.capture`. The only caller is `main.py` (line 21: `from capture import run_capture_session`). |
| **Evidence** | File docstring: *"Deprecated: Will be removed in Phase 7."* Emits `DeprecationWarning` at import. |
| **References** | `main.py:21` |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** — update `main.py` to import directly from `docbot.recorder.capture` |

---

### `annotate.py`

| Attribute | Value |
|---|---|
| **File** | `c:\doc_automation_v2\annotate.py` |
| **Why unused** | Shim re-exporting `render_annotations` from `docbot.processing.annotate`. |
| **Evidence** | File docstring: *"Deprecated: Will be removed in Phase 7."* Emits `DeprecationWarning`. |
| **References** | `main.py:25` |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** — update `main.py` import |

---

### `detect_regions.py`

| Attribute | Value |
|---|---|
| **File** | `c:\doc_automation_v2\detect_regions.py` |
| **Why unused** | Shim re-exporting `process_screen_regions` / `detect_regions` from `docbot.processing.regions`. |
| **Evidence** | File docstring: *"Deprecated: Will be removed in Phase 7."* Emits `DeprecationWarning`. |
| **References** | `main.py:22` (imported but `process_screen_regions` is never called from `main.py` — only `detect_regions` is called directly from the `docbot.*` namespace) |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** — the import `from detect_regions import process_screen_regions` on line 22 of `main.py` is actually dead (the function is never called in `main.py`); update the import. |

---

### `review_ui.py`

| Attribute | Value |
|---|---|
| **File** | `c:\doc_automation_v2\review_ui.py` |
| **Why unused** | Shim re-exporting `open_review_ui` from `ui.review`. |
| **Evidence** | File docstring: *"Deprecated: Will be removed in Phase 8."* Emits `DeprecationWarning`. |
| **References** | `main.py:24` |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** — update `main.py` import |

---

### `labeler.py`

| Attribute | Value |
|---|---|
| **File** | `c:\doc_automation_v2\labeler.py` |
| **Why unused** | `Labeler` class is a shim adapter around `Generator`. File emits `DeprecationWarning` at module import, and warns again in `__init__`. |
| **Evidence** | File docstring: *"Deprecated: Will be removed in Phase 7."* Module-level `warnings.warn()` call. |
| **References** | `main.py:23, 61, 264` — creates `Labeler(provider)` and calls `generate_module_intro` |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** — replace the three `Labeler` usages in `main.py` with direct `Generator` calls. The `generate_module_intro` method on `Generator` is already available (`generator.generate_module_intro(session, client_profile=...)`). |

---

## 2. Orphaned Files

### `llm_ui.py`

| Attribute | Value |
|---|---|
| **File** | `c:\doc_automation_v2\llm_ui.py` |
| **Why unused** | A 7 KB standalone LLM UI script. Not imported by any other module. Not referenced in `requirements.txt`, `README.md`, or any other file. |
| **Evidence** | No `import llm_ui` or `from llm_ui import` found anywhere in the codebase. |
| **References** | None |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** (archive first if desired) |

---

### `manual_builder.zip`

| Attribute | Value |
|---|---|
| **File** | `c:\doc_automation_v2\manual_builder.zip` |
| **Why unused** | A 104 KB ZIP archive of an older version of `manual_builder/`. |
| **Evidence** | Binary ZIP file; no code imports it. The live `manual_builder/` package is the active version. |
| **References** | None |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** — move to a `/archive/` folder or delete. |

---

### `llm_prompt.txt`

| Attribute | Value |
|---|---|
| **File** | `c:\doc_automation_v2\llm_prompt.txt` |
| **Why unused** | A 185-byte text file containing a placeholder/test prompt. Not loaded by `load_prompt()` (which searches `prompts/v3/` and `providers/prompts/`). |
| **Evidence** | `providers/base.py::load_prompt()` searches `prompts/{version}/{name}.txt` and `providers/prompts/{name}.txt`. `llm_prompt.txt` is in neither location. |
| **References** | None |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** |

---

### `v3 changes` (plain-text file)

| Attribute | Value |
|---|---|
| **File** | `c:\doc_automation_v2\v3 changes` |
| **Why unused** | A plain-text changelog file (22 KB) with no extension. Not referenced anywhere. |
| **Evidence** | No import or reference in any code file. |
| **References** | None |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** — superseded by proper git commit history and `ARCHITECTURE.md` |

---

### `docbot/export/renderers/` (sub-package)

| Attribute | Value |
|---|---|
| **Directory** | `c:\doc_automation_v2\docbot\export\renderers\` |
| **Why flagged** | The `docbot/export/` directory contains a `renderers/` sub-folder. The main renderers live in `manual_builder/renderers/`. This sub-package may be a leftover of an earlier layout. |
| **Evidence** | `docbot/export/__init__.py` imports only `qa` and `word_fields`. No code in the pipeline imports from `docbot.export.renderers`. |
| **References** | None found |
| **Confidence** | **Medium** (need to confirm contents are empty or identical to `manual_builder/renderers/`) |
| **Safe to remove?** | **Verify first** |

---

## 3. Duplicate / Redundant Logic

### `assemble.py::assemble_master()` vs `master_assembler.py::assemble_master_manual()`

| Attribute | Value |
|---|---|
| **Files** | `c:\doc_automation_v2\assemble.py` (lines 83–120), `c:\doc_automation_v2\master_assembler.py` |
| **Why flagged** | Both functions build a master manual from multiple session directories. `assemble_master()` in `assemble.py` is nearly identical to `assemble_master_manual()` in `master_assembler.py`. |
| **Evidence** | Both: load manifest/style, create NumberingTracker, create GenericBuilder, call `build_full_manual()`, save `.docx`, run QA. |
| **References** | `ui/launcher.py` imports and calls `master_assembler.assemble_master_manual()`. `assemble.py::assemble_master()` has no callers. |
| **Confidence** | **High** — `assemble_master()` in `assemble.py` is dead code. |
| **Safe to remove?** | **Yes** — remove `assemble_master()` from `assemble.py`; keep `assemble_module()`. |

---

### `ManifestConfig.numbering_mode` vs `ClientProfile.numbering_mode`

| Attribute | Value |
|---|---|
| **Files** | `manual_builder/manifest_loader.py`, `docbot/clients/profile.py` |
| **Why flagged** | `numbering_mode` is read from manifest in both the `ManifestConfig` (via `getattr(manifest, "numbering_mode", ...)`) and `ClientProfile.numbering_mode` property. The value is loaded from the same YAML key. |
| **Evidence** | `assemble.py:49`, `master_assembler.py:30`, `assemble.py:100` all do `getattr(manifest, "numbering_mode", "module_prefixed")`. `ClientProfile.numbering_mode` at `profile.py:132` reads the same. |
| **Confidence** | **Low** — slight duplication, but acceptable since they serve different code paths. |
| **Safe to remove?** | **No** — acceptable design |

---

### `get_available_clients_v3()` in `ui/launcher.py` vs `get_available_clients()` in `manual_builder/manifest_loader.py`

| Attribute | Value |
|---|---|
| **Files** | `ui/launcher.py:30–41`, `manual_builder/manifest_loader.py:152–172` |
| **Why flagged** | Both scan `clients/` and `content/` for manifest files. The logic is nearly identical. |
| **Evidence** | `ui/launcher.py` defines its own `get_available_clients_v3()` instead of importing from `manifest_loader`. |
| **Confidence** | **Medium** |
| **Safe to remove?** | **Refactor opportunity** — not safe to silently remove, but `ui/launcher.py` should call `manifest_loader.get_available_clients()` |

---

## 4. Commented-Out Code & Debug Artifacts

### `main.py` — Unused import `process_screen_regions`

| Attribute | Value |
|---|---|
| **Location** | `main.py:22`: `from detect_regions import process_screen_regions` |
| **Why flagged** | `process_screen_regions` is never called in `main.py`. The pipeline uses `detect_regions()` (from `docbot.processing.regions`) directly. |
| **Confidence** | **High** |
| **Safe to remove?** | **Yes** — remove from `main.py` |

---

### `docbot/processing/generator.py` — Unused import `ScreenContent` in `_merge_result_into_screen`

| Attribute | Value |
|---|---|
| **Location** | `generator.py:374`: `from docbot.models import FieldDetail, Step, Region, ScreenContent` |
| **Why flagged** | `ScreenContent` is imported but not used in `_merge_result_into_screen`. The function modifies `screen.content` fields directly. |
| **Confidence** | **Medium** |
| **Safe to remove?** | **Yes** — remove `ScreenContent` from the import |

---

### `manual_builder/renderers/screen.py` — Hard-coded comment about `List Number` style

| Attribute | Value |
|---|---|
| **Location** | `screen.py:329–330`: Comment says `# Use bullet list instead of numbered list`, then uses `"List Bullet"`. |
| **Why flagged** | The F2 spec says "numbered list" but the implementation uses bullets. The comment reveals a spec/implementation discrepancy, not dead code per se, but misleading technical debt. |
| **Confidence** | **Low** |
| **Safe to remove?** | **Clarify spec** |

---

## 5. Obsolete Assets

### `providers/prompts/` (legacy v2 prompts)

| Attribute | Value |
|---|---|
| **Directory** | `c:\doc_automation_v2\providers\prompts\` |
| **Why flagged** | `load_prompt()` in `providers/base.py` searches `providers/prompts/{name}.txt` as a **fallback** after `prompts/v3/`. If any v3 template exists, the legacy version is never read. |
| **Evidence** | `providers/base.py:57–66` — fallback path only reached if `prompts/v3/{name}.txt` does not exist. |
| **Confidence** | **Medium** (if all prompt names exist under `prompts/v3/`) |
| **Safe to remove?** | **Verify** that `prompts/v3/screen_documentation.txt` and `prompts/v3/module_intro.txt` cover all cases first |

---

### `styles/` global YAML files

| Attribute | Value |
|---|---|
| **Directory** | `c:\doc_automation_v2\styles\` |
| **Why flagged** | Global `styles/<key>.yaml` files are superseded by per-client `clients/<key>/style.yaml`. `load_style()` in `manual_builder/style_loader.py` first checks `clients/<key>/style.yaml`. |
| **Evidence** | `style_loader.py` fallback chain: `clients/<key>/style.yaml` → `styles/<key>.yaml` → `styles/_default.yaml`. |
| **Confidence** | **Medium** — only flagged if all active clients have `clients/<key>/style.yaml`. |
| **Safe to remove?** | **Verify** all clients have their own `style.yaml` before removing `styles/ncb.yaml`, `styles/ncd.yaml`. Keep `styles/_default.yaml` as ultimate fallback. |

---

### `Instruction/` directory

| Attribute | Value |
|---|---|
| **Directory** | `c:\doc_automation_v2\Instruction\` |
| **Why flagged** | Directory of human-readable instruction documents. Not part of the code pipeline. |
| **Evidence** | No Python file imports from or writes to `Instruction/`. |
| **Confidence** | **Medium** |
| **Safe to remove?** | **No** — keep as reference documentation for operators |

---

## 6. Unused Dependencies

| Package | In `requirements.txt`? | Directly used? | Notes |
|---|---|---|---|
| `pytest` | Yes | In `tests/` only | Correct — dev dependency only, not needed in production runtime |
| `anthropic` SDK | **No** | Partially | `anthropic_api.py` uses raw `httpx` to call Anthropic directly, not the `anthropic` Python SDK. If the SDK is installed separately and not listed, it could cause version drift. |
| `lxml` | **No** | Yes (`docbot/export/qa.py`) | Used for `etree.fromstring()` in OOXML validation. Should be added to `requirements.txt`. |

> [!WARNING]
> **`lxml` is missing from `requirements.txt`** but is required by `docbot/export/qa.py`. The validation will fail silently or crash if lxml is not installed. Add `lxml>=4.9,<6` to `requirements.txt`.

---

## 7. Circular Dependency Check

No circular imports were detected. The dependency direction is strictly:

```
ui.* → main / master_assembler → docbot.* → providers.*
                                ↓
                         manual_builder.* → docbot.export.*
```

`docbot.models` is a leaf with no application-level imports, only stdlib. No module re-imports the caller.

---

## 8. Summary Table

| # | File / Item | Type | Confidence | Safe to Remove? |
|---|---|---|---|---|
| 1 | `capture.py` | Deprecated shim | **High** | **Yes** |
| 2 | `annotate.py` | Deprecated shim | **High** | **Yes** |
| 3 | `detect_regions.py` | Deprecated shim | **High** | **Yes** |
| 4 | `review_ui.py` | Deprecated shim | **High** | **Yes** |
| 5 | `labeler.py` | Deprecated shim | **High** | **Yes** |
| 6 | `llm_ui.py` | Orphaned file | **High** | **Yes** |
| 7 | `manual_builder.zip` | Orphaned archive | **High** | **Yes** |
| 8 | `llm_prompt.txt` | Orphaned file | **High** | **Yes** |
| 9 | `v3 changes` | Orphaned file | **High** | **Yes** |
| 10 | `assemble.py::assemble_master()` | Dead function | **High** | **Yes** |
| 11 | `main.py:22` unused `process_screen_regions` import | Dead import | **High** | **Yes** |
| 12 | `generator.py:374` unused `ScreenContent` import | Dead import | **Medium** | **Yes** |
| 13 | `get_available_clients_v3()` duplicate | Duplication | **Medium** | Refactor |
| 14 | `providers/prompts/` | Legacy fallback | **Medium** | Verify first |
| 15 | `styles/ncb.yaml`, `styles/ncd.yaml` | Legacy fallback | **Medium** | Verify first |
| 16 | `docbot/export/renderers/` | Possibly empty | **Medium** | Verify first |
| 17 | Missing `lxml` in `requirements.txt` | Missing dep | **High** | **Add it** |
| 18 | `screen.py:329` comment mismatch | Tech debt | **Low** | Clarify |
