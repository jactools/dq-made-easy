"""add connector sync job and schedule tracking

Revision ID: 20260710_0063
Revises: 20260628_0062
Create Date: 2026-07-10 00:00:01.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260710_0063"
down_revision = "20260628_0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Connector sync jobs
    op.create_table(
        "connector_sync_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("connector_instance_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), server_default="full_sync", nullable=False),
        sa.Column("trigger", sa.Text(), server_default="manual", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
        sa.Column("synced_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("added_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("removed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "error_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "result_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_connector_sync_jobs_instance",
        "connector_sync_jobs",
        ["connector_instance_id"],
    )
    op.create_index(
        "ix_connector_sync_jobs_provider",
        "connector_sync_jobs",
        ["provider"],
    )
    op.create_index(
        "ix_connector_sync_jobs_status",
        "connector_sync_jobs",
        ["status"],
    )
    op.create_index(
        "ix_connector_sync_jobs_created_at",
        "connector_sync_jobs",
        ["created_at"],
    )
    op.create_index(
        "ix_connector_sync_jobs_workspace",
        "connector_sync_jobs",
        ["workspace_id"],
    )

    # Connector sync schedules
    op.create_table(
        "connector_sync_schedules",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("connector_instance_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("frequency", sa.Text(), server_default="day", nullable=False),
        sa.Column("cron_expression", sa.Text(), nullable=True),
        sa.Column("interval_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "next_run_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_run_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_job_id", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("timezone", sa.Text(), server_default="UTC", nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_connector_sync_schedules_instance",
        "connector_sync_schedules",
        ["connector_instance_id"],
    )
    op.create_index(
        "ix_connector_sync_schedules_provider",
        "connector_sync_schedules",
        ["provider"],
    )
    op.create_index(
        "ix_connector_sync_schedules_next_run",
        "connector_sync_schedules",
        ["next_run_at"],
    )
    op.create_index(
        "ix_connector_sync_schedules_active",
        "connector_sync_schedules",
        ["is_active"],
    )

    # Connector asset snapshots (for incremental sync)
    op.create_table(
        "connector_asset_snapshots",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("connector_instance_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("asset_identifier", sa.Text(), nullable=False),
        sa.Column("asset_kind", sa.Text(), nullable=False),
        sa.Column(
            "asset_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connector_instance_id",
            "asset_identifier",
            name="uq_connector_asset_snapshot_lookup",
        ),
    )
    op.create_index(
        "ix_connector_asset_snapshots_instance",
        "connector_asset_snapshots",
        ["connector_instance_id"],
    )
    op.create_index(
        "ix_connector_asset_snapshots_provider",
        "connector_asset_snapshots",
        ["provider"],
    )
    op.create_index(
        "ix_connector_asset_snapshots_lookup",
        "connector_asset_snapshots",
        ["connector_instance_id", "asset_identifier"],
    )


def downgrade() -> None:
    op.drop_index("ix_connector_asset_snapshots_lookup", "connector_asset_snapshots")
    op.drop_index("ix_connector_asset_snapshots_provider", "connector_asset_snapshots")
    op.drop_index("ix_connector_asset_snapshots_instance", "connector_asset_snapshots")
    op.drop_table("connector_asset_snapshots")

    op.drop_index("ix_connector_sync_schedules_active", "connector_sync_schedules")
    op.drop_index("ix_connector_sync_schedules_next_run", "connector_sync_schedules")
    op.drop_index("ix_connector_sync_schedules_provider", "connector_sync_schedules")
    op.drop_index("ix_connector_sync_schedules_instance", "connector_sync_schedules")
    op.drop_table("connector_sync_schedules")

    op.drop_index("ix_connector_sync_jobs_workspace", "connector_sync_jobs")
    op.drop_index("ix_connector_sync_jobs_created_at", "connector_sync_jobs")
    op.drop_index("ix_connector_sync_jobs_status", "connector_sync_jobs")
    op.drop_index("ix_connector_sync_jobs_provider", "connector_sync_jobs")
    op.drop_index("ix_connector_sync_jobs_instance", "connector_sync_jobs")
    op.drop_table("connector_sync_jobs")
