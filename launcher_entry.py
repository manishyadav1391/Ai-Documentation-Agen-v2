import os
import sys
from pathlib import Path

# Add project root to sys.path to ensure absolute imports resolve correctly
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from docbot import paths
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(paths.data_dir() / "browsers"))
paths.ensure_first_run()

from ui.launcher import main
if __name__ == "__main__":
    main()
