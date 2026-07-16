# Implementation Plan — Phase 7 Code Cleanup

> **Objective:** Remove all deprecated compatibility shims, dead files, and redundant code identified in the Phase 2 Dead Code Report. Update all callers to import from the correct `docbot.*` / `ui.*` locations. Fix the missing `lxml` dependency.

---

## Scope

This plan covers the following items from `docs/02_dead_code_report.md`:

| # | Item | Priority |
|---|---|---|
| 1 | Remove 5 deprecated root-level shims | High |
| 2 | Update `main.py` to import directly | High |
| 3 | Remove `assemble.py::assemble_master()` dead function | High |
| 4 | Remove orphaned files (`llm_ui.py`, `manual_builder.zip`, `llm_prompt.txt`, `v3 changes`) | High |
| 5 | Remove unused import `process_screen_regions` from `main.py` | High |
| 6 | Add `lxml` to `requirements.txt` | Critical |
| 7 | Refactor `get_available_clients_v3()` in `ui/launcher.py` | Medium |

---

## Changes

### 1. `requirements.txt` — Add missing `lxml`

**File:** [`requirements.txt`](file:///c:/doc_automation_v2/requirements.txt)

```diff
 playwright==1.52.0
 python-docx==1.1.2
 pydantic>=2.0,<3
 PyYAML>=6.0,<7
 python-dotenv>=1.0,<2
 httpx>=0.28,<1
 Pillow>=10.0,<13
 loguru>=0.7,<1
 pytest>=8.0,<9
+lxml>=4.9,<6
```

---

### 2. `main.py` — Update imports; remove shim calls

**File:** [`main.py`](file:///c:/doc_automation_v2/main.py)

Replace all shim imports with direct imports:

```diff
-from capture import run_capture_session
-from detect_regions import process_screen_regions
-from labeler import Labeler
-from review_ui import open_review_ui
-from annotate import render_annotations
+from docbot.recorder.capture import run_capture_session
+from docbot.processing.regions import detect_regions
+from docbot.processing.generator import Generator
+from ui.review import open_review_ui
+from docbot.processing.annotate import render_annotations
```

Replace `Labeler` usage with direct `Generator`:

```diff
-bot_labeler = Labeler(provider)
+generator = Generator(provider)
```

```diff
-bot_labeler.generate_module_intro(session_dir, module_name, module_number)
+generator.generate_module_intro(SessionStore.load(session_dir), client_profile=profile.data)
```

Remove unused import of `process_screen_regions`.

---

### 3. `assemble.py` — Remove dead `assemble_master()` function

**File:** [`assemble.py`](file:///c:/doc_automation_v2/assemble.py)

Remove lines 83–120 (`assemble_master()` function). Keep `assemble_module()` (lines 30–80).

The master assembly entrypoint is `master_assembler.assemble_master_manual()` which is called from `ui/launcher.py`.

---

### 4. `ui/launcher.py` — Remove duplicate `get_available_clients_v3()`

**File:** [`ui/launcher.py`](file:///c:/doc_automation_v2/ui/launcher.py)

```diff
-def get_available_clients_v3() -> list[str]:
-    """Scan clients/ and content/ directories for manifests."""
-    ...  # 12 lines of duplicated logic
-
+from manual_builder.manifest_loader import get_available_clients
```

Replace all calls to `get_available_clients_v3()` with `get_available_clients()`.

---

### 5. Delete shim files

Files to delete (after step 2 is complete and verified):

- `c:\doc_automation_v2\capture.py`
- `c:\doc_automation_v2\annotate.py`
- `c:\doc_automation_v2\detect_regions.py`
- `c:\doc_automation_v2\review_ui.py`
- `c:\doc_automation_v2\labeler.py`

---

### 6. Delete orphaned/artifact files

Files to delete:

- `c:\doc_automation_v2\llm_ui.py`
- `c:\doc_automation_v2\llm_prompt.txt`
- `c:\doc_automation_v2\v3 changes`

Files to archive or delete:

- `c:\doc_automation_v2\manual_builder.zip` — move to `archive/` or delete

---

## Verification Plan

### After each change, run:

```bash
# Full test suite must continue to pass
pytest tests/ -v

# Import test — no DeprecationWarning on import of main.py
python -c "import main; print('OK')"

# Verify assemble_module still works
python -c "from assemble import assemble_module; print('OK')"

# Verify master_assembler still works
python -c "from master_assembler import assemble_master_manual; print('OK')"

# Verify launcher imports correctly
python -c "from ui.launcher import LauncherUI; print('OK')"
```

### Smoke test (manual):

1. Run `python ui/launcher.py`
2. Verify the launcher opens without errors in the terminal
3. Verify no `DeprecationWarning` is printed to stderr
4. Verify the client dropdown populates correctly

---

## Rollback Plan

All changes are tracked in git. To revert:

```bash
git checkout -- main.py assemble.py ui/launcher.py requirements.txt
git checkout -- capture.py annotate.py detect_regions.py review_ui.py labeler.py
```

Deleted orphaned files (`llm_ui.py`, `llm_prompt.txt`, etc.) can be recovered from git history:

```bash
git checkout HEAD^ -- llm_ui.py
```

---

## Order of Execution

1. **Add `lxml` to `requirements.txt`** → `pip install lxml` → verify `qa.py` works
2. **Update `main.py`** imports (without deleting shims yet) → run all tests → confirm passing
3. **Delete shim files** → run all tests → confirm still passing
4. **Remove `assemble_master()`** from `assemble.py` → run all tests
5. **Refactor `get_available_clients_v3()`** in `ui/launcher.py` → smoke test launcher
6. **Delete orphaned files** → final test run
7. **Commit** with message: `feat: Phase 7 — remove deprecated shims and dead code`
