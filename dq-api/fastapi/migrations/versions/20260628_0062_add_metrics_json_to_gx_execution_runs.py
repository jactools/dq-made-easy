"""add metrics json to gx execution runs

Revision ID: 20260628_0062
Revises: 20260606_0061
Create Date: 2026-06-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260628_0062"
down_revision = "20260606_0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gx_execution_runs",
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gx_execution_runs", "metrics_json")