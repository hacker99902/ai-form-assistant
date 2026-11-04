
import re
from difflib import get_close_matches


INDIAN_STATES_AND_UTS = [
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
]


def validate_pincode(value: str | None) -> dict:
    """Validate the format of an Indian PIN code."""

    if not value:
        return {
            "valid": False,
            "message": "PIN code is missing",
        }

    digits = re.sub(r"\D", "", value)

    if not re.fullmatch(r"[1-9]\d{5}", digits):
        return {
            "valid": False,
            "message": "PIN code must contain exactly 6 digits and cannot start with 0",
        }

    return {
        "valid": True,
        "message": "PIN code format is valid",
    }


def suggest_state_correction(state: str | None) -> dict:
    """Suggest a possible state-name correction without changing the value."""

    if not state or not state.strip():
        return {
            "original": state,
            "suggestion": None,
            "needs_review": True,
            "message": "State is missing",
        }

    state = state.strip()

    # Exact case-insensitive match
    for official_state in INDIAN_STATES_AND_UTS:
        if state.casefold() == official_state.casefold():
            return {
                "original": state,
                "suggestion": None,
                "needs_review": False,
                "message": "State name matches the reference list",
            }

    # Conservative fuzzy matching
    matches = get_close_matches(
        state.casefold(),
        [item.casefold() for item in INDIAN_STATES_AND_UTS],
        n=1,
        cutoff=0.80,
    )

    if matches:
        suggestion = next(
            item
            for item in INDIAN_STATES_AND_UTS
            if item.casefold() == matches[0]
        )

        return {
            "original": state,
            "suggestion": suggestion,
            "needs_review": True,
            "message": "Possible OCR spelling error. Please verify.",
        }

    return {
        "original": state,
        "suggestion": None,
        "needs_review": True,
        "message": "State could not be matched confidently",
    }


def find_duplicate_components(components: dict) -> list:
    """Find identical non-empty values across address components."""

    seen = {}
    duplicates = []

    for field, value in components.items():
        if not isinstance(value, str) or not value.strip():
            continue

        normalized = " ".join(value.casefold().split())

        if normalized in seen:
            duplicates.append({
                "field": field,
                "duplicate_of": seen[normalized],
                "value": value,
            })
        else:
            seen[normalized] = field

    return duplicates


def find_suspicious_numbers(address: str | None) -> list:
    """Flag phone-like or unusually long numeric sequences for review."""

    if not address:
        return []

    flagged = []

    for match in re.finditer(r"(?<!\d)\d{7,}(?!\d)", address):
        flagged.append({
            "value": match.group(),
            "reason": "Unusually long numeric sequence in address",
        })

    for match in re.finditer(
        r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)",
        address,
    ):
        flagged.append({
            "value": match.group(),
            "reason": "Possible mobile number in address",
        })

    # Remove duplicate flags for the same numeric sequence.
    unique = {}
    for item in flagged:
        unique[item["value"]] = item

    return list(unique.values())


def assess_address_quality(
    address: str | None,
    components: dict,
) -> dict:
    """
    Assess extracted address quality.

    This function only reports issues and suggestions.
    It never modifies the original extracted values.
    """

    state_result = suggest_state_correction(
        components.get("state")
    )

    pincode_result = validate_pincode(
        components.get("pincode")
    )

    duplicates = find_duplicate_components(components)

    suspicious_numbers = find_suspicious_numbers(address)

    issues = []

    if state_result["needs_review"]:
        issues.append("state_needs_review")

    if not pincode_result["valid"]:
        issues.append("pincode_needs_review")

    if duplicates:
        issues.append("duplicate_components")

    if suspicious_numbers:
        issues.append("suspicious_numbers")

    missing_components = [
        field
        for field, value in components.items()
        if not value or not str(value).strip()
    ]

    if missing_components:
        issues.append("missing_address_components")

    return {
        "original_address": address,
        "suggestions": {
            "state": state_result,
            "pincode": pincode_result,
        },
        "duplicates": duplicates,
        "suspicious_numbers": suspicious_numbers,
        "missing_components": missing_components,
        "issues": issues,
        "needs_review": bool(issues),
    }
