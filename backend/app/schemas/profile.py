
from pydantic import BaseModel, Field, field_validator

ALLOWED_PROFILE_FIELDS = {
    "full_name",
    "aadhaar_number",
    "date_of_birth",
    "year_of_birth",
    "gender",
    "address",
    "father_or_husband_name",
    "address_house_number",
    "address_street",
    "address_locality",
    "address_city",
    "address_district",
    "address_state",
    "address_pincode",
}


class UpdateProfileFieldsRequest(BaseModel):
    fields: dict[str, str] = Field(min_length=1)

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, fields):

        if not fields:
            raise ValueError("At least one field is required")

        unknown_fields = set(fields) - ALLOWED_PROFILE_FIELDS

        if unknown_fields:
            raise ValueError(
                f"Unsupported fields: {', '.join(sorted(unknown_fields))}"
            )

        for field_name, value in fields.items():

            if not isinstance(value, str):
                raise ValueError(
                    f"{field_name} must be a string"
                )

            if not value.strip():
                raise ValueError(
                    f"{field_name} cannot be empty"
                )

            if len(value) > 2000:
                raise ValueError(
                    f"{field_name} exceeds the maximum length"
                )

        # Validate Aadhaar only when it is being corrected.
        if "aadhaar_number" in fields:
            digits = "".join(
                char for char in fields["aadhaar_number"]
                if char.isdigit()
            )

            if (
                len(digits) != 12
                or digits[0] not in "23456789"
            ):
                raise ValueError(
                    "Enter a valid 12-digit Aadhaar number"
                )

        return fields
