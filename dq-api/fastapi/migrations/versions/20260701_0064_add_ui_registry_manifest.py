"""add ui registry manifest

Revision ID: 20260701_0064
Revises: 20260701_0063
Create Date: 2026-07-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260701_0064"
down_revision = "20260701_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ui_registry_manifest",
        sa.Column("manifest_key", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("manifest_version", sa.Text(), nullable=False),
        sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("persisted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("manifest_key"),
    )


def downgrade() -> None:
    op.drop_table("ui_registry_manifest")