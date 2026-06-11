"""add federated metadata registry external party approval state

Revision ID: 20260531_0058
Revises: 20260531_0057
Create Date: 2026-05-31 01:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260531_0058"
down_revision = "20260531_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "federated_metadata_registry_external_parties",
        sa.Column("approval_status", sa.Text(), nullable=False, server_default="pending"),
    )
    op.add_column(
        "federated_metadata_registry_external_parties",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "federated_metadata_registry_external_parties",
        sa.Column("approved_by", sa.Text(), nullable=True),
    )
    op.add_column(
        "federated_metadata_registry_external_parties",
        sa.Column("approval_notes", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_fed_meta_reg_ext_party_appr_reg_at",
        "federated_metadata_registry_external_parties",
        ["approval_status", "registered_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fed_meta_reg_ext_party_appr_reg_at",
        table_name="federated_metadata_registry_external_parties",
    )
    op.drop_column("federated_metadata_registry_external_parties", "approval_notes")
    op.drop_column("federated_metadata_registry_external_parties", "approved_by")
    op.drop_column("federated_metadata_registry_external_parties", "approved_at")
    op.drop_column("federated_metadata_registry_external_parties", "approval_status")
