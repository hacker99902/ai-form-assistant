
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class AadhaarAddress(BaseModel):
    house_number: Optional[str] = None
    street: Optional[str] = None
    locality: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


class AadhaarDetails(BaseModel):

    full_name: Optional[str] = None

    aadhaar_number: Optional[str] = None

    date_of_birth: Optional[str] = None

    year_of_birth: Optional[str] = None

    gender: Optional[str] = None

    # Preserve the address as extracted.
    address: Optional[str] = None

    # Structured address components.
    address_components: AadhaarAddress = Field(
        default_factory=AadhaarAddress
    )

    father_or_husband_name: Optional[str] = None

    # Overall extraction confidence.
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0
    )

    # Individual field confidence estimates.
    field_confidence: dict[str, float] = Field(
        default_factory=dict
    )

    missing_fields: list[str] = Field(
        default_factory=list
    )

    # Convert numeric year values into strings.
    @field_validator("year_of_birth", mode="before")
    @classmethod
    def convert_year_to_string(cls, value):

        if value is None:
            return None

        if isinstance(value, bool):
            raise ValueError("Invalid year of birth")

        if isinstance(value, (int, float)):
            if value == int(value):
                return str(int(value))

            return str(value)

        return value
