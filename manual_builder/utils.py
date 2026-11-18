"""
Word document helper utilities.

Consolidates XML-level helpers used by all renderers.
"""

import re
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls
from docx.enum.text import WD_ALIGN_PARAGRAPH


_HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
# Characters XML 1.0 forbids (python-docx raises ValueError on them): C0 controls
# other than tab/LF/CR, lone surrogates and the U+FFFE/U+FFFF non-characters.
_XML_ILLEGAL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def is_hex_color(value: Any) -> bool:
    return bool(_HEX_RE.match(str(value).lstrip("#")))


def hex_to_rgb(hex_str: str) -> RGBColor:
    """Convert a hex color string (with or without '#') to docx RGBColor."""
    hex_str = str(hex_str).lstrip("#")
    if not _HEX_RE.match(hex_str):
        logger.warning(f"Invalid colour '{hex_str}' in style; using fallback 1B365D.")
        return RGBColor(27, 54, 93)  # fallback dark slate
    return RGBColor(*(int(hex_str[i:i + 2], 16) for i in (0, 2, 4)))


def xml_safe(value: Any) -> Any:
    """
    Recursively strip XML-illegal characters from strings in *value*
    (str / list / tuple / dict). Applied once to LLM- and file-sourced content
    as it enters the builder so a stray control character cannot abort a build.
    """
    if isinstance(value, str):
        return _XML_ILLEGAL_RE.sub("", value)
    if isinstance(value, list):
        return [xml_safe(v) for v in value]
    if isinstance(value, tuple):
        return tuple(xml_safe(v) for v in value)
    if isinstance(value, dict):
        return {k: xml_safe(v) for k, v in value.items()}
    return value


def load_yaml_file(path: Path) -> Any:
    """Read a YAML content file and return XML-safe data ({} when empty)."""
    import yaml
    with Path(path).open("r", encoding="utf-8") as f:
        return xml_safe(yaml.safe_load(f) or {})


def read_text_file(path: Path) -> str:
    """Read a text content file as XML-safe text."""
    return xml_safe(Path(path).read_text(encoding="utf-8"))


def source_file(section_entry, manifest, renderer: str = "renderer") -> Optional[Path]:
    """
    Resolve a section's ``source`` to an existing file, or return None (with a
    warning) when the source is missing, empty or points at a directory.
    """
    src = (getattr(section_entry, "source", "") or "").strip()
    sid = getattr(section_entry, "id", "?")
    if not src:
        logger.warning(f"Section '{sid}' ({renderer}) has no 'source'; rendering heading only.")
        return None
    path = manifest.get_source_path(src)
    if not path.is_file():
        logger.warning(f"Source file for section '{sid}' not found: {path}")
        return None
    return path


def usable_width_emu(doc_or_section, include_body_indent: bool = False) -> int:
    """
    Text width of a section (page width minus left/right margins) in EMU.
    With *include_body_indent*, also subtract the Normal style's left indent so
    that inline images in indented body paragraphs stay inside the margin.
    """
    sec = doc_or_section.sections[-1] if hasattr(doc_or_section, "sections") else doc_or_section
    try:
        width = int(sec.page_width - sec.left_margin - sec.right_margin)
    except Exception:
        width = int(Inches(6.0))
    if include_body_indent and hasattr(doc_or_section, "styles"):
        try:
            indent = doc_or_section.styles["Normal"].paragraph_format.left_indent
            if indent:
                width -= int(indent)
        except Exception:
            pass
    return width


def set_table_width(table, col_widths) -> None:
    """Set column widths (EMU / Length) on a table, cells included, and its total width."""
    for idx, w in enumerate(col_widths):
        table.columns[idx].width = w
        for cell in table.columns[idx].cells:
            cell.width = w
    tblPr = table._tbl.tblPr
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(int(sum(int(w) for w in col_widths) / 635)))  # EMU -> twips


def scaled_widths(doc, inches: list) -> list:
    """Scale nominal column widths (inches) down to fit the section's usable width."""
    usable = usable_width_emu(doc)
    total = sum(int(Inches(w)) for w in inches)
    factor = min(1.0, usable / total) if total else 1.0
    return [int(int(Inches(w)) * factor) for w in inches]


def set_cell_background(cell, fill_hex: str):
    """Set cell background shading."""
    fill_hex = str(fill_hex).lstrip("#")
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)


def set_table_borders(table, border_color_hex: str = "CCCCCC", sz: str = "4"):
    """Set custom borders on all cells in a table."""
    border_color_hex = str(border_color_hex).lstrip("#")
    tblPr = table._tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        table._tbl.insert(0, tblPr)
    tblBorders = OxmlElement("w:tblBorders")
    for border_name in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        border = OxmlElement(f"w:{border_name}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), str(sz))
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), border_color_hex)
        tblBorders.append(border)
    tblPr.append(tblBorders)


