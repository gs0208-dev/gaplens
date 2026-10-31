import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class LlmCall(CreatedAtMixin, Base):
    """One call to a language model: how big, how long, how it ended. By design it holds no
    prompt and no output, so it can be kept and read without exposing a document."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint("purpose IN ('gap_report', 'chat', 'eval')", name="purpose"),
        CheckConstraint("status IN ('ok', 'error', 'timeout', 'invalid_output')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    purpose: Mapped[str]
    model: Mapped[str]
    prompt_version: Mapped[str]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    status: Mapped[str]
    error_code: Mapped[str | None]
    request_id: Mapped[str | None]


Index("llm_calls_owner_created_idx", LlmCall.owner_id, LlmCall.created_at.desc())
Index("llm_calls_created_idx", LlmCall.created_at)
