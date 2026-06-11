"""add data asset business context

Revision ID: 20260525_0038
Revises: 20260524_0037
Create Date: 2026-05-25 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_0038"
down_revision = "20260524_0037"
branch_labels = None
depends_on = None


def _create_data_assets_table() -> None:
    op.create_table(
        "data_assets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("current_version_id", sa.Text(), nullable=True),
        sa.Column("source_object_version_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("business_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", name="uq_data_assets_id"),
    )
    op.create_index("ix_data_assets_workspace_name", "data_assets", ["workspace_id", "name"], unique=False)


def _create_data_asset_versions_table() -> None:
    op.create_table(
        "data_asset_versions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("data_asset_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("source_bindings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("derived_fields_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("upload_preview_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_asset_id", "version", name="uq_data_asset_versions_asset_version"),
    )
    op.create_index(
        "ix_data_asset_versions_data_asset_id_version",
        "data_asset_versions",
        ["data_asset_id", "version"],
        unique=False,
    )


def _create_data_asset_contract_versions_table() -> None:
    op.create_table(
        "data_asset_contract_versions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("data_asset_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contract_yaml", sa.Text(), nullable=False),
        sa.Column("contract_hash", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by", sa.Text(), nullable=True),
        sa.Column("generated_where", sa.Text(), nullable=True),
        sa.Column("generated_what", sa.Text(), nullable=True),
        sa.Column("source_data_asset_version_id", sa.Text(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comments", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_asset_id", "version", name="uq_data_asset_contract_versions_asset_version"),
    )
    op.create_index(
        "ix_data_asset_contract_versions_data_asset_id_version",
        "data_asset_contract_versions",
        ["data_asset_id", "version"],
        unique=False,
    )
    op.create_index(
        "ix_data_asset_contract_versions_contract_hash",
        "data_asset_contract_versions",
        ["contract_hash"],
        unique=False,
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "data_assets" not in existing_tables:
        _create_data_assets_table()
        existing_tables.add("data_assets")
    else:
        existing_columns = {column["name"] for column in inspector.get_columns("data_assets")}
        if "business_context_json" not in existing_columns:
            op.add_column(
                "data_assets",
                sa.Column("business_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )

    if "data_asset_versions" not in existing_tables:
        _create_data_asset_versions_table()

    if "data_asset_contract_versions" not in existing_tables:
        _create_data_asset_contract_versions_table()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "data_asset_contract_versions" in existing_tables:
        op.drop_index(
            "ix_data_asset_contract_versions_contract_hash",
            table_name="data_asset_contract_versions",
        )
        op.drop_index(
            "ix_data_asset_contract_versions_data_asset_id_version",
            table_name="data_asset_contract_versions",
        )
        op.drop_table("data_asset_contract_versions")

    if "data_asset_versions" in existing_tables:
        op.drop_index(
            "ix_data_asset_versions_data_asset_id_version",
            table_name="data_asset_versions",
        )
        op.drop_table("data_asset_versions")

    if "data_assets" in existing_tables:
        op.drop_index("ix_data_assets_workspace_name", table_name="data_assets")
        op.drop_table("data_assets")