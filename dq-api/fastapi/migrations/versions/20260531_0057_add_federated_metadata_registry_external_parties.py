"""add federated metadata registry external parties

Revision ID: 20260531_0057
Revises: 20260531_0056
Create Date: 2026-05-31 00:57:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "20260531_0057"
down_revision = "20260531_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "federated_metadata_registry_external_parties",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("governing_scope_json", JSONB(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_by", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_fed_meta_reg_ext_party_ws_reg_at",
        "federated_metadata_registry_external_parties",
        ["workspace_id", "registered_at"],
    )
    op.create_index(
        "ix_fed_meta_reg_ext_party_tenant_reg_at",
        "federated_metadata_registry_external_parties",
        ["tenant_id", "registered_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fed_meta_reg_ext_party_tenant_reg_at",
        table_name="federated_metadata_registry_external_parties",
    )
    op.drop_index(
        "ix_fed_meta_reg_ext_party_ws_reg_at",
        table_name="federated_metadata_registry_external_parties",
    )
    op.drop_table("federated_metadata_registry_external_parties")