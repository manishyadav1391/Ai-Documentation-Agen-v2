"""
review_ui.py — v3 import shim.

The review UI implementation has moved to ``ui/review.py``.
This shim re-exports ``open_review_ui`` for backward compatibility.

Deprecated: Will be removed in Phase 8.
"""

import warnings
warnings.warn(
    "review_ui.py is a compatibility shim. Import from ui.review instead.",
    DeprecationWarning,
    stacklevel=2,
)

from ui.review import open_review_ui  # noqa: F401 E402