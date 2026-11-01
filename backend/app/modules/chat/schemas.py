import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

MAX_QUESTION_LENGTH = 1000


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH)
    ]
    thread_id: uuid.UUID | None = None


class CitationOut(BaseModel):
    chunk_id: uuid.UUID
    section_label: str | None
    quote: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    grounded: bool | None
    citations: list[CitationOut]
    created_at: datetime


class ChatResponse(BaseModel):
    thread_id: uuid.UUID
    message: MessageOut


class MessagePage(BaseModel):
    items: list[MessageOut]
    next_cursor: str | None


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ThreadPage(BaseModel):
    items: list[ThreadOut]
    next_cursor: str | None
