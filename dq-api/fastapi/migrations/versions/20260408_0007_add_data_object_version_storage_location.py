"""add storage location fields to data_object_versions

Revision ID: 20260408_0007
Revises: 20260407_0006
Create Date: 2026-04-08 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260408_0007"
down_revision = "20260407_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_object_versions",
        sa.Column("storage_uri", sa.Text(), nullable=True),
    )
    op.add_column(
        "data_object_versions",
        sa.Column("storage_format", sa.Text(), nullable=True),
    )
    op.add_column(
        "data_object_versions",
        sa.Column("storage_options_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("data_object_versions", "storage_options_json")
    op.drop_column("data_object_versions", "storage_format")
    op.drop_column("data_object_versions", "storage_uri")
