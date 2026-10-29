"""s1 add users and auth tables

Revision ID: 0001
Revises:
Create Date: 2026-10-30 02:37:20.619513

Written by hand from docs/database.md. Autogenerate does not reliably handle expression
indexes or CHECK constraints, and both are used here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("users_pkey")),
        sa.CheckConstraint("length(email) <= 254", name=op.f("users_email_length_check")),
        sa.CheckConstraint("role IN ('user', 'admin')", name=op.f("users_role_check")),
    )
    op.create_index("users_email_lower_uidx", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        # SHA-256 hex of the opaque token. The token itself is never stored.
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("refresh_tokens_pkey")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("refresh_tokens_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by"],
            ["refresh_tokens.id"],
            name=op.f("refresh_tokens_replaced_by_fkey"),
            ondelete="SET NULL",
        ),
    )
    op.create_index("refresh_tokens_token_hash_uidx", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("refresh_tokens_user_id_idx", "refresh_tokens", ["user_id"])
    op.create_index("refresh_tokens_family_id_idx", "refresh_tokens", ["family_id"])
    # Serves the cleanup job that purges expired tokens.
    op.create_index("refresh_tokens_expires_at_idx", "refresh_tokens", ["expires_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("audit_events_pkey")),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("audit_events_actor_id_fkey"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "audit_events_actor_created_idx",
        "audit_events",
        ["actor_id", sa.text("created_at DESC")],
    )
    op.create_index("audit_events_resource_idx", "audit_events", ["resource_type", "resource_id"])


def downgrade() -> None:
    # Dropping a table drops its indexes. Order matters: both tables below point at users.
    op.drop_table("audit_events")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
