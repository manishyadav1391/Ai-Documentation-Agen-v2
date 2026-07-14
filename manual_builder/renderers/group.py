"""Group section renderer (for section grouping)."""

from manual_builder.utils import add_styled_heading


def render_group(doc, section_entry, manifest, style, builder_dispatch_func):
    """
    Renders a group heading and recursively dispatches its subsections.
    Useful for sections like SOP that group buttons, icons, and calendar together.
    """
    # Render heading
    if section_entry.heading:
        add_styled_heading(doc, section_entry.heading, level=1, style_config=style)

    # Process subsections
    for sub in section_entry.subsections:
        builder_dispatch_func(sub)
