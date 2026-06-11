"""add explicit rule ownership columns

Revision ID: 20260530_0053_rule_ownership
Revises: 20260530_0052_rule_lifecycle
Create Date: 2026-05-30 11:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260530_0053_rule_ownership"
down_revision = "20260530_0052_rule_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("data_steward", sa.Text(), nullable=True))
    op.add_column("rules", sa.Column("domain_owner", sa.Text(), nullable=True))
    op.add_column("rules", sa.Column("technical_owner", sa.Text(), nullable=True))
    op.add_column("rule_versions", sa.Column("data_steward", sa.Text(), nullable=True))
    op.add_column("rule_versions", sa.Column("domain_owner", sa.Text(), nullable=True))
    op.add_column("rule_versions", sa.Column("technical_owner", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rule_versions", "technical_owner")
    op.drop_column("rule_versions", "domain_owner")
    op.drop_column("rule_versions", "data_steward")
    op.drop_column("rules", "technical_owner")
    op.drop_column("rules", "domain_owner")
    op.drop_column("rules", "data_steward")