def set_cell_margins(cell, top: int = 120, bottom: int = 120, left: int = 180, right: int = 180):
    """Set cell padding in dxa (1 pt = 20 dxa)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for margin, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        node = OxmlElement(f"w:{margin}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)


def set_cell_left_border(cell, color_hex: str, size_sz: int = 36):
    """Set a thick left border on a cell (for callout styling)."""
    color_hex = str(color_hex).lstrip("#")
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), str(size_sz))
    left.set(qn("w:space"), "0")
    left.set(qn("w:color"), color_hex)
    tcBorders.append(left)
    for border_name in ["top", "bottom", "right"]:
        b = OxmlElement(f"w:{border_name}")
        b.set(qn("w:val"), "none")
        tcBorders.append(b)
    tcPr.append(tcBorders)


def remove_table_borders(table):
    """Remove all borders from a table (useful for layout tables)."""
    tblPr = table._tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        table._tbl.insert(0, tblPr)
    tblBorders = OxmlElement("w:tblBorders")
    for border_name in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        border = OxmlElement(f"w:{border_name}")
        border.set(qn("w:val"), "none")
        tblBorders.append(border)
    tblPr.append(tblBorders)


def add_bottom_border(paragraph, color_hex: str = "CCCCCC", sz: int = 6):
    """Add a bottom border to a paragraph (divider line)."""
    color_hex = str(color_hex).lstrip("#")
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(sz))
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color_hex)
    pBdr.append(bottom)
    pPr.append(pBdr)


def add_page_field(run):
    """Append the PAGE number field XML to a run."""
    for tag_type, text in [("begin", None), ("instrText", "PAGE"), ("separate", None), ("end", None)]:
        if tag_type == "instrText":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
            run._r.append(el)
        else:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), tag_type)
            run._r.append(fc)


def add_numpages_field(run):
    """Append the NUMPAGES field XML to a run."""
    for tag_type, text in [("begin", None), ("instrText", "NUMPAGES"), ("separate", None), ("end", None)]:
        if tag_type == "instrText":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
            run._r.append(el)
        else:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), tag_type)
            run._r.append(fc)


def add_toc_field(paragraph, max_depth: int = 3, placeholder: str = "Table of contents will update automatically."):
    """
    Add a native Word TOC field to a paragraph.
    Every fldChar/instrText is correctly wrapped in its own <w:r> (OOXML-correct).
    """
    def _run_with(el):
        r = OxmlElement("w:r")
        r.append(el)
        paragraph._p.append(r)

    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    _run_with(begin)

    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f'TOC \\o "1-{max_depth}" \\h \\z \\u'
    _run_with(instr)

    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    _run_with(sep)

    if placeholder:
        paragraph.add_run(placeholder)

    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    _run_with(end)


def add_body_paragraph(doc, text: str, font_name: str = "Calibri", size_pt: float = 11,
                       color_hex: str = "000000"):
    """Add a standard body text paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(text)
    r.font.name = font_name
    r.font.size = Pt(size_pt)
    r.font.color.rgb = hex_to_rgb(color_hex)
    return p


def add_styled_heading(doc, text: str, level: int, style_config, numbering=None):
    """
    Add a heading at the given level using style config for font/size/color.

    If numbering string is provided, prepends it (e.g., "10.1 Add Case").
    """
    level = max(1, min(int(level), 4))
    h = doc.add_heading(level=level)
    display_text = f"{numbering}\t{text}" if numbering else text
    run = h.add_run(display_text)
    hcfg = style_config.heading_config(level)
    run.font.name = style_config.heading_font
    run.font.size = Pt(hcfg["size_pt"])
    run.font.bold = hcfg["bold"]
    run.font.color.rgb = hex_to_rgb(hcfg["color"])
    h.paragraph_format.space_before = Pt(hcfg.get("before_pt", 18))
    h.paragraph_format.space_after = Pt(hcfg.get("after_pt", 8))
    h.paragraph_format.keep_with_next = True
    return h


