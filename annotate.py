"""
annotate.py — v3 import shim.

Annotation implementation moved to docbot.processing.annotate.
Deprecated: Will be removed in Phase 7.
"""

import warnings
warnings.warn(
    "annotate.py is a compatibility shim. "
    "Import from docbot.processing.annotate instead.",
    DeprecationWarning,
    stacklevel=2,
)

from docbot.processing.annotate import render_annotations  # noqa: F401 E402