import uuid
import re
from app.services.aadhaar_service import extract_aadhaar_details
from app.core.encryption import encrypt_value
from uuid import UUID
from app.services.address_quality_service import assess_address_quality
from psycopg.types.json import Jsonb
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.schemas.profile import UpdateProfileFieldsRequest
import uuid
from psycopg.types.json import Jsonb
from app.core.encryption import decrypt_value
from app.core.database import get_db_pool
import logging
logger = logging.getLogger(__name__)
from app.services.pdf_service import (
    validate_pdf,
    extract_pdf_metadata,
    extract_page_text,
    generate_page_preview,
)
from app.services.marksheet_extraction import (
    extract_marksheet_details
)
from app.services.ocr_service import extract_text_from_image
from app.services.classification_service import classify_documents
from app.schemas.marksheet import MarksheetCorrectionRequest

from app.services.resume_extraction import extract_resume_details
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

def recalculate_marksheet_totals(data: dict) -> dict:
    """
    Recalculate semester totals and overall totals
    using the subject marks.
    """

    semesters = data.get("semesters", [])

    for semester in semesters:
        subjects = semester.get("subjects", [])

        # Recalculate semester obtained marks
        marks = [s.get("marks_obtained") for s in subjects]

        if subjects and all(mark is not None for mark in marks):
            semester["total_marks_obtained"] = sum(marks)

        # Recalculate semester maximum marks
        maximums = [s.get("maximum_marks") for s in subjects]

        if subjects and all(mark is not None for mark in maximums):
            semester["maximum_marks"] = sum(maximums)

    # Recalculate overall totals only when all semester totals exist
    if semesters and all(
        s.get("total_marks_obtained") is not None
        for s in semesters
    ):
        data["total_marks_obtained"] = sum(
            s["total_marks_obtained"] for s in semesters
        )

    if semesters and all(
        s.get("maximum_marks") is not None
        for s in semesters
    ):
        data["maximum_marks"] = sum(
            s["maximum_marks"] for s in semesters
        )

    # Calculate percentage when maximum marks are available
    total = data.get("total_marks_obtained")
    maximum = data.get("maximum_marks")

    if total is not None and maximum is not None and maximum > 0:
        data["percentage"] = round((total / maximum) * 100, 2)

    return data

def recalculate_marksheet_totals(data: dict) -> dict:
    """Recalculate semester and overall marks totals."""

    semesters = data.get("semesters", [])

    for semester in semesters:
        subjects = semester.get("subjects", [])

        marks = [s.get("marks_obtained") for s in subjects]
        maximums = [s.get("maximum_marks") for s in subjects]

        if subjects and all(mark is not None for mark in marks):
            semester["total_marks_obtained"] = sum(marks)

        if subjects and all(mark is not None for mark in maximums):
            semester["maximum_marks"] = sum(maximums)

    if semesters and all(
        s.get("total_marks_obtained") is not None for s in semesters
    ):
        data["total_marks_obtained"] = sum(
            s["total_marks_obtained"] for s in semesters
        )

    if semesters and all(
        s.get("maximum_marks") is not None for s in semesters
    ):
        data["maximum_marks"] = sum(
            s["maximum_marks"] for s in semesters
        )

    total = data.get("total_marks_obtained")
    maximum = data.get("maximum_marks")

    if total is not None and maximum is not None and maximum > 0:
        data["percentage"] = round((total / maximum) * 100, 2)

    return data


def reject_placeholder_values(data):
    """Reject empty and common Swagger placeholder strings."""

    if isinstance(data, dict):
        for value in data.values():
            reject_placeholder_values(value)

    elif isinstance(data, list):
        for value in data:
            reject_placeholder_values(value)

    elif isinstance(data, str):
        invalid_values = {
            "",
            "string",
            "null",
            "none",
            "undefined"
        }

        if data.strip().lower() in invalid_values:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid placeholder value: {data!r}"
            )


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
                            "document_subtype": group.document_subtype,
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
                        "document_subtype": group.document_subtype,
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
                    "document_subtype": item["document_subtype"],
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

