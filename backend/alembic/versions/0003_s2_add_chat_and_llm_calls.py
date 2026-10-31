"""s2 add chat threads, chat messages and llm calls

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 12:00:00.000000

Written by hand from docs/database.md, like 0001 and 0002.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_primary_key() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _timestamp(name: str) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        _uuid_primary_key(),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("chat_threads_pkey")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("chat_threads_document_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("chat_threads_owner_id_fkey"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "chat_threads_document_updated_idx",
        "chat_threads",
        ["document_id", sa.text("updated_at DESC")],
    )

    op.create_table(
        "chat_messages",
        _uuid_primary_key(),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=True),
        sa.Column(
            "citations",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("chat_messages_pkey")),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["chat_threads.id"],
            name=op.f("chat_messages_thread_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("chat_messages_role_check")),
    )
    op.create_index(
        "chat_messages_thread_created_idx", "chat_messages", ["thread_id", "created_at", "id"]
    )

    op.create_table(
        "llm_calls",
        _uuid_primary_key(),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("llm_calls_pkey")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("llm_calls_owner_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "purpose IN ('gap_report', 'chat', 'eval')", name=op.f("llm_calls_purpose_check")
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'timeout', 'invalid_output')",
            name=op.f("llm_calls_status_check"),
        ),
    )
    op.create_index(
        "llm_calls_owner_created_idx", "llm_calls", ["owner_id", sa.text("created_at DESC")]
    )
    # Serves the retention cleanup (llm_calls are kept 90 days).
    op.create_index("llm_calls_created_idx", "llm_calls", ["created_at"])


def downgrade() -> None:
    # This deletes every chat thread, message and llm_calls row.
    op.drop_table("llm_calls")
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
