"""add validation artifact registry

Revision ID: 20260426_0026
Revises: 20260420_0025
Create Date: 2026-04-26 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260426_0026"
down_revision = "20260420_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_artifact_registry",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("validation_artifact_id", sa.Text(), nullable=False),
        sa.Column("validation_artifact_version", sa.Integer(), nullable=False),
        sa.Column("artifact_contract_version", sa.Text(), nullable=False, server_default="v1"),
        sa.Column("engine_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("data_object_id", sa.Text(), nullable=True),
        sa.Column("dataset_id", sa.Text(), nullable=True),
        sa.Column("data_product_id", sa.Text(), nullable=True),
        sa.Column(
            "resolved_data_object_version_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "compiled_rule_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("compiler_version", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "envelope_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("saved_by", sa.Text(), nullable=True),
        sa.Column("source_pipeline", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'deprecated', 'disabled')",
            name="ck_validation_artifact_registry_status",
        ),
        sa.CheckConstraint(
            "data_object_id IS NOT NULL OR dataset_id IS NOT NULL OR data_product_id IS NOT NULL",
            name="ck_validation_artifact_registry_assignment_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "validation_artifact_id",
            "validation_artifact_version",
            name="uq_validation_artifact_registry_artifact_version",
        ),
    )
    op.create_index(
        "ix_validation_artifact_registry_artifact_status",
        "validation_artifact_registry",
        ["validation_artifact_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_validation_artifact_registry_data_object_status",
        "validation_artifact_registry",
        ["data_object_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_validation_artifact_registry_dataset_status",
        "validation_artifact_registry",
        ["dataset_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_validation_artifact_registry_data_product_status",
        "validation_artifact_registry",
        ["data_product_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_validation_artifact_registry_engine_status",
        "validation_artifact_registry",
        ["engine_type", "status"],
        unique=False,
    )

    op.create_table(
        "validation_artifact_status_history",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("validation_artifact_id", sa.Text(), nullable=False),
        sa.Column("validation_artifact_version", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Text(), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["validation_artifact_id", "validation_artifact_version"],
            [
                "validation_artifact_registry.validation_artifact_id",
                "validation_artifact_registry.validation_artifact_version",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_artifact_status_history_artifact",
        "validation_artifact_status_history",
        ["validation_artifact_id", "validation_artifact_version"],
        unique=False,
    )
    op.create_index(
        "ix_validation_artifact_status_history_changed_at",
        "validation_artifact_status_history",
        ["changed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_validation_artifact_status_history_changed_at",
        table_name="validation_artifact_status_history",
    )
    op.drop_index(
        "ix_validation_artifact_status_history_artifact",
        table_name="validation_artifact_status_history",
    )
    op.drop_table("validation_artifact_status_history")

    op.drop_index(
        "ix_validation_artifact_registry_engine_status",
        table_name="validation_artifact_registry",
    )
    op.drop_index(
        "ix_validation_artifact_registry_data_product_status",
        table_name="validation_artifact_registry",
    )
    op.drop_index(
        "ix_validation_artifact_registry_dataset_status",
        table_name="validation_artifact_registry",
    )
    op.drop_index(
        "ix_validation_artifact_registry_data_object_status",
        table_name="validation_artifact_registry",
    )
    op.drop_index(
        "ix_validation_artifact_registry_artifact_status",
        table_name="validation_artifact_registry",
    )
    op.drop_table("validation_artifact_registry")