@router.get("/extracted/{extracted_document_id}/review")
def get_document_for_review(extracted_document_id: UUID):
    """
    Retrieve extracted profile fields for user review.
    Aadhaar numbers are never returned in full.
    """

    try:
        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.cursor() as cursor:

                # 1. Retrieve document information.
                cursor.execute("""
                    SELECT
                        ed.id,
                        ed.document_type,
                        ed.start_page,
                        ed.end_page,
                        ed.extraction_metadata,
                        d.filename
                    FROM extracted_documents ed
                    JOIN documents d
                        ON d.id = ed.document_id
                    WHERE ed.id = %s
                """, (extracted_document_id,))

                document = cursor.fetchone()

                if not document:
                    raise HTTPException(
                        status_code=404,
                        detail="Extracted document not found"
                    )

                (
                    extracted_id,
                    document_type,
                    start_page,
                    end_page,
                    extraction_metadata,
                    filename
                ) = document

                # 2. Retrieve extracted profile fields.
                cursor.execute("""
                    SELECT
                        field_name,
                        extracted_value,
                        corrected_value,
                        source_page,
                        confidence,
                        status
                    FROM profile_fields
                    WHERE extracted_document_id = %s
                    ORDER BY field_name
                """, (extracted_document_id,))

                rows = cursor.fetchall()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail="No extracted fields found for review"
            )

        # 3. Prepare fields for the review interface.
        fields = {}

        for row in rows:

            (
                field_name,
                extracted_value,
                corrected_value,
                source_page,
                confidence,
                status
            ) = row

            # Prefer a corrected value when one exists.
            value = (
                corrected_value
                if corrected_value is not None
                else extracted_value
            )

            # Aadhaar is encrypted in the database.
            # Never expose its ciphertext or full number.
            if field_name == "aadhaar_number":
                value = "XXXX XXXX XXXX"

            fields[field_name] = {
                "value": value,
                "status": status,
                "confidence": float(confidence)
                    if confidence is not None else None,
                "source_page": source_page
            }

        # 4. Retrieve address quality information.
        metadata = extraction_metadata or {}

        address_quality = metadata.get(
            "address_quality",
            {}
        )

        # 5. Return review information.
        return {
            "message": "Document review information retrieved",
            "extracted_document_id": str(extracted_id),
            "document_type": document_type,
            "filename": filename,
            "page_range": {
                "start_page": start_page,
                "end_page": end_page
            },
            "verification_status": "needs_review",
            "fields": fields,
            "address_quality": address_quality
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Could not retrieve document review information"
        )

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve document review information"
        )


@router.put("/extracted/{extracted_document_id}/fields")
def update_extracted_fields(
    extracted_document_id: UUID,
    request: UpdateProfileFieldsRequest
):
    """
    Save user-corrected values without overwriting
    the original AI-extracted values.
    """

    try:
        pool = get_db_pool()
        updated_fields = []

        with pool.connection() as conn:
            with conn.cursor() as cursor:

                # 1. Lock the document's existing profile fields.
                cursor.execute("""
                    SELECT field_name
                    FROM profile_fields
                    WHERE extracted_document_id = %s
                    FOR UPDATE
                """, (extracted_document_id,))

                existing_fields = {
                    row[0] for row in cursor.fetchall()
                }

                if not existing_fields:
                    raise HTTPException(
                        status_code=404,
                        detail="No extracted profile fields found"
                    )

                # 2. Ensure every requested field belongs
                # to this extracted document.
                unavailable_fields = (
                    set(request.fields) - existing_fields
                )

                if unavailable_fields:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "error": "Some fields were not found",
                            "fields": sorted(unavailable_fields)
                        }
                    )

                # 3. Save corrections.
                for field_name, value in request.fields.items():

                    corrected_value = value.strip()

                    # Normalize and encrypt Aadhaar.
                    if field_name == "aadhaar_number":

                        corrected_value = "".join(
                            char for char in corrected_value
                            if char.isdigit()
                        )

                        corrected_value = (
                            "fernet:v1:"
                            + encrypt_value(corrected_value)
                        )

                    cursor.execute("""
                        UPDATE profile_fields
                        SET
                            corrected_value = %s,
                            status = 'corrected'
                        WHERE
                            extracted_document_id = %s
                            AND field_name = %s
                    """, (
                        corrected_value,
                        extracted_document_id,
                        field_name
                    ))

                    if cursor.rowcount != 1:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Could not update {field_name}"
                        )

                    updated_fields.append(field_name)

        return {
            "message": "Corrected information saved successfully",
            "extracted_document_id": str(
                extracted_document_id
            ),
            "updated_fields": updated_fields,
            "field_status": "corrected"
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Could not update extracted profile fields"
        )

        raise HTTPException(
            status_code=500,
            detail="Could not update extracted profile fields"
        )


