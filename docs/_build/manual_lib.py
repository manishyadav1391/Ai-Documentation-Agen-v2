"""Helpers for building DocBot's own Word documents in the house manual style.

House style (taken from the reference manuals):
  * A4, 1 in margins; header "User Manual for ..." on every page except the cover;
    footer "Page X of Y" right-aligned.
  * Cover, Revision History (six columns), Table of Contents (levels 1-3).
  * Headings: H1 Calibri Light 20, H2 Calibri Light 16, H3 Calibri 14, numbered 1 / 1.1 / 1.1.1.
  * Body Calibri 12, justified.
  * Figures: full text width, thin blue outline, caption "Figure <chapter>-<n>" below.
  * Bullets "Label – description. (Control type)"; notes "Note:" in red.
"""
from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor, Emu

BLUE = RGBColor(0x2F, 0x54, 0x96)
DARK_BLUE = RGBColor(0x1F, 0x37, 0x63)
RED = RGBColor(0xEE, 0x00, 0x00)
TEXT_W_IN = 8.27 - 2.0          # A4 width minus 1 in margins


# ----------------------------------------------------------------------------
# low-level XML helpers
# ----------------------------------------------------------------------------
def _el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(k) if ":" in k else k, str(v))
    return e


def add_field(paragraph, instr: str, cached: str = "", bold=False, size=None):
    """Complex field (begin / instr / separate / cached result / end)."""
    def run_with(child):
        r = paragraph.add_run()
        if bold:
            r.bold = True
        if size:
            r.font.size = size
        r._r.append(child)
        return r
    run_with(_el("w:fldChar", **{"w:fldCharType": "begin"}))
    it = _el("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = f" {instr} "
    run_with(it)
    run_with(_el("w:fldChar", **{"w:fldCharType": "separate"}))
    r = paragraph.add_run(cached)
    if bold:
        r.bold = True
    if size:
        r.font.size = size
    r._r.get_or_add_rPr().append(_el("w:noProof"))
    run_with(_el("w:fldChar", **{"w:fldCharType": "end"}))


def set_cell_shading(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(_el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": hex_fill}))


def set_table_borders(table, color="595959", size=4):
    tblPr = table._tbl.tblPr
    borders = _el("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        borders.append(_el(f"w:{edge}", **{"w:val": "single", "w:sz": size, "w:space": 0, "w:color": color}))
    tblPr.append(borders)


def keep_with_next(paragraph):
    paragraph.paragraph_format.keep_with_next = True


# ----------------------------------------------------------------------------
# document
# ----------------------------------------------------------------------------
class Manual:
    def __init__(self, header_text: str):
        self.doc = Document()
        self.header_text = header_text
        self.chapter = 0
        self.fig_in_chapter = 0
        self.headings: list[tuple[int, str, str]] = []   # (level, number, text)
        self._h = [0, 0, 0]
        self._bookmark_id = 100
        self._setup_page()
        self._setup_styles()
        self._setup_numbering()

    # ---------------------------------------------------------------- setup
    def _setup_page(self):
        s = self.doc.sections[0]
        s.page_width, s.page_height = Inches(8.27), Inches(11.69)
        for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            setattr(s, side, Inches(1))
        s.header_distance = s.footer_distance = Inches(0.49)
        s.different_first_page_header_footer = True
        # header
        hp = s.header.paragraphs[0]
        hp.text = ""
        r = hp.add_run(self.header_text)
        r.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = DARK_BLUE
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        pPr = hp._p.get_or_add_pPr()
        bdr = _el("w:pBdr")
        bdr.append(_el("w:bottom", **{"w:val": "single", "w:sz": 6, "w:space": 1, "w:color": "2F5496"}))
        pPr.append(bdr)
        # footer: Page X of Y
        fp = s.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        size = Pt(10)
        fp.add_run("Page ").font.size = size
        add_field(fp, "PAGE", "1", bold=True, size=size)
        fp.add_run(" of ").font.size = size
        add_field(fp, "NUMPAGES", "1", bold=True, size=size)
        # ask Word to refresh TOC / page fields on open
        settings = self.doc.settings.element
        settings.append(_el("w:updateFields", **{"w:val": "true"}))

    def _setup_styles(self):
        st = self.doc.styles
        normal = st["Normal"]
        normal.font.name = "Calibri"
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        normal.font.size = Pt(12)
        normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.08
        spec = {"Heading 1": ("Calibri Light", 20, BLUE, 18, 8),
                "Heading 2": ("Calibri Light", 16, BLUE, 12, 6),
                "Heading 3": ("Calibri", 14, DARK_BLUE, 10, 4)}
        for name, (font, size, color, before, after) in spec.items():
            h = st[name]
            h.font.name = font
            rpr = h.element.get_or_add_rPr()
            rf = rpr.find(qn("w:rFonts"))
            if rf is None:
                rf = _el("w:rFonts")
                rpr.insert(0, rf)
            for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                rf.set(qn(a), font)
            for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                if rf.get(qn(a)) is not None:
                    del rf.attrib[qn(a)]
            h.font.size = Pt(size)
            h.font.bold = name != "Heading 1" and name != "Heading 2" or False
            h.font.color.rgb = color
            h.paragraph_format.space_before = Pt(before)
            h.paragraph_format.space_after = Pt(after)
            h.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            h.paragraph_format.keep_with_next = True
        cap = st["Caption"]
        cap.font.name = "Calibri"
        cap.font.size = Pt(10)
        cap.font.italic = False
        cap.font.bold = True
        cap.font.color.rgb = DARK_BLUE
        cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_after = Pt(12)
        for name in ("List Bullet", "List Bullet 2"):
            lb = st[name]
            lb.font.name = "Calibri"
            lb.font.size = Pt(12)
            lb.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            lb.paragraph_format.space_after = Pt(3)

    def _setup_numbering(self):
        numbering = self.doc.part.numbering_part.element
        abs_id = 90
        absn = _el("w:abstractNum", **{"w:abstractNumId": abs_id})
        absn.append(_el("w:multiLevelType", **{"w:val": "multilevel"}))
        fmts = ["%1", "%1.%2", "%1.%2.%3"]
        for lvl, txt in enumerate(fmts):
            l = _el("w:lvl", **{"w:ilvl": lvl})
            l.append(_el("w:start", **{"w:val": 1}))
            l.append(_el("w:numFmt", **{"w:val": "decimal"}))
            l.append(_el("w:pStyle", **{"w:val": f"Heading{lvl + 1}"}))
            l.append(_el("w:lvlText", **{"w:val": txt}))
            l.append(_el("w:lvlJc", **{"w:val": "left"}))
            ppr = _el("w:pPr")
            ind = [(576, 576), (720, 720), (864, 864)][lvl]   # room for "10" / "10.10"
            ppr.append(_el("w:ind", **{"w:left": ind[0], "w:hanging": ind[1]}))
            l.append(ppr)
            absn.append(l)
        # abstractNum elements must precede num elements
        first_num = numbering.find(qn("w:num"))
        if first_num is not None:
            first_num.addprevious(absn)
        else:
            numbering.append(absn)
        num = _el("w:num", **{"w:numId": 90})
        num.append(_el("w:abstractNumId", **{"w:val": abs_id}))
        numbering.append(num)
        for lvl in range(3):
            style = self.doc.styles[f"Heading {lvl + 1}"]
            ppr = style.element.get_or_add_pPr()
            numpr = _el("w:numPr")
            numpr.append(_el("w:ilvl", **{"w:val": lvl}))
            numpr.append(_el("w:numId", **{"w:val": 90}))
            ppr.insert(0, numpr)

    # ---------------------------------------------------------------- front matter
    def cover(self, org: str, title: str, subtitle: str, version: str, when: str):
        d = self.doc
        for _ in range(5):
            d.add_paragraph()
        def line(text, size, color=BLUE, bold=False, after=10):
            p = d.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(after)
            r = p.add_run(text)
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = color
            r.font.name = "Calibri Light"
            return p
        line(org, 20, DARK_BLUE, True, 36)
        line(title, 36, BLUE, True, 6)
        line(subtitle, 22, BLUE, False, 60)
        for _ in range(8):
            d.add_paragraph()
        line(f"Version {version}", 18, RGBColor(0, 0, 0), False, 4)
        line(when, 14, RGBColor(0x59, 0x59, 0x59), False, 0)
        d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def revision_history(self, rows: list[list[str]]):
        p = self.doc.add_paragraph()
        r = p.add_run("Revision History")
        r.bold = True
        r.font.size = Pt(14)
        r.font.color.rgb = DARK_BLUE
        cols = ["Revision No.", "Revision Date", "Author", "Approved Date", "Approved By", "Description"]
        widths = [0.85, 1.05, 1.25, 1.05, 1.1, 1.97]
        t = self.doc.add_table(rows=1 + len(rows), cols=6)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_borders(t)
        for i, c in enumerate(cols):
            cell = t.rows[0].cells[i]
            cell.text = ""
            run = cell.paragraphs[0].add_run(c)
            run.bold = True
            run.font.size = Pt(9)
            set_cell_shading(cell, "D9E2F3")
        for ri, row in enumerate(rows, start=1):
            for ci, val in enumerate(row):
                cell = t.rows[ri].cells[ci]
                cell.text = ""
                para = cell.paragraphs[0]
                para.alignment = WD_ALIGN_PARAGRAPH.LEFT
                para.add_run(val).font.size = Pt(9)
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)
        self.doc.add_paragraph()

    def toc_placeholder(self):
        """Inserted now, filled by finalize_toc() once all headings are known."""
        p = self.doc.add_paragraph()
        r = p.add_run("Table of Contents")
        r.bold = True
        r.font.size = Pt(16)
        r.font.color.rgb = BLUE
        self._toc_anchor = self.doc.add_paragraph()
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def finalize_toc(self, page_numbers: dict[str, int] | None = None):
        """Write a TOC field whose cached result lists every heading (levels 1-3).
        Word refreshes it on open (updateFields); the cached copy keeps the TOC
        readable in viewers that do not update fields."""
        page_numbers = page_numbers or {}
        anchor = self._toc_anchor
        body = anchor._p.getparent()
        idx = list(body).index(anchor._p)
        paras = []
        for i, (lvl, num, text) in enumerate(self.headings):
            p = copy.deepcopy(anchor._p)
            paras.append((p, lvl, num, text))
        # first paragraph carries the field begin, last carries the end
        from docx.text.paragraph import Paragraph
        built = []
        for i, (p_el, lvl, num, text) in enumerate(paras):
            body.insert(idx + i, p_el)
            para = Paragraph(p_el, anchor._parent)
            para.style = self.doc.styles[f"TOC {lvl}"] if f"TOC {lvl}" in [s.name for s in self.doc.styles] else None
            pf = para.paragraph_format
            pf.left_indent = Inches(0.25 * (lvl - 1))
            pf.space_after = Pt(2)
            pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pPr = p_el.get_or_add_pPr()
            tabs = _el("w:tabs")
            tabs.append(_el("w:tab", **{"w:val": "right", "w:leader": "dot", "w:pos": int(TEXT_W_IN * 1440)}))
            pPr.append(tabs)
            if i == 0:
                for tag, extra in (("w:fldChar", {"w:fldCharType": "begin"}), ("w:instrText", None),
                                   ("w:fldChar", {"w:fldCharType": "separate"})):
                    r = para.add_run()
                    if tag == "w:instrText":
                        it = _el("w:instrText")
                        it.set(qn("xml:space"), "preserve")
                        it.text = ' TOC \\o "1-3" \\h \\z \\u '
                        r._r.append(it)
                    else:
                        r._r.append(_el(tag, **extra))
            run = para.add_run(f"{num}\t" if False else f"{num}  {text}")
            run.font.size = Pt(12 if lvl == 1 else 11)
            run.bold = lvl == 1
            pg = page_numbers.get(f"{num} {text}")
            para.add_run(f"\t{pg if pg else ''}").font.size = Pt(11)
            built.append(para)
        if built:
            built[-1].add_run()._r.append(_el("w:fldChar", **{"w:fldCharType": "end"}))
        body.remove(anchor._p)

    # ---------------------------------------------------------------- body
    def heading(self, text: str, level: int = 1, page_break: bool | None = None):
        if level == 1:
            self.chapter += 1
            self.fig_in_chapter = 0
            if page_break is None:
                page_break = self.chapter > 1
        if page_break:
            self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        self._h[level - 1] += 1
        for i in range(level, 3):
            self._h[i] = 0
        number = ".".join(str(n) for n in self._h[:level])
        self.headings.append((level, number, text))
        return self.doc.add_heading(text, level=level)

    def para(self, text: str = "", bold_lead: str | None = None, italic=False):
        p = self.doc.add_paragraph()
        if bold_lead:
            p.add_run(bold_lead).bold = True
            if text:
                p.add_run(" ")
        if text:
            self._rich(p, text, italic=italic)
        return p

    def _rich(self, p, text, italic=False):
        """**bold** spans inside text."""
        parts = text.split("**")
        for i, part in enumerate(parts):
            if part:
                r = p.add_run(part)
                r.bold = i % 2 == 1
                r.italic = italic

    def bullet(self, label: str | None, desc: str, control: str | None = None, level: int = 1):
        p = self.doc.add_paragraph(style="List Bullet" if level == 1 else "List Bullet 2")
        if label:
            p.add_run(label).bold = True
            p.add_run(" – ")
        self._rich(p, desc.rstrip())
        if control:
            if not desc.rstrip().endswith("."):
                p.add_run(".")
            p.add_run(f" ({control})")
        return p

    def steps(self, items: list[str]):
        """Numbered steps; numbering restarts at 1 for every call."""
        for i, s in enumerate(items, 1):
            p = self.doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent = Inches(0.35)
            pf.first_line_indent = Inches(-0.25)
            pf.space_after = Pt(3)
            pf.tab_stops.add_tab_stop(Inches(0.35))
            p.add_run(f"{i}.\t")
            self._rich(p, s)

    def note(self, text: str):
        p = self.doc.add_paragraph()
        r = p.add_run("Note:")
        r.bold = True
        r.font.color.rgb = RED
        r2 = p.add_run(" " + text)
        r2.font.color.rgb = RED
        return p

    def figure(self, image: Path, width_in: float = TEXT_W_IN, alt: str = ""):
        from PIL import Image
        with Image.open(image) as im:
            w, h = im.size
        # small dialogs are not blown up beyond ~110 px per inch
        width_in = min(width_in, TEXT_W_IN, w / 110)
        # keep very tall images on one page
        max_h = 7.2
        if width_in * h / w > max_h:
            width_in = max_h * w / h
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        keep_with_next(p)
        run = p.add_run()
        shape = run.add_picture(str(image), width=Inches(width_in))
        # thin blue outline on the picture
        spPr = shape._inline.graphic.graphicData.pic.spPr
        ln = _el("a:ln", w=9525)
        fill = _el("a:solidFill")
        fill.append(_el("a:srgbClr", val="4472C4"))
        ln.append(fill)
        spPr.append(ln)
        if alt:
            shape._inline.docPr.set("descr", alt)
        self.fig_in_chapter += 1
        cap = self.doc.add_paragraph(style="Caption")
        # Chapter number written as text: STYLEREF is evaluated differently by
        # Word and LibreOffice. The SEQ field restarts at each Heading 1.
        cap.add_run(f"Figure {self.chapter}-")
        add_field(cap, "SEQ Figure \\* ARABIC \\s 1", str(self.fig_in_chapter))
        return f"Figure {self.chapter}-{self.fig_in_chapter}"

    def table(self, header: list[str], rows: list[list[str]], widths: list[float] | None = None, size=10):
        t = self.doc.add_table(rows=1 + len(rows), cols=len(header))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_borders(t)
        for i, c in enumerate(header):
            cell = t.rows[0].cells[i]
            cell.text = ""
            r = cell.paragraphs[0].add_run(c)
            r.bold = True
            r.font.size = Pt(size)
            set_cell_shading(cell, "D9E2F3")
        # repeat header row on each page
        trPr = t.rows[0]._tr.get_or_add_trPr()
        trPr.append(_el("w:tblHeader", **{"w:val": "true"}))
        for ri, row in enumerate(rows, start=1):
            for ci, val in enumerate(row):
                cell = t.rows[ri].cells[ci]
                cell.text = ""
                para = cell.paragraphs[0]
                para.alignment = WD_ALIGN_PARAGRAPH.LEFT
                self._rich(para, str(val))
                for r in para.runs:
                    r.font.size = Pt(size)
        if widths:
            for row in t.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Inches(w)
        self.doc.add_paragraph()
        return t

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(str(path))
        return path


# ----------------------------------------------------------------------------
# Screenshot annotation: red boxes + speech-bubble callouts baked into the image
# ----------------------------------------------------------------------------
CALLOUT_RED = (224, 64, 58)


def _font(size):
    from PIL import ImageFont
    for name in ("calibri.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def annotate(src: Path, dst: Path, marks: list[dict], scale_font: float = 1.0):
    """marks: {"box": [x, y, w, h], "text": "...", "side": "r|l|t|b", "dx": 0, "dy": 0, "box_only": bool}"""
    from PIL import Image, ImageDraw
    im = Image.open(src).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    fsize = max(14, int(W / 52 * scale_font))
    font = _font(fsize)
    pad = max(6, fsize // 2)
    # boxes first
    for m in marks:
        x, y, w, h = m["box"]
        g = m.get("grow", 3)
        d.rectangle([x - g, y - g, x + w + g, y + h + g], outline=CALLOUT_RED, width=max(2, W // 450))
    for m in marks:
        text = m.get("text")
        if not text or m.get("box_only"):
            continue
        x, y, w, h = m["box"]
        g = m.get("grow", 3)
        lines = text.split("\n")
        tw = max(d.textlength(l, font=font) for l in lines)
        th = fsize * 1.25 * len(lines)
        bw, bh = tw + 2 * pad, th + 2 * pad - fsize * 0.2
        gap = m.get("gap", fsize * 2.2)
        side = m.get("side", "r")
        cx, cy = x + w / 2, y + h / 2
        if side == "in":
            # large region: label inside the box, no tail
            bx, by = x + 2 * pad + m.get("dx", 0), y + 2 * pad + m.get("dy", 0)
            bx = max(4, min(W - bw - 4, bx))
            by = max(4, min(H - bh - 4, by))
            lw = max(2, W // 600)
            d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(bh / 3), fill="white",
                                outline=CALLOUT_RED, width=lw)
            for i, l in enumerate(lines):
                lx = bx + (bw - d.textlength(l, font=font)) / 2
                d.text((lx, by + pad - fsize * 0.15 + i * fsize * 1.25), l, fill=CALLOUT_RED, font=font)
            continue
        if side == "r":
            bx, by = x + w + g + gap, cy - bh / 2
        elif side == "l":
            bx, by = x - g - gap - bw, cy - bh / 2
        elif side == "t":
            bx, by = cx - bw / 2, y - g - gap - bh
        else:
            bx, by = cx - bw / 2, y + h + g + gap
        bx += m.get("dx", 0)
        by += m.get("dy", 0)
        bx = max(4, min(W - bw - 4, bx))
        by = max(4, min(H - bh - 4, by))
        # tail: triangle from bubble edge toward the box edge
        bcx, bcy = bx + bw / 2, by + bh / 2
        tx = min(max(cx, x - g), x + w + g)
        ty = min(max(cy, y - g), y + h + g)
        if side in ("r", "l"):
            ex = bx if side == "r" else bx + bw
            ey = min(max(ty, by + bh * 0.3), by + bh * 0.7)
            tip = (x + w + g if side == "r" else x - g, ty)
            base = [(ex, ey - bh * 0.18), (ex, ey + bh * 0.18)]
        else:
            ey = by + bh if side == "t" else by
            ex = min(max(tx, bx + bw * 0.25), bx + bw * 0.75)
            tip = (tx, y - g if side == "t" else y + h + g)
            base = [(ex - bw * 0.1, ey), (ex + bw * 0.1, ey)]
        lw = max(2, W // 600)
        d.polygon([base[0], tip, base[1]], fill="white", outline=CALLOUT_RED)
        d.line([base[0], tip, base[1]], fill=CALLOUT_RED, width=lw)
        d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(bh / 3), fill="white",
                            outline=CALLOUT_RED, width=lw)
        # cover the tail base seam so bubble and tail read as one shape
        if side in ("r", "l"):
            sx = ex + (lw if side == "r" else -lw)
            d.line([(sx, base[0][1] + lw), (sx, base[1][1] - lw)], fill="white", width=lw + 1)
        else:
            sy = ey + (lw if side == "b" else -lw)
            d.line([(base[0][0] + lw, sy), (base[1][0] - lw, sy)], fill="white", width=lw + 1)
        for i, l in enumerate(lines):
            lx = bx + (bw - d.textlength(l, font=font)) / 2
            d.text((lx, by + pad - fsize * 0.15 + i * fsize * 1.25), l, fill=CALLOUT_RED, font=font)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst)
    return dst


# ----------------------------------------------------------------------------
# Two-pass build: real page numbers in the cached TOC (via LibreOffice)
# ----------------------------------------------------------------------------
SOFFICE = Path(r"C:\Program Files\LibreOffice\program\soffice.exe")


def to_pdf(docx_path: Path, out_dir: Path, profile_dir: Path) -> Path | None:
    import subprocess
    if not SOFFICE.exists():
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(SOFFICE), f"-env:UserInstallation={profile_dir.as_uri()}", "--headless",
                    "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
                   check=False, capture_output=True, timeout=240)
    pdf = out_dir / (docx_path.stem + ".pdf")
    return pdf if pdf.exists() else None


def heading_pages(pdf: Path, headings: list[tuple[int, str, str]]) -> dict[str, int]:
    """Page (1-based, as printed in the footer) where each heading first appears,
    searching forward from the page after the table of contents."""
    import fitz
    import re
    doc = fitz.open(str(pdf))
    texts = [re.sub(r"\s+", " ", p.get_text()) for p in doc]
    start = next((i for i, t in enumerate(texts) if "Table of Contents" in t), 0) + 1
    result, page = {}, start
    for lvl, num, text in headings:
        pat = re.compile(r"(^|\s)" + re.escape(num) + r"\s+" + re.escape(text[:40]))
        for i in range(page, len(texts)):
            if pat.search(texts[i]):
                result[f"{num} {text}"] = i + 1
                page = i
                break
    return result


def build_with_page_numbers(build_fn, out_path: Path, work_dir: Path):
    """build_fn(page_numbers) -> Manual (unsaved). Builds, measures, rebuilds."""
    m = build_fn({})
    m.save(out_path)
    pdf = to_pdf(out_path, work_dir, work_dir / "lo_profile")
    if pdf is None:
        return out_path, None
    pages = heading_pages(pdf, m.headings)
    m2 = build_fn(pages)
    m2.save(out_path)
    pdf2 = to_pdf(out_path, work_dir, work_dir / "lo_profile")
    return out_path, pdf2
