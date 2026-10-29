import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, func, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin


class User(CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(email) <= 254", name="email_length"),
        CheckConstraint("role IN ('user', 'admin')", name="role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str]
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(server_default="user")
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    last_login_at: Mapped[datetime | None]


# Case-insensitive uniqueness: "A@x.com" and "a@x.com" are the same account.
Index("users_email_lower_uidx", func.lower(User.email), unique=True)


class RefreshToken(CreatedAtMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("refresh_tokens_token_hash_uidx", "token_hash", unique=True),
        Index("refresh_tokens_user_id_idx", "user_id"),
        Index("refresh_tokens_family_id_idx", "family_id"),
        Index("refresh_tokens_expires_at_idx", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID]
    token_hash: Mapped[str]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    user_agent: Mapped[str | None]
    ip: Mapped[str | None] = mapped_column(INET)


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
