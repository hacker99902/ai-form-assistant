
import json
import logging

from groq import Groq
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.marksheet import MarksheetDetails


logger = logging.getLogger(__name__)


# Reuse the existing Groq configuration
client = Groq(
    api_key=settings.GROQ_API_KEY,
    timeout=120.0,
    max_retries=2
)


SYSTEM_PROMPT = """
You are an expert academic document information extraction system.

Your task is to extract structured information from Indian academic
marksheets and transcripts.

IMPORTANT RULES:

1. Extract information ONLY from the supplied document text.

2. Never invent student details, marks, grades, credits or results.

3. If a field is unavailable, return null.

4. Do not calculate missing marks, percentages, SGPA or CGPA.

5. Preserve student names, USN, subject codes and subject names
   exactly as they appear.

6. Identify every semester present in the document.

7. Extract every subject separately.

8. Preserve the original marks and grade information.

9. Do not confuse:
   - Maximum marks with marks obtained.
   - Internal marks with external marks.
   - SGPA with CGPA.
   - Subject grade with grade points.

10. If a transcript contains multiple semesters, include every
    semester in the semesters array.

11. If the document is a single semester marksheet, include that
    semester in the semesters array.

12. Do not assume a grading scale or calculate percentage from CGPA.

13. Confidence must represent the reliability of the extraction,
    not academic performance.

14. Use document_type:
    - "marksheet" for an individual marksheet.
    - "transcript" for a consolidated transcript.

15. Return ONLY valid JSON.
"""


def build_extraction_prompt(extracted_text: str) -> str:

    return f"""
Extract all academic information from the following document.

DOCUMENT TEXT:

---------------- DOCUMENT START ----------------

{extracted_text}

---------------- DOCUMENT END ----------------


Return JSON following this exact structure:

{{
    "document_type": "marksheet",

    "student": {{
        "full_name": null,
        "usn": null,
        "roll_number": null,
        "registration_number": null,
        "date_of_birth": null,
        "college_name": null,
        "university_name": null,
        "degree": null,
        "branch": null
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

- Use "transcript" if multiple semester records are present.
- Include all subjects visible in the document.
- Do not create empty semester records.
- If there are no subjects, return an empty subjects array.
- Use null for unavailable values.
- Do not include explanations outside the JSON.
"""


def extract_marksheet_details(
    extracted_text: str
) -> MarksheetDetails:
    """
    Extract structured academic information from marksheet
    or transcript text using Groq.

    Args:
        extracted_text: Text extracted from PDF/OCR.

    Returns:
        Validated MarksheetDetails object.
    """

    if not extracted_text or not extracted_text.strip():
        raise ValueError(
            "Extracted document text is empty."
        )

    logger.info(
        "Starting marksheet information extraction."
    )

    try:

        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": build_extraction_prompt(
                        extracted_text
                    )
                }
            ],

            response_format={
                "type": "json_object"
            },

            temperature=0.1,
            max_tokens=8000
        )

        response_content = response.choices[0].message.content

        if not response_content:
            raise ValueError(
                "Groq returned an empty response."
            )

        logger.info(
            "Groq marksheet extraction response received."
        )

        # Parse JSON
        try:
            extracted_data = json.loads(response_content)

        except json.JSONDecodeError as error:
            logger.error(
                "Invalid JSON returned by Groq: %s",
                error
            )

            raise ValueError(
                "Groq returned invalid JSON."
            ) from error

        # Validate using Pydantic
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
