
from app.schemas.resume import ResumeDetails

sample_resume = {
    "document_type": "resume",
    "personal_details": {
        "full_name": "Demo Student",
        "email": "demo@example.com",
        "phone": "9999999999",
        "github_url": "https://github.com/demo"
    },
    "education": [
        {
            "institution_name": "Demo Engineering College",
            "degree": "Bachelor of Engineering",
            "branch": "Computer Science",
            "graduation_year": 2028,
            "cgpa": 8.8
        }
    ],
    "skills": [
        "Python",
        "C++",
        "Machine Learning",
        "FastAPI"
    ],
    "projects": [
        {
            "project_name": "AI Document Assistant",
            "description": "An AI-powered document extraction platform",
            "technologies": ["Python", "FastAPI", "Groq"]
        }
    ],
    "experience": [],
    "certifications": [],
    "achievements": []
}

resume = ResumeDetails.model_validate(sample_resume)

print("Resume schema validation successful!")
print(resume.model_dump_json(indent=4))
