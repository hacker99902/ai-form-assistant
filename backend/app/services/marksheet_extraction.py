
import json
import logging

from groq import Groq
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.marksheet import MarksheetDetails
from app.services.pii_redaction import redact_pii


logger = logging.getLogger(__name__)


# ==========================================
# GROQ CLIENT
# ==========================================

client = Groq(
    api_key=settings.GROQ_API_KEY,
    timeout=120.0,
    max_retries=2
)


# ==========================================
# SYSTEM PROMPT
# ==========================================

SYSTEM_PROMPT = """
You are an expert academic document information extraction system.

You specialize in Indian academic documents, including:

- Class 10 / SSLC marksheets
- Class 12 / PUC marksheets
- CBSE marksheets
- ICSE marksheets
- State board marksheets
- Diploma marksheets
- Engineering semester marksheets
- Consolidated university transcripts

Your task is to extract accurate, structured information
from the supplied document text.

GENERAL RULES:

1. Extract information ONLY from the supplied document.

2. Never invent student details, marks, grades, results,
   registration numbers or contact information.

3. If information is unavailable, return null.

4. Preserve names, subject names, subject codes and
   registration numbers exactly as printed.

5. Do not confuse student names with parent names.

6. Do not confuse maximum marks with marks obtained.

7. Do not confuse internal marks with external marks.

8. Do not confuse SGPA with CGPA.

9. Do not calculate missing marks, percentages or grades.

10. Confidence must represent extraction reliability,
    not academic performance.

PERSONAL INFORMATION:

Extract these fields whenever explicitly present:

- full_name
- father_name
- mother_name
- date_of_birth
- mobile_number
- email

Recognize different printed labels.

For mother's name, look for:

- Mother's Name
- Mother Name
- Name of Mother
- MOTHER
- M/O

For father's name, look for:

- Father's Name
- Father Name
- Name of Father
- FATHER
- F/O

IMPORTANT:

Do not assign a father's name to mother_name.

Do not assign a mother's name to father_name.

Do not assume that M/O or F/O always contains a complete
parent name. Extract only when the relationship is clear.

INSTITUTION INFORMATION:

Extract:

- school_name
- board
- college_name
- university_name
- degree
- branch
- stream

IDENTIFICATION INFORMATION:

Extract:

- roll_number
- registration_number
- usn

ACADEMIC INFORMATION:

1. Identify every semester present.

2. Extract every subject separately.

3. Preserve subject codes and names.

4. Extract credits, maximum marks, obtained marks,
   internal marks, external marks, grades and grade points
   whenever available.

5. Extract semester total marks and SGPA.

6. Extract overall total marks, maximum marks,
   percentage, CGPA and overall result when printed.

7. Extract year of passing.

8. Do not assume a grading scale.

DOCUMENT TYPE:

- Use "marksheet" for an individual marksheet.
- Use "transcript" for a consolidated transcript.

Return only valid JSON matching the requested structure.
Do not include explanations outside JSON.
"""


# ==========================================
# EXTRACTION PROMPT
# ==========================================

