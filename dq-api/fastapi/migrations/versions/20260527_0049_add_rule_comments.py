"""add comments to rules

Revision ID: 20260527_0049_rule_comments
Revises: 20260527_0048_incident_rc
Create Date: 2026-05-27 20:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_0049_rule_comments"
down_revision = "20260527_0048_incident_rc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("comments", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rules", "comments")