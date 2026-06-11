"""add natural language analysis requests

Revision ID: 20260510_0032
Revises: 20260506_0031
Create Date: 2026-05-10 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260510_0032"
down_revision = "20260506_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "natural_language_analysis_requests",
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("requested_by_user_id", sa.Text(), nullable=False),
        sa.Column("current_workspace_id", sa.Text(), nullable=False),
        sa.Column("search_scope", sa.Text(), nullable=False),
        sa.Column("analysis_provider", sa.Text(), nullable=False),
        sa.Column("analysis_type", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("selected_attribute_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("accessible_workspace_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending", nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("suggestion_id", sa.Text(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index(
        "ix_nl_analysis_requests_user_workspace_requested",
        "natural_language_analysis_requests",
        ["requested_by_user_id", "current_workspace_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_nl_analysis_requests_status_requested",
        "natural_language_analysis_requests",
        ["status", "requested_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_nl_analysis_requests_status_requested",
        table_name="natural_language_analysis_requests",
    )
    op.drop_index(
        "ix_nl_analysis_requests_user_workspace_requested",
        table_name="natural_language_analysis_requests",
    )
    op.drop_table("natural_language_analysis_requests")