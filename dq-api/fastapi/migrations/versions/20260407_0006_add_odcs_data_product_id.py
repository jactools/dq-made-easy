"""add odcs data product id to data_products

Revision ID: 20260407_0006
Revises: 20260406_0005
Create Date: 2026-04-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260407_0006"
down_revision = "20260406_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_products",
        sa.Column("odcs_data_product_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("data_products", "odcs_data_product_id")
