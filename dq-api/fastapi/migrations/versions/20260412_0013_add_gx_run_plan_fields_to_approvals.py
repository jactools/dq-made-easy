"""add gx run plan fields to approvals

Revision ID: 20260412_0013
Revises: 20260412_0012
Create Date: 2026-04-12 11:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260412_0013"
down_revision = "20260412_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("gxrunplanid", sa.Text(), nullable=True))
    op.add_column("approvals", sa.Column("gxrunplanversionid", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("approvals", "gxrunplanversionid")
    op.drop_column("approvals", "gxrunplanid")