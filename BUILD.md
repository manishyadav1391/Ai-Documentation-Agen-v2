# Building DocBot for Windows

This guide describes how to compile the DocBot application into a standalone Windows executable.

## Prerequisites

1. **Python 3.10+** (64-bit recommended)
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

## Files Bundled

The PyInstaller configuration in [docbot.spec](file:///c:/doc_automation_v2/docbot.spec) bundles:
- `clients/_default/`: Templates for client identity, styles, and onboarding configurations.
- `providers/prompts/`: Prompt engineering system templates for LLM instruction generation.

## Execution / Compilation

To build the executable:
1. Double-click [build.bat](file:///c:/doc_automation_v2/build.bat) or run it from a PowerShell terminal:
   ```powershell
   .\build.bat
   ```
2. The compiled outputs will be generated under `dist/DocBot/`.
3. Launch the application by running `dist/DocBot/DocBot.exe`.

## Troubleshooting

### Missing Import Errors (ModuleNotFoundError)
If the application crashes on startup with a `ModuleNotFoundError` for a library:
1. Open [docbot.spec](file:///c:/doc_automation_v2/docbot.spec).
2. Locate the `hiddenimports` list.
3. Add the missing module name to the list (e.g., `'some_missing_package'`).
4. Re-run `build.bat`.

### Playwright Browser Binary Errors
If Playwright crashes stating "browser binary not found" in production:
- The first-run wizard in [ui/launcher.py](file:///c:/doc_automation_v2/ui/launcher.py) is designed to automatically detect missing binaries and download Chromium using a background subprocess.
- Ensure the user's internet connection is active during first-run.
- Alternatively, the user can configure a custom path to Chrome or Microsoft Edge by adding the `browser_executable_path` key inside `%LOCALAPPDATA%\DocBot\config.yaml` to bypass automatic download entirely.
