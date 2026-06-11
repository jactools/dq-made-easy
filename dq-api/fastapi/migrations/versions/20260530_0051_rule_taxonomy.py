"""add rule taxonomy columns

Revision ID: 20260530_0051_rule_taxonomy
Revises: 20260530_0050_gx_run_comments
Create Date: 2026-05-30 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260530_0051_rule_taxonomy"
down_revision = "20260530_0050_gx_run_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("taxonomy", sa.Text(), nullable=True))
    op.add_column("rule_versions", sa.Column("taxonomy", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rule_versions", "taxonomy")
    op.drop_column("rules", "taxonomy")
