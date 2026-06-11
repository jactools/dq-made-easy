"""add token fields to sessions

Revision ID: 20260409_0008
Revises: 20260408_0007
Create Date: 2026-04-09 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260409_0008"
down_revision = "20260408_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("access_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("id_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("refresh_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "token_expires_at")
    op.drop_column("sessions", "refresh_token")
    op.drop_column("sessions", "id_token")
    op.drop_column("sessions", "access_token")
