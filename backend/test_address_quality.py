
from app.services.address_quality_service import assess_address_quality


address = (
    "705 4th Stage BEML Layout "
    "Rajarajeshwari Nagar Bengaluru Karnataka 560098"
)

components = {
    "house_number": "705",
    "street": "4th Stage BEML Layout",
    "locality": "Rajarajeshwari Nagar",
    "city": "Bengaluru",
    "district": None,
    "state": "Karnalaka",
    "pincode": "560098",
}

result = assess_address_quality(address, components)

print("\nADDRESS QUALITY RESULT")
print("======================")

print("State:", result["suggestions"]["state"])
print("PIN code:", result["suggestions"]["pincode"])
print("Duplicates:", result["duplicates"])
print("Suspicious numbers:", result["suspicious_numbers"])
print("Missing components:", result["missing_components"])
print("Issues:", result["issues"])
print("Needs review:", result["needs_review"])
