
import json
import logging

from groq import Groq
from groq import APIError, RateLimitError

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


SYSTEM_PROMPT = """
You are an expert document classification system.

Your task is to identify different documents inside a combined PDF.

You will receive text extracted from individual PDF pages.

STRICT INSTRUCTIONS:

1. Identify document types using the available page text.

2. You MUST use ONLY these exact document_type values:

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

3. Never return alternative labels such as:
   "lecture notes", "class notes", "academic notes".
   Always use "study_notes" instead.

4. Educational material, lecture notes, textbook content,
   classroom notes and learning materials must be classified
   as "study_notes".

5. Use "unknown" when there is insufficient evidence to
   identify the document type.

6. Use "other" for identifiable documents outside the
   supported categories.

7. Never invent document information.

8. Group consecutive pages belonging to the same document.

9. Every page must belong to exactly one document.

10. Do not create overlapping page ranges.

11. Use the original page numbers supplied in the input.

12. Confidence must be between 0 and 1.

13. Provide short evidence explaining each classification.

14. Do not classify a document based only on a single
    generic word or heading.

Return ONLY valid JSON in this format:

{
    "documents": [
        {
            "document_type": "study_notes",
            "start_page": 1,
            "end_page": 3,
            "confidence": 0.95,
            "evidence": "Contains educational material and lecture notes."
        }
    ]
}
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
        text = page.get("text", "").strip()

        page_content.append(
            f"PAGE {page_number}:\n"
            f"{text or '[No readable text]'}"
        )

    user_prompt = "\n\n".join(page_content)

    max_attempts = 2

    for attempt in range(max_attempts):

        retry_instruction = ""

        if attempt > 0:
            retry_instruction = """
IMPORTANT: Your previous response failed validation.

Return corrected JSON.

Use only the exact supported document_type values.
Cover every supplied page exactly once.
Do not create overlapping page ranges.
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

            # Check whether the model completed its response.
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
