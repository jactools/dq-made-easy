"""add storage location to data_delivery_notes

Revision ID: 20260417_0023
Revises: 20260417_0022
Create Date: 2026-04-17 13:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260417_0023"
down_revision = "20260417_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_delivery_notes", sa.Column("storage_location", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("data_delivery_notes", "storage_location")