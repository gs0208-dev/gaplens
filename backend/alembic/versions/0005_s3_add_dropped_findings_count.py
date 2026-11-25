"""s3 add dropped_findings_count to analyses

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-26 12:00:00.000000

Written by hand from docs/database.md, like 0001 to 0004.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A constant default, so Postgres adds the column without rewriting the table.
    op.add_column(
        "analyses",
        sa.Column(
            "dropped_findings_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("analyses", "dropped_findings_count")
