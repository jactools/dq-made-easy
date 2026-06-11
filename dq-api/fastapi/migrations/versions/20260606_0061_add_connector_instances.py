"""add connector instances

Revision ID: 20260606_0061
Revises: 20260606_0060
Create Date: 2026-06-06 00:00:01.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260606_0061"
down_revision = "20260606_0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_instances",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Text(), nullable=True),
        sa.Column(
            "configuration_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_connector_instances_provider",
        "connector_instances",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_connector_instances_display_name",
        "connector_instances",
        ["display_name"],
        unique=False,
    )
    op.create_index(
        "ix_connector_instances_workspace_scope",
        "connector_instances",
        ["workspace_id", "tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_connector_instances_workspace_scope", table_name="connector_instances")
    op.drop_index("ix_connector_instances_display_name", table_name="connector_instances")
    op.drop_index("ix_connector_instances_provider", table_name="connector_instances")
    op.drop_table("connector_instances")