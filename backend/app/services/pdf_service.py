
import pymupdf
from pathlib import Path


MAX_PAGES = 100


def validate_pdf(file_bytes: bytes):
    """Validate PDF structure and page count."""

    if not file_bytes:
        raise ValueError("Uploaded PDF is empty")

    try:
        pdf = pymupdf.open(stream=file_bytes, filetype="pdf")

        if pdf.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported")

        if len(pdf) == 0:
            raise ValueError("PDF contains no pages")

        if len(pdf) > MAX_PAGES:
            raise ValueError(
                f"PDF exceeds the maximum of {MAX_PAGES} pages"
            )

        return pdf

    except pymupdf.FileDataError as exc:
        raise ValueError("Invalid or corrupted PDF") from exc


def extract_pdf_metadata(pdf):
    """Extract basic PDF metadata."""

    return {
        "page_count": len(pdf),
        "title": pdf.metadata.get("title"),
        "author": pdf.metadata.get("author"),
        "subject": pdf.metadata.get("subject"),
        "creator": pdf.metadata.get("creator"),
    }


def extract_page_text(pdf):
    """Extract selectable text from every PDF page."""

    pages = []

    for index, page in enumerate(pdf):
        text = page.get_text("text").strip()

        pages.append({
            "page_number": index + 1,
            "text": text,
            "character_count": len(text),
            "has_text": bool(text),
            "source": "pymupdf" if text else None,
        })

    return pages

def generate_page_preview(pdf, page_number: int):
    """Render one PDF page as an image."""

    if page_number < 1 or page_number > len(pdf):
        raise ValueError("Invalid page number")

    page = pdf[page_number - 1]

    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(1.5, 1.5),
        alpha=False
    )

    return pix.tobytes("png")
