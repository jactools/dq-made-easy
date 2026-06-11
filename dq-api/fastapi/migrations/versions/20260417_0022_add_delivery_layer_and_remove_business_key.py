"""add delivery layer and remove business key

Revision ID: 20260417_0022
Revises: 20260417_0021
Create Date: 2026-04-17 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260417_0022"
down_revision = "20260417_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_deliveries",
        sa.Column("layer", sa.Text(), server_default="standardized", nullable=False),
    )
    op.add_column(
        "data_delivery_notes",
        sa.Column("layer", sa.Text(), server_default="standardized", nullable=False),
    )

    op.execute(
        """
        UPDATE data_deliveries
        SET delivery_location = CASE
            WHEN delivery_location LIKE 'standardized/%' THEN delivery_location
            WHEN COALESCE(business_key, '') <> '' THEN 'standardized/' || business_key
            ELSE 'standardized/' || regexp_replace(COALESCE(delivery_location, ''), '^[^:]+://', '')
        END,
            layer = COALESCE(layer, 'standardized')
        """
    )
    op.execute("UPDATE data_delivery_notes SET layer = COALESCE(layer, 'standardized')")

    op.drop_column("data_deliveries", "business_key")
    op.drop_column("data_delivery_notes", "business_key")


def downgrade() -> None:
    op.add_column("data_delivery_notes", sa.Column("business_key", sa.Text(), nullable=True))
    op.add_column("data_deliveries", sa.Column("business_key", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE data_deliveries
        SET business_key = CASE
            WHEN delivery_location LIKE 'standardized/%' THEN substr(delivery_location, length('standardized/') + 1)
            ELSE delivery_location
        END
        """
    )

    op.drop_column("data_delivery_notes", "layer")
    op.drop_column("data_deliveries", "layer")