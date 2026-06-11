"""add incident root cause suggestions

Revision ID: 20260527_0048_incident_rc
Revises: 20260527_0047
Create Date: 2026-05-27 03:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260527_0048_incident_rc"
down_revision = "20260527_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_root_cause_suggestions",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("incident_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("incident_count", sa.Integer(), nullable=False),
        sa.Column("suggested_root_cause", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=True, server_default="pending"),
        sa.Column("events_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("assistance_requested_at", sa.DateTime(), nullable=True),
        sa.Column("assistance_request_reference_id", sa.Text(), nullable=True),
        sa.Column("assistance_request_ticket_id", sa.Text(), nullable=True),
        sa.Column("assistance_request_ticket_number", sa.Text(), nullable=True),
        sa.Column("assistance_request_ticket_url", sa.Text(), nullable=True),
        sa.Column("assistance_request_ticket_system", sa.Text(), nullable=True),
        sa.Column("assistance_request_delivery_modes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("assistance_request_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_incident_root_cause_suggestions_workspace",
        "incident_root_cause_suggestions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_incident_root_cause_suggestions_status",
        "incident_root_cause_suggestions",
        ["status"],
    )
    op.create_index(
        "ix_incident_root_cause_suggestions_created_at",
        "incident_root_cause_suggestions",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_incident_root_cause_suggestions_created_at", table_name="incident_root_cause_suggestions")
    op.drop_index("ix_incident_root_cause_suggestions_status", table_name="incident_root_cause_suggestions")
    op.drop_index("ix_incident_root_cause_suggestions_workspace", table_name="incident_root_cause_suggestions")
    op.drop_table("incident_root_cause_suggestions")