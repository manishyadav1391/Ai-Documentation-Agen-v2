"""Central path resolution for source-run and PyInstaller-frozen modes."""
import os
import sys
import shutil
from pathlib import Path

APP_NAME = "DocBot"

def is_frozen() -> bool:
    return getattr(sys, "frozen", False)

def bundle_dir() -> Path:
    """Read-only resources shipped with the app (prompts, default clients)."""
    if is_frozen():
        return Path(sys._MEIPASS)          # onefile/onedir
    return Path(__file__).resolve().parent.parent   # repo root

def app_dir() -> Path:
    """Folder holding DocBot.exe (frozen) or the repo root (source run)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return bundle_dir()

def bundled_browsers_dir() -> Path:
    """Chromium shipped next to the exe by the installer (may not exist)."""
    return app_dir() / "browsers"

def data_dir() -> Path:
    """User-writable workspace: config, clients, sessions, outputs, logs.

    Set the ``DOCBOT_DATA_DIR`` environment variable to point DocBot at a
    different workspace (used for isolated test runs and for keeping separate
    workspaces side by side).
    """
    override = os.environ.get("DOCBOT_DATA_DIR", "").strip()
    if override:
        base = Path(override).expanduser().resolve()
    elif is_frozen():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    else:
        base = Path(__file__).resolve().parent.parent   # repo root in dev
    base.mkdir(parents=True, exist_ok=True)
    return base

# Convenience accessors — the rest of the codebase must ONLY use these:
def config_path()   -> Path: return data_dir() / "config.yaml"
def clients_dir()   -> Path: return data_dir() / "clients"
def content_dir()   -> Path: return data_dir() / "content"
def styles_dir()    -> Path: return data_dir() / "styles"
def sessions_dir()  -> Path: return data_dir() / "sessions"
def outputs_dir()   -> Path: return data_dir() / "Final_Manuals"
def logs_dir()      -> Path: return data_dir() / "logs"
def prompts_dir()   -> Path: return bundle_dir() / "prompts"      # read-only
def provider_prompts_dir() -> Path: return bundle_dir() / "providers" / "prompts"

def _seed_config(src: Path, dst: Path) -> None:
    """Copy the bundled config.yaml for a fresh install.

    The bundled file is the developer's working config, so per-machine state
    (first_run_done, saved window geometry) is reset; otherwise a new install
    would never show the Welcome Wizard.
    """
    try:
        import yaml
        data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("bundled config.yaml is not a mapping")
        data["first_run_done"] = False
        for k in ("window_geometry", "review_geometry"):
            data.pop(k, None)
        dst.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except Exception:
        shutil.copy2(src, dst)


def ensure_first_run() -> None:
    """On first launch of the frozen app, seed the data dir from bundled defaults."""
    seeds = [
        ("clients", clients_dir()),
        ("content", content_dir()),
        ("styles", styles_dir()),
        ("config.yaml", config_path()),
        ("USER_GUIDE.md", data_dir() / "USER_GUIDE.md"),
    ]
    for src_name, dst in seeds:
        src = bundle_dir() / src_name
        if src.exists():
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    item_dst = dst / item.name
                    if not item_dst.exists():
                        if item.is_dir():
                            shutil.copytree(item, item_dst)
                        else:
                            shutil.copy2(item, item_dst)
            else:
                if not dst.exists():
                    if src_name == "config.yaml":
                        _seed_config(src, dst)
                    else:
                        shutil.copy2(src, dst)
    for d in (sessions_dir(), outputs_dir(), logs_dir()):
        d.mkdir(parents=True, exist_ok=True)