def build_extraction_prompt(extracted_text: str) -> str:

    return f"""
Extract all available student and academic information
from the following document.

DOCUMENT TEXT:

---------------- DOCUMENT START ----------------

{extracted_text}

---------------- DOCUMENT END ----------------


Return JSON using exactly this structure:

{{
    "document_type": "marksheet",

    "student": {{
        "full_name": null,
        "father_name": null,
        "mother_name": null,
        "date_of_birth": null,
        "mobile_number": null,
        "email": null,
        "school_name": null,
        "board": null,
        "roll_number": null,
        "registration_number": null,
        "usn": null,
        "college_name": null,
        "university_name": null,
        "degree": null,
        "branch": null,
        "stream": null
    }},

    "semesters": [
        {{
            "semester_number": null,
            "semester_name": null,
            "examination_month": null,
            "examination_year": null,

            "subjects": [
                {{
                    "subject_code": null,
                    "subject_name": null,
                    "credits": null,
                    "maximum_marks": null,
                    "marks_obtained": null,
                    "internal_marks": null,
                    "external_marks": null,
                    "grade": null,
                    "grade_points": null,
                    "result": null
                }}
            ],

            "total_marks_obtained": null,
            "maximum_marks": null,
            "sgpa": null,
            "result": null
        }}
    ],

    "total_marks_obtained": null,
    "maximum_marks": null,
    "percentage": null,
    "cgpa": null,
    "overall_result": null,
    "year_of_passing": null,

    "confidence": 0.0,

    "field_confidence": {{}},

    "missing_fields": []
}}


ADDITIONAL INSTRUCTIONS:

1. Extract mother's name separately from father's name.

2. Extract parent names even when they appear near
   the student's name or in the personal details section.

3. Extract school and board names from the document heading
   or institution details.

4. Extract EVERY subject visible in the document.
   Never omit a subject because its marks are missing.

5. IMPORTANT: The semesters array must contain academic
   examination records for individual marksheets too.

6. For Class 10 / SSLC marksheets:
   - Create exactly one academic record.
   - Set semester_number to null.
   - Set semester_name to "Class 10 Examination".
   - Put every Class 10 subject inside its subjects array.
   - Extract marks and maximum marks as printed.

7. For Class 12 / PUC marksheets:
   - Create one academic record for the examination.
   - Set semester_number to null.
   - Set semester_name to "Class 12 Examination".
   - Include all subjects and their marks.

8. For engineering marksheets:
   - Create separate records for each semester.
   - Preserve semester numbers and names.

9. For consolidated transcripts:
   - Include every semester separately.

10. Do not create fictional subjects, marks or grades.

11. Do not calculate missing values.

12. If subject names are available but marks are missing,
    still include the subject with null marks.

13. Extract total marks and maximum marks only when
    explicitly available in the document.

14. Return only valid JSON matching the requested structure.
"""


# ==========================================
# MARKSHEET EXTRACTION
# ==========================================

def extract_marksheet_details(
    extracted_text: str
) -> MarksheetDetails:
    """
    Extract structured student and academic information
    from marksheet or transcript text using Groq.

    PII redaction is applied locally before sending
    document text to the external model.
    """

    if not extracted_text or not extracted_text.strip():
        raise ValueError(
            "Extracted document text is empty."
        )

    logger.info(
        "Starting marksheet information extraction."
    )

    try:

        # 1. Redact sensitive information locally.
        safe_text = redact_pii(extracted_text)

        logger.info(
            "PII redaction applied before extraction."
        )

        # 2. Build extraction prompt.
        extraction_prompt = build_extraction_prompt(
            safe_text
        )

        # 3. Send sanitized document text to Groq.
        response = client.chat.completions.create(

            model=settings.GROQ_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": extraction_prompt
                }
            ],

            response_format={
                "type": "json_object"
            },

            temperature=0.1,

            max_tokens=8000
        )

        response_content = (
            response.choices[0].message.content
        )

        if not response_content:
            raise ValueError(
                "Groq returned an empty response."
            )

        logger.info(
            "Groq marksheet extraction response received."
        )

        # 4. Parse JSON.
        try:

            extracted_data = json.loads(
                response_content
            )

        except json.JSONDecodeError as error:

            logger.error(
                "Invalid JSON returned by Groq: %s",
                error
            )

            raise ValueError(
                "Groq returned invalid JSON."
            ) from error

        # 5. Validate extracted information.
        try:

            validated_data = MarksheetDetails.model_validate(
                extracted_data
            )

        except ValidationError as error:

            logger.error(
                "Marksheet schema validation failed: %s",
                error
            )

            raise ValueError(
                "Extracted marksheet data failed validation."
            ) from error

        logger.info(
            "Marksheet extraction and validation completed."
        )

        return validated_data

    except Exception:

        logger.exception(
            "Marksheet extraction failed."
        )

        raise
