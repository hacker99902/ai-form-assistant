
from app.schemas.marksheet import MarksheetDetails

sample_data = {
    "document_type": "transcript",

    "student": {
        "full_name": "Demo Student",
        "usn": "1XX23CS001",
        "college_name": "Demo Engineering College",
        "university_name": "Demo University",
        "degree": "B.E.",
        "branch": "Computer Science"
    },

    "semesters": [
        {
            "semester_number": 1,
            "examination_year": 2024,
            "subjects": [
                {
                    "subject_code": "CS101",
                    "subject_name": "Programming",
                    "credits": 4,
                    "maximum_marks": 100,
                    "marks_obtained": 90,
                    "grade": "A+"
                },
                {
                    "subject_code": "MA101",
                    "subject_name": "Mathematics",
                    "credits": 4,
                    "maximum_marks": 100,
                    "marks_obtained": 85,
                    "grade": "A"
                }
            ],
            "sgpa": 9.0,
            "result": "PASS"
        }
    ],

    "cgpa": 9.0,
    "overall_result": "PASS",
    "year_of_passing": 2028,
    "confidence": 0.95
}

result = MarksheetDetails.model_validate(sample_data)

print(result.model_dump_json(indent=4))
print("\nSchema validation successful!")
