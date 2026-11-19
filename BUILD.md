# Building the DocBot installer

The result is one installer, `DocBot_Setup_<version>.exe`, that a user can run on any 64-bit Windows 10/11 PC.
Everything DocBot needs is inside it: the application, the Python runtime and libraries, the Chromium browser used
for recording, and the user manual. Nothing has to be installed separately and no internet connection is needed to
install. An internet connection is needed later only for AI generation (OpenRouter, Anthropic, ...).

## 1. Prerequisites (build PC only)

| Tool | Notes |
|---|---|
| Python 3.14 64-bit | Only used to create the clean build environment `.buildenv`. |
| Inno Setup 6 | <https://jrsoftware.org/isinfo.php> |
| Chromium for Playwright 1.58 | Optional. `build_exe.py` copies it from `%LOCALAPPDATA%\ms-playwright\chromium-1208` if present, otherwise downloads it. |

## 2. Build the application folder

```bat
build.bat
```

`build.bat` runs `build_exe.py`, which:

1. creates or updates **`.buildenv`**, a clean virtual environment with only `requirements.txt` and PyInstaller
   (building from the global Python bundles every installed package and gave a 1.4 GB folder);
2. runs PyInstaller with `docbot.spec` and writes `dist\DocBot\DocBot.exe`;
3. copies the Chromium build that matches the bundled Playwright into `dist\DocBot\browsers`;
4. copies the user manual into `dist\DocBot\docs`;
5. runs **`DocBot.exe --selftest`** against a throw-away workspace. The build stops if any check fails.

Expected result: about 150 MB of application plus about 400 MB of Chromium (the installer compresses this to
roughly 200 MB).

`build.bat --no-browser` skips step 3 and 5. The installer is then smaller, and DocBot downloads Chromium
(about 150 MB) the first time the user starts a recording.

## 3. Compile the installer

Open `installer\DocBot.iss` in Inno Setup and click **Compile**, or run:

```bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DocBot.iss
```

Output: `installer\Output\DocBot_Setup_3.1.0.exe`. Change `MyAppVersion` in `DocBot.iss` (and `DOCBOT_VERSION`
for the exe's version information) for a new release.

## 4. What the installer does

* Installs per user by default (no administrator rights); the first page offers "Install for all users".
* Creates Start-menu entries: **DocBot**, **DocBot User Manual**, **DocBot Installation Check**, Uninstall; optional desktop icon.
* Removes the previous version's program files on upgrade.
* Never installs API keys: the user enters them in the Welcome Wizard or Settings.

At first start DocBot creates the user's workspace in `%LOCALAPPDATA%\DocBot` (config, client profiles, sessions,
Final_Manuals, logs, secrets.yaml) and shows the Welcome Wizard.
On uninstall the user is asked whether to delete that workspace; the default keeps it.

## 5. Checking an installed copy

Start menu > **DocBot Installation Check** runs the same self-test and opens the result
(`%LOCALAPPDATA%\DocBot\selftest\selftest.log`). It checks bundled files, libraries, Tk, configuration, client
profiles, launches Chromium with the recorder script, and builds a one-page Word module. It does not contact any
AI provider.

## Troubleshooting

| Problem | Fix |
|---|---|
| Build stops at "Self-test FAILED" | Read the log printed above it; each failing check names the missing file or library. |
| `ModuleNotFoundError` when DocBot starts | Add the module to `hiddenimports` in `docbot.spec` and rebuild. |
| Antivirus flags DocBot.exe | UPX is disabled in the spec to avoid this; sign the exe and installer with a code-signing certificate for distribution. |
| "Browser Download Required" on a user PC | The installer was built with `--no-browser`; let DocBot download it, or rebuild without that option. |
