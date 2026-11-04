from pathlib import Path
import fitz

from app.services.pdf_service import generate_page_preview
from app.services.pdf_service import validate_pdf
from app.services.ocr_service import extract_text_from_image


# Change this to your scanned PDF's local path.
PDF_PATH = Path(
    r"C:\Users\asus tuf a15\Downloads\WhatsApp Image 2026-10-25 at 10.36.15 AM.pdf"
)


def main():
    if not PDF_PATH.exists():
        print("PDF file not found:", PDF_PATH)
        return

    pdf_bytes = PDF_PATH.read_bytes()

    pdf = validate_pdf(pdf_bytes)

    print("Pages:", len(pdf))

    for page_number in range(1, len(pdf) + 1):
        print(f"\nProcessing page {page_number}...")

        image_bytes = generate_page_preview(pdf, page_number)

        result = extract_text_from_image(
            image_bytes=image_bytes,
            page_number=page_number
        )

        print("Extracted text:")
        print(result["text"])

        print("Average confidence:", result["average_confidence"])

    pdf.close()


if __name__ == "__main__":
    main()