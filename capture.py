"""
capture.py — v3 import shim.

The capture implementation has moved to ``docbot.recorder.capture``.
This module re-exports ``run_capture_session`` for backward compatibility
with main.py and any external callers.

Deprecated: Will be removed in Phase 7.
"""

import warnings
warnings.warn(
    "capture.py is a compatibility shim. Import from docbot.recorder.capture instead.",
    DeprecationWarning,
    stacklevel=2,
)

from docbot.recorder.capture import run_capture_session, CaptureSession  # noqa: F401 E402