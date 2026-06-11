"""add data_object_version_id and delivery_location to data_deliveries

Revision ID: 20260412_0015
Revises: 20260412_0014
Create Date: 2026-04-12 00:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260412_0015"
down_revision = "20260412_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_deliveries",
        sa.Column(
            "data_object_version_id",
            sa.Text(),
            sa.ForeignKey("data_object_versions.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "data_deliveries",
        sa.Column("delivery_location", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_data_deliveries_data_object_version_id",
        "data_deliveries",
        ["data_object_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_data_deliveries_data_object_version_id", table_name="data_deliveries")
    op.drop_column("data_deliveries", "delivery_location")
    op.drop_column("data_deliveries", "data_object_version_id")