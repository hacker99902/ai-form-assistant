
import uuid
from uuid import UUID
from psycopg.types.json import Jsonb
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.core.database import get_db_pool

from app.services.pdf_service import (
    validate_pdf,
    extract_pdf_metadata,
    extract_page_text,
    generate_page_preview,
)

from app.services.ocr_service import extract_text_from_image

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/sessions")
def create_session():
    """Create a temporary processing session in Neon."""

    try:
        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO processing_sessions (status)
                    VALUES ('active')
                    RETURNING id, status, created_at, expires_at
                """)

                session = cursor.fetchone()

        return {
            "message": "Processing session created",
            "session": {
                "id": str(session[0]),
                "status": session[1],
                "created_at": session[2],
                "expires_at": session[3],
            }
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not create processing session"
        ) from exc


@router.post("/upload")
async def upload_document(
    session_id: UUID,
    file: UploadFile = File(...)
):
    """Upload PDF, extract text and persist everything in Neon."""

    pdf = None

    try:
        # 1. Validate file.
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF files are allowed")

        if file.content_type != "application/pdf":
            raise HTTPException(400, "Invalid content type")

        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(400, "Uploaded PDF is empty")

        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(413, "PDF exceeds 20 MB limit")

        if not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(400, "Invalid PDF file signature")

        # 2. Validate and inspect PDF.
        pdf = validate_pdf(file_bytes)

        metadata = extract_pdf_metadata(pdf)
        pages = extract_page_text(pdf)

        # 3. Extract text using OCR only when needed.
        ocr_pages = 0

        for page_data in pages:

            if not page_data["has_text"]:
                page_number = page_data["page_number"]

                image_bytes = generate_page_preview(
                    pdf,
                    page_number
                )

                ocr_result = extract_text_from_image(
                    image_bytes,
                    page_number
                )

                page_data["text"] = ocr_result["text"]
                page_data["character_count"] = len(
                    ocr_result["text"]
                )
                page_data["has_text"] = bool(
                    ocr_result["text"].strip()
                )
                page_data["source"] = "paddleocr"
                page_data["ocr_confidence"] = (
                    ocr_result["average_confidence"]
                )
                page_data["ocr_lines"] = ocr_result["lines"]

                ocr_pages += 1

        # 4. Prepare combined text and metadata.
        combined_text = "\n\n".join(
            f"--- Page {page['page_number']} ---\n{page['text']}"
            for page in pages
            if page["text"].strip()
        )

        extraction_metadata = {
            "total_pages": len(pages),
            "ocr_pages": ocr_pages,
            "text_extraction_pages": len(pages) - ocr_pages,
            "pages": [
                {
                    "page_number": page["page_number"],
                    "source": page.get("source"),
                    "character_count": page["character_count"],
                    "has_text": page["has_text"],
                    "ocr_confidence": page.get("ocr_confidence"),
                }
                for page in pages
            ]
        }

        document_id = uuid.uuid4()
        extracted_document_id = uuid.uuid4()

        # 5. Store PDF and extracted text in one transaction.
        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT id
                    FROM processing_sessions
                    WHERE id = %s
                    AND status = 'active'
                    AND expires_at > NOW()
                """, (session_id,))

                session = cursor.fetchone()

                if not session:
                    raise HTTPException(
                        status_code=404,
                        detail="Invalid or expired processing session"
                    )

                cursor.execute("""
                    INSERT INTO documents (
                        id,
                        session_id,
                        filename,
                        storage_path,
                        mime_type,
                        file_size,
                        page_count,
                        status,
                        file_data
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    document_id,
                    session_id,
                    file.filename,
                    f"neon://documents/{document_id}",
                    "application/pdf",
                    len(file_bytes),
                    metadata["page_count"],
                    "processed",
                    file_bytes
                ))

                cursor.execute("""
                    INSERT INTO extracted_documents (
                        id,
                        document_id,
                        document_type,
                        start_page,
                        end_page,
                        extraction_status,
                        extracted_text,
                        extraction_metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    extracted_document_id,
                    document_id,
                    "unclassified",
                    1,
                    metadata["page_count"],
                    "completed",
                    combined_text,
                    Jsonb(extraction_metadata)
                ))

        # 6. Return processing summary.
        return {
            "message": "PDF uploaded, extracted and stored in Neon successfully",
            "document_id": str(document_id),
            "extracted_document_id": str(extracted_document_id),
            "filename": file.filename,
            "file_size": len(file_bytes),
            "metadata": metadata,
            "processing": {
                "total_pages": len(pages),
                "ocr_pages": ocr_pages,
                "text_extraction_pages": len(pages) - ocr_pages,
                "extracted_characters": len(combined_text),
            },
            "pages": pages
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF processing or database storage failed"
        ) from exc

    finally:
        if pdf is not None:
            pdf.close()

        await file.close()
