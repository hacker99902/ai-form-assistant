
from app.services.aadhaar_service import extract_aadhaar_details


pages = [
    {
        "page_number": 1,
        "text": """
        GOVERNMENT OF INDIA

        Name: Ramesh Kumar
        Date of Birth: 15/08/2002
        Male

        Address:
        705 4th Stage BEML Layout
        Rajarajeshwari Nagar
        Bengaluru
        Karnataka 560098

        Aadhaar Number: 2345 6789 0123
        """
    }
]


try:
    result = extract_aadhaar_details(pages)

    print("\nAadhaar extraction successful!\n")

    print("Name:", result.full_name)
    print("DOB:", result.date_of_birth)
    print("Year of birth:", result.year_of_birth)
    print("Gender:", result.gender)

    if result.aadhaar_number:
        print(
            "Aadhaar:",
            "XXXX XXXX " + result.aadhaar_number[-4:]
        )

    print("\nAddress:")
    print("Original:", result.address)

    print("\nStructured address:")

    for field, value in result.address_components.model_dump().items():
        print(f"{field}: {value}")

    print("\nField confidence:")

    for field, confidence in result.field_confidence.items():
        print(f"{field}: {confidence}")

    print("\nOverall confidence:", result.confidence)

    print("Missing fields:", result.missing_fields)

except Exception as error:
    print("Extraction failed:", error)
