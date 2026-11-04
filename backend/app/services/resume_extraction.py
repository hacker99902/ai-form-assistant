import json
import logging
import re
from typing import Any

from groq import Groq

from app.core.config import settings
from app.schemas.resume import ResumeDetails


logger = logging.getLogger(__name__)

client = Groq(
    api_key=settings.GROQ_API_KEY,
    timeout=120.0,
    max_retries=2,
)
SYSTEM_PROMPT = """
You are a highly accurate resume parsing and information extraction system.

Your task is to extract structured information from the supplied resume text.

IMPORTANT RULES:
- Extract every detail explicitly present in the resume.
- Never invent information.
- Do not return null when a value can be identified.
- Preserve the original meaning of all information.
- Do not merge unrelated sections or records.
- Return valid JSON matching the ResumeDetails schema.

PERSONAL DETAILS:
- Extract the person's full name from the resume heading.
- Extract email, phone, location, LinkedIn, GitHub, and portfolio URLs.
- Keep contact information in the correct fields.
- Do not confuse the person's name with an institution or organization.

EDUCATION:
- Extract each education record separately.
- Extract institution_name, degree, branch, and specialization separately.
- Extract start_year, end_year, graduation_year, CGPA, percentage, and grade.
- Do not convert CGPA into percentage.
- CGPA must be numeric. For example, "8.88/10" must become 8.88.
- percentage must be numeric. For example, "85%" must become 85.0.
- institution_name MUST contain only the actual school, college, or university name.
- Never put CGPA, coursework, subjects covered, academic scores, or degree details inside institution_name.
- Do not mistake a line containing "Cumulative Grade Point Average",
  "Subjects Covered", "CGPA", or "Percentage" for an institution name.
- If the actual institution name cannot be identified confidently, return null.
- Do not guess an institution name.

EXPERIENCE:
- Extract every company, job title, employment type, location, dates, and description.
- Include internships.
- Extract whether the role is current.
- Preserve descriptions and technologies.
- Keep separate jobs and internships as separate objects.

PROJECTS:
- Extract every project as a separate object.
- Extract project_name from the actual project heading.
- Extract the project description separately.
- Extract technologies into a separate list.
- Extract start_date, end_date, project_url, and github_url when available.
- Never merge separate projects.
- Do not include technologies inside project_name.
- If a project heading contains a "|" separator followed by technologies,
  keep only the text before "|" as project_name.
- Put the technologies after "|" into the technologies list.
- Example:
  Input heading:
  "Saathi - AI Document Platform | Python, Flask, RAG, Groq"
  Output:
  {
    "project_name": "Saathi - AI Document Platform",
    "technologies": ["Python", "Flask", "RAG", "Groq"]
  }
- Do not return project_name as null when a clear project heading is available.
- If the heading genuinely cannot be identified, return null.
- Never invent project names from descriptions.

SKILLS:
- Extract all technical and non-technical skills as separate items.
- Include programming languages, frameworks, libraries, databases,
  AI/ML tools, platforms, and development tools.
- Do not miss skills explicitly listed in the resume.
- Do not duplicate the same skill unnecessarily.
- Do not confuse project descriptions with the skills section.

CERTIFICATIONS:
- Extract the complete certificate title as certification_name.
- Extract issuing organization separately.
- Extract issue_date, expiry_date, credential_id, and credential_url.
- Never leave certification_name null when a certificate title is present.
- Do not use only the organization name as the certificate title.
- Example:
  Input: "Deloitte AI Analyst Certificate"
  Output:
  {
    "certification_name": "Deloitte AI Analyst Certificate",
    "issuing_organization": "Deloitte"
  }

ACHIEVEMENTS:
- Preserve achievement statements.
- Extract title, description, date, and organization where available.
- Do not discard plain achievement statements.
- Do not invent dates or organizations.

LANGUAGES:
- Extract all languages explicitly mentioned in the resume.
- Do not assume a language based on the person's location or name.

INTERESTS:
- Extract interests explicitly mentioned in the resume.
- Do not invent interests.

PROFESSIONAL SUMMARY:
- Extract the summary only if it is explicitly present.
- Do not generate a new summary from other resume sections.

GENERAL EXTRACTION RULES:
1. Preserve all records.
2. Use null only when information is genuinely absent.
3. Use empty arrays for absent list sections.
4. Do not confuse education with experience.
5. Do not confuse project technologies with general skills.
6. Preserve dates as written where the schema allows strings.
7. Do not invent missing information.
8. Keep every project, education record, certification, and achievement separate.
9. Do not place unrelated text in a field just to avoid returning null.
10. Return only valid JSON. Do not include Markdown fences or explanations.

CONFIDENCE:
- confidence must be a number between 0 and 1.
- field_confidence must be a dictionary of scores between 0 and 1.
- missing_fields must be a list of strings.
- Assign high confidence only when the information is clearly present.
- Assign low confidence when information is uncertain.
- Do not assign confidence 1.0 to missing fields.
- Include genuinely missing information in missing_fields.
- If a section is empty because it is absent from the resume,
  its field_confidence must be 0.0.
- If a field is explicitly present and clearly extracted,
  assign a high confidence score.
- If a field is partially extracted, assign a moderate score.
- Never assign 0.95 or 1.0 to an empty section.
- Missing fields must have low confidence.

OUTPUT REQUIREMENTS:
- document_type must be "resume".
- personal_details must be an object.
- education, experience, projects, certifications, and achievements
  must be lists of objects.
- skills, languages, interests, and missing_fields must be lists.
- confidence must be numeric.
- field_confidence must be a dictionary.
- Do not return null for list fields.
- Do not put field_confidence inside confidence.
- Follow the ResumeDetails schema exactly.
"""

