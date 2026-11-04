import uuid
import re
from app.services.aadhaar_service import extract_aadhaar_details
from app.core.encryption import encrypt_value
from uuid import UUID
from app.services.address_quality_service import assess_address_quality
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
from app.services.classification_service import classify_documents

import logging

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def split_extracted_text(extracted_text: str) -> dict[int, str]:
    """Split combined extracted text into individual page texts."""

    page_pattern = re.compile(
        r"--- Page (\d+) ---\s*\n(.*?)(?=\n\n--- Page \d+ ---|\Z)",
        re.DOTALL
    )

    page_texts = {}

    for match in page_pattern.finditer(extracted_text or ""):
        page_number = int(match.group(1))
        page_text = match.group(2).strip()

        page_texts[page_number] = page_text

    return page_texts

def find_source_page(value: str, pages: list[dict]) -> int | None:
    """Find the page containing an extracted value."""

    if not value:
        return None

    normalized_value = " ".join(value.lower().split())

    for page in pages:
        page_text = " ".join(
            page["text"].lower().split()
        )

        if normalized_value in page_text:
            return page["page_number"]

        # Also support matching Aadhaar digits despite spaces.
        digits = "".join(
            char for char in value if char.isdigit()
        )

        page_digits = "".join(
            char for char in page["text"] if char.isdigit()
        )

        if len(digits) == 12 and digits in page_digits:
            return page["page_number"]

    return None



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
        logger.exception("Could not create processing session")

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


