"""add federated metadata registry access grants

Revision ID: 20260531_0059
Revises: 20260531_0058
Create Date: 2026-05-31 01:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260531_0059"
down_revision = "20260531_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "federated_metadata_registry_access_grants",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("external_party_id", sa.Text(), sa.ForeignKey("federated_metadata_registry_external_parties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("subscribed", sa.Boolean(), nullable=False),
        sa.Column("can_push", sa.Boolean(), nullable=False),
        sa.Column("can_pull", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granted_by", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.UniqueConstraint("external_party_id", "target_kind", "target_id", name="uq_fed_meta_reg_access_grants_party_target"),
    )
    op.create_index(
        "ix_fed_meta_reg_access_grants_party_at",
        "federated_metadata_registry_access_grants",
        ["external_party_id", "granted_at"],
    )
    op.create_index(
        "ix_fed_meta_reg_access_grants_target_at",
        "federated_metadata_registry_access_grants",
        ["target_kind", "target_id", "granted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fed_meta_reg_access_grants_target_at",
        table_name="federated_metadata_registry_access_grants",
    )
    op.drop_index(
        "ix_fed_meta_reg_access_grants_party_at",
        table_name="federated_metadata_registry_access_grants",
    )
    op.drop_table("federated_metadata_registry_access_grants")