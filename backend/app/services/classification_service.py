import json
import logging
import re
from app.services.pii_redaction import redact_pii
from groq import Groq, APIError, RateLimitError
from pydantic import ValidationError
from app.core.config import settings
from app.schemas.classification import ClassificationResult

logger = logging.getLogger(__name__)


# Initialize Groq client.
client = Groq(
    api_key=settings.GROQ_API_KEY,
    timeout=120.0,
    max_retries=2
)

def redact_pii(text: str) -> str:
    """
    Redact sensitive personal information locally
    before sending document text to an AI provider.
    """

    if not text:
        return text

    # Aadhaar: 12 digits, optionally separated by spaces or hyphens.
    text = re.sub(
        r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)",
        "[AADHAAR_REDACTED]",
        text
    )

    # Indian mobile numbers.
    text = re.sub(
        r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)",
        "[PHONE_REDACTED]",
        text
    )

    # Email addresses.
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[EMAIL_REDACTED]",
        text
    )

    return text

SYSTEM_PROMPT = """
You are an expert document classification system.

Your task is to identify separate documents inside a combined PDF.

You will receive text extracted from individual PDF pages.
Each page includes its original page number.

Return one classification entry for each distinct document.
Group consecutive pages that belong to the same document.

--------------------------------------------------
1. ALLOWED DOCUMENT TYPES
--------------------------------------------------

You MUST use only these exact document_type values:

- identity_document
- marksheet
- transcript
- resume
- certificate
- offer_letter
- admission_letter
- study_notes
- other
- unknown

--------------------------------------------------
2. ALLOWED DOCUMENT SUBTYPES
--------------------------------------------------

You MUST use only these exact document_subtype values,
or null when a subtype cannot be identified.

IDENTITY DOCUMENTS:

- aadhaar
- pan_card
- passport
- voter_id
- driving_license
- other_identity

SCHOOL AND ACADEMIC DOCUMENTS:

- class_10
- class_12
- diploma
- undergraduate
- engineering_semester
- engineering_consolidated
- postgraduate
- academic_transcript
- other_academic

CERTIFICATES:

- academic_certificate
- professional_certificate
- course_certificate
- internship_certificate
- experience_certificate
- other_certificate

OFFER LETTERS:

- employment_offer
- internship_offer

ADMISSION LETTERS:

- college_admission_letter
- university_admission_letter

GENERAL:

- other

--------------------------------------------------
3. IMPORTANT ACADEMIC CLASSIFICATION RULES
--------------------------------------------------

These rules are especially important.

A. CLASS 10 MARKSHEET

Classify as:

document_type = "marksheet"
document_subtype = "class_10"

Evidence may include:

- Secondary School Examination
- Class X
- SSLC
- 10th Standard
- CBSE Class 10
- Subject-wise marks, grades or examination results

B. CLASS 12 MARKSHEET

Classify as:

document_type = "marksheet"
document_subtype = "class_12"

Evidence may include:

- Senior Secondary Examination
- Second Year PUC Examination
- PUC II
- Class XII
- 12th Standard
- HSC
- Subject-wise theory, practical and total marks

IMPORTANT:

A PUC or board examination document must NOT be
classified as a generic certificate merely because
its heading contains the words "Marks Statement Cum
Certificate" or "Certificate".

If it contains subject-wise examination marks,
grades, total marks or examination results,
classify it as a marksheet.

C. DIPLOMA MARKSHEET

Classify as:

document_type = "marksheet"
document_subtype = "diploma"

Use this for diploma examination results and
subject-wise diploma marks.

D. ENGINEERING SEMESTER GRADE CARD

Classify as:

document_type = "marksheet"
document_subtype = "engineering_semester"

Evidence may include:

- University or engineering college grade card
- Semester number
- Course codes and course names
- CIE and SEE marks
- Total marks
- Grade points and grades
- SGPA

A provisional semester grade card is still a
marksheet. Do not classify it as a generic certificate.

E. ENGINEERING CONSOLIDATED MARKSHEET

Classify as:

document_type = "marksheet"
document_subtype = "engineering_consolidated"

Use when the document contains consolidated academic
results across multiple semesters.

Evidence may include:

- Multiple semester results
- Overall CGPA
- Cumulative credits
- Consolidated grade statement

F. ACADEMIC TRANSCRIPT

Classify as:

document_type = "transcript"
document_subtype = "academic_transcript"

Use for formal academic transcripts that summarize
courses and grades, especially across multiple terms
or semesters.

Do not automatically classify every semester grade
card as a transcript.

G. OTHER ACADEMIC DOCUMENTS

If the document is clearly academic but does not fit
the above categories, use:

document_type = "marksheet"
document_subtype = "other_academic"

--------------------------------------------------
4. IDENTITY DOCUMENT RULES
--------------------------------------------------

For an Aadhaar card:

document_type = "identity_document"
document_subtype = "aadhaar"

For other identity documents, use the corresponding
supported subtype:

- PAN card: pan_card
- Passport: passport
- Voter ID: voter_id
- Driving licence: driving_license
- Other identity document: other_identity

--------------------------------------------------
5. CERTIFICATE CLASSIFICATION RULES
--------------------------------------------------

Use document_type = "certificate" for documents whose
primary purpose is to certify an achievement,
qualification, participation, employment or
course completion.

A. ACADEMIC CERTIFICATE

Classify as:

document_type = "certificate"
document_subtype = "academic_certificate"

Examples:

- Academic achievement certificate
- Educational qualification certificate
- Degree completion certificate
- Academic excellence certificate

B. PROFESSIONAL CERTIFICATE

Classify as:

document_type = "certificate"
document_subtype = "professional_certificate"

Examples:

- Professional certification
- Industry certification
- Technical certification
- Vendor certification

C. COURSE COMPLETION CERTIFICATE

Classify as:

document_type = "certificate"
document_subtype = "course_certificate"

Examples:

- Online course completion certificate
- Training completion certificate
- Technical course certificate
- Workshop completion certificate

D. INTERNSHIP CERTIFICATE

Classify as:

document_type = "certificate"
document_subtype = "internship_certificate"

Examples:

- Internship completion certificate
- Internship participation certificate
- Internship experience certificate

E. EXPERIENCE CERTIFICATE

Classify as:

document_type = "certificate"
document_subtype = "experience_certificate"

Examples:

- Employment experience certificate
- Work experience certificate
- Relieving certificate
- Employment verification certificate

F. OTHER CERTIFICATES

Classify as:

document_type = "certificate"
document_subtype = "other_certificate"

Use when the document certifies something but does
not fit the categories above.

IMPORTANT CERTIFICATE RULES:

- Do not classify examination marksheets as certificates
  merely because their heading contains "certificate".
- Distinguish an internship offer letter from an
  internship completion certificate.
- Distinguish a job offer letter from an experience
  certificate.
- Use the primary purpose and actual document content
  rather than relying only on the title.

--------------------------------------------------
6. OFFER LETTER CLASSIFICATION RULES
--------------------------------------------------

Use document_type = "offer_letter" for documents
formally offering employment or an internship.

A. EMPLOYMENT OFFER LETTER

Classify as:

document_type = "offer_letter"
document_subtype = "employment_offer"

Evidence may include:

- Company or employer name
- Job title or designation
- Offered salary or compensation
- Joining date
- Employment type
- Employment terms and conditions
- Acceptance instructions
- Candidate details

B. INTERNSHIP OFFER LETTER

Classify as:

document_type = "offer_letter"
document_subtype = "internship_offer"

Evidence may include:

- Internship role
- Company or organization name
- Internship duration
- Stipend
- Internship start date
- Internship responsibilities
- Internship conditions
- Acceptance instructions

IMPORTANT OFFER LETTER RULES:

- An internship offer letter is not an internship
  completion certificate.
- An employment offer letter is not an experience
  certificate.
- A job application or interview invitation is not
  automatically an offer letter.
- If the document does not clearly offer employment
  or an internship, do not classify it as an offer letter.

--------------------------------------------------
7. ADMISSION LETTER CLASSIFICATION RULES
--------------------------------------------------

Use document_type = "admission_letter" for formal
documents confirming or offering admission to an
educational institution or academic program.

A. COLLEGE ADMISSION LETTER

Classify as:

document_type = "admission_letter"
document_subtype = "college_admission_letter"

Evidence may include:

- College admission confirmation
- College name
- Course or degree program
- Admission or academic year
- Student details
- Enrollment instructions
- Fee details
- Admission conditions

B. UNIVERSITY ADMISSION LETTER

Classify as:

document_type = "admission_letter"
document_subtype = "university_admission_letter"

Evidence may include:

- University admission confirmation
- University name
- Degree or postgraduate program
- Academic department
- Admission semester
- Enrollment instructions
- Admission conditions
- Fee details

IMPORTANT ADMISSION RULES:

- Distinguish admission confirmation from an application
  acknowledgement.
- A university transcript is not an admission letter.
- A college fee receipt is not automatically an
  admission letter.
- Use the institution and the primary purpose of
  the document to identify the correct subtype.

--------------------------------------------------
8. OTHER DOCUMENT TYPES
--------------------------------------------------

A. RESUME

Use:

document_type = "resume"
document_subtype = null

A resume or curriculum vitae containing personal
details, education, skills, projects and experience.

B. STUDY MATERIAL

Use:

document_type = "study_notes"
document_subtype = null

This includes:

- Lecture notes
- Textbook content
- Classroom notes
- Learning materials
- Study guides

C. OTHER

Use:

document_type = "other"
document_subtype = "other"

For identifiable documents outside the supported
categories.

D. UNKNOWN

Use:

document_type = "unknown"
document_subtype = null

When there is insufficient evidence to identify
the document.

--------------------------------------------------
9. PAGE GROUPING RULES
--------------------------------------------------

1. Group consecutive pages belonging to the same
   physical document.

2. A document may contain multiple pages.

3. A new document may start on the next page even
   when it has the same document type as the previous
   document.

4. Do not combine two separate marksheets merely
   because both are marksheets.

5. Use document boundaries, headings, institution
   names, registration numbers and content changes
   to identify separate documents.

6. Every supplied page must belong to exactly one
   document.

7. Do not create overlapping page ranges.

8. Use the original page numbers supplied in the input.

9. Do not invent missing pages or document details.

10. If two consecutive pages clearly belong to the
    same document, group them into one entry.

11. If a new document begins on the next page,
    create a separate classification entry.

--------------------------------------------------
10. CONFIDENCE AND EVIDENCE
--------------------------------------------------

- Confidence must be between 0 and 1.
- Provide short evidence based on actual page content.
- Do not assign high confidence without clear evidence.
- Do not classify based only on one generic heading.
- Use null for document_subtype if uncertain.
- Evidence must not contain sensitive personal data.
- Never reproduce Aadhaar numbers, PAN numbers,
  phone numbers, email addresses or other personal
  identifiers in the evidence field.
- Describe the document using its structure and
  non-sensitive identifying characteristics.

--------------------------------------------------
11. OUTPUT FORMAT
--------------------------------------------------

Return ONLY valid JSON.

Use exactly this structure:

{
    "documents": [
        {
            "document_type": "marksheet",
            "document_subtype": "class_10",
            "start_page": 1,
            "end_page": 1,
            "confidence": 0.95,
            "evidence": "Secondary School Examination with subject-wise marks."
        }
    ]
}

Rules:

- documents must always be a list.
- Every entry must contain all six required fields.
- start_page and end_page must be valid page numbers.
- document_type must use an allowed value.
- document_subtype must use an allowed value or null.
- confidence must be between 0 and 1.
- evidence must be a short string.
- Do not include Markdown fences.
- Do not include explanations outside JSON.
"""


