"""add data_delivery_notes table

Revision ID: 20260412_0016
Revises: 20260412_0015
Create Date: 2026-04-12 00:16:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260412_0016"
down_revision = "20260412_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_delivery_notes",
        sa.Column(
            "data_delivery_id",
            sa.Text(),
            sa.ForeignKey("data_deliveries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("delivery_format", sa.Text(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=True),
        sa.Column("ingestor_name", sa.Text(), nullable=True),
        sa.Column("ingestor_run_id", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_snapshot_id", sa.Text(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("checksum_algorithm", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("data_delivery_notes")