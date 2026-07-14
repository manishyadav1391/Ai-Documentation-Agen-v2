"""manual_builder.renderers — pluggable section renderers."""

from .cover import render_cover
from .revision_history import render_revision_history
from .toc import render_toc, render_table_of_tables, render_table_of_figures
from .prose import render_prose
from .bullet_list import render_bullet_list
from .icon_table import render_icon_table
from .group import render_group

__all__ = [
    "render_cover",
    "render_revision_history",
    "render_toc",
    "render_table_of_tables",
    "render_table_of_figures",
    "render_prose",
    "render_bullet_list",
    "render_icon_table",
    "render_group",
]
