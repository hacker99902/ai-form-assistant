
import json
import logging
import re

from groq import Groq, APIError, RateLimitError
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.aadhaar import AadhaarDetails


logger = logging.getLogger(__name__)


# Initialize Groq client.
client = Groq(
    api_key=settings.GROQ_API_KEY,
    timeout=120.0,
    max_retries=2
)


SYSTEM_PROMPT = """
You are an expert Indian Aadhaar document information extraction system.

Extract information only from the supplied OCR text.

STRICT RULES:

1. Extract only information explicitly supported by OCR.
2. Never invent missing information.
3. Do not silently correct OCR spelling errors.
4. Do not confuse enrollment dates with dates of birth.
5. DOB must come from an explicitly labelled DOB or Date of Birth field.
6. Extract year_of_birth only when explicitly available.
7. Extract father or husband's name only when explicitly labelled.
8. Aadhaar numbers have been redacted. Return null for aadhaar_number.
9. Mobile numbers have been redacted. Never include mobile numbers in addresses.

ADDRESS EXTRACTION:

10. Identify the address belonging to the Aadhaar holder.
11. Exclude mobile numbers, Aadhaar numbers, enrollment numbers,
    VID numbers, barcode text and unrelated numeric identifiers.
12. Preserve address wording supported by OCR.
13. Extract these components separately:
    house_number, street, locality, city, district, state, pincode.
14. Do not repeat locality or city names unnecessarily.
15. PIN code must contain exactly six digits supported by OCR.
16. If a component is uncertain, return null.

CONFIDENCE:

17. Provide individual confidence scores for each field.
18. Confidence must be between 0 and 1.
19. Scores are estimates, not calibrated probabilities.
20. Do not assign high confidence to unclear OCR.
21. Overall confidence should reflect extraction quality.

Return ONLY valid JSON:

{
    "full_name": null,
    "aadhaar_number": null,
    "date_of_birth": null,
    "year_of_birth": null,
    "gender": null,
    "address": null,
    "address_components": {
        "house_number": null,
        "street": null,
        "locality": null,
        "city": null,
        "district": null,
        "state": null,
        "pincode": null
    },
    "father_or_husband_name": null,
    "confidence": 0.0,
    "field_confidence": {
        "full_name": 0.0,
        "date_of_birth": 0.0,
        "gender": 0.0,
        "address": 0.0,
        "father_or_husband_name": 0.0,
        "pincode": 0.0
    },
    "missing_fields": []
}
"""


# Aadhaar number detection.
AADHAAR_PATTERN = re.compile(
    r"(?<!\d)([2-9]\d{3})[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)"
)


# Indian mobile number detection.
MOBILE_PATTERN = re.compile(
    r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"
)


def extract_aadhaar_candidate(text: str) -> list[str]:
    """Detect candidate Aadhaar numbers locally."""

    candidates = []

    for match in AADHAAR_PATTERN.finditer(text):
        number = "".join(match.groups())

        if number not in candidates:
            candidates.append(number)

    return candidates


def redact_aadhaar_numbers(text: str) -> str:
    return AADHAAR_PATTERN.sub(
        "[AADHAAR NUMBER REDACTED]",
        text
    )


def redact_mobile_numbers(text: str) -> str:
    return MOBILE_PATTERN.sub(
        "[MOBILE NUMBER REDACTED]",
        text
    )


def prepare_safe_text(text: str) -> str:
    """Remove sensitive number patterns before external API calls."""

    text = redact_aadhaar_numbers(text)
    text = redact_mobile_numbers(text)

    return text


def validate_field_confidence(details: AadhaarDetails):
    """Validate confidence scores."""

    for field_name, score in details.field_confidence.items():

        if not isinstance(score, (int, float)):
            raise ValueError(
                f"Invalid confidence for {field_name}"
            )

        if not 0 <= score <= 1:
            raise ValueError(
                f"Confidence for {field_name} must be between 0 and 1"
            )


def extract_response_content(response) -> str:
    """Extract and validate content from Groq response."""

    if not response.choices:
        raise RuntimeError(
            "Groq returned no completion choices"
        )

    choice = response.choices[0]

    content = choice.message.content

    if choice.finish_reason == "length":
        logger.error(
            "Groq Aadhaar response was truncated. "
            "Model=%s",
            response.model
        )

        raise RuntimeError(
            "Groq response was truncated due to token limits"
        )

    if not isinstance(content, str) or not content.strip():
        logger.error(
            "Groq returned empty Aadhaar content. "
            "Finish reason=%s, model=%s",
            choice.finish_reason,
            response.model
        )

        raise RuntimeError(
            "Groq returned empty extraction content"
        )

    return content.strip()