def setup_header_footer(doc, style_config, manifest=None):
    """
    Set up professional header/footer on all sections.

    Header: logo (left) + document title (right), OR full-width banner image.
    Footer: company name (left) + page number (right)
    """
    logo_path_str = style_config.logo.get("path", "") or ""
    logo_path = Path(logo_path_str) if logo_path_str else None
    if logo_path is not None and not logo_path.is_absolute() and manifest is not None:
        # Relative logo paths are relative to the client folder (clients/<key>/)
        try:
            from docbot import paths
            cand = paths.clients_dir() / manifest.client_key / logo_path
            if cand.exists():
                logo_path = cand
        except Exception:
            pass
    font_name = style_config.body_font

    if manifest:
        doc_title = f"{manifest.client_display_name} — {manifest.manual_title}"
        company = manifest.client_display_name
    else:
        doc_title = "User Manual"
        company = ""

    hdr_mode = style_config.raw.get("header", {}).get("mode", "table")

    for section in doc.sections:
        # Page 1 only drops the header/footer when a cover is actually
        # rendered (GenericBuilder turns this on after the cover).
        section.different_first_page_header_footer = False
        full_w = usable_width_emu(section)
        half_w = full_w // 2

        # ── HEADER ──
        header = section.header
        header.is_linked_to_previous = False
        hdr_element = header._element
        for child in list(hdr_element):
            hdr_element.remove(child)

        if hdr_mode == "banner":
            hdr_p = header.add_paragraph()
            hdr_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            banner_rel = style_config.raw.get("header", {}).get("banner_path", "")
            banner_path = None
            if banner_rel:
                if manifest:
                    banner_path = manifest.content_dir / banner_rel
                if not banner_path or not banner_path.exists():
                    banner_path = Path(banner_rel)
            
            if banner_path and banner_path.exists():
                try:
                    hdr_p.add_run().add_picture(str(banner_path), width=full_w)
                except Exception:
                    pass
        else:
            hdr_p = OxmlElement("w:p")
            hdr_element.append(hdr_p)

            table = header.add_table(rows=1, cols=2, width=full_w)
            table.autofit = False
            remove_table_borders(table)
            set_table_width(table, [half_w, full_w - half_w])

            cell_logo = table.cell(0, 0)
            p_logo = cell_logo.paragraphs[0]
            p_logo.alignment = WD_ALIGN_PARAGRAPH.LEFT
            if logo_path and logo_path.exists():
                try:
                    # D1: logo height 0.45" per reference manual spec
                    logo_h_in = style_config.raw.get("header", {}).get("logo_height_inches", 0.45)
                    p_logo.add_run().add_picture(str(logo_path), height=Inches(logo_h_in))
                except Exception:
                    pass

            cell_title = table.cell(0, 1)
            p_title = cell_title.paragraphs[0]
            p_title.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            # D1: right-aligned italic 8pt gray "<client> — <title>"
            right_pt = style_config.raw.get("header", {}).get("right_text_pt", 8)
            right_color_hex = style_config.raw.get("header", {}).get("right_text_color", "666666")
            run_title = p_title.add_run(doc_title)
            run_title.font.name = font_name
            run_title.font.size = Pt(right_pt)
            run_title.font.italic = True
            try:
                from manual_builder.utils import hex_to_rgb as _h2r
                run_title.font.color.rgb = _h2r(right_color_hex)
            except Exception:
                run_title.font.color.rgb = RGBColor(100, 100, 100)

            sep_p = header.add_paragraph()
            add_bottom_border(sep_p, color_hex="CCCCCC", sz=4)
            sep_p.paragraph_format.space_before = Pt(2)
            sep_p.paragraph_format.space_after = Pt(0)


        # ── FOOTER ──
        footer = section.footer
        footer.is_linked_to_previous = False
        ftr_element = footer._element
        for child in list(ftr_element):
            ftr_element.remove(child)

        ftr_p_xml = OxmlElement("w:p")
        ftr_element.append(ftr_p_xml)

        ftr_table = footer.add_table(rows=1, cols=2, width=full_w)
        ftr_table.autofit = False
        remove_table_borders(ftr_table)
        set_table_width(ftr_table, [half_w, full_w - half_w])

        p_left = ftr_table.cell(0, 0).paragraphs[0]
        p_left.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_company = p_left.add_run(company)
        r_company.font.name = font_name
        r_company.font.size = Pt(8)
        r_company.font.color.rgb = RGBColor(130, 130, 130)

        p_right = ftr_table.cell(0, 1).paragraphs[0]
        p_right.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_pre = p_right.add_run("Page ")
        r_pre.font.name = font_name
        r_pre.font.size = Pt(8)
        r_pre.font.color.rgb = RGBColor(100, 100, 100)
        # Field runs need the same formatting, or the digits render at body size
        r_page = p_right.add_run()
        _format_like(r_page, r_pre)
        add_page_field(r_page)
        r_mid = p_right.add_run(" of ")
        r_mid.font.name = font_name
        r_mid.font.size = Pt(8)
        r_mid.font.color.rgb = RGBColor(100, 100, 100)
        r_total = p_right.add_run()
        _format_like(r_total, r_pre)
        add_numpages_field(r_total)


def _format_like(run, model) -> None:
    run.font.name = model.font.name
    run.font.size = model.font.size
    run.font.color.rgb = model.font.color.rgb