@router.post("/{document_id}/classify")
def classify_uploaded_document(document_id: UUID):
    """
    Classify an uploaded PDF using OpenRouter
    and save the classified document groups in Neon.
    """

    try:
        pool = get_db_pool()

        # 1. Retrieve and lock the existing extracted document.
        with pool.connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        id,
                        document_type,
                        extraction_status,
                        extracted_text,
                        extraction_metadata
                    FROM extracted_documents
                    WHERE document_id = %s
                    ORDER BY created_at, id
                    FOR UPDATE
                """, (document_id,))

                records = cursor.fetchall()

                if not records:
                    raise HTTPException(
                        status_code=404,
                        detail="Extracted document not found"
                    )

                # This endpoint currently expects one aggregate
                # unclassified row created by the upload endpoint.
                if len(records) != 1:
                    raise HTTPException(
                        status_code=409,
                        detail="Document does not have one unclassified record"
                    )

                record = records[0]

                (
                    extracted_document_id,
                    document_type,
                    extraction_status,
                    extracted_text,
                    extraction_metadata
                ) = record

                if document_type != "unclassified":
                    raise HTTPException(
                        status_code=409,
                        detail="Document has already been classified"
                    )

                if extraction_status != "completed":
                    raise HTTPException(
                        status_code=409,
                        detail="Document extraction is not completed"
                    )

                if not extracted_text:
                    raise HTTPException(
                        status_code=400,
                        detail="No extracted text available"
                    )

                # 2. Reconstruct individual page text.
                metadata = extraction_metadata or {}

                total_pages = metadata.get("total_pages", 0)

                if not total_pages:
                    raise HTTPException(
                        status_code=400,
                        detail="Page metadata is missing"
                    )

                stored_page_texts = split_extracted_text(
                    extracted_text
                )

                pages = []

                for page_number in range(1, total_pages + 1):
                    pages.append({
                        "page_number": page_number,
                        "text": stored_page_texts.get(
                            page_number, ""
                        )
                    })

                # 3. Run AI classification.
                try:
                    classification = classify_documents(pages)

                except Exception as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=f"AI classification failed: {str(exc)}"
                    ) from exc

                # 4. Prepare database records.
                classified_groups = classification.documents

                if not classified_groups:
                    raise HTTPException(
                        status_code=422,
                        detail="AI returned no classified documents"
                    )

                classified_records = []

                for index, group in enumerate(classified_groups):

                    group_pages = [
                        page for page in pages
                        if group.start_page <= page["page_number"] <= group.end_page
                    ]

                    group_text = "\n\n".join(
                        f"--- Page {page['page_number']} ---\n{page['text']}"
                        for page in group_pages
                        if page["text"].strip()
                    )

                    group_metadata = {
                        **metadata,
                        "classification": {
                            "document_type": group.document_type,
                            "confidence": group.confidence,
                            "evidence": group.evidence,
                            "start_page": group.start_page,
                            "end_page": group.end_page,
                        }
                    }

                    classified_records.append({
                        "id": (
                            extracted_document_id
                            if index == 0
                            else uuid.uuid4()
                        ),
                        "document_type": group.document_type,
                        "start_page": group.start_page,
                        "end_page": group.end_page,
                        "extracted_text": group_text,
                        "extraction_metadata": group_metadata,
                    })

                # 5. Update the original row and insert additional groups.
                first_record = classified_records[0]

                cursor.execute("""
                    UPDATE extracted_documents
                    SET
                        document_type = %s,
                        start_page = %s,
                        end_page = %s,
                        extracted_text = %s,
                        extraction_metadata = %s
                    WHERE id = %s
                """, (
                    first_record["document_type"],
                    first_record["start_page"],
                    first_record["end_page"],
                    first_record["extracted_text"],
                    Jsonb(first_record["extraction_metadata"]),
                    first_record["id"]
                ))

                for classified_record in classified_records[1:]:

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
                        classified_record["id"],
                        document_id,
                        classified_record["document_type"],
                        classified_record["start_page"],
                        classified_record["end_page"],
                        "completed",
                        classified_record["extracted_text"],
                        Jsonb(classified_record["extraction_metadata"])
                    ))

        # 6. Return classification summary.
        return {
            "message": "Document classification completed and saved successfully",
            "document_id": str(document_id),
            "total_classified_documents": len(classified_records),
            "documents": [
                {
                    "extracted_document_id": str(item["id"]),
                    "document_type": item["document_type"],
                    "start_page": item["start_page"],
                    "end_page": item["end_page"],
                    "confidence": item["extraction_metadata"]["classification"]["confidence"],
                    "evidence": item["extraction_metadata"]["classification"]["evidence"],
                }
                for item in classified_records
            ]
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Document classification or database save failed"
        )

        raise HTTPException(
            status_code=500,
            detail="Could not classify and save document"
        )


@router.post("/extracted/{extracted_document_id}/extract-aadhaar")
def extract_aadhaar_from_document(
    extracted_document_id: UUID
):
    """Extract Aadhaar details, assess address quality,
    and save extracted fields and review suggestions in Neon.
    """

    try:
        pool = get_db_pool()

        # --------------------------------------------------
        # 1. Retrieve the classified document
        # --------------------------------------------------

        with pool.connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        ed.id,
                        ed.document_id,
                        ed.document_type,
                        ed.start_page,
                        ed.end_page,
                        ed.extracted_text,
                        ed.extraction_metadata,
                        d.session_id
                    FROM extracted_documents ed
                    JOIN documents d
                        ON d.id = ed.document_id
                    WHERE ed.id = %s
                """, (extracted_document_id,))

                record = cursor.fetchone()

        if not record:
            raise HTTPException(
                status_code=404,
                detail="Extracted document not found"
            )

        (
            extracted_id,
            document_id,
            document_type,
            start_page,
            end_page,
            extracted_text,
            extraction_metadata,
            session_id
        ) = record

        # --------------------------------------------------
        # 2. Validate document type
        # --------------------------------------------------

        if document_type != "identity_document":
            raise HTTPException(
                status_code=400,
                detail=(
                    "This document is not classified as "
                    "an identity document"
                )
            )

        if not extracted_text:
            raise HTTPException(
                status_code=400,
                detail="No extracted text available"
            )

        # --------------------------------------------------
        # 3. Reconstruct individual pages
        # --------------------------------------------------

        stored_pages = split_extracted_text(extracted_text)

        pages = []

        for page_number in range(start_page, end_page + 1):
            pages.append({
                "page_number": page_number,
                "text": stored_pages.get(page_number, "")
            })

        # --------------------------------------------------
        # 4. Run Aadhaar extraction
        # --------------------------------------------------

        details = extract_aadhaar_details(pages)

        # --------------------------------------------------
        # 5. Prepare structured address components
        # --------------------------------------------------

        components = details.address_components

        address_components = {
            "house_number": components.house_number,
            "street": components.street,
            "locality": components.locality,
            "city": components.city,
            "district": components.district,
            "state": components.state,
            "pincode": components.pincode,
        }

        # --------------------------------------------------
        # 6. Assess address quality
        # --------------------------------------------------

        address_quality = assess_address_quality(
            address=details.address,
            components=address_components,
        )

        # --------------------------------------------------
        # 7. Prepare extracted fields
        # --------------------------------------------------

        field_values = {
            "full_name": details.full_name,
            "aadhaar_number": details.aadhaar_number,
            "date_of_birth": details.date_of_birth,
            "year_of_birth": details.year_of_birth,
            "gender": details.gender,
            "address": details.address,
            "father_or_husband_name": (
                details.father_or_husband_name
            ),

            # Structured address fields
            "address_house_number": components.house_number,
            "address_street": components.street,
            "address_locality": components.locality,
            "address_city": components.city,
            "address_district": components.district,
            "address_state": components.state,
            "address_pincode": components.pincode,
        }

        categories = {
            "full_name": "personal",
            "aadhaar_number": "identity",
            "date_of_birth": "personal",
            "year_of_birth": "personal",
            "gender": "personal",
            "address": "address",
            "father_or_husband_name": "personal",

            "address_house_number": "address",
            "address_street": "address",
            "address_locality": "address",
            "address_city": "address",
            "address_district": "address",
            "address_state": "address",
            "address_pincode": "address",
        }

        # --------------------------------------------------
        # 8. Save fields and quality report in one transaction
        # --------------------------------------------------

        saved_fields = []

        with pool.connection() as conn:
            with conn.cursor() as cursor:

                # Lock the extracted document to prevent
                # concurrent duplicate extraction.

                cursor.execute("""
                    SELECT id
                    FROM extracted_documents
                    WHERE id = %s
                    FOR UPDATE
                """, (extracted_id,))

                if not cursor.fetchone():
                    raise HTTPException(
                        status_code=404,
                        detail="Extracted document no longer exists"
                    )

                # Check whether fields already exist.

                cursor.execute("""
                    SELECT field_name
                    FROM profile_fields
                    WHERE extracted_document_id = %s
                """, (extracted_id,))

                existing_fields = {
                    row[0] for row in cursor.fetchall()
                }

                if existing_fields:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Fields have already been extracted "
                            "for this document"
                        )
                    )

                # Save extracted profile fields.

                for field_name, value in field_values.items():

                    if value is None or not str(value).strip():
                        continue

                    original_value = str(value)

                    # Encrypt Aadhaar before database storage.

                    if field_name == "aadhaar_number":
                        stored_value = (
                            "fernet:v1:"
                            + encrypt_value(original_value)
                        )
                    else:
                        stored_value = original_value

                    # Find the source page using the original value.

                    source_page = find_source_page(
                        original_value,
                        pages
                    )

                    cursor.execute("""
                        INSERT INTO profile_fields (
                            id,
                            session_id,
                            document_id,
                            extracted_document_id,
                            field_name,
                            field_category,
                            extracted_value,
                            corrected_value,
                            source_page,
                            confidence,
                            status
                        )
                        VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, NULL, %s, %s, %s
                        )
                    """, (
                        uuid.uuid4(),
                        session_id,
                        document_id,
                        extracted_id,
                        field_name,
                        categories[field_name],
                        stored_value,
                        source_page,
                        details.field_confidence.get(
                            field_name,
                            details.confidence
                        ),
                        "needs_review"
                    ))

                    saved_fields.append(field_name)

                # Save address-quality assessment in JSONB.
                # This does not overwrite extracted profile values.

                cursor.execute("""
                    UPDATE extracted_documents
                    SET extraction_metadata =
                        COALESCE(
                            extraction_metadata,
                            '{}'::jsonb
                        ) || %s
                    WHERE id = %s
                """, (
                    Jsonb({
                        "address_quality": address_quality
                    }),
                    extracted_id
                ))

        # --------------------------------------------------
        # 9. Mask Aadhaar number for API response
        # --------------------------------------------------

        masked_aadhaar = None

        if details.aadhaar_number:
            masked_aadhaar = (
                "XXXX XXXX "
                + details.aadhaar_number[-4:]
            )

        # --------------------------------------------------
        # 10. Return extraction and quality report
        # --------------------------------------------------

        return {
            "message": (
                "Aadhaar information extracted and saved"
            ),

            "extracted_document_id": str(extracted_id),

            "document_type": document_type,

            "fields_saved": saved_fields,

            "details": {
                "full_name": details.full_name,
                "aadhaar_number": masked_aadhaar,
                "date_of_birth": details.date_of_birth,
                "year_of_birth": details.year_of_birth,
                "gender": details.gender,
                "address": details.address,
                "address_components": address_components,
                "father_or_husband_name": (
                    details.father_or_husband_name
                ),
                "confidence": details.confidence,
                "missing_fields": details.missing_fields,
            },

            "address_quality": address_quality,

            "verification_status": "needs_review"
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Aadhaar extraction or database storage failed"
        )

        raise HTTPException(
            status_code=500,
            detail="Aadhaar extraction or database storage failed"
        )
