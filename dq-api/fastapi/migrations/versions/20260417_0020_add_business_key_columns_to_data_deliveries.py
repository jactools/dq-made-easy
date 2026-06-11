"""add business key columns to data_deliveries and data_delivery_notes

Revision ID: 20260417_0020
Revises: 20260417_0019
Create Date: 2026-04-17 10:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260417_0020"
down_revision = "20260417_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_deliveries", sa.Column("business_key", sa.Text(), nullable=True))
    op.add_column("data_delivery_notes", sa.Column("business_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("data_delivery_notes", "business_key")
    op.drop_column("data_deliveries", "business_key")