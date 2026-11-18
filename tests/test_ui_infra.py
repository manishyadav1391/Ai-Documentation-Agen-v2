"""Regression tests for launcher / workspace infrastructure fixes (Nov 2026 audit)."""
import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------
# First-run seeding: bundled config.yaml must not mark the wizard as done
# --------------------------------------------------------------------------
def test_seeded_config_resets_first_run(tmp_path, monkeypatch):
    from docbot import paths
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "config.yaml").write_text(yaml.safe_dump({
        "provider": "openrouter", "current_client": "ncb",
        "first_run_done": True, "window_geometry": "1900x1009+0+0", "review_geometry": "1x1+0+0",
    }), encoding="utf-8")
    data = tmp_path / "data"
    monkeypatch.setenv("DOCBOT_DATA_DIR", str(data))
    monkeypatch.setattr(paths, "bundle_dir", lambda: bundle)
    paths.ensure_first_run()
    seeded = yaml.safe_load((data / "config.yaml").read_text(encoding="utf-8"))
    assert seeded["first_run_done"] is False
    assert "window_geometry" not in seeded and "review_geometry" not in seeded
    assert seeded["provider"] == "openrouter"          # other settings kept


def test_seed_does_not_overwrite_existing_config(tmp_path, monkeypatch):
    from docbot import paths
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "config.yaml").write_text("first_run_done: true\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    (data / "config.yaml").write_text("first_run_done: true\nprovider: ollama\n", encoding="utf-8")
    monkeypatch.setenv("DOCBOT_DATA_DIR", str(data))
    monkeypatch.setattr(paths, "bundle_dir", lambda: bundle)
    paths.ensure_first_run()
    assert yaml.safe_load((data / "config.yaml").read_text())["provider"] == "ollama"


# --------------------------------------------------------------------------
# Chromium detection
# --------------------------------------------------------------------------
def _fake_chrome(base: Path, dirname: str):
    exe = base / dirname / "chrome-win64" / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCBOT_DATA_DIR", str(tmp_path / "data"))
    import ui.launcher as L
    return L


def test_chromium_found_in_default_ms_playwright(launcher, monkeypatch, tmp_path):
    local = tmp_path / "local"
    _fake_chrome(local / "ms-playwright", "chromium-9999")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(launcher, "_expected_chromium_dirname", lambda: "chromium-9999")
    assert launcher.check_chromium_exists() is True
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(local / "ms-playwright")


def test_chromium_wrong_revision_not_accepted(launcher, monkeypatch, tmp_path):
    local = tmp_path / "local"
    _fake_chrome(local / "ms-playwright", "chromium-1169")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(launcher, "_expected_chromium_dirname", lambda: "chromium-1208")
    assert launcher.check_chromium_exists() is False


def test_chromium_found_in_data_dir_browsers(launcher, monkeypatch, tmp_path):
    from docbot import paths
    _fake_chrome(paths.data_dir() / "browsers", "chromium-1208")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty"))
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(launcher, "_expected_chromium_dirname", lambda: "chromium-1208")
    assert launcher.check_chromium_exists() is True
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(paths.data_dir() / "browsers")


def test_expected_chromium_matches_installed_playwright(launcher):
    name = launcher._expected_chromium_dirname()
    assert name is None or name.startswith("chromium-")


# --------------------------------------------------------------------------
# Recordings view: client filter helper
# --------------------------------------------------------------------------
def test_recordings_norm_client():
    from ui.views.recordings import RecordingsView
    assert RecordingsView._norm_client(None) == ""
    assert RecordingsView._norm_client("default") == ""
    assert RecordingsView._norm_client(" ncb ") == "ncb"


# --------------------------------------------------------------------------
# Review window must not restyle the launcher's global ttk styles
# --------------------------------------------------------------------------
def test_review_setup_style_leaves_global_styles():
    import tkinter as tk
    from tkinter import ttk
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        root.withdraw()
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#123456")
        style.configure("Sidebar.TFrame", background="#654321")
        from ui.review import ReviewSessionUI
        ReviewSessionUI._setup_style(object.__new__(ReviewSessionUI))
        assert style.lookup("TFrame", "background") == "#123456"
        assert style.lookup("Sidebar.TFrame", "background") == "#654321"
        assert style.lookup("Review.Sidebar.TFrame", "background") == "#F1F5F9"
    finally:
        root.destroy()
