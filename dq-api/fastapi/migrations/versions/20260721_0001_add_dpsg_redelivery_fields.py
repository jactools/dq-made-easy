"""add DPSG-compliant redelivery fields to data_delivery_notes

Adds delivery_type, predecessor_time_event, superseded_by_time_event,
correction_reason, and delivered_by columns to the data_delivery_notes
table to support traceability of corrections, supersession, and redeliveries
per DPSG immutability standards.

Revision ID: 20260721_0001
Revises: 20260710_0001
Create Date: 2026-07-21

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20260721_0001"
down_revision = "20260710_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Delivery type classification
    op.add_column(
        "data_delivery_notes",
        sa.Column(
            "delivery_type",
            sa.Text(),
            nullable=True,
            comment="Delivery type: initial, retry, correction, backfill, deletion, retention",
        ),
    )
    # Predecessor reference (correction workflow)
    op.add_column(
        "data_delivery_notes",
        sa.Column(
            "predecessor_time_event",
            sa.Text(),
            nullable=True,
            comment="UUIDv7 of the delivery being corrected or replaced",
        ),
    )
    op.create_index(
        "ix_data_delivery_notes_predecessor_time_event",
        "data_delivery_notes",
        ["predecessor_time_event"],
    )
    # Supersession reference
    op.add_column(
        "data_delivery_notes",
        sa.Column(
            "superseded_by_time_event",
            sa.Text(),
            nullable=True,
            comment="UUIDv7 of the delivery that supersedes this one",
        ),
    )
    op.create_index(
        "ix_data_delivery_notes_superseded_by_time_event",
        "data_delivery_notes",
        ["superseded_by_time_event"],
    )
    # Correction reason
    op.add_column(
        "data_delivery_notes",
        sa.Column(
            "correction_reason",
            sa.Text(),
            nullable=True,
            comment="Reason the correction was needed",
        ),
    )
    # Delivered by (pipeline/agent identifier)
    op.add_column(
        "data_delivery_notes",
        sa.Column(
            "delivered_by",
            sa.Text(),
            nullable=True,
            comment="Pipeline or agent that produced this delivery",
        ),
    )


def downgrade() -> None:
    op.drop_column("data_delivery_notes", "delivered_by")
    op.drop_column("data_delivery_notes", "correction_reason")
    op.drop_index("ix_data_delivery_notes_superseded_by_time_event", table_name="data_delivery_notes")
    op.drop_column("data_delivery_notes", "superseded_by_time_event")
    op.drop_index("ix_data_delivery_notes_predecessor_time_event", table_name="data_delivery_notes")
    op.drop_column("data_delivery_notes", "predecessor_time_event")
    op.drop_column("data_delivery_notes", "delivery_type")
