"""add incident remediation tracking

Revision ID: 20260524_0037
Revises: 20260524_0036
Create Date: 2026-05-24 12:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260524_0037"
down_revision = "20260524_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("comments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "incidents",
        sa.Column("resolution_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incidents", "resolution_history")
    op.drop_column("incidents", "comments")
