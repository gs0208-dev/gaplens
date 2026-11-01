"""s3 add analyses, findings and finding citations

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02 12:00:00.000000

Written by hand from docs/database.md, like 0001 to 0003.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
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
        "analyses",
        _uuid_primary_key(),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("findings_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        _timestamp("created_at"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("analyses_pkey")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("analyses_document_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("analyses_owner_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name=op.f("analyses_status_check"),
        ),
    )
    # Serves "latest analysis of a document" (GET /documents/{id}/analyses/latest).
    op.create_index(
        "analyses_document_created_idx",
        "analyses",
        ["document_id", sa.text("created_at DESC")],
    )
    # Serves the start of an analysis: the database refuses a second active one, so a double
    # click or two tabs cannot spend the model budget twice.
    op.create_index(
        "analyses_one_active_per_document_uidx",
        "analyses",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "findings",
        _uuid_primary_key(),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suggested_question", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), server_default="open", nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("findings_pkey")),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("findings_analysis_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('missing', 'unclear', 'contradiction')", name=op.f("findings_kind_check")
        ),
        sa.CheckConstraint(
            "severity IN ('high', 'medium', 'low')", name=op.f("findings_severity_check")
        ),
        sa.CheckConstraint("length(title) <= 160", name=op.f("findings_title_length_check")),
        sa.CheckConstraint(
            "review_status IN ('open', 'confirmed', 'dismissed')",
            name=op.f("findings_review_status_check"),
        ),
    )
    # Serves the report: the findings of one analysis in display order.
    op.create_index(
        "findings_analysis_position_uidx",
        "findings",
        ["analysis_id", "position"],
        unique=True,
    )

    op.create_table(
        "finding_citations",
        _uuid_primary_key(),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_label", sa.Text(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("finding_citations_pkey")),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name=op.f("finding_citations_finding_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("finding_citations_chunk_id_fkey"),
            ondelete="CASCADE",
        ),
    )
    # Serves the report join from findings to their citations.
    op.create_index("finding_citations_finding_id_idx", "finding_citations", ["finding_id"])
    # Serves the cascade when chunks are deleted (document delete): without it, every deleted
    # chunk would scan the whole citations table.
    op.create_index("finding_citations_chunk_id_idx", "finding_citations", ["chunk_id"])


def downgrade() -> None:
    # This deletes every analysis, finding and citation.
    op.drop_table("finding_citations")
    op.drop_table("findings")
    op.drop_table("analyses")
