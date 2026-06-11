"""add rule lifecycle status columns

Revision ID: 20260530_0052_rule_lifecycle
Revises: 20260530_0051_rule_taxonomy
Create Date: 2026-05-30 10:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260530_0052_rule_lifecycle"
down_revision = "20260530_0051_rule_taxonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("lifecycle_status", sa.Text(), nullable=True))
    op.add_column("rule_versions", sa.Column("lifecycle_status", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE rules
        SET lifecycle_status = CASE
            WHEN deleted_on IS NOT NULL THEN 'retired'
            ELSE 'active'
        END
        WHERE lifecycle_status IS NULL
        """
    )
    op.execute(
        """
        UPDATE rule_versions
        SET lifecycle_status = 'active'
        WHERE lifecycle_status IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("rule_versions", "lifecycle_status")
    op.drop_column("rules", "lifecycle_status")