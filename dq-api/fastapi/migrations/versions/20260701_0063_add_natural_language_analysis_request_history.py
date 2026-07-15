"""add natural language analysis request history

Revision ID: 20260701_0063
Revises: 20260628_0062
Create Date: 2026-07-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260701_0063"
down_revision = "20260628_0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS natural_language_analysis_request_history (
            id text PRIMARY KEY,
            request_id text NOT NULL REFERENCES natural_language_analysis_requests(request_id) ON DELETE CASCADE,
            action text NOT NULL,
            from_status text NULL,
            to_status text NULL,
            actor_id text NULL,
            changed_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
            details_json jsonb NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_natural_language_analysis_request_history_request ON natural_language_analysis_request_history (request_id, changed_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_natural_language_analysis_request_history_changed_at ON natural_language_analysis_request_history (changed_at)"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_natural_language_analysis_request_history_changed_at",
        table_name="natural_language_analysis_request_history",
    )
    op.drop_index(
        "ix_natural_language_analysis_request_history_request",
        table_name="natural_language_analysis_request_history",
    )
    op.drop_table("natural_language_analysis_request_history")