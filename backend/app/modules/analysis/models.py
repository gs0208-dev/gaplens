import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin


class Analysis(CreatedAtMixin, Base):
    """One gap report run on one document. It has no updated_at on purpose: the status moves
    forward a few times within minutes, and the stuck-job sweep can use created_at."""

    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="status"),
        # Serves "latest analysis of a document".
        Index("analyses_document_created_idx", "document_id", text("created_at DESC")),
        # At most one active analysis per document, enforced by the database so that two
        # simultaneous starts cannot both pass (idempotent start, no double spend).
        Index(
            "analyses_one_active_per_document_uidx",
            "document_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    # Repeated from the document on purpose, so every query can filter on it directly.
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(server_default="queued")
    prompt_version: Mapped[str]
    model: Mapped[str]
    summary: Mapped[str | None]
    findings_count: Mapped[int] = mapped_column(server_default=text("0"))
    error_message: Mapped[str | None]
    completed_at: Mapped[datetime | None]


class Finding(CreatedAtMixin, UpdatedAtMixin, Base):
    """One gap in the document. It has no owner_id: it is reached through its analysis, and
    every query must join analyses to filter on the owner."""

    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint("kind IN ('missing', 'unclear', 'contradiction')", name="kind"),
        CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity"),
        CheckConstraint("length(title) <= 160", name="title_length"),
        CheckConstraint(
            "review_status IN ('open', 'confirmed', 'dismissed')", name="review_status"
        ),
        # Serves the report: the findings of one analysis in display order.
        Index("findings_analysis_position_uidx", "analysis_id", "position", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    # Display order within the analysis.
    position: Mapped[int]
    kind: Mapped[str]
    severity: Mapped[str]
    title: Mapped[str]
    description: Mapped[str]
    suggested_question: Mapped[str]
    review_status: Mapped[str] = mapped_column(server_default="open")


class FindingCitation(Base):
    """A verified quote that backs a finding. Unlike chat citations, which are a display
    snapshot, these are rows because they are validated, joined and cascade with the chunk."""

    __tablename__ = "finding_citations"
    __table_args__ = (
        # Serves the report join from findings to their citations.
        Index("finding_citations_finding_id_idx", "finding_id"),
        # Serves the cascade when chunks are deleted.
        Index("finding_citations_chunk_id_idx", "chunk_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE")
    )
    section_label: Mapped[str | None]
    # A verbatim substring of the chunk, checked in code before it is stored.
    quote: Mapped[str]
