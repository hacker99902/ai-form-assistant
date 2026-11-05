from app.services.pii_redaction import redact_pii
from app.services.marksheet_extraction import build_extraction_prompt


sample_text = """
Student Name: Demo Student
Aadhaar Number: 6454 7576 5606
Mobile: 9876543210
Email: demo@example.com

SECOND YEAR PRE-UNIVERSITY EXAMINATION

Physics: 95
Chemistry: 96
Mathematics: 98
Total Marks: 289
"""

safe_text = redact_pii(sample_text)

prompt = build_extraction_prompt(safe_text)

assert "6454 7576 5606" not in prompt
assert "9876543210" not in prompt
assert "demo@example.com" not in prompt

assert "[AADHAAR_REDACTED]" in prompt
assert "SECOND YEAR PRE-UNIVERSITY EXAMINATION" in prompt
assert "Physics: 95" in prompt
assert "Total Marks: 289" in prompt

print("Marksheet redaction integration test passed!")