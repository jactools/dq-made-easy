"""add attribute definition mappings

Revision ID: 20260420_0025
Revises: 20260418_0024
Create Date: 2026-04-20 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260420_0025"
down_revision = "20260418_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attribute_definition_mappings",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("attribute_id", sa.Text(), nullable=False),
        sa.Column("definition_id", sa.Text(), nullable=True),
        sa.Column("mapping_state", sa.Text(), nullable=False, server_default="mapped"),
        sa.Column("mapped_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("mapping_state IN ('mapped', 'unmapped')", name="ck_attribute_definition_mappings_state"),
        sa.CheckConstraint(
            "(mapping_state = 'mapped' AND definition_id IS NOT NULL) OR (mapping_state = 'unmapped' AND definition_id IS NULL)",
            name="ck_attribute_definition_mappings_definition_consistency",
        ),
        sa.ForeignKeyConstraint(["attribute_id"], ["attributes_catalog.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attribute_id", name="uq_attribute_definition_mappings_attribute_id"),
    )
    op.create_index(
        "ix_attribute_definition_mappings_definition_id",
        "attribute_definition_mappings",
        ["definition_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attribute_definition_mappings_definition_id", table_name="attribute_definition_mappings")
    op.drop_table("attribute_definition_mappings")