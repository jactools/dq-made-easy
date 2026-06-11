"""expand gx execution runs for grouped scope

Revision ID: 20260410_0011
Revises: 20260410_0010
Create Date: 2026-04-10 00:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0011"
down_revision = "20260410_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("gx_execution_runs", "suite_id", nullable=True)
    op.alter_column("gx_execution_runs", "suite_version", nullable=True)
    op.alter_column("gx_execution_runs", "rule_id", nullable=True)
    op.alter_column("gx_execution_runs", "rule_version_id", nullable=True)
    op.add_column("gx_execution_runs", sa.Column("execution_progress_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("gx_execution_runs", "execution_progress_json")
    op.execute(
        """
        UPDATE gx_execution_runs
        SET suite_id = COALESCE(suite_id, '__grouped_scope__'),
            suite_version = COALESCE(suite_version, 1),
            rule_id = COALESCE(rule_id, '__grouped_scope__'),
            rule_version_id = COALESCE(rule_version_id, '__grouped_scope__')
        """
    )
    op.alter_column("gx_execution_runs", "rule_version_id", nullable=False)
    op.alter_column("gx_execution_runs", "rule_id", nullable=False)
    op.alter_column("gx_execution_runs", "suite_version", nullable=False)
    op.alter_column("gx_execution_runs", "suite_id", nullable=False)