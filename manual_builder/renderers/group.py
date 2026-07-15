"""Group section renderer (for section grouping)."""

from manual_builder.utils import add_styled_heading


def render_group(doc, section_entry, manifest, style, builder_dispatch_func, heading_text: str = None):
    """
    Renders a group heading and recursively dispatches its subsections.
    Useful for sections like SOP that group buttons, icons, and calendar together.
    """
    # Render heading
    title = heading_text if heading_text is not None else section_entry.heading
    if title:
        add_styled_heading(doc, title, level=1, style_config=style)

    # Process subsections
    for sub in section_entry.subsections:
        builder_dispatch_func(sub)
