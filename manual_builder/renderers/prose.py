"""Prose (markdown) renderer."""

import re
from docx.shared import Pt
from manual_builder.utils import add_styled_heading, add_body_paragraph, hex_to_rgb, read_text_file, source_file

# Emphasis only at word boundaries: the opening marker must not follow a word
# character and must be followed by non-space; the closing marker mirrors that.
# A closing marker followed by ".ext" is part of a file name (__init__.py).
# So file_name_v2.txt, http://x/a_b_c, 2 * 3 * 4 and a*b stay literal.
_EMPHASIS_RE = re.compile(
    r"(?<![\w*])\*\*(?=\S)(?P<b1>.+?)(?<=\S)\*\*(?![\w*]|\.\w)"
    r"|(?<![\w_])__(?=\S)(?P<b2>.+?)(?<=\S)__(?![\w_]|\.\w)"
    r"|(?<![\w*])\*(?=[^\s*])(?P<i1>.+?)(?<=[^\s*])\*(?![\w*]|\.\w)"
    r"|(?<![\w_])_(?=[^\s_])(?P<i2>.+?)(?<=[^\s_])_(?![\w_]|\.\w)"
)


def _apply_inline_formatting(run_target, text, style, bold=False, italic=False):
    """Processes markdown bold/italic tags and adds formatted runs to a paragraph."""
    pos = 0
    for m in _EMPHASIS_RE.finditer(text):
        if m.start() > pos:
            _add_run(run_target, text[pos:m.start()], style, bold, italic)
        if m.group("b1") is not None or m.group("b2") is not None:
            inner = m.group("b1") if m.group("b1") is not None else m.group("b2")
            _apply_inline_formatting(run_target, inner, style, True, italic)
        else:
            inner = m.group("i1") if m.group("i1") is not None else m.group("i2")
            _apply_inline_formatting(run_target, inner, style, bold, True)
        pos = m.end()
    if pos < len(text):
        _add_run(run_target, text[pos:], style, bold, italic)


def _add_run(run_target, part, style, bold, italic):
    if not part:
        return
    r = run_target.add_run(part)
    r.font.name = style.body_font
    r.font.size = Pt(style.body_size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = hex_to_rgb(style.get_color("body_text"))


def render_prose(doc, section_entry, manifest, style, heading_text: str = None, heading_level: int = 1):
    """
    Reads a markdown file, parses headings, bullets, bold/italic, and renders to docx.
    """
    # 1. Heading
    title = heading_text if heading_text is not None else section_entry.heading
    if title:
        add_styled_heading(doc, title, level=heading_level, style_config=style)

    prose_path = source_file(section_entry, manifest, "prose")
    if prose_path is None:
        return

    content = read_text_file(prose_path)

    # Process line by line
    lines = content.splitlines()
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check for headings
        h_match = re.match(r'^(#{2,4})\s+(.*)$', stripped)
        if h_match:
            hashes, h_text = h_match.groups()
            # "##" is one level below the section's own heading
            level = heading_level + len(hashes) - 1
            add_styled_heading(doc, h_text, level=level, style_config=style)
            in_list = False
            continue

        # Check for bullets
        b_match = re.match(r'^[\-\*]\s+(.*)$', stripped)
        if b_match:
            bullet_text = b_match.group(1)
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            _apply_inline_formatting(p, bullet_text, style)
            in_list = True
            continue

        # Standard paragraph
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.15
        _apply_inline_formatting(p, stripped, style)
        in_list = False
