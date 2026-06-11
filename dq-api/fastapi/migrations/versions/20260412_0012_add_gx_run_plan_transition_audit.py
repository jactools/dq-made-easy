"""add gx run plan transition audit

Revision ID: 20260412_0012
Revises: 20260410_0011
Create Date: 2026-04-12 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260412_0012"
down_revision = "20260410_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gx_run_plan_versions", sa.Column("governance_state", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE gx_run_plan_versions
        SET governance_state = CASE
            WHEN EXISTS (
                SELECT 1
                FROM gx_run_plans plan
                WHERE plan.id = gx_run_plan_versions.run_plan_id
                  AND plan.current_active_version_id = gx_run_plan_versions.id
            ) THEN 'active'
            WHEN review_status = 'superseded' THEN 'superseded'
            WHEN review_status = 'cancelled' OR validation_status = 'cancelled' THEN 'cancelled'
            WHEN validation_status = 'failed' THEN 'validation_failed'
            WHEN review_status = 'pending' THEN 'pending_review'
            WHEN review_status = 'approved' OR validation_status IN ('approved', 'passed') THEN 'approved_pending_activation'
            WHEN validation_status = 'pending' THEN 'pending_validation'
            ELSE 'draft'
        END
        """
    )
    op.alter_column("gx_run_plan_versions", "governance_state", nullable=False)

    op.execute(
        """
        UPDATE gx_run_plans AS plan
        SET status = CASE
            WHEN plan.current_active_version_id IS NOT NULL THEN 'active'
            ELSE COALESCE(
                (
                    SELECT version.governance_state
                    FROM gx_run_plan_versions AS version
                    WHERE version.run_plan_id = plan.id
                      AND version.governance_state IN (
                          'draft',
                          'pending_validation',
                          'validation_failed',
                          'pending_review',
                          'approved_pending_activation'
                      )
                    ORDER BY version.created_at DESC
                    LIMIT 1
                ),
                plan.status,
                'draft'
            )
        END
        """
    )

    op.create_table(
        "gx_run_plan_transitions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_plan_id", sa.Text(), nullable=False),
        sa.Column("run_plan_version_id", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_plan_id"], ["gx_run_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_plan_version_id"], ["gx_run_plan_versions.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_gx_run_plan_transitions_plan_occurred_at",
        "gx_run_plan_transitions",
        ["run_plan_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_gx_run_plan_transitions_version_occurred_at",
        "gx_run_plan_transitions",
        ["run_plan_version_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_gx_run_plan_transitions_version_occurred_at", table_name="gx_run_plan_transitions")
    op.drop_index("ix_gx_run_plan_transitions_plan_occurred_at", table_name="gx_run_plan_transitions")
    op.drop_table("gx_run_plan_transitions")
    op.drop_column("gx_run_plan_versions", "governance_state")