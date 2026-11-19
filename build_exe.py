"""Build the DocBot Windows distribution folder for the Inno Setup installer.

    python build_exe.py              full build (recommended)
    python build_exe.py --no-browser skip staging Chromium (smaller, users download it on first recording)

Steps
  1. Create / update the clean build environment .buildenv (requirements.txt + PyInstaller).
     Building from a global Python bundles every installed package; this keeps the
     output to DocBot's real dependencies.
  2. Run PyInstaller with docbot.spec  ->  dist\\DocBot\\DocBot.exe
  3. Stage the Chromium build that matches the bundled Playwright in dist\\DocBot\\browsers
     (copied from the local Playwright cache, or downloaded).
  4. Copy the user manual to dist\\DocBot\\docs.
  5. Run "DocBot.exe --selftest" against a throw-away workspace; the build fails if any check fails.

Afterwards compile installer\\DocBot.iss with Inno Setup.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".buildenv"
VPY = VENV / "Scripts" / "python.exe"
DIST = ROOT / "dist" / "DocBot"


def run(cmd, **kw):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def step(msg):
    print(f"\n=== {msg} ===", flush=True)


def ensure_venv():
    step("1/5 Build environment")
    if not VPY.exists():
        run([sys.executable, "-m", "venv", VENV])
    run([VPY, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    run([VPY, "-m", "pip", "install", "-q", "-r", ROOT / "requirements.txt", "pyinstaller"])


def pyinstaller():
    step("2/5 PyInstaller")
    for d in (ROOT / "build", ROOT / "dist"):
        shutil.rmtree(d, ignore_errors=True)
    run([VPY, "-m", "PyInstaller", "--clean", "--noconfirm", "docbot.spec"], cwd=ROOT)
    if not (DIST / "DocBot.exe").exists():
        sys.exit("PyInstaller did not produce dist\\DocBot\\DocBot.exe")


def chromium_dirname() -> str:
    out = subprocess.run([str(VPY), "-c",
                          "import json,pathlib,playwright;"
                          "p=pathlib.Path(playwright.__file__).parent/'driver'/'package'/'browsers.json';"
                          "print([b['revision'] for b in json.loads(p.read_text())['browsers'] if b['name']=='chromium'][0])"],
                         check=True, capture_output=True, text=True).stdout.strip()
    return f"chromium-{out}"


def stage_browser():
    step("3/5 Chromium")
    name = chromium_dirname()
    target = DIST / "browsers"
    target.mkdir(parents=True, exist_ok=True)
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    for src in (local / "ms-playwright" / name, ROOT / "browsers" / name):
        if (src / "INSTALLATION_COMPLETE").exists() and any(src.glob("**/chrome.exe")):
            print(f"copying {src} -> {target / name}")
            shutil.copytree(src, target / name)
            break
    else:
        env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(target))
        run([VPY, "-m", "playwright", "install", "chromium"], env=env)
        # only the headed browser is needed by the recorder
        for extra in target.iterdir():
            if extra.name != name:
                shutil.rmtree(extra, ignore_errors=True) if extra.is_dir() else extra.unlink()
    if not any((target / name).glob("**/chrome.exe")):
        sys.exit(f"Chromium staging failed: {target / name}")


def copy_docs():
    step("4/5 Documentation")
    docs = DIST / "docs"
    docs.mkdir(exist_ok=True)
    for f in ("DocBot_User_Manual_v1.1.docx",):
        src = ROOT / "docs" / f
        if src.exists():
            shutil.copy2(src, docs / f)
            print("copied", f)


def selftest():
    step("5/5 Self-test of the built exe")
    ws = ROOT / "build" / "selftest_ws"
    shutil.rmtree(ws, ignore_errors=True)
    env = dict(os.environ, DOCBOT_DATA_DIR=str(ws))
    env.pop("PLAYWRIGHT_BROWSERS_PATH", None)
    t0 = time.time()
    proc = subprocess.run([str(DIST / "DocBot.exe"), "--selftest"], env=env, timeout=600)
    log = ws / "selftest" / "selftest.log"
    print(log.read_text(encoding="utf-8") if log.exists() else "(no self-test log written)")
    print(f"exit code {proc.returncode} after {time.time() - t0:.0f}s")
    if proc.returncode != 0:
        sys.exit("Self-test FAILED - do not ship this build.")


def folder_size(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1024 / 1024


def main():
    no_browser = "--no-browser" in sys.argv
    ensure_venv()
    pyinstaller()
    if not no_browser:
        stage_browser()
    copy_docs()
    if not no_browser:
        selftest()
    step("Done")
    print(f"dist\\DocBot: {folder_size(DIST):.0f} MB "
          f"(application {folder_size(DIST / '_internal'):.0f} MB)")
    print("Next: compile installer\\DocBot.iss with Inno Setup 6.")


if __name__ == "__main__":
    main()
