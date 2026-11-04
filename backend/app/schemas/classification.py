from typing import Literal
from pydantic import BaseModel, Field, model_validator


DocumentType = Literal[
    "identity_document",
    "marksheet",
    "transcript",
    "resume",
    "certificate",
    "offer_letter",
    "admission_letter",
    "study_notes",
    "other",
    "unknown"
]


class ClassifiedDocument(BaseModel):

    document_type: DocumentType

    start_page: int = Field(ge=1)

    end_page: int = Field(ge=1)

    confidence: float = Field(ge=0.0, le=1.0)

    evidence: str


    @model_validator(mode="after")
    def validate_page_range(self):
        if self.start_page > self.end_page:
            raise ValueError("start_page cannot exceed end_page")

        return self


class ClassificationResult(BaseModel):

    documents: list[ClassifiedDocument]

    @model_validator(mode="after")
    def validate_document_ranges(self):
        documents = sorted(
            self.documents,
            key=lambda document: document.start_page
        )

        for previous, current in zip(documents, documents[1:]):
            if current.start_page <= previous.end_page:
                raise ValueError("Document page ranges cannot overlap")

        return self