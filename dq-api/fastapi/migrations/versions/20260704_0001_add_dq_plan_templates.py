"""add dq plan templates

Revision ID: 20260704_0001
Revises: 20260531_0059
Create Date: 2026-07-04

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = "20260704_0001"
down_revision = "20260531_0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create dq_plan_templates table
    op.create_table(
        "dq_plan_templates",
        sa.Column("template_id", sa.Text(), nullable=False),
        sa.Column("template_name", sa.Text(), nullable=False),
        sa.Column("template_description", sa.Text(), nullable=True),
        sa.Column("template_version", sa.Text(), nullable=False),
        sa.Column("template_type", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("parameters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("suites_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("configuration_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("schedule_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("approver", sa.Text(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approval_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("template_id"),
    )
    
    # Create indexes
    op.create_index("ix_dq_plan_templates_workspace", "dq_plan_templates", ["workspace_id"])
    op.create_index("ix_dq_plan_templates_domain", "dq_plan_templates", ["domain"])
    op.create_index("ix_dq_plan_templates_type", "dq_plan_templates", ["template_type"])
    op.create_index("ix_dq_plan_templates_tags", "dq_plan_templates", ["tags"], postgresql_using="gin")
    op.create_index("ix_dq_plan_templates_is_active", "dq_plan_templates", ["is_active"])
    
    # Create dq_plan_template_versions table
    op.create_table(
        "dq_plan_template_versions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("template_id", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Text(), nullable=False),
        sa.Column("template_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "template_version", name="uq_template_version"),
    )
    
    # Create indexes for versions
    op.create_index("ix_dq_plan_template_versions_template_id", "dq_plan_template_versions", ["template_id"])
    op.create_index("ix_dq_plan_template_versions_created_at", "dq_plan_template_versions", ["created_at"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_dq_plan_template_versions_created_at", table_name="dq_plan_template_versions")
    op.drop_index("ix_dq_plan_template_versions_template_id", table_name="dq_plan_template_versions")
    op.drop_index("ix_dq_plan_templates_is_active", table_name="dq_plan_templates")
    op.drop_index("ix_dq_plan_templates_tags", table_name="dq_plan_templates")
    op.drop_index("ix_dq_plan_templates_type", table_name="dq_plan_templates")
    op.drop_index("ix_dq_plan_templates_domain", table_name="dq_plan_templates")
    op.drop_index("ix_dq_plan_templates_workspace", table_name="dq_plan_templates")
    
    # Drop tables
    op.drop_table("dq_plan_template_versions")
    op.drop_table("dq_plan_templates")