@router.post(
    "/extracted/{extracted_document_id}/fields/{field_name}/verify"
)
def verify_profile_field(
    extracted_document_id: UUID,
    field_name: str
):
    """Verify one extracted or corrected profile field."""

    try:
        from app.schemas.profile import ALLOWED_PROFILE_FIELDS

        # 1. Validate field name.
        if field_name not in ALLOWED_PROFILE_FIELDS:
            raise HTTPException(
                status_code=400,
                detail="Unsupported profile field"
            )

        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.cursor() as cursor:

                # 2. Retrieve and lock the field.
                cursor.execute("""
                    SELECT
                        id,
                        extracted_value,
                        corrected_value,
                        status
                    FROM profile_fields
                    WHERE extracted_document_id = %s
                      AND field_name = %s
                    FOR UPDATE
                """, (
                    extracted_document_id,
                    field_name
                ))

                record = cursor.fetchone()

                if not record:
                    raise HTTPException(
                        status_code=404,
                        detail="Profile field not found"
                    )

                (
                    field_id,
                    extracted_value,
                    corrected_value,
                    current_status
                ) = record

                # 3. Prevent verification of missing fields.
                effective_value = (
                    corrected_value
                    if corrected_value is not None
                    else extracted_value
                )

                if (
                    effective_value is None
                    or not str(effective_value).strip()
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot verify an empty field"
                    )

                # 4. Prevent duplicate verification.
                if current_status == "verified":
                    raise HTTPException(
                        status_code=409,
                        detail="This field is already verified"
                    )

                if current_status == "missing":
                    raise HTTPException(
                        status_code=400,
                        detail="Missing fields cannot be verified"
                    )

                # 5. Update verification status.
                cursor.execute("""
                    UPDATE profile_fields
                    SET
                        status = 'verified',
                        verified_at = NOW()
                    WHERE id = %s
                """, (field_id,))

                # 6. Record verification history.
                # Do not duplicate personal information in the audit log.
                cursor.execute("""
                    INSERT INTO verification_history (
                        id,
                        field_id,
                        old_value,
                        new_value,
                        action
                    )
                    VALUES (
                        %s,
                        %s,
                        NULL,
                        NULL,
                        'verified'
                    )
                """, (
                    uuid.uuid4(),
                    field_id
                ))

        return {
            "message": "Field verified successfully",
            "extracted_document_id": str(
                extracted_document_id
            ),
            "field_name": field_name,
            "status": "verified"
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Could not verify profile field"
        )

        raise HTTPException(
            status_code=500,
            detail="Could not verify profile field"
        )

@router.post("/extracted/{extracted_document_id}/save-profile")

