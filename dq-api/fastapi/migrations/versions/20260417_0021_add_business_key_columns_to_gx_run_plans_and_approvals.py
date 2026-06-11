"""add business key columns to gx run plans and approvals

Revision ID: 20260417_0021
Revises: 20260417_0020
Create Date: 2026-04-17 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260417_0021"
down_revision = "20260417_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gx_run_plans", sa.Column("business_key", sa.Text(), nullable=True))
    op.add_column("approvals", sa.Column("business_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("approvals", "business_key")
    op.drop_column("gx_run_plans", "business_key")