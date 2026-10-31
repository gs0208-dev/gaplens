import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin


class ChatThread(CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "chat_threads"
    __table_args__ = (
        Index("chat_threads_document_updated_idx", "document_id", text("updated_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    # Repeated from the document on purpose, so every query can filter on it directly.
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str | None]


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        Index("chat_messages_thread_created_idx", "thread_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"))
    role: Mapped[str]
    content: Mapped[str]
    # Assistant messages only.
    grounded: Mapped[bool | None]
    # A display snapshot, [{chunk_id, section_label, quote}]. It is never queried.
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    # Set by the code, not by now(): the question and its answer are written in one transaction,
    # where now() would be the same for both and the order of the pair would be a coin flip.
    created_at: Mapped[datetime]
