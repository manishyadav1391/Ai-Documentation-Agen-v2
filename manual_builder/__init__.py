"""
manual_builder — Generic manifest-driven document builder.

Replaces hard-coded corporate template logic with a config-driven system
that reads content from content/<client>/ and styles from styles/<client>.yaml.
"""

from .manifest_loader import load_manifest, ManifestConfig
from .style_loader import load_style, StyleConfig
from .numbering import NumberingTracker
from .generic_builder import GenericBuilder

__all__ = [
    "load_manifest",
    "ManifestConfig",
    "load_style",
    "StyleConfig",
    "NumberingTracker",
    "GenericBuilder",
]