def validate_page_coverage(
    classification: ClassificationResult,
    pages: list[dict]
) -> None:

    expected_pages = {
        page["page_number"] for page in pages
    }

    classified_pages = []

    for document in classification.documents:

        if document.start_page not in expected_pages:
            raise ValueError(
                f"Invalid starting page: {document.start_page}"
            )

        if document.end_page not in expected_pages:
            raise ValueError(
                f"Invalid ending page: {document.end_page}"
            )

        classified_pages.extend(
            range(
                document.start_page,
                document.end_page + 1
            )
        )

    if len(classified_pages) != len(set(classified_pages)):
        raise ValueError(
            "Classification contains overlapping page ranges"
        )

    missing_pages = expected_pages - set(classified_pages)

    unexpected_pages = set(classified_pages) - expected_pages

    if missing_pages:
        raise ValueError(
            f"Classification is missing pages: {sorted(missing_pages)}"
        )

    if unexpected_pages:
        raise ValueError(
            f"Classification contains unexpected pages: "
            f"{sorted(unexpected_pages)}"
        )


def classify_documents(pages: list[dict]) -> ClassificationResult:

    if not pages:
        raise ValueError(
            "No page text provided for classification"
        )

    page_content = []

    page_numbers = [
        page["page_number"] for page in pages
    ]

    if len(page_numbers) != len(set(page_numbers)):
        raise ValueError("Duplicate page numbers provided")

    if sorted(page_numbers) != list(
        range(min(page_numbers), max(page_numbers) + 1)
    ):
        raise ValueError("Input pages must be consecutive")

    for page in pages:

        page_number = page["page_number"]

        original_text = page.get("text", "").strip()

        # Redact sensitive information before sending to Groq.
        safe_text = redact_pii(original_text)

        page_content.append(
            f"PAGE {page_number}:\n"
            f"{safe_text or '[No readable text]'}"
        )

    user_prompt = "\n\n".join(page_content)

    max_attempts = 2

    for attempt in range(max_attempts):

        retry_instruction = ""

        if attempt > 0:
            retry_instruction = """
IMPORTANT: Your previous response failed validation.

Return corrected JSON.

Requirements:
- Use only supported document_type values.
- Use only supported document_subtype values or null.
- Cover every supplied page exactly once.
- Do not create overlapping page ranges.
- Classify PUC examination marksheets as class_12.
- Classify engineering semester grade cards as
  engineering_semester.
- Do not classify a marksheet as a generic certificate
  just because its heading contains the word certificate.
"""

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
                        "content": (
                            user_prompt
                            + "\n\n"
                            + retry_instruction
                        )
                    }
                ],

                response_format={
                    "type": "json_object"
                },

                temperature=0.1,

                max_tokens=4000,

                reasoning_effort="low",

                include_reasoning=False
            )

            choice = response.choices[0]

            if choice.finish_reason == "length":
                raise ValueError(
                    "Groq classification response was truncated "
                    "because of token limits"
                )

            content = choice.message.content

            if not content:
                raise ValueError(
                    "Groq returned empty classification content"
                )

            parsed_json = json.loads(content)

            classification = (
                ClassificationResult.model_validate(
                    parsed_json
                )
            )

            validate_page_coverage(
                classification,
                pages
            )

            logger.info(
                "Document classification successful | "
                "model=%s | documents=%d | tokens=%s",
                response.model,
                len(classification.documents),
                response.usage.total_tokens
                if response.usage else None
            )

            return classification

        except (RateLimitError, APIError) as exc:

            logger.exception(
                "Groq API error during document classification"
            )

            raise RuntimeError(
                f"Groq API error: {str(exc)[:500]}"
            ) from exc

        except (
            IndexError,
            json.JSONDecodeError,
            ValidationError,
            ValueError
        ) as exc:

            logger.warning(
                "Classification attempt %d/%d failed: %s",
                attempt + 1,
                max_attempts,
                str(exc)
            )

            if attempt == max_attempts - 1:

                raise RuntimeError(
                    f"Classification failed after "
                    f"{max_attempts} attempts: {exc}"
                ) from exc

    raise RuntimeError("Classification failed")
