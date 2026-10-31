import uuid
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class AuditEvent(CreatedAtMixin, Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str]
    resource_type: Mapped[str | None]
    resource_id: Mapped[uuid.UUID | None]
    ip: Mapped[str | None] = mapped_column(INET)
    request_id: Mapped[str | None]
    # The column is named "metadata", but that attribute name is reserved by SQLAlchemy.
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )


Index("audit_events_actor_created_idx", AuditEvent.actor_id, AuditEvent.created_at.desc())
Index("audit_events_resource_idx", AuditEvent.resource_type, AuditEvent.resource_id)
