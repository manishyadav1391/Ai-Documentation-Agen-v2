import os
import sys
from pathlib import Path

# Add project root to sys.path to ensure absolute imports resolve correctly
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from docbot import paths


def _set_browsers_path():
    """Chromium shipped by the installer ({app}\\browsers) wins; otherwise the
    per-user download folder in the workspace. ui.launcher.check_chromium_exists
    also looks in %LOCALAPPDATA%\\ms-playwright and re-points the variable."""
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    bundled = paths.bundled_browsers_dir()
    if bundled.is_dir() and any(bundled.glob("chromium-*")):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)
    else:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(paths.data_dir() / "browsers")


_set_browsers_path()
paths.ensure_first_run()

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from docbot.selftest import main as selftest_main
        sys.exit(selftest_main())
    from ui.launcher import main
    main()
