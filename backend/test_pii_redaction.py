from app.services.classification_service import redact_pii


sample_text = """
Name: Demo User
Aadhaar Number: 6454 7576 5606
Mobile: 9876543210
Email: demo@example.com
Examination: Secondary School Examination
Total Marks: 550
"""

result = redact_pii(sample_text)

print("REDACTED TEXT:")
print(result)

assert "6454 7576 5606" not in result
assert "9876543210" not in result
assert "demo@example.com" not in result

assert "[AADHAAR_REDACTED]" in result
assert "[PHONE_REDACTED]" in result
assert "[EMAIL_REDACTED]" in result

assert "Secondary School Examination" in result
assert "550" in result

print("\nAll redaction tests passed!")