"""add validation run plan tables

Revision ID: 20260426_0027
Revises: 20260426_0026
Create Date: 2026-04-26 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260426_0027"
down_revision = "20260426_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_run_plans",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("business_key", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("scope_selector_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("planning_mode", sa.Text(), nullable=False),
        sa.Column("current_active_version_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.Text(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_dispatched_run_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_run_plans_workspace", "validation_run_plans", ["workspace_id"], unique=False)
    op.create_index("ix_validation_run_plans_status", "validation_run_plans", ["status"], unique=False)

    op.create_table(
        "validation_run_plan_versions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_plan_id", sa.Text(), nullable=False),
        sa.Column(
            "validation_artifact_selection_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("artifact_id", sa.Text(), nullable=True),
        sa.Column("artifact_version", sa.Integer(), nullable=True),
        sa.Column("artifact_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("execution_contract_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("schedule_definition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("governance_state", sa.Text(), nullable=False),
        sa.Column("validation_status", sa.Text(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_version_id", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_plan_id"], ["validation_run_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_run_plan_versions_plan",
        "validation_run_plan_versions",
        ["run_plan_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_validation_run_plan_versions_artifact",
        "validation_run_plan_versions",
        ["artifact_id", "artifact_version"],
        unique=False,
    )

    op.create_table(
        "validation_run_plan_transitions",
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
        sa.ForeignKeyConstraint(["run_plan_id"], ["validation_run_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_plan_version_id"], ["validation_run_plan_versions.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_validation_run_plan_transitions_plan_occurred_at",
        "validation_run_plan_transitions",
        ["run_plan_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_validation_run_plan_transitions_version_occurred_at",
        "validation_run_plan_transitions",
        ["run_plan_version_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_validation_run_plan_transitions_version_occurred_at",
        table_name="validation_run_plan_transitions",
    )
    op.drop_index(
        "ix_validation_run_plan_transitions_plan_occurred_at",
        table_name="validation_run_plan_transitions",
    )
    op.drop_table("validation_run_plan_transitions")

    op.drop_index(
        "ix_validation_run_plan_versions_artifact",
        table_name="validation_run_plan_versions",
    )
    op.drop_index(
        "ix_validation_run_plan_versions_plan",
        table_name="validation_run_plan_versions",
    )
    op.drop_table("validation_run_plan_versions")

    op.drop_index("ix_validation_run_plans_status", table_name="validation_run_plans")
    op.drop_index("ix_validation_run_plans_workspace", table_name="validation_run_plans")
    op.drop_table("validation_run_plans")