"""expand gx run plan governance shape

Revision ID: 20260410_0010
Revises: 20260410_0009
Create Date: 2026-04-10 00:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260410_0010"
down_revision = "20260410_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gx_run_plan_versions",
        sa.Column("gx_suite_selection_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        """
        UPDATE gx_run_plan_versions
        SET gx_suite_selection_json = jsonb_build_object(
            'selectionMode', 'single_suite',
            'suiteId', suite_id,
            'suiteVersion', suite_version
        )
        WHERE gx_suite_selection_json IS NULL
        """
    )
    op.alter_column("gx_run_plan_versions", "gx_suite_selection_json", nullable=False)
    op.alter_column("gx_run_plan_versions", "suite_id", nullable=True)
    op.alter_column("gx_run_plan_versions", "suite_version", nullable=True)
    op.alter_column("gx_run_plan_versions", "suite_snapshot_json", nullable=True)


def downgrade() -> None:
    op.execute(
        """
        UPDATE gx_run_plan_versions
        SET suite_id = COALESCE(suite_id, '__grouped_scope__'),
            suite_version = COALESCE(suite_version, 1),
            suite_snapshot_json = COALESCE(suite_snapshot_json, '{}'::jsonb)
        """
    )
    op.alter_column("gx_run_plan_versions", "suite_snapshot_json", nullable=False)
    op.alter_column("gx_run_plan_versions", "suite_version", nullable=False)
    op.alter_column("gx_run_plan_versions", "suite_id", nullable=False)
    op.drop_column("gx_run_plan_versions", "gx_suite_selection_json")