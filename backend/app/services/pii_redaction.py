
import re


def redact_pii(text: str) -> str:
    """
    Redact common sensitive personal information locally
    before sending extracted document text to an AI provider.

    Currently handles:
    - Aadhaar numbers
    - Indian mobile numbers
    - Email addresses

    This is an initial regex-based protection layer,
    not a complete PII detection system.
    """

    if not text:
        return text

    # 1. Aadhaar numbers (12 digits, spaces or hyphens optional).
    text = re.sub(
        r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)",
        "[AADHAAR_REDACTED]",
        text
    )

    # 2. Indian mobile numbers.
    text = re.sub(
        r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)",
        "[PHONE_REDACTED]",
        text
    )

    # 3. Email addresses.
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[EMAIL_REDACTED]",
        text
    )

    return text
