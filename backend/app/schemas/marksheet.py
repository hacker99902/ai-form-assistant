
from typing import Optional, Literal

from pydantic import BaseModel, Field, model_validator


# ==========================================
# STUDENT DETAILS
# ==========================================

class StudentDetails(BaseModel):

    full_name: Optional[str] = None

    father_name: Optional[str] = None
    mother_name: Optional[str] = None

    date_of_birth: Optional[str] = None

    mobile_number: Optional[str] = None
    email: Optional[str] = None

    school_name: Optional[str] = None
    board: Optional[str] = None

    roll_number: Optional[str] = None
    registration_number: Optional[str] = None
    usn: Optional[str] = None

    college_name: Optional[str] = None
    university_name: Optional[str] = None

    degree: Optional[str] = None
    branch: Optional[str] = None
    stream: Optional[str] = None


# ==========================================
# SUBJECT DETAILS
# ==========================================

class SubjectDetails(BaseModel):

    subject_code: Optional[str] = None
    subject_name: Optional[str] = None

    credits: Optional[float] = Field(
        default=None, ge=0
    )

    maximum_marks: Optional[float] = Field(
        default=None, ge=0
    )

    marks_obtained: Optional[float] = Field(
        default=None, ge=0
    )

    internal_marks: Optional[float] = Field(
        default=None, ge=0
    )

    external_marks: Optional[float] = Field(
        default=None, ge=0
    )

    grade: Optional[str] = None

    grade_points: Optional[float] = Field(
        default=None, ge=0
    )

    result: Optional[str] = None


# ==========================================
# SEMESTER DETAILS
# ==========================================

class SemesterDetails(BaseModel):

    semester_number: Optional[int] = Field(
        default=None, ge=1
    )

    semester_name: Optional[str] = None

    examination_month: Optional[str | int] = None

    examination_year: Optional[int] = Field(
        default=None, ge=1900, le=2100
    )

    subjects: list[SubjectDetails] = Field(
        default_factory=list
    )

    total_marks_obtained: Optional[float] = Field(
        default=None, ge=0
    )

    maximum_marks: Optional[float] = Field(
        default=None, ge=0
    )

    sgpa: Optional[float] = Field(
        default=None, ge=0, le=10
    )

    result: Optional[str] = None


# ==========================================
# COMPLETE MARKSHEET DETAILS
# ==========================================

class MarksheetDetails(BaseModel):

    document_type: Literal[
        "marksheet",
        "transcript"
    ]

    student: StudentDetails = Field(
        default_factory=StudentDetails
    )

    semesters: list[SemesterDetails] = Field(
        default_factory=list
    )

    # Overall academic information

    total_marks_obtained: Optional[float] = Field(
        default=None, ge=0
    )

    maximum_marks: Optional[float] = Field(
        default=None, ge=0
    )

    percentage: Optional[float] = Field(
        default=None, ge=0, le=100
    )

    cgpa: Optional[float] = Field(
        default=None, ge=0, le=10
    )

    overall_result: Optional[str] = None

    year_of_passing: Optional[int] = Field(
        default=None, ge=1900, le=2100
    )

    # Extraction metadata

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0
    )

    field_confidence: dict[str, float] = Field(
        default_factory=dict
    )

    missing_fields: list[str] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_semester_data(self):

        semester_numbers = [
            semester.semester_number
            for semester in self.semesters
            if semester.semester_number is not None
        ]

        if len(semester_numbers) != len(set(semester_numbers)):
            raise ValueError(
                "Duplicate semester numbers detected"
            )

        return self


# ==========================================
# STUDENT CORRECTIONS
# ==========================================

class StudentCorrection(BaseModel):

    full_name: Optional[str] = None

    father_name: Optional[str] = None
    mother_name: Optional[str] = None

    date_of_birth: Optional[str] = None

    mobile_number: Optional[str] = None
    email: Optional[str] = None

    school_name: Optional[str] = None
    board: Optional[str] = None

    usn: Optional[str] = None
    roll_number: Optional[str] = None
    registration_number: Optional[str] = None

    college_name: Optional[str] = None
    university_name: Optional[str] = None

    degree: Optional[str] = None
    branch: Optional[str] = None
    stream: Optional[str] = None


# ==========================================
# SUBJECT CORRECTIONS
# ==========================================

class SubjectCorrection(BaseModel):

    semester_index: int = Field(ge=0)
    subject_index: int = Field(ge=0)

    subject_code: Optional[str] = None
    subject_name: Optional[str] = None

    credits: Optional[float] = Field(
        default=None, ge=0
    )

    maximum_marks: Optional[float] = Field(
        default=None, ge=0
    )

    marks_obtained: Optional[float] = Field(
        default=None, ge=0
    )

    internal_marks: Optional[float] = Field(
        default=None, ge=0
    )

    external_marks: Optional[float] = Field(
        default=None, ge=0
    )

    grade: Optional[str] = None

    grade_points: Optional[float] = Field(
        default=None, ge=0
    )

    result: Optional[str] = None

    @model_validator(mode="after")
    def validate_correction(self):

        fields = self.model_fields_set - {
            "semester_index",
            "subject_index"
        }

        if not fields:
            raise ValueError(
                "At least one subject field must be provided"
            )

        return self


# ==========================================
# COMPLETE MARKSHEET CORRECTION REQUEST
# ==========================================

class MarksheetCorrectionRequest(BaseModel):

    student: Optional[StudentCorrection] = None

    subject_corrections: list[SubjectCorrection] = Field(
        default_factory=list
    )

    total_marks_obtained: Optional[float] = Field(
        default=None, ge=0
    )

    maximum_marks: Optional[float] = Field(
        default=None, ge=0
    )

    percentage: Optional[float] = Field(
        default=None, ge=0, le=100
    )

    cgpa: Optional[float] = Field(
        default=None, ge=0, le=10
    )

    overall_result: Optional[str] = None

    year_of_passing: Optional[int] = Field(
        default=None, ge=1900, le=2100
    )

    @model_validator(mode="after")
    def validate_request(self):

        has_student_changes = (
            self.student is not None
            and bool(self.student.model_fields_set)
        )

        has_summary_changes = bool(
            self.model_fields_set
            & {
                "total_marks_obtained",
                "maximum_marks",
                "percentage",
                "cgpa",
                "overall_result",
                "year_of_passing"
            }
        )

        if not (
            has_student_changes
            or self.subject_corrections
            or has_summary_changes
        ):
            raise ValueError(
                "At least one correction must be provided"
            )

        return self
