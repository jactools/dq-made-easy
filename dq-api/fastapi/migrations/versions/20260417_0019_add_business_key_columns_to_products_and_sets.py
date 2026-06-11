"""add business key columns to data_products and data_sets

Revision ID: 20260417_0019
Revises: 20260417_0018
Create Date: 2026-04-17 10:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260417_0019"
down_revision = "20260417_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_products", sa.Column("business_key", sa.Text(), nullable=True))
    op.add_column("data_sets", sa.Column("business_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("data_sets", "business_key")
    op.drop_column("data_products", "business_key")