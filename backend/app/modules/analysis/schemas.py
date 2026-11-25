import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ReviewStatus = Literal["open", "confirmed", "dismissed"]


class CitationOut(BaseModel):
    chunk_id: uuid.UUID
    section_label: str | None
    quote: str


class FindingDetail(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str
    title: str
    description: str
    suggested_question: str
    review_status: str
    citations: list[CitationOut]


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    summary: str | None
    findings_count: int
    dropped_findings_count: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    findings: list[FindingDetail] = []


class AnalysisResponse(BaseModel):
    analysis: AnalysisOut


class FindingResponse(BaseModel):
    finding: FindingDetail


class ReviewStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: ReviewStatus
