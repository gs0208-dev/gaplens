import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    status: Literal["uploaded", "processing", "ready", "failed"]
    error_message: str | None
    page_count: int | None
    chunk_count: int
    created_at: datetime


class DocumentResponse(BaseModel):
    document: DocumentOut


class DocumentSummary(BaseModel):
    """One row of the documents list: what a table needs, nothing more."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: Literal["uploaded", "processing", "ready", "failed"]
    page_count: int | None
    chunk_count: int
    created_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentSummary]
    next_cursor: str | None


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    section_label: str | None
    heading: str | None
    content: str
    page_start: int | None


class ChunkList(BaseModel):
    items: list[ChunkOut]
