from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatAnswerOut(BaseModel):
    """What the model must return for a chat question (docs/ai-engineering.md, Chat answer)."""

    # The response format is a JSON schema the API enforces, which is why extra keys are refused.
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(max_length=4000)
    # Numbers of the sources the answer relies on, as shown in the prompt: [S1] is 1.
    cited_sources: list[int] = Field(max_length=20)
    grounded: bool


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_label: str | None = None
    # Checked against the stored chunks in code (S3-4); the model only proposes it.
    quote: str = Field(min_length=10, max_length=400)


class FindingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["missing", "unclear", "contradiction"]
    severity: Literal["high", "medium", "low"]
    title: str = Field(max_length=160)
    description: str = Field(max_length=800)
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_question: str = Field(max_length=300)


class GapReportOut(BaseModel):
    """What the model must return for a gap report (docs/ai-engineering.md, Gap report)."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(max_length=800)
    findings: list[FindingOut] = Field(max_length=40)


@dataclass(frozen=True)
class Turn:
    """One message sent to the model."""

    role: Literal["user", "assistant"]
    content: str
