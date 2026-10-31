import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CHAR, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin

# Must match the embedding model in AGENTS.md. Changing it needs a migration and re-embedding.
EMBEDDING_DIMENSIONS = 384


class Document(CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("length(title) BETWEEN 1 AND 200", name="title_length"),
        CheckConstraint("length(filename) <= 255", name="filename_length"),
        CheckConstraint("size_bytes > 0", name="size_bytes"),
        CheckConstraint("status IN ('uploaded', 'processing', 'ready', 'failed')", name="status"),
        # The same file uploaded twice by one user is rejected, unless the earlier one was deleted.
        Index(
            "documents_owner_sha256_uidx",
            "owner_id",
            "sha256",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Serves the document list (keyset pagination).
        Index(
            "documents_owner_created_idx",
            "owner_id",
            text("created_at DESC"),
            text("id DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str]
    filename: Mapped[str]
    mime_type: Mapped[str]
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(CHAR(64))
    status: Mapped[str] = mapped_column(server_default="uploaded")
    error_message: Mapped[str | None]
    page_count: Mapped[int | None]
    chunk_count: Mapped[int] = mapped_column(server_default=text("0"))
    embedding_model: Mapped[str | None]
    deleted_at: Mapped[datetime | None]


class DocumentChunk(CreatedAtMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("chunk_index >= 0", name="chunk_index"),
        CheckConstraint("token_count > 0", name="token_count"),
        # No vector index: retrieval filters to one document first, so an exact scan over a few
        # hundred rows is fast and has perfect recall (ADR-009).
        Index("document_chunks_doc_index_uidx", "document_id", "chunk_index", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    # Repeated from the document on purpose, so every query can filter on it directly.
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    chunk_index: Mapped[int]
    section_label: Mapped[str | None]
    heading: Mapped[str | None]
    content: Mapped[str]
    token_count: Mapped[int]
    page_start: Mapped[int | None]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
