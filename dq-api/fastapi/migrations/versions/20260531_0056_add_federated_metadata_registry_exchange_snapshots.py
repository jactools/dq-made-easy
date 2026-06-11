"""add federated metadata registry exchange snapshots

Revision ID: 20260531_0056
Revises: 20260530_0055
Create Date: 2026-05-31 02:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260531_0056"
down_revision = "20260530_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "federated_metadata_registry_exchange_snapshots",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("package_id", sa.Text(), nullable=False),
        sa.Column("package_kind", sa.Text(), nullable=False),
        sa.Column("exchange_kind", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("data_product_id", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_by", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("package_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fed_meta_reg_ex_snap_ws_captured_at",
        "federated_metadata_registry_exchange_snapshots",
        ["workspace_id", "captured_at"],
        unique=False,
    )
    op.create_index(
        "ix_fed_meta_reg_ex_snap_pkg_captured_at",
        "federated_metadata_registry_exchange_snapshots",
        ["package_id", "captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fed_meta_reg_ex_snap_pkg_captured_at",
        table_name="federated_metadata_registry_exchange_snapshots",
    )
    op.drop_index(
        "ix_fed_meta_reg_ex_snap_ws_captured_at",
        table_name="federated_metadata_registry_exchange_snapshots",
    )
    op.drop_table("federated_metadata_registry_exchange_snapshots")