def parse_model_json(content: str) -> dict:
    """Parse JSON returned by the model."""

    content = content.strip()

    # Remove optional Markdown JSON fences.
    if content.startswith("```"):

        content = re.sub(
            r"^```(?:json)?\s*",
            "",
            content,
            flags=re.IGNORECASE
        )

        content = re.sub(
            r"\s*```$",
            "",
            content
        )

    try:
        parsed = json.loads(content)

    except json.JSONDecodeError as exc:

        logger.error(
            "Groq returned malformed JSON. Error: %s",
            exc.msg
        )

        raise RuntimeError(
            "Groq returned invalid JSON"
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(
            "Groq response must be a JSON object"
        )

    return parsed


def extract_aadhaar_details(
    pages: list[dict]
) -> AadhaarDetails:

    if not pages:
        raise ValueError("No page text provided")

    page_numbers = [
        page["page_number"] for page in pages
    ]

    if len(page_numbers) != len(set(page_numbers)):
        raise ValueError("Duplicate page numbers provided")

    original_page_texts = []

    for page in pages:

        page_number = page["page_number"]
        text = page.get("text", "").strip()

        original_page_texts.append(
            f"PAGE {page_number}:\n{text}"
        )

    original_text = "\n\n".join(original_page_texts)

    if not original_text.strip():
        raise ValueError("No readable text available")

    # Detect Aadhaar candidates locally.
    aadhaar_candidates = extract_aadhaar_candidate(
        original_text
    )

    # Redact sensitive values before external API calls.
    safe_pages = []

    for page in pages:

        page_number = page["page_number"]
        text = page.get("text", "").strip()

        safe_text = prepare_safe_text(text)

        safe_pages.append(
            f"PAGE {page_number}:\n"
            f"{safe_text or '[No readable text]'}"
        )

    user_prompt = "\n\n".join(safe_pages)

    max_attempts = 2

    for attempt in range(max_attempts):

        retry_instruction = ""

        if attempt > 0:
            retry_instruction = """
Your previous response failed validation.

Return corrected JSON.
Follow the exact requested schema.
Do not invent missing information.
Return valid JSON only.
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

            content = extract_response_content(response)

            parsed_json = parse_model_json(content)

            details = AadhaarDetails.model_validate(
                parsed_json
            )

            validate_field_confidence(details)

            # Never accept Aadhaar number from the LLM.
            details.aadhaar_number = None

            # Accept only one locally detected candidate.
            if len(aadhaar_candidates) == 1:

                details.aadhaar_number = (
                    aadhaar_candidates[0]
                )

            elif len(aadhaar_candidates) > 1:

                if "aadhaar_number" not in details.missing_fields:
                    details.missing_fields.append(
                        "aadhaar_number"
                    )

            # Check for duplicate address components.
            components = details.address_components

            component_values = [
                components.house_number,
                components.street,
                components.locality,
                components.city,
                components.district,
                components.state,
                components.pincode,
            ]

            normalized_values = [
                value.strip().casefold()
                for value in component_values
                if value and value.strip()
            ]

            if len(normalized_values) != len(
                set(normalized_values)
            ):

                if "address_components_review" not in details.missing_fields:
                    details.missing_fields.append(
                        "address_components_review"
                    )

            logger.info(
                "Aadhaar extraction completed successfully. "
                "Model=%s, finish_reason=%s",
                response.model,
                response.choices[0].finish_reason
            )

            return details

        except RateLimitError as exc:

            logger.exception(
                "Groq rate limit reached during Aadhaar extraction"
            )

            raise RuntimeError(
                "Groq rate limit reached. Please retry later."
            ) from exc

        except APIError as exc:

            logger.exception(
                "Groq API error during Aadhaar extraction"
            )

            raise RuntimeError(
                f"Groq API error: {str(exc)[:500]}"
            ) from exc

        except (
            json.JSONDecodeError,
            ValidationError,
            ValueError,
            RuntimeError
        ) as exc:

            logger.warning(
                "Aadhaar extraction attempt %d/%d failed: %s",
                attempt + 1,
                max_attempts,
                str(exc)
            )

            if attempt == max_attempts - 1:
                raise RuntimeError(
                    f"Aadhaar extraction failed after "
                    f"{max_attempts} attempts: {exc}"
                ) from exc

    raise RuntimeError("Aadhaar extraction failed")
