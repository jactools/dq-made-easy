"""add business key columns to data objects

Revision ID: 20260417_0018
Revises: 20260417_0017
Create Date: 2026-04-17 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260417_0018"
down_revision = "20260417_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_objects", sa.Column("business_key", sa.Text(), nullable=True))
    op.add_column("data_objects_catalog", sa.Column("business_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("data_objects_catalog", "business_key")
    op.drop_column("data_objects", "business_key")