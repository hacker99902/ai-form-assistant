
from app.services.marksheet_extraction import (
    extract_marksheet_details
)


sample_text = """
DEMO UNIVERSITY

BACHELOR OF ENGINEERING

STUDENT NAME: DEMO STUDENT
USN: 1XX23CS001

SEMESTER: 1
EXAMINATION YEAR: 2024

SUBJECT CODE: CS101
SUBJECT NAME: PROGRAMMING
MAXIMUM MARKS: 100
MARKS OBTAINED: 90
CREDITS: 4
GRADE: A+

SUBJECT CODE: MA101
SUBJECT NAME: MATHEMATICS
MAXIMUM MARKS: 100
MARKS OBTAINED: 85
CREDITS: 4
GRADE: A

SGPA: 9.0
RESULT: PASS
"""


result = extract_marksheet_details(sample_text)

print("\nMARKSHEET EXTRACTION RESULT\n")

print(
    result.model_dump_json(indent=4)
)

print("\nExtraction successful!")
