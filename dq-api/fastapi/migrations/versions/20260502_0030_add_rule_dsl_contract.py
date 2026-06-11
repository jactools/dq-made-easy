"""add rule dsl contract columns

Revision ID: 20260502_0030
Revises: 20260427_0029
Create Date: 2026-05-02 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260502_0030"
down_revision = "20260427_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("dsl", sa.Text(), nullable=True))
    op.add_column("rule_versions", sa.Column("dsl", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rule_versions", "dsl")
    op.drop_column("rules", "dsl")