def extract_resume_fallbacks(text: str) -> dict[str, Any]:
    """
    Extract a small set of predictable fields directly from resume text.

    These are fallback values only: they are used when the model leaves a
    field empty. The heuristics are intentionally conservative and should
    still be reviewed by the user.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    result: dict[str, Any] = {
        "full_name": None,
        "email": None,
        "phone": None,
        "github_url": None,
        "linkedin_url": None,
        "portfolio_url": None,
        "institution_name": None,
        "project_name": None,
    }

    # Email
    email_match = re.search(
        r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
        text,
        flags=re.IGNORECASE,
    )
    if email_match:
        result["email"] = email_match.group(0)

    # Phone: retain the original formatting after checking digit count.
    phone_match = re.search(
        r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)",
        text,
    )
    if phone_match:
        phone = phone_match.group(0).strip()
        digit_count = len(re.sub(r"\D", "", phone))
        if 10 <= digit_count <= 15:
            result["phone"] = phone

    # URLs
    urls = re.findall(r"https?://[^\s,<>]+", text, flags=re.IGNORECASE)
    for url in urls:
        url = url.rstrip(".,;:)")
        lower_url = url.lower()

        if "github.com/" in lower_url:
            result["github_url"] = url
        elif "linkedin.com/" in lower_url:
            result["linkedin_url"] = url
        elif not result["portfolio_url"]:
            result["portfolio_url"] = url

    # Name heuristic: first short, non-contact heading in the opening lines.
    contact_prefixes = (
        "email",
        "phone",
        "mobile",
        "github",
        "linkedin",
        "portfolio",
        "address",
        "location",
    )
    ignored_headings = {
        "resume",
        "curriculum vitae",
        "cv",
        "profile",
        "professional summary",
    }

    for line in lines[:8]:
        lower_line = line.lower()
        if (
            "@" in line
            or re.search(r"\d", line)
            or lower_line.startswith(contact_prefixes)
            or lower_line in ignored_headings
            or "http://" in lower_line
            or "https://" in lower_line
        ):
            continue

        words = line.split()
        if 1 <= len(words) <= 5 and len(line) <= 70:
            result["full_name"] = line
            break

    # Institution heuristic: commonly follows the degree line.
    degree_keywords = (
        "bachelor",
        "master",
        "degree",
        "diploma",
        "phd",
        "b.e.",
        "b.tech",
        "m.e.",
        "m.tech",
    )
    for index, line in enumerate(lines):
        lower_line = line.lower()
        if any(keyword in lower_line for keyword in degree_keywords):
            if index + 1 < len(lines):
                candidate = lines[index + 1]
                candidate_lower = candidate.lower()
                looks_like_metadata = (
                    bool(re.search(r"\b(19|20)\d{2}\b", candidate))
                    or "cgpa" in candidate_lower
                    or "percentage" in candidate_lower
                    or candidate_lower.startswith(("skills", "projects"))
                )
                if not looks_like_metadata:
                    result["institution_name"] = candidate
            break

    # Simple project-heading fallback for a section titled PROJECTS.
    for index, line in enumerate(lines):
        if line.strip().rstrip(":").lower() in {
            "projects",
            "academic projects",
            "personal projects",
        }:
            if index + 1 < len(lines):
                candidate = lines[index + 1]
                if candidate.lower() not in {
                    "experience",
                    "education",
                    "skills",
                    "certifications",
                }:
                    result["project_name"] = candidate
            break

    return result

def normalize_project_names(extracted_data: dict) -> dict:
    projects = extracted_data.get("projects", [])

    if not isinstance(projects, list):
        return extracted_data

    for project in projects:
        if not isinstance(project, dict):
            continue

        name = project.get("project_name")

        if isinstance(name, str):
            name = name.split("|")[0].strip()
            project["project_name"] = name or None

    return extracted_data


def normalize_academic_scores(extracted_data: dict) -> dict:
    """
    Convert CGPA and percentage strings into numeric values
    before Pydantic validation.
    """

    def parse_score(value):
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            match = re.search(r"\d+(?:\.\d+)?", value)

            if match:
                return float(match.group())

        return value

    education = extracted_data.get("education", [])

    if not isinstance(education, list):
        return extracted_data

    for item in education:
        if not isinstance(item, dict):
            continue

        if item.get("cgpa") is not None:
            item["cgpa"] = parse_score(item["cgpa"])

        if item.get("percentage") is not None:
            item["percentage"] = parse_score(item["percentage"])

    return extracted_data


def _normalize_list_fields(data: dict[str, Any]) -> None:
    """Ensure schema list fields are lists rather than null."""
    list_fields = (
        "education",
        "experience",
        "projects",
        "skills",
        "certifications",
        "achievements",
        "languages",
        "interests",
        "missing_fields",
    )

    for field in list_fields:
        if data.get(field) is None:
            data[field] = []


def _normalize_achievements(data: dict[str, Any]) -> None:
    """Convert plain-text achievement entries into schema objects."""
    normalized = []

    for achievement in data.get("achievements", []):
        if isinstance(achievement, str):
            normalized.append(
                {
                    "title": achievement,
                    "description": None,
                    "date": None,
                    "organization": None,
                }
            )
        elif isinstance(achievement, dict):
            normalized.append(achievement)
        else:
            raise ValueError(
                "Invalid achievement format returned by Groq"
            )

    data["achievements"] = normalized


def _normalize_confidence(data: dict[str, Any]) -> None:
    """Handle either numeric confidence or the occasional nested format."""
    confidence = data.get("confidence", 0.0)

    if isinstance(confidence, dict):
        overall = confidence.get("overall", 0.0)
        nested_scores = confidence.get("field_confidence", {})
        existing_scores = data.get("field_confidence") or {}

        if not isinstance(nested_scores, dict):
            nested_scores = {}
        if not isinstance(existing_scores, dict):
            existing_scores = {}

        existing_scores.update(nested_scores)
        data["confidence"] = overall
        data["field_confidence"] = existing_scores
    elif confidence is None:
        data["confidence"] = 0.0

    field_confidence = data.get("field_confidence")
    if field_confidence is None:
        data["field_confidence"] = {}
    elif not isinstance(field_confidence, dict):
        raise ValueError(
            "Invalid field_confidence format returned by Groq"
        )


def _apply_fallbacks(
    data: dict[str, Any],
    fallbacks: dict[str, Any],
) -> None:
    """Fill missing model fields without overwriting extracted values."""
    personal = data.get("personal_details")
    if personal is None:
        personal = {}
        data["personal_details"] = personal
    elif not isinstance(personal, dict):
        raise ValueError("Invalid personal_details format returned by Groq")

    personal_fields = (
        "full_name",
        "email",
        "phone",
        "github_url",
        "linkedin_url",
        "portfolio_url",
    )
    for field in personal_fields:
        if not personal.get(field) and fallbacks.get(field):
            personal[field] = fallbacks[field]

    # Only use the single detected institution as a fallback for the first
    # education entry. Review the result because resume layouts vary.
    education = data.get("education") or []
    for entry in education:
        if (
            isinstance(entry, dict)
            and not entry.get("institution_name")
            and fallbacks.get("institution_name")
        ):
            entry["institution_name"] = fallbacks["institution_name"]
            break

    # Likewise, use the heading fallback only for the first unnamed project.
    projects = data.get("projects") or []
    for entry in projects:
        if (
            isinstance(entry, dict)
            and not entry.get("project_name")
            and fallbacks.get("project_name")
        ):
            entry["project_name"] = fallbacks["project_name"]
            break

def normalize_project_names(extracted_data: dict) -> dict:
    projects = extracted_data.get("projects", [])

    if not isinstance(projects, list):
        return extracted_data

    for project in projects:
        if not isinstance(project, dict):
            continue

        name = project.get("project_name")

        if isinstance(name, str):
            # Remove technology text after the pipe separator
            name = name.split("|")[0].strip()

            project["project_name"] = name or None

    return extracted_data


def extract_resume_details(extracted_text: str) -> ResumeDetails:
    """
    Extract structured resume information using Groq, apply conservative
    text-based fallbacks, normalize the response, and validate it with Pydantic.
    """
    if not extracted_text or not extracted_text.strip():
        raise ValueError("Resume text cannot be empty")

    try:
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=8000,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "Extract the resume information from this text.\n\n"
                        "OUTPUT REQUIREMENTS:\n"
                        "- achievements, certifications, education, "
                        "experience, and projects must be lists of objects.\n"
                        "- skills, languages, interests, and missing_fields "
                        "must be lists.\n"
                        "- confidence must be a number from 0 to 1.\n"
                        "- field_confidence must be a dictionary of scores.\n"
                        "- Do not return null for list fields.\n"
                        "- Do not put field_confidence inside confidence.\n\n"
                        f"RESUME TEXT:\n{extracted_text}"
                    ),
                },
            ],
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq returned an empty response")

        extracted_data = json.loads(content)
        if not isinstance(extracted_data, dict):
            raise ValueError("Groq response must be a JSON object")

        # Apply deterministic fallbacks before normalizing and validating.
        fallbacks = extract_resume_fallbacks(extracted_text)
        _apply_fallbacks(extracted_data, fallbacks)

        _normalize_list_fields(extracted_data)
        _normalize_achievements(extracted_data)
        _normalize_confidence(extracted_data)

        # Enforce the expected document type.
        extracted_data["document_type"] = "resume"

        # Normalize CGPA and percentage values
        # Normalize project names
        extracted_data = normalize_project_names(extracted_data)

        # Normalize CGPA and percentage values
        extracted_data = normalize_academic_scores(extracted_data)

        # Validate structured resume data
        resume_details = ResumeDetails.model_validate(
            extracted_data
        )

        logger.info("Resume extraction completed successfully")
        return resume_details

    except Exception:
        logger.exception("Resume extraction failed")
        raise
