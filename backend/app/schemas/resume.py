
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class PersonalDetails(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None


class EducationDetails(BaseModel):
    institution_name: Optional[str] = None
    degree: Optional[str] = None
    branch: Optional[str] = None
    specialization: Optional[str] = None
    start_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    end_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    graduation_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    cgpa: Optional[float] = Field(default=None, ge=0, le=10)
    percentage: Optional[float] = Field(default=None, ge=0, le=100)
    grade: Optional[str] = None


class ExperienceDetails(BaseModel):
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: Optional[bool] = None
    description: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class ProjectDetails(BaseModel):
    project_name: Optional[str] = None
    description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    project_url: Optional[str] = None
    github_url: Optional[str] = None


class CertificationDetails(BaseModel):
    certification_name: Optional[str] = None
    issuing_organization: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None


class AchievementDetails(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    organization: Optional[str] = None


class ResumeDetails(BaseModel):
    document_type: str = "resume"

    personal_details: PersonalDetails = Field(
        default_factory=PersonalDetails
    )

    professional_summary: Optional[str] = None

    education: list[EducationDetails] = Field(
        default_factory=list
    )

    experience: list[ExperienceDetails] = Field(
        default_factory=list
    )

    projects: list[ProjectDetails] = Field(
        default_factory=list
    )

    skills: list[str] = Field(
        default_factory=list
    )

    certifications: list[CertificationDetails] = Field(
        default_factory=list
    )

    achievements: list[AchievementDetails] = Field(
        default_factory=list
    )

    languages: list[str] = Field(
        default_factory=list
    )

    interests: list[str] = Field(
        default_factory=list
    )

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    field_confidence: dict[str, float] = Field(
        default_factory=dict
    )

    missing_fields: list[str] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_confidence(self):
        for field_name, score in self.field_confidence.items():
            if not 0.0 <= score <= 1.0:
                raise ValueError(
                    f"Invalid confidence score for {field_name}"
                )

        return self
