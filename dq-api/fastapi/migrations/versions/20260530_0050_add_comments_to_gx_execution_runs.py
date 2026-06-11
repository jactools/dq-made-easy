"""add comments to gx execution runs

Revision ID: 20260530_0050_gx_run_comments
Revises: 20260527_0049_rule_comments
Create Date: 2026-05-30 00:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260530_0050_gx_run_comments"
down_revision = "20260527_0049_rule_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gx_execution_runs", sa.Column("comments", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("gx_execution_runs", "comments")
