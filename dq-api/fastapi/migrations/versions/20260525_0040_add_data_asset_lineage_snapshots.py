"""add data asset lineage snapshots

Revision ID: 20260525_0040
Revises: 20260525_0039
Create Date: 2026-05-25 13:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_0040"
down_revision = "20260525_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_asset_lineage_snapshots",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("data_asset_id", sa.Text(), nullable=False),
        sa.Column("snapshot_kind", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("captured_by", sa.Text(), nullable=True),
        sa.Column("lineage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("business_context_overlay_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("classification_view_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("anomaly_annotations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_asset_lineage_snapshots_data_asset_id_captured_at",
        "data_asset_lineage_snapshots",
        ["data_asset_id", "captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_asset_lineage_snapshots_data_asset_id_captured_at",
        table_name="data_asset_lineage_snapshots",
    )
    op.drop_table("data_asset_lineage_snapshots")