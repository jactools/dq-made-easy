"""add exception fact access requests table

Revision ID: 20260506_0031
Revises: 20260502_0030
Create Date: 2026-05-06 21:31:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260506_0031"
down_revision = "20260502_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exception_fact_access_requests",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column(
            "requester_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column(
            "role_id",
            sa.Text(),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("requested_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column(
            "reviewed_by",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_exception_fact_access_requests_workspace",
        "exception_fact_access_requests",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_exception_fact_access_requests_requester",
        "exception_fact_access_requests",
        ["requester_id"],
        unique=False,
    )
    op.create_index(
        "ix_exception_fact_access_requests_status",
        "exception_fact_access_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_exception_fact_access_requests_expires_at",
        "exception_fact_access_requests",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_exception_fact_access_requests_expires_at", table_name="exception_fact_access_requests")
    op.drop_index("ix_exception_fact_access_requests_status", table_name="exception_fact_access_requests")
    op.drop_index("ix_exception_fact_access_requests_requester", table_name="exception_fact_access_requests")
    op.drop_index("ix_exception_fact_access_requests_workspace", table_name="exception_fact_access_requests")
    op.drop_table("exception_fact_access_requests")
