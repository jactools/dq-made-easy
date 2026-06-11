"""add business key flag to attributes_catalog

Revision ID: 20260417_0017
Revises: 20260412_0016
Create Date: 2026-04-17 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260417_0017"
down_revision = "20260412_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attributes_catalog",
        sa.Column("is_business_key", sa.Boolean(), server_default="false", nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attributes_catalog", "is_business_key")