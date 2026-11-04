
from app.services.resume_extraction import extract_resume_details


sample_resume_text = """
DEMO STUDENT

Email: demo@example.com
Phone: 9999999999
GitHub: https://github.com/demo

EDUCATION

Bachelor of Engineering in Computer Science
Demo Engineering College
2024 - 2028
CGPA: 8.8

SKILLS

Python, C++, Machine Learning, FastAPI

PROJECTS

AI Document Assistant

Developed an AI-powered document extraction platform
using Python, FastAPI and Groq.

CERTIFICATIONS

Deloitte AI Analyst Certificate

ACHIEVEMENTS

Participated in a global hackathon.
"""

resume = extract_resume_details(sample_resume_text)

print("Resume extraction successful!")

print(resume.model_dump_json(indent=4))
