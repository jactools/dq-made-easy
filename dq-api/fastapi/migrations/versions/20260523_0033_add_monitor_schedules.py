"""add monitor schedules

Revision ID: 20260523_0033
Revises: 20260510_0032
Create Date: 2026-05-23 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260523_0033"
down_revision = "20260510_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitor_schedules",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("scope_kind", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("monitor_type", sa.Text(), nullable=False, server_default="scheduled_monitor"),
        sa.Column("cron_expression", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="UTC"),
        sa.Column("window_minutes", sa.Integer(), nullable=False, server_default="1440"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_kind", "scope_id", name="uq_monitor_schedules_scope"),
    )
    op.create_index(
        "ix_monitor_schedules_scope",
        "monitor_schedules",
        ["scope_kind", "scope_id"],
        unique=False,
    )
    op.create_index(
        "ix_monitor_schedules_workspace",
        "monitor_schedules",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_monitor_schedules_workspace", table_name="monitor_schedules")
    op.drop_index("ix_monitor_schedules_scope", table_name="monitor_schedules")
    op.drop_table("monitor_schedules")
