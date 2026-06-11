"""add suggestion preview interactions

Revision ID: 20260427_0029
Revises: 20260426_0028
Create Date: 2026-04-27 11:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260427_0029"
down_revision = "20260426_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suggestion_preview_interactions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_suggestion_preview_interactions_workspace_action_created",
        "suggestion_preview_interactions",
        ["workspace_id", "action", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_suggestion_preview_interactions_user_created",
        "suggestion_preview_interactions",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_suggestion_preview_interactions_user_created",
        table_name="suggestion_preview_interactions",
    )
    op.drop_index(
        "ix_suggestion_preview_interactions_workspace_action_created",
        table_name="suggestion_preview_interactions",
    )
    op.drop_table("suggestion_preview_interactions")