def save_verified_profile(extracted_document_id: UUID):

    pool = get_db_pool()

    try:
        with pool.connection() as conn:
            with conn.cursor() as cursor:

                # 1. Get the processing session associated with this document
                cursor.execute(
                    """
                    SELECT d.session_id
                    FROM extracted_documents ed
                    JOIN documents d ON d.id = ed.document_id
                    WHERE ed.id = %s
                    FOR UPDATE OF ed, d
                    """,
                    (extracted_document_id,)
                )

                document = cursor.fetchone()

                if not document:
                    raise HTTPException(
                        status_code=404,
                        detail="Extracted document not found"
                    )

                session_id = document[0]

                # 2. Fetch all extracted profile fields
                cursor.execute(
                    """
                    SELECT
                        field_name,
                        extracted_value,
                        corrected_value,
                        status
                    FROM profile_fields
                    WHERE extracted_document_id = %s
                    ORDER BY field_name
                    FOR UPDATE
                    """,
                    (extracted_document_id,)
                )

                rows = cursor.fetchall()

                if not rows:
                    raise HTTPException(
                        status_code=404,
                        detail="No profile fields found"
                    )

                # 3. Ensure every field has been verified
                unverified_fields = [
                    row[0]
                    for row in rows
                    if row[3] != "verified"
                ]

                if unverified_fields:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "message": "All fields must be verified before saving the profile",
                            "unverified_fields": unverified_fields
                        }
                    )

                # 4. Build the consolidated profile
                profile_data = {}

                for field_name, extracted_value, corrected_value, status in rows:

                    value = (
                        corrected_value
                        if corrected_value is not None
                        else extracted_value
                    )

                    if value is None or not str(value).strip():
                        raise HTTPException(
                            status_code=400,
                            detail=f"Field '{field_name}' has an empty value"
                        )

                    # Keep Aadhaar encrypted in profile_data
                    if field_name == "aadhaar_number":

                        if not value.startswith("fernet:v1:"):
                            raise HTTPException(
                                status_code=500,
                                detail="Aadhaar must be encrypted before profile storage"
                            )

                    profile_data[field_name] = value

                # 5. Prevent duplicate profile creation
                cursor.execute(
                    """
                    SELECT id
                    FROM verified_profiles
                    WHERE session_id = %s
                    """,
                    (session_id,)
                )

                existing_profile = cursor.fetchone()

                if existing_profile:
                    raise HTTPException(
                        status_code=409,
                        detail="A profile already exists for this session"
                    )

                # 6. Save the consolidated profile as a draft
                profile_id = uuid.uuid4()

                cursor.execute(
                    """
                    INSERT INTO verified_profiles (
                        id,
                        session_id,
                        profile_data,
                        status,
                        approved_at
                    )
                    VALUES (%s, %s, %s, 'draft', NULL)
                    RETURNING id, status, created_at
                    """,
                    (
                        profile_id,
                        session_id,
                        Jsonb(profile_data)
                    )
                )

                saved_profile = cursor.fetchone()

        return {
            "message": "Verified profile saved successfully",
            "profile_id": str(saved_profile[0]),
            "session_id": str(session_id),
            "status": saved_profile[1],
            "created_at": saved_profile[2].isoformat()
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to save verified profile")

        raise HTTPException(
            status_code=500,
            detail="An error occurred while saving the verified profile"
        )

@router.get("/profiles/{profile_id}")

def get_saved_profile(profile_id: UUID):

    pool = get_db_pool()

    try:
        with pool.connection() as conn:
            with conn.cursor() as cursor:

                # 1. Retrieve the saved profile
                cursor.execute(
                    """
                    SELECT
                        id,
                        session_id,
                        profile_data,
                        status,
                        approved_at,
                        created_at
                    FROM verified_profiles
                    WHERE id = %s
                    """,
                    (profile_id,)
                )

                profile = cursor.fetchone()

                if not profile:
                    raise HTTPException(
                        status_code=404,
                        detail="Profile not found"
                    )

        # 2. Unpack the database result
        (
            saved_profile_id,
            session_id,
            profile_data,
            status,
            approved_at,
            created_at
        ) = profile

        # 3. Convert JSONB into a Python dictionary
        profile_data = dict(profile_data)

        # 4. Decrypt Aadhaar internally and mask it
        if profile_data.get("aadhaar_number"):

            encrypted_value = profile_data["aadhaar_number"]

            if not encrypted_value.startswith("fernet:v1:"):
                raise HTTPException(
                    status_code=500,
                    detail="Unexpected Aadhaar storage format"
                )

            encrypted_value = encrypted_value.removeprefix("fernet:v1:")

            try:
                aadhaar = decrypt_value(encrypted_value)

            except ValueError:
                raise HTTPException(
                    status_code=500,
                    detail="Could not retrieve Aadhaar information"
                )

            digits = "".join(
                char for char in aadhaar if char.isdigit()
            )

            profile_data["aadhaar_number"] = (
                f"XXXX XXXX {digits[-4:]}"
                if len(digits) == 12
                else "XXXX XXXX XXXX"
            )

        # 5. Return the profile safely
        return {
            "message": "Profile retrieved successfully",
            "profile_id": str(saved_profile_id),
            "session_id": str(session_id),
            "status": status,
            "approved_at": (
                approved_at.isoformat()
                if approved_at else None
            ),
            "created_at": created_at.isoformat(),
            "profile_data": profile_data
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to retrieve saved profile")

        raise HTTPException(
            status_code=500,
            detail="An error occurred while retrieving the profile"
        )


@router.post("/profiles/{profile_id}/approve")
def approve_saved_profile(profile_id: UUID):

    pool = get_db_pool()

    try:
        with pool.connection() as conn:
            with conn.cursor() as cursor:

                # 1. Find and lock the profile
                cursor.execute(
                    """
                    SELECT id, status
                    FROM verified_profiles
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (profile_id,)
                )

                profile = cursor.fetchone()

                if not profile:
                    raise HTTPException(
                        status_code=404,
                        detail="Profile not found"
                    )

                saved_profile_id, current_status = profile

                # 2. Prevent duplicate approval
                if current_status == "approved":
                    raise HTTPException(
                        status_code=409,
                        detail="Profile has already been approved"
                    )

                if current_status != "draft":
                    raise HTTPException(
                        status_code=400,
                        detail="Only draft profiles can be approved"
                    )

                # 3. Approve the profile
                cursor.execute(
                    """
                    UPDATE verified_profiles
                    SET
                        status = 'approved',
                        approved_at = NOW()
                    WHERE id = %s
                    RETURNING id, status, approved_at
                    """,
                    (profile_id,)
                )

                approved_profile = cursor.fetchone()

        return {
            "message": "Profile approved successfully",
            "profile_id": str(approved_profile[0]),
            "status": approved_profile[1],
            "approved_at": approved_profile[2].isoformat()
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to approve profile")

        raise HTTPException(
            status_code=500,
            detail="An error occurred while approving the profile"
        )

@router.post("/extracted/{extracted_document_id}/extract-marksheet")
def extract_marksheet_from_document(
    extracted_document_id: UUID
):
    """
    Extract marksheet or transcript information,
    validate it and store structured data in Neon JSONB.
    """

    try:
        pool = get_db_pool()

        # 1. Retrieve the classified document.
        with pool.connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT
                        id,
                        document_type,
                        extraction_status,
                        extracted_text
                    FROM extracted_documents
                    WHERE id = %s
                """, (extracted_document_id,))

                record = cursor.fetchone()

        if not record:
            raise HTTPException(
                status_code=404,
                detail="Extracted document not found"
            )

        (
            extracted_id,
            document_type,
            extraction_status,
            extracted_text
        ) = record

        # 2. Validate document type.
        if document_type not in ("marksheet", "transcript"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Document must be classified as "
                    "marksheet or transcript"
                )
            )

        if extraction_status != "completed":
            raise HTTPException(
                status_code=409,
                detail="Document extraction is not completed"
            )

        if not extracted_text or not extracted_text.strip():
            raise HTTPException(
                status_code=400,
                detail="No extracted text available"
            )

        # 3. Check whether extraction was already completed.
        with pool.connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT extraction_metadata
                    FROM extracted_documents
                    WHERE id = %s
                """, (extracted_id,))

                metadata_row = cursor.fetchone()

        metadata = metadata_row[0] or {}

        if metadata.get("marksheet_extraction"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Marksheet information has already "
                    "been extracted for this document"
                )
            )

        # 4. Run Groq marksheet extraction.
        details = extract_marksheet_details(extracted_text)

        # 5. Convert Pydantic model into JSON-compatible data.
        marksheet_data = details.model_dump(mode="json")

        # 6. Save structured data in Neon JSONB.
        with pool.connection() as conn:
            with conn.cursor() as cursor:

                # Lock the row before saving to prevent
                # concurrent duplicate extraction.

                cursor.execute("""
                    SELECT extraction_metadata
                    FROM extracted_documents
                    WHERE id = %s
                    FOR UPDATE
                """, (extracted_id,))

                locked_row = cursor.fetchone()

                if not locked_row:
                    raise HTTPException(
                        status_code=404,
                        detail="Extracted document no longer exists"
                    )

                current_metadata = locked_row[0] or {}

                if current_metadata.get("marksheet_extraction"):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Marksheet extraction was already "
                            "saved by another request"
                        )
                    )

                extraction_metadata = {
                    "marksheet_extraction": marksheet_data,
                    "marksheet_verification_status": "needs_review"
                }

                cursor.execute("""
                    UPDATE extracted_documents
                    SET extraction_metadata =
                        COALESCE(
                            extraction_metadata,
                            '{}'::jsonb
                        ) || %s
                    WHERE id = %s
                """, (
                    Jsonb(extraction_metadata),
                    extracted_id
                ))

        logger.info(
            "Marksheet extraction completed for document %s",
            extracted_id
        )

        # 7. Return structured extraction.
        return {
            "message": (
                "Marksheet information extracted "
                "and saved successfully"
            ),
            "extracted_document_id": str(extracted_id),
            "document_type": document_type,
            "verification_status": "needs_review",
            "details": marksheet_data
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Marksheet extraction or database storage failed"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Marksheet extraction or database storage failed"
            )
        )

@router.get("/extracted/{extracted_document_id}/review-marksheet")
def get_marksheet_for_review(extracted_document_id: UUID):
    """
    Retrieve structured marksheet/transcript information
    for user review.
    """

    try:
        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        ed.id,
                        ed.document_type,
                        ed.start_page,
                        ed.end_page,
                        ed.extraction_metadata,
                        d.filename
                    FROM extracted_documents ed
                    JOIN documents d
                        ON d.id = ed.document_id
                    WHERE ed.id = %s
                    """,
                    (extracted_document_id,)
                )

                record = cursor.fetchone()

        if not record:
            raise HTTPException(
                status_code=404,
                detail="Extracted document not found"
            )

        (
            extracted_id,
            document_type,
            start_page,
            end_page,
            extraction_metadata,
            filename
        ) = record

        # Validate document type
        if document_type not in ("marksheet", "transcript"):
            raise HTTPException(
                status_code=400,
                detail="Document is not a marksheet or transcript"
            )

        # Retrieve structured extraction
        metadata = extraction_metadata or {}

        marksheet_data = metadata.get("marksheet_extraction")

        if not marksheet_data:
            raise HTTPException(
                status_code=404,
                detail="Marksheet information has not been extracted"
            )

        verification_status = metadata.get(
            "marksheet_verification_status",
            "needs_review"
        )

        return {
            "message": "Marksheet review information retrieved successfully",
            "extracted_document_id": str(extracted_id),
            "document_type": document_type,
            "filename": filename,
            "page_range": {
                "start_page": start_page,
                "end_page": end_page
            },
            "verification_status": verification_status,
            "details": marksheet_data
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Could not retrieve marksheet review information"
        )

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve marksheet review information"
        )
@router.put("/extracted/{extracted_document_id}/update-marksheet")
def update_marksheet(
    extracted_document_id: UUID,
    request: MarksheetCorrectionRequest
):
    """Save validated user corrections and recalculate marksheet totals."""

    import copy

    try:
        pool = get_db_pool()

        # 1. Validate request values
        request_data = request.model_dump(exclude_unset=True)
        reject_placeholder_values(request_data)

        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cursor:

                    # 2. Lock and retrieve document
                    cursor.execute(
                        """
                        SELECT document_type, extraction_metadata
                        FROM extracted_documents
                        WHERE id = %s
                        FOR UPDATE
                        """,
                        (extracted_document_id,)
                    )

                    record = cursor.fetchone()

                    if not record:
                        raise HTTPException(
                            status_code=404,
                            detail="Extracted document not found"
                        )

                    document_type, metadata = record

                    if document_type not in ("marksheet", "transcript"):
                        raise HTTPException(
                            status_code=400,
                            detail="Document is not a marksheet or transcript"
                        )

                    metadata = metadata or {}
                    original_data = metadata.get("marksheet_extraction")

                    if not original_data:
                        raise HTTPException(
                            status_code=404,
                            detail="Original marksheet extraction not found"
                        )

                    # 3. Start from original data or previous corrections
                    corrected_data = copy.deepcopy(
                        metadata.get("marksheet_corrected", original_data)
                    )

                    # 4. Update student fields
                    if request.student is not None:
                        student_updates = request.student.model_dump(
                            exclude_unset=True
                        )

                        corrected_data.setdefault("student", {})
                        corrected_data["student"].update(student_updates)

                    # 5. Update individual subjects
                    for correction in request.subject_corrections:

                        semester_index = correction.semester_index
                        subject_index = correction.subject_index

                        semesters = corrected_data.get("semesters", [])

                        if semester_index >= len(semesters):
                            raise HTTPException(
                                status_code=422,
                                detail="Invalid semester_index"
                            )

                        subjects = semesters[semester_index].get(
                            "subjects", []
                        )

                        if subject_index >= len(subjects):
                            raise HTTPException(
                                status_code=422,
                                detail="Invalid subject_index"
                            )

                        updates = correction.model_dump(
                            exclude_unset=True
                        )

                        updates.pop("semester_index")
                        updates.pop("subject_index")

                        current_subject = subjects[subject_index]

                        # Determine effective marks after correction
                        effective_marks = updates.get(
                            "marks_obtained",
                            current_subject.get("marks_obtained")
                        )

                        effective_maximum = updates.get(
                            "maximum_marks",
                            current_subject.get("maximum_marks")
                        )

                        if (
                            effective_marks is not None
                            and effective_maximum is not None
                            and effective_marks > effective_maximum
                        ):
                            raise HTTPException(
                                status_code=422,
                                detail=(
                                    f"Marks obtained cannot exceed maximum "
                                    f"marks for {current_subject.get('subject_name')}"
                                )
                            )

                        # Validate internal + external marks
                        internal = updates.get(
                            "internal_marks",
                            current_subject.get("internal_marks")
                        )

                        external = updates.get(
                            "external_marks",
                            current_subject.get("external_marks")
                        )

                        if (
                            effective_marks is not None
                            and internal is not None
                            and external is not None
                            and internal + external != effective_marks
                        ):
                            raise HTTPException(
                                status_code=422,
                                detail=(
                                    "Internal marks plus external marks "
                                    "must equal marks obtained"
                                )
                            )

                        current_subject.update(updates)

                    # 6. Update manually supplied summary fields
                    summary_fields = [
                        "total_marks_obtained",
                        "maximum_marks",
                        "percentage",
                        "cgpa",
                        "overall_result",
                        "year_of_passing"
                    ]

                    for field in summary_fields:
                        if field in request_data:
                            corrected_data[field] = request_data[field]

                    # 7. Recalculate semester totals
                    semesters = corrected_data.get("semesters", [])

                    for semester in semesters:
                        subjects = semester.get("subjects", [])

                        subject_marks = [
                            subject.get("marks_obtained")
                            for subject in subjects
                        ]

                        subject_maximums = [
                            subject.get("maximum_marks")
                            for subject in subjects
                        ]

                        if subjects and all(
                            mark is not None for mark in subject_marks
                        ):
                            semester["total_marks_obtained"] = sum(
                                subject_marks
                            )

                        if subjects and all(
                            mark is not None for mark in subject_maximums
                        ):
                            semester["maximum_marks"] = sum(
                                subject_maximums
                            )

                    # 8. Recalculate overall totals
                    if semesters and all(
                        semester.get("total_marks_obtained") is not None
                        for semester in semesters
                    ):
                        corrected_data["total_marks_obtained"] = sum(
                            semester["total_marks_obtained"]
                            for semester in semesters
                        )

                    if semesters and all(
                        semester.get("maximum_marks") is not None
                        for semester in semesters
                    ):
                        corrected_data["maximum_marks"] = sum(
                            semester["maximum_marks"]
                            for semester in semesters
                        )

                    # 9. Recalculate percentage
                    total = corrected_data.get("total_marks_obtained")
                    maximum = corrected_data.get("maximum_marks")

                    if (
                        total is not None
                        and maximum is not None
                        and maximum > 0
                    ):
                        if total > maximum:
                            raise HTTPException(
                                status_code=422,
                                detail="Total marks cannot exceed maximum marks"
                            )

                        corrected_data["percentage"] = round(
                            (total / maximum) * 100,
                            2
                        )

                    # 10. Save corrected copy separately
                    metadata["marksheet_corrected"] = corrected_data
                    metadata["marksheet_verification_status"] = "needs_review"

                    cursor.execute(
                        """
                        UPDATE extracted_documents
                        SET extraction_metadata = %s
                        WHERE id = %s
                        """,
                        (
                            Jsonb(metadata),
                            extracted_document_id
                        )
                    )

        return {
            "message": "Marksheet corrections saved successfully",
            "extracted_document_id": str(extracted_document_id),
            "verification_status": "needs_review",
            "corrected_details": corrected_data
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Could not update marksheet information")

        raise HTTPException(
            status_code=500,
            detail="Could not update marksheet information"
        )



@router.post("/extracted/{extracted_document_id}/verify-marksheet")
def verify_marksheet(extracted_document_id: UUID):
    """Verify a marksheet after explicit user confirmation."""

    from datetime import datetime, timezone

    try:
        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cursor:

                    # 1. Retrieve and lock the document
                    cursor.execute(
                        """
                        SELECT document_type, extraction_metadata
                        FROM extracted_documents
                        WHERE id = %s
                        FOR UPDATE
                        """,
                        (extracted_document_id,)
                    )

                    record = cursor.fetchone()

                    if not record:
                        raise HTTPException(
                            status_code=404,
                            detail="Extracted document not found"
                        )

                    document_type, metadata = record

                    # 2. Check document type
                    if document_type not in ("marksheet", "transcript"):
                        raise HTTPException(
                            status_code=400,
                            detail="Document is not a marksheet or transcript"
                        )

                    metadata = metadata or {}

                    # 3. Prefer corrected data over original extraction
                    marksheet_data = metadata.get(
                        "marksheet_corrected"
                    ) or metadata.get("marksheet_extraction")

                    if not marksheet_data:
                        raise HTTPException(
                            status_code=404,
                            detail="No marksheet extraction found"
                        )

                    # 4. Validate essential information
                    student = marksheet_data.get("student") or {}
                    semesters = marksheet_data.get("semesters") or []

                    if not student.get("full_name"):
                        raise HTTPException(
                            status_code=422,
                            detail="Student name is missing"
                        )

                    if not semesters:
                        raise HTTPException(
                            status_code=422,
                            detail="No semester information found"
                        )

                    if not any(
                        semester.get("subjects")
                        for semester in semesters
                    ):
                        raise HTTPException(
                            status_code=422,
                            detail="No subject information found"
                        )

                    # 5. Mark as verified
                    verified_at = datetime.now(timezone.utc).isoformat()

                    metadata["marksheet_verification_status"] = "verified"
                    metadata["marksheet_verified_at"] = verified_at

                    cursor.execute(
                        """
                        UPDATE extracted_documents
                        SET extraction_metadata = %s
                        WHERE id = %s
                        """,
                        (
                            Jsonb(metadata),
                            extracted_document_id
                        )
                    )

        return {
            "message": "Marksheet verified successfully",
            "extracted_document_id": str(extracted_document_id),
            "verification_status": "verified",
            "verified_at": verified_at,
            "verified_details": marksheet_data
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Could not verify marksheet")

        raise HTTPException(
            status_code=500,
            detail="Could not verify marksheet"
        )

@router.post("/extracted/{extracted_document_id}/extract-resume")
def extract_resume_from_document(extracted_document_id: UUID):
    """
    Extract structured resume information and save it in extraction_metadata.
    The original extracted text is preserved.
    """
    try:
        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    # Lock the row so simultaneous requests cannot save
                    # duplicate resume extractions.
                    cursor.execute(
                        """
                        SELECT
                            document_type,
                            extraction_status,
                            extracted_text,
                            extraction_metadata
                        FROM extracted_documents
                        WHERE id = %s
                        FOR UPDATE
                        """,
                        (extracted_document_id,)
                    )
                    record = cursor.fetchone()

                    if not record:
                        raise HTTPException(
                            status_code=404,
                            detail="Extracted document not found"
                        )

                    (
                        document_type,
                        extraction_status,
                        extracted_text,
                        metadata
                    ) = record

                    if document_type != "resume":
                        raise HTTPException(
                            status_code=400,
                            detail="Document is not classified as a resume"
                        )

                    if extraction_status != "completed":
                        raise HTTPException(
                            status_code=409,
                            detail="Document text extraction is not completed"
                        )

                    if not extracted_text or not extracted_text.strip():
                        raise HTTPException(
                            status_code=400,
                            detail="No extracted text available"
                        )

                    metadata = metadata or {}

                    if metadata.get("resume_extraction"):
                        raise HTTPException(
                            status_code=409,
                            detail="Resume information has already been extracted"
                        )

                    # Call the resume extraction service while holding the
                    # row lock to prevent concurrent duplicate extraction.
                    details = extract_resume_details(extracted_text)
                    resume_data = details.model_dump(mode="json")

                    metadata.update({
                        "resume_extraction": resume_data,
                        "resume_verification_status": "needs_review"
                    })

                    cursor.execute(
                        """
                        UPDATE extracted_documents
                        SET extraction_metadata = %s
                        WHERE id = %s
                        """,
                        (
                            Jsonb(metadata),
                            extracted_document_id
                        )
                    )

        logger.info(
            "Resume extraction completed for document %s",
            extracted_document_id
        )

        return {
            "message": "Resume information extracted and saved successfully",
            "extracted_document_id": str(extracted_document_id),
            "document_type": "resume",
            "verification_status": "needs_review",
            "details": resume_data
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Resume extraction or database storage failed")
        raise HTTPException(
            status_code=500,
            detail="Resume extraction or database storage failed"
        )


@router.get("/extracted/{extracted_document_id}/review-resume")
def get_resume_for_review(extracted_document_id: UUID):
    """
    Retrieve extracted resume information for user review.
    Corrected data is preferred when available.
    """
    try:
        pool = get_db_pool()

        with pool.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ed.id,
                        ed.document_type,
                        ed.start_page,
                        ed.end_page,
                        ed.extraction_metadata,
                        d.filename
                    FROM extracted_documents ed
                    JOIN documents d
                        ON d.id = ed.document_id
                    WHERE ed.id = %s
                    """,
                    (extracted_document_id,)
                )
                record = cursor.fetchone()

        if not record:
            raise HTTPException(
                status_code=404,
                detail="Extracted document not found"
            )

        (
            extracted_id,
            document_type,
            start_page,
            end_page,
            extraction_metadata,
            filename
        ) = record

        if document_type != "resume":
            raise HTTPException(
                status_code=400,
                detail="Document is not classified as a resume"
            )

        metadata = extraction_metadata or {}
        resume_data = (
            metadata.get("resume_corrected")
            or metadata.get("resume_extraction")
        )

        if not resume_data:
            raise HTTPException(
                status_code=404,
                detail="Resume information has not been extracted"
            )

        verification_status = metadata.get(
            "resume_verification_status",
            "needs_review"
        )

        return {
            "message": "Resume review information retrieved successfully",
            "extracted_document_id": str(extracted_id),
            "document_type": document_type,
            "filename": filename,
            "page_range": {
                "start_page": start_page,
                "end_page": end_page
            },
            "verification_status": verification_status,
            "details": resume_data
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Could not retrieve resume review information")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve resume review information"
        )
