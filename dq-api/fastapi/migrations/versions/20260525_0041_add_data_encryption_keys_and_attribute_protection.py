"""add data encryption keys and attribute protection fields

Revision ID: 20260525_0041
Revises: 20260525_0040
Create Date: 2026-05-25 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_0041"
down_revision = "20260525_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_encryption_keys",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("key_name", sa.Text(), nullable=False),
        sa.Column("key_scope", sa.Text(), nullable=False, server_default="app"),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("key_algorithm", sa.Text(), nullable=False, server_default="fernet"),
        sa.Column("key_material_encrypted", sa.Text(), nullable=False),
        sa.Column("key_fingerprint", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "attributes_catalog",
        sa.Column("masking_method", sa.Text(), nullable=True, server_default="none"),
    )
    op.add_column(
        "attributes_catalog",
        sa.Column("encryption_required", sa.Boolean(), nullable=True, server_default="false"),
    )
    op.add_column(
        "attributes_catalog",
        sa.Column(
            "encryption_key_id",
            sa.Text(),
            sa.ForeignKey("data_encryption_keys.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("attributes_catalog", "encryption_key_id")
    op.drop_column("attributes_catalog", "encryption_required")
    op.drop_column("attributes_catalog", "masking_method")
    op.drop_table("data_encryption_keys")
