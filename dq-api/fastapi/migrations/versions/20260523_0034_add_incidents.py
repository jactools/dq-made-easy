"""add incidents

Revision ID: 20260523_0034
Revises: 20260523_0033
Create Date: 2026-05-23 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260523_0034"
down_revision = "20260523_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("incident_kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=True),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("run_plan_id", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("scope_kind", sa.Text(), nullable=True),
        sa.Column("scope_id", sa.Text(), nullable=True),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("violated_rule_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("violation_count", sa.Integer(), nullable=True),
        sa.Column("itsm_ticket_id", sa.Text(), nullable=True),
        sa.Column("itsm_ticket_number", sa.Text(), nullable=True),
        sa.Column("assigned_to", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_kind", "incidents", ["incident_kind"], unique=False)
    op.create_index("ix_incidents_status", "incidents", ["status"], unique=False)
    op.create_index("ix_incidents_workspace", "incidents", ["workspace_id"], unique=False)
    op.create_index("ix_incidents_run_id", "incidents", ["run_id"], unique=False)
    op.create_index("ix_incidents_scope", "incidents", ["scope_kind", "scope_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_incidents_scope", table_name="incidents")
    op.drop_index("ix_incidents_run_id", table_name="incidents")
    op.drop_index("ix_incidents_workspace", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_kind", table_name="incidents")
    op.drop_table("incidents")
