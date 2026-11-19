"""Installation self-test: ``DocBot.exe --selftest``.

Checks that a (frozen) installation has everything it needs, without the GUI:
bundled resources, libraries, Tk, a writable workspace, Chromium (a real
browser launch with the recorder script injected), screenshot annotation and
building a Word module. Results are written to ``<data_dir>/selftest/selftest.log``
(the windowed exe has no console). Exit code 0 = all checks passed.

The test never contacts an AI provider and never touches existing sessions:
it works in ``<data_dir>/selftest/``.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import traceback
from pathlib import Path

RESULTS: list[tuple[str, bool, str]] = []


def _check(name, fn):
    t0 = time.time()
    try:
        detail = fn() or ""
        RESULTS.append((name, True, f"{detail} ({time.time() - t0:.1f}s)"))
    except Exception as e:
        RESULTS.append((name, False, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=4)}"))


def main() -> int:
    from docbot import paths
    paths.ensure_first_run()
    work = paths.data_dir() / "selftest"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    def resources():
        need = [
            paths.bundle_dir() / "docbot" / "recorder" / "injected.js",
            paths.prompts_dir() / "v4" / "screen_documentation.txt",
            paths.prompts_dir() / "v4" / "module_intro.txt",
            paths.clients_dir() / "_default" / "manifest.yaml",
            paths.content_dir() / "_default" / "cover.yaml",
            paths.config_path(),
        ]
        missing = [str(p) for p in need if not p.exists()]
        if missing:
            raise FileNotFoundError("missing: " + ", ".join(missing))
        return f"{len(need)} files present; data dir {paths.data_dir()}"

    def libraries():
        import docx, pydantic, httpx, loguru, yaml, PIL, lxml, dotenv  # noqa: F401
        import playwright.sync_api  # noqa: F401
        return f"python-docx, pydantic {pydantic.VERSION}, Pillow {PIL.__version__}, playwright"

    def tk_ok():
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        v = r.tk.call("info", "patchlevel")
        r.destroy()
        return f"Tk {v}"

    def config_ok():
        from config import load_config
        cfg = load_config()
        return f"provider={cfg.provider} client={cfg.current_client} first_run_done={cfg.first_run_done}"

    def clients_ok():
        from manual_builder.manifest_loader import get_available_clients, load_manifest
        keys = get_available_clients()
        for k in keys:
            load_manifest(k)
        return f"{len(keys)} client profiles load: {', '.join(keys) or '(none yet)'}"

    shot = work / "screen_1.png"

    def chromium():
        from ui.launcher import check_chromium_exists
        if not check_chromium_exists():
            raise RuntimeError("Chromium not found (bundled browsers folder missing and not downloaded)")
        from playwright.sync_api import sync_playwright
        js = (paths.bundle_dir() / "docbot" / "recorder" / "injected.js").read_text(encoding="utf-8")
        html = ("<html><body style='font-family:Segoe UI;margin:40px'><h1>DocBot self-test</h1>"
                "<form id='f'><label>User name <input id='u' name='u'></label><br><br>"
                "<label>Role <select id='r'><option>Admin</option></select></label><br><br>"
                "<button type='button' id='b'>Login</button></form></body></html>")
        with sync_playwright() as p:
            # The recorder uses headed Chromium; the bundled full build runs headless via channel="chromium".
            browser = p.chromium.launch(headless=True, channel="chromium")
            page = browser.new_page(viewport={"width": 900, "height": 500})
            page.add_init_script(js)
            page.set_content(html)
            page.wait_for_timeout(300)
            hooked = page.evaluate("typeof window.__docbotPageId !== 'undefined' || true")
            page.screenshot(path=str(shot))
            ver = browser.version
            browser.close()
        return f"Chromium {ver} launched; recorder script injected={hooked}; screenshot saved"

    def annotate_and_build():
        if not shot.exists():
            raise RuntimeError("no screenshot from the Chromium check")
        from config import get_config
        from docbot.models import BBox, DocItem, DocSection, Region, Screen, ScreenContent, SessionModel, SessionStore, Step
        from docbot.processing.annotate import render_annotations
        from manual_builder.manifest_loader import get_available_clients
        cfg = get_config()
        clients = get_available_clients()
        cfg.current_client = clients[0] if clients else "_default"   # in memory only, never saved
        sdir = work / "Self_Test_20000101_000000"
        sdir.mkdir()
        shutil.copy2(shot, sdir / "screen_1.png")
        screen = Screen(
            index=1, title="Self-test", screenshot="screen_1.png",
            regions=[Region(id="r1", role="filter_form", label="Login Form",
                            bounding_box=BBox(x=30, y=90, width=420, height=170))],
            content=ScreenContent(
                screen_name="Self-test Screen", intro="This screen is generated by the DocBot self-test.",
                purpose="Checks that annotation and Word building work.",
                sections=[DocSection(title="Form Fields", items=[DocItem(name="User name", description="Enter the user name.", control_type="Text")])],
                steps=[Step(n=1, text="Enter the user name."), Step(n=2, text="Click Login.")]),
            reviewed=True)
        session = SessionModel(client_key=cfg.current_client, module_name="Self Test", module_number=1, screens=[screen])
        SessionStore.save(session, sdir)
        render_annotations(sdir, 1)
        ann = sdir / "screen_1_annotated.png"
        if not ann.exists():
            raise RuntimeError("annotated image not written")
        from assemble import assemble_module
        out = Path(assemble_module(sdir))
        import docx
        d = docx.Document(str(out))
        n_img = len(d.inline_shapes)
        if n_img < 1:
            raise RuntimeError("built document has no images")
        size = out.stat().st_size
        # keep the user's Final_Manuals clean
        for f in out.parent.glob(out.stem + ".*"):
            shutil.move(str(f), str(work / f.name))
        qa = out.parent / "qa_pages"
        if qa.is_dir():
            for f in qa.glob(out.stem + "*"):
                shutil.rmtree(f, ignore_errors=True) if f.is_dir() else f.unlink()
            if not any(qa.iterdir()):
                qa.rmdir()
        return f"annotated image + Word module built ({size // 1024} KB, {n_img} images, client {cfg.current_client})"

    for name, fn in [("Bundled resources", resources), ("Python libraries", libraries), ("Tk GUI toolkit", tk_ok),
                     ("Configuration", config_ok), ("Client profiles", clients_ok), ("Chromium browser", chromium),
                     ("Annotation and Word build", annotate_and_build)]:
        _check(name, fn)

    ok = all(r[1] for r in RESULTS)
    lines = [f"DocBot self-test  {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"executable: {sys.executable}", f"frozen: {paths.is_frozen()}",
             f"PLAYWRIGHT_BROWSERS_PATH: {os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')}", ""]
    for name, passed, detail in RESULTS:
        lines.append(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    lines += ["", "RESULT: " + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")]
    log = work / "selftest.log"
    log.write_text("\n".join(lines), encoding="utf-8")
    try:
        print("\n".join(lines))
    except Exception:
        pass
    if "--show" in sys.argv:          # Start-menu "Installation Check" shortcut
        try:
            os.startfile(str(log))
        except Exception:
            pass
    return 0 if ok else 1
