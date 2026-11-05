
import re
import json
import logging

from app.core.database import get_db_pool
from app.services.classification_service import classify_documents


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def split_extracted_text(extracted_text: str, page_metadata: list) -> list:
    """
    Recover individual page text using the stored page markers.
    """

    pages = []

    for page in page_metadata:
        page_number = page.get("page_number")

        if page_number is None:
            logger.warning("Page metadata missing page_number")
            continue

        marker = f"--- Page {page_number} ---"

        match = re.search(
            re.escape(marker) + r"\s*\n?",
            extracted_text
        )

        if not match:
            logger.warning("Could not find text for page %s", page_number)
            text = ""
        else:
            start = match.end()

            next_marker_pattern = (
                r"\n?\s*--- Page \d+ ---"
            )

            next_match = re.search(
                next_marker_pattern,
                extracted_text[start:]
            )

            if next_match:
                end = start + next_match.start()
            else:
                end = len(extracted_text)

            text = extracted_text[start:end].strip()

        pages.append({
            "page_number": page_number,
            "text": text
        })

    return pages


def main():

    pool = get_db_pool()
    pool.open(wait=True)

    try:
        # 1. Fetch the latest unclassified document.
        with pool.connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        id,
                        extracted_text,
                        extraction_metadata
                    FROM extracted_documents
                    WHERE document_type = 'unclassified'
                    ORDER BY created_at DESC
                    LIMIT 1
                """)

                row = cursor.fetchone()

        if not row:
            print("\nNo unclassified document found.")
            print(
                "Upload a fresh PDF through your upload API "
                "and run this test again."
            )
            return

        extracted_document_id, extracted_text, metadata = row

        print("\nDocument ID:", extracted_document_id)

        # 2. Validate stored extraction data.
        if not extracted_text:
            print("No extracted text found.")
            return

        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        page_metadata = metadata.get("pages", [])

        if not page_metadata:
            print("No page metadata found.")
            return

        # 3. Recover individual pages.
        pages = split_extracted_text(
            extracted_text,
            page_metadata
        )

        if not pages:
            print("No pages could be recovered.")
            return

        print("\nTotal pages:", len(pages))

        for page in pages:
            print(
                f"Page {page['page_number']}: "
                f"{len(page['text'])} characters"
            )

        # 4. Run classification.
        print("\nRunning Groq classification...\n")

        result = classify_documents(pages)

        # 5. Display classification results.
        if not result.documents:
            print("Classifier returned no documents.")
            return

        print("=" * 60)
        print("CLASSIFICATION RESULTS")
        print("=" * 60)

        for index, document in enumerate(result.documents, start=1):

            print(f"\nDocument {index}")
            print("Type:", document.document_type)
            print("Subtype:", document.document_subtype)
            print(
                "Pages:",
                document.start_page,
                "-",
                document.end_page
            )
            print("Confidence:", document.confidence)
            print("Evidence:", document.evidence)
            print("-" * 60)

        print("\nClassification completed successfully.")

    except Exception:
        logger.exception("Classification test failed.")
        raise

    finally:
        pool.close()


if __name__ == "__main__":
    main()
