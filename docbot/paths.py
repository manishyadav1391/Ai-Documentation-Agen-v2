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

def data_dir() -> Path:
    """User-writable workspace: config, clients, sessions, outputs, logs."""
    if is_frozen():
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
                    shutil.copy2(src, dst)
    for d in (sessions_dir(), outputs_dir(), logs_dir()):
        d.mkdir(parents=True, exist_ok=True)
