from app.core.database import get_db_pool
from app.services.classification_service import classify_documents


pool = get_db_pool()
pool.open(wait=True)

try:
    with pool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT extracted_text, extraction_metadata
                FROM extracted_documents
                WHERE document_type = 'unclassified'
                ORDER BY created_at DESC
                LIMIT 1
            """)

            row = cursor.fetchone()

    if not row:
        print("No unclassified document found.")
        raise SystemExit

    extracted_text, metadata = row

    pages = []

    for page in metadata["pages"]:
        page_number = page["page_number"]

        # Recover individual page text from the stored extraction.
        marker = f"--- Page {page_number} ---\n"
        start = extracted_text.find(marker)

        if start == -1:
            text = ""
        else:
            start += len(marker)
            next_marker = f"\n\n--- Page {page_number + 1} ---"

            end = extracted_text.find(next_marker, start)

            if end == -1:
                end = len(extracted_text)

            text = extracted_text[start:end].strip()

        pages.append({
            "page_number": page_number,
            "text": text
        })

    print("Total pages:", len(pages))
    print("\nRunning classification...\n")

    result = classify_documents(pages)

    for document in result.documents:
        print("Type:", document.document_type)
        print("Pages:", document.start_page, "-", document.end_page)
        print("Confidence:", document.confidence)
        print("Evidence:", document.evidence)
        print("-" * 50)

finally:
    pool.close()