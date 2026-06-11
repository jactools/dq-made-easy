"""add effective status to approvals

Revision ID: 20260412_0014
Revises: 20260412_0013
Create Date: 2026-04-12 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260412_0014"
down_revision = "20260412_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("effectivestatus", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("approvals", "effectivestatus")