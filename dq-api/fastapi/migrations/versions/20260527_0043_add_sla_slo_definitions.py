from __future__ import annotations

"""Add SLA/SLO definitions table.

Revision ID: 20260527_0043_sla_slo_def
Revises: 20260526_0042
Create Date: 2026-05-27 00:43:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260527_0043_sla_slo_def"
down_revision = "20260526_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sla_slo_definitions",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope_kind", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("metric_kind", sa.Text(), nullable=False),
        sa.Column("threshold_value", sa.Numeric(12, 4), nullable=False),
        sa.Column("threshold_operator", sa.Text(), nullable=False, server_default="gte"),
        sa.Column("lookback_amount", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("lookback_unit", sa.Text(), nullable=False, server_default="day"),
        sa.Column("lifecycle_status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("approval_status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("requested_by", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("itsm_system", sa.Text(), nullable=True),
        sa.Column("itsm_ticket_id", sa.Text(), nullable=True),
        sa.Column("itsm_ticket_number", sa.Text(), nullable=True),
        sa.Column("itsm_ticket_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sla_slo_definitions_workspace", "sla_slo_definitions", ["workspace_id"])
    op.create_index("ix_sla_slo_definitions_scope", "sla_slo_definitions", ["scope_kind", "scope_id"])
    op.create_index("ix_sla_slo_definitions_metric", "sla_slo_definitions", ["metric_kind"])
    op.create_index("ix_sla_slo_definitions_status", "sla_slo_definitions", ["lifecycle_status", "approval_status"])


def downgrade() -> None:
    op.drop_index("ix_sla_slo_definitions_status", table_name="sla_slo_definitions")
    op.drop_index("ix_sla_slo_definitions_metric", table_name="sla_slo_definitions")
    op.drop_index("ix_sla_slo_definitions_scope", table_name="sla_slo_definitions")
    op.drop_index("ix_sla_slo_definitions_workspace", table_name="sla_slo_definitions")
    op.drop_table("sla_slo_definitions")
