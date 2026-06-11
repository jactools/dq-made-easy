"""add connector registry

Revision ID: 20260606_0060
Revises: 20260531_0059
Create Date: 2026-06-06 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260606_0060"
down_revision = "20260531_0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_registry",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("implementation_path", sa.Text(), nullable=True),
        sa.Column(
            "capabilities_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "supported_asset_kinds_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider"),
    )
    op.create_index(
        "ix_connector_registry_display_name",
        "connector_registry",
        ["display_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_connector_registry_display_name", table_name="connector_registry")
    op.drop_table("connector_registry")