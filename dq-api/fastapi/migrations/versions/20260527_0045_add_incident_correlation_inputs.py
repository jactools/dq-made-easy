"""add incident correlation inputs

Revision ID: 20260527_0045
Revises: 20260527_0044
Create Date: 2026-05-27 09:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_0045"
down_revision = "20260527_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("source_correlation_id", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("source_parent_correlation_id", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("source_request_id", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("source_queue_message_id", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("source_trace_id", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("source_system", sa.Text(), nullable=True))
    op.create_index("ix_incidents_source_correlation", "incidents", ["source_correlation_id"], unique=False)
    op.create_index("ix_incidents_source_parent_correlation", "incidents", ["source_parent_correlation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_incidents_source_parent_correlation", table_name="incidents")
    op.drop_index("ix_incidents_source_correlation", table_name="incidents")
    op.drop_column("incidents", "source_system")
    op.drop_column("incidents", "source_trace_id")
    op.drop_column("incidents", "source_queue_message_id")
    op.drop_column("incidents", "source_request_id")
    op.drop_column("incidents", "source_parent_correlation_id")
    op.drop_column("incidents", "source_correlation_id")