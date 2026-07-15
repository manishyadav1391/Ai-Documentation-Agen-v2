"""
detect_regions.py — v3 import shim.

The region detection implementation has moved to
``docbot.processing.regions``.  This module re-exports the orchestrator
function for backward compatibility with main.py and any external callers.

Deprecated: Will be removed in Phase 7.
"""

import warnings
warnings.warn(
    "detect_regions.py is a compatibility shim. "
    "Import from docbot.processing.regions instead.",
    DeprecationWarning,
    stacklevel=2,
)

from docbot.processing.regions import (  # noqa: F401 E402
    process_screen_regions,
    detect_regions,
)