"""
DocBot v3 — Export Quality Assurance (QA) Hook.

After generating a Word manual, converts it to PDF via LibreOffice (if installed)
and rasterises the first few pages to inspect formatting.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger


def run_qa_check(docx_path: Path) -> Optional[Path]:
    """
    Run automated QA on the generated docx file:
    1. Look for LibreOffice `soffice` executable.
    2. Convert docx to PDF in headless mode.
    3. Rasterise the first 3 pages to PNG for quick inspection.

    Args:
        docx_path: Path to the generated docx manual.

    Returns:
        Path to the generated PDF file if successful, otherwise None.
    """
    docx_path = Path(docx_path).resolve()
    if not docx_path.exists():
        logger.error(f"[QA] docx file does not exist: {docx_path}")
        return None

    # Search for LibreOffice
    soffice = _find_soffice()
    if not soffice:
        logger.warning(
            "[QA] LibreOffice 'soffice' executable not found. "
            "Please install LibreOffice to enable PDF generation and visual QA check."
        )
        return None

    logger.info(f"[QA] Converting {docx_path.name} to PDF via LibreOffice…")
    pdf_dir = docx_path.parent
    try:
        cmd = [
            soffice,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(pdf_dir),
            str(docx_path)
        ]
        # Run with a 45 second timeout
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=True)
    except Exception as e:
        logger.warning(f"[QA] PDF conversion failed: {e}")
        return None

    pdf_path = pdf_dir / f"{docx_path.stem}.pdf"
    if pdf_path.exists():
        logger.info(f"[QA] PDF generated successfully: {pdf_path.resolve()}")
        # Visual rasterisation pass
        _rasterise_pages(pdf_path)
        return pdf_path
    else:
        logger.warning("[QA] PDF file was not created by LibreOffice.")
        return None


def _find_soffice() -> Optional[str]:
    """Resolve soffice executable path on Windows / Linux."""
    # Check PATH first
    path_check = shutil.which("soffice")
    if path_check:
        return path_check

    # Common Windows installation locations
    windows_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for p in windows_paths:
        if Path(p).exists():
            return p
    return None


def _rasterise_pages(pdf_path: Path) -> None:
    """Attempt to rasterise the first 3 pages of the PDF to PNG images."""
    png_dir = pdf_path.parent / "qa_pages"
    png_dir.mkdir(parents=True, exist_ok=True)

    # 1. Try PyMuPDF / fitz
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        num_pages = min(len(doc), 3)
        logger.info(f"[QA] Rasterising first {num_pages} pages using fitz…")
        for i in range(num_pages):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=150)
            out_png = png_dir / f"page_{i + 1}.png"
            pix.save(str(out_png))
            logger.debug(f"[QA] Rasterised page {i + 1} → {out_png.name}")
        return
    except ImportError:
        pass

    # 2. Try pdf2image (requires poppler)
    try:
        from pdf2image import convert_from_path
        logger.info("[QA] Rasterising first 3 pages using pdf2image…")
        images = convert_from_path(str(pdf_path), last_page=3, dpi=150)
        for i, img in enumerate(images):
            out_png = png_dir / f"page_{i + 1}.png"
            img.save(str(out_png), "PNG")
            logger.debug(f"[QA] Rasterised page {i + 1} → {out_png.name}")
        return
    except ImportError:
        pass

    logger.debug("[QA] Skipping visual page rasterisation (fitz / pdf2image not installed).")
