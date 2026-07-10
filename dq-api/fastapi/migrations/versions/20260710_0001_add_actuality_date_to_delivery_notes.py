"""add actuality_date fields to data_delivery_notes

Adds ``actuality_date`` (TIMESTAMPTZ) and ``actuality_date_attribute`` (TEXT)
columns to the ``data_delivery_notes`` table so that delivery notes can carry
first-class actuality-date metadata for cross-delivery DQ rules.

Revision ID: 20260710_0001
Revises: 20260704_0001
Create Date: 2026-07-10

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20260710_0001"
down_revision = "20260704_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Actuality-date timestamp (nullable — existing rows unaffected)
    op.add_column(
        "data_delivery_notes",
        sa.Column(
            "actuality_date",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="The actuality-date of this delivery (ISO-8601 / timestamptz)",
        ),
    )
    # Which dataset column is the canonical actuality-date
    op.add_column(
        "data_delivery_notes",
        sa.Column(
            "actuality_date_attribute",
            sa.Text(),
            nullable=True,
            comment="Dataset attribute name that is the canonical actuality date",
        ),
    )


def downgrade() -> None:
    op.drop_column("data_delivery_notes", "actuality_date_attribute")
    op.drop_column("data_delivery_notes", "actuality_date")
