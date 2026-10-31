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
