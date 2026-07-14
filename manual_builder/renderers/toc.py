"""Table of Contents and Index listings renderers."""

from docx.shared import Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from manual_builder.utils import add_styled_heading, add_body_paragraph


def render_toc(doc, section_entry, manifest, style):
    """
    Adds the Table of Contents section with native Word field code placeholder.
    """
    title_text = style.toc.get("title", "Table of Contents")
    add_styled_heading(doc, title_text, level=1, style_config=style)

    p_desc = doc.add_paragraph()
    p_desc.paragraph_format.space_after = Pt(12)
    r_desc = p_desc.add_run(
        "This Table of Contents is dynamically generated using native Microsoft Word index fields. "
        "Please right-click the block below and select 'Update Field' to refresh page numbers."
    )
    r_desc.font.name = style.body_font
    r_desc.font.size = Pt(9.5)
    r_desc.font.italic = True
    r_desc.font.color.rgb = RGBColor(110, 110, 110)

    p_toc = doc.add_paragraph()
    p_element = p_toc._p

    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    max_depth = style.toc.get("max_depth", 3)
    instrText.text = f'TOC \\o "1-{max_depth}" \\h \\z \\u'
    
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "separate")
    
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "end")

    p_element.append(fldChar1)
    p_element.append(instrText)
    p_element.append(fldChar2)

    r = OxmlElement("w:r")
    rText = OxmlElement("w:t")
    rText.text = "[Right-click here and select 'Update Field' to generate Table of Contents]"
    r.append(rText)
    p_element.append(r)
    p_element.append(fldChar3)

    doc.add_page_break()


def render_table_of_tables(doc, section_entry, manifest, style):
    """
    Renders Table of Tables section with native Word field code for captioned tables.
    """
    add_styled_heading(doc, section_entry.heading or "Table of Tables", level=1, style_config=style)

    p_desc = doc.add_paragraph()
    p_desc.paragraph_format.space_after = Pt(12)
    r_desc = p_desc.add_run(
        "Please right-click the block below and select 'Update Field' to refresh Table of Tables listing."
    )
    r_desc.font.name = style.body_font
    r_desc.font.size = Pt(9.5)
    r_desc.font.italic = True
    r_desc.font.color.rgb = RGBColor(110, 110, 110)

    p_tot = doc.add_paragraph()
    p_element = p_tot._p

    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    table_prefix = style.numbering.get("table_prefix", "Table")
    instrText.text = f'TOC \\c "{table_prefix}"'
    
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "separate")
    
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "end")

    p_element.append(fldChar1)
    p_element.append(instrText)
    p_element.append(fldChar2)

    r = OxmlElement("w:r")
    rText = OxmlElement("w:t")
    rText.text = f"[Right-click here and select 'Update Field' to generate listing of captioned {table_prefix}s]"
    r.append(rText)
    p_element.append(r)
    p_element.append(fldChar3)

    doc.add_page_break()


def render_table_of_figures(doc, section_entry, manifest, style):
    """
    Renders Table of Figures section with native Word field code for captioned figures.
    """
    add_styled_heading(doc, section_entry.heading or "Table of Figures", level=1, style_config=style)

    p_desc = doc.add_paragraph()
    p_desc.paragraph_format.space_after = Pt(12)
    r_desc = p_desc.add_run(
        "Please right-click the block below and select 'Update Field' to refresh Table of Figures listing."
    )
    r_desc.font.name = style.body_font
    r_desc.font.size = Pt(9.5)
    r_desc.font.italic = True
    r_desc.font.color.rgb = RGBColor(110, 110, 110)

    p_tof = doc.add_paragraph()
    p_element = p_tof._p

    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    figure_prefix = style.numbering.get("figure_prefix", "Figure")
    instrText.text = f'TOC \\c "{figure_prefix}"'
    
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "separate")
    
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "end")

    p_element.append(fldChar1)
    p_element.append(instrText)
    p_element.append(fldChar2)

    r = OxmlElement("w:r")
    rText = OxmlElement("w:t")
    rText.text = f"[Right-click here and select 'Update Field' to generate listing of captioned {figure_prefix}s]"
    r.append(rText)
    p_element.append(r)
    p_element.append(fldChar3)

    doc.add_page_break()
