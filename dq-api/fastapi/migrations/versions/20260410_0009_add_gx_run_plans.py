"""add gx run plan tables

Revision ID: 20260410_0009
Revises: 20260409_0008
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260410_0009"
down_revision = "20260409_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gx_run_plans",
        sa.Column("id", sa.Text(), nullable=False),
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
    op.create_index("ix_gx_run_plans_workspace", "gx_run_plans", ["workspace_id"], unique=False)
    op.create_index("ix_gx_run_plans_status", "gx_run_plans", ["status"], unique=False)

    op.create_table(
        "gx_run_plan_versions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_plan_id", sa.Text(), nullable=False),
        sa.Column("suite_id", sa.Text(), nullable=False),
        sa.Column("suite_version", sa.Integer(), nullable=False),
        sa.Column("suite_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("execution_contract_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("schedule_definition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_status", sa.Text(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_version_id", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_plan_id"], ["gx_run_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gx_run_plan_versions_plan", "gx_run_plan_versions", ["run_plan_id", "created_at"], unique=False)
    op.create_index("ix_gx_run_plan_versions_suite", "gx_run_plan_versions", ["suite_id", "suite_version"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gx_run_plan_versions_suite", table_name="gx_run_plan_versions")
    op.drop_index("ix_gx_run_plan_versions_plan", table_name="gx_run_plan_versions")
    op.drop_table("gx_run_plan_versions")
    op.drop_index("ix_gx_run_plans_status", table_name="gx_run_plans")
    op.drop_index("ix_gx_run_plans_workspace", table_name="gx_run_plans")
    op.drop_table("gx_run_plans")