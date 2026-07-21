"""create EMR schema for Canonical Delivery Registry

Creates a dedicated `emr` schema in the existing dq-db PostgreSQL instance
to serve as the Canonical Delivery Registry per the Solution Design:
Canonical Data Delivery Phase 1.

This avoids spinning up a separate EMR container while providing clear
separation of concerns through schema boundaries.

Tables created:
  emr.deliveries            — Core delivery record (DeliveryId, DeliveryTimeEvent)
  emr.delivery_lifecycle_events — Timeline events for delivery lifecycle tracking
  emr.delivery_errors        — Error records for failed deliveries
  emr.delivery_metadata      — Extended metadata (DDN reference, producer info)

Revision ID: 20260721_0002
Revises: 20260721_0001
Create Date: 2026-07-21

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260721_0002"
down_revision = "20260721_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the EMR schema (idempotent)
    op.execute("CREATE SCHEMA IF NOT EXISTS emr")

    # ------------------------------------------------------------------
    # emr.deliveries
    # ------------------------------------------------------------------
    op.create_table(
        "deliveries",
        sa.Column("delivery_id", sa.Text(), nullable=False, primary_key=True,
                   comment="Deterministic business key: {producerSystem}:{dataObjectLogicalName}:{version}:{jobId}"),
        sa.Column("delivery_time_event", sa.Text(), nullable=False, unique=True,
                   comment="UUIDv7 — unique occurrence identifier"),
        sa.Column("delivery_version", sa.Integer(), nullable=True, default=1,
                   comment="Monotonically increasing business version"),
        sa.Column("delivery_type", sa.Text(), nullable=True, default="initial",
                   comment="Delivery type: initial, retry, correction, backfill, deletion, retention"),
        sa.Column("producer_system", sa.Text(), nullable=False,
                   comment="Producer system code (e.g., sap, crm, emr)"),
        sa.Column("data_object_logical_name", sa.Text(), nullable=False,
                   comment="Data Object logical name (e.g., orders, payments)"),
        sa.Column("data_object_version", sa.Integer(), nullable=True,
                   comment="Data Object version"),
        sa.Column("job_id", sa.Text(), nullable=False,
                   comment="Pipeline job ID used to deliver the data"),
        sa.Column("layer", sa.Text(), nullable=True,
                   comment="Brown, gold, silver layer"),
        sa.Column("delivery_location", sa.Text(), nullable=True,
                   comment="Consumer-facing delivery location"),
        sa.Column("storage_location", sa.Text(), nullable=True,
                   comment="Internal storage location"),
        sa.Column("record_count", sa.Integer(), nullable=True, default=0),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True, default=0),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("checksum_algorithm", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True), nullable=False,
                   comment="Canonical delivery timestamp"),
        sa.Column("delivered_by", sa.Text(), nullable=True,
                   comment="Pipeline or agent identifier"),
        sa.Column("status", sa.Text(), nullable=True, default="registered",
                   comment="Lifecycle status: registered, ingested, validated, archived, superseded"),
        sa.Column("predecessor_time_event", sa.Text(), nullable=True,
                   comment="UUIDv7 of the delivery being corrected"),
        sa.Column("superseded_by_time_event", sa.Text(), nullable=True,
                   comment="UUIDv7 of the delivery that supersedes this one"),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                   server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                   server_default=sa.text("CURRENT_TIMESTAMP")),
        schema="emr",
    )
    op.create_index("ix_emr_deliveries_delivery_time_event", "deliveries",
                     ["delivery_time_event"], schema="emr")
    op.create_index("ix_emr_deliveries_producer_system", "deliveries",
                     ["producer_system"], schema="emr")
    op.create_index("ix_emr_deliveries_data_object_logical_name", "deliveries",
                     ["data_object_logical_name"], schema="emr")
    op.create_index("ix_emr_deliveries_delivered_at", "deliveries",
                     ["delivered_at"], schema="emr")
    op.create_index("ix_emr_deliveries_status", "deliveries",
                     ["status"], schema="emr")
    op.create_index("ix_emr_deliveries_predecessor_time_event", "deliveries",
                     ["predecessor_time_event"], schema="emr")
    op.create_index("ix_emr_deliveries_superseded_by_time_event", "deliveries",
                     ["superseded_by_time_event"], schema="emr")

    # ------------------------------------------------------------------
    # emr.delivery_lifecycle_events
    # ------------------------------------------------------------------
    op.create_table(
        "delivery_lifecycle_events",
        sa.Column("id", sa.Text(), nullable=False, primary_key=True),
        sa.Column("delivery_time_event", sa.Text(), nullable=False,
                   comment="UUIDv7 of the delivery this event belongs to"),
        sa.Column("event_type", sa.Text(), nullable=False,
                   comment="Lifecycle event type: registered, ingested, validated, archived, superseded, error"),
        sa.Column("event_kind", sa.Text(), nullable=False, default="instantaneous",
                   comment="Event kind: instantaneous, elapsed"),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=True,
                   comment="Instantaneous event timestamp"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True,
                   comment="Elapsed event start timestamp"),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True,
                   comment="Elapsed event end timestamp"),
        sa.Column("triggered_by", sa.Text(), nullable=True,
                   comment="Service or agent that triggered this event (e.g., DTC, DQ, Guard, EMR)"),
        sa.Column("correlation_id", sa.Text(), nullable=True,
                   comment="Correlation ID linking related events"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                   server_default=sa.text("CURRENT_TIMESTAMP")),
        schema="emr",
    )
    op.create_index("ix_emr_delivery_lifecycle_events_delivery_time_event",
                     "delivery_lifecycle_events", ["delivery_time_event"], schema="emr")
    op.create_index("ix_emr_delivery_lifecycle_events_event_type",
                     "delivery_lifecycle_events", ["event_type"], schema="emr")
    op.create_index("ix_emr_delivery_lifecycle_events_occurred_at",
                     "delivery_lifecycle_events", ["occurred_at"], schema="emr")

    # ------------------------------------------------------------------
    # emr.delivery_errors
    # ------------------------------------------------------------------
    op.create_table(
        "delivery_errors",
        sa.Column("id", sa.Text(), nullable=False, primary_key=True),
        sa.Column("delivery_time_event", sa.Text(), nullable=False,
                   comment="UUIDv7 of the delivery that encountered the error"),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=True, default="warning",
                   comment="Error severity: warning, error, critical"),
        sa.Column("reported_by", sa.Text(), nullable=True,
                   comment="Service or agent that reported this error"),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False,
                   comment="When the error was reported"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                   server_default=sa.text("CURRENT_TIMESTAMP")),
        schema="emr",
    )
    op.create_index("ix_emr_delivery_errors_delivery_time_event",
                     "delivery_errors", ["delivery_time_event"], schema="emr")
    op.create_index("ix_emr_delivery_errors_severity",
                     "delivery_errors", ["severity"], schema="emr")

    # ------------------------------------------------------------------
    # emr.delivery_metadata
    # ------------------------------------------------------------------
    op.create_table(
        "delivery_metadata",
        sa.Column("delivery_time_event", sa.Text(), nullable=False, primary_key=True,
                   comment="UUIDv7 of the delivery"),
        sa.Column("data_product_id", sa.Text(), nullable=True,
                   comment="ODCS Data Product identifier"),
        sa.Column("data_set_id", sa.Text(), nullable=True,
                   comment="Data Set identifier"),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_snapshot_id", sa.Text(), nullable=True),
        sa.Column("object_storage_classification", sa.Text(), nullable=True,
                   comment="Synthetic vs real data classification"),
        sa.Column("evidence_classification", sa.Text(), nullable=True,
                   comment="Test vs evidence classification"),
        sa.Column("delivery_format", sa.Text(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=True),
        sa.Column("file_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ingestor_name", sa.Text(), nullable=True),
        sa.Column("ingestor_run_id", sa.Text(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("checksum_algorithm", sa.Text(), nullable=True),
        sa.Column("ddn_reference", sa.Text(), nullable=True,
                   comment="Reference to the Data Delivery Note ID"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                   server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                   server_default=sa.text("CURRENT_TIMESTAMP")),
        schema="emr",
    )
    op.create_index("ix_emr_delivery_metadata_data_product_id",
                     "delivery_metadata", ["data_product_id"], schema="emr")
    op.create_index("ix_emr_delivery_metadata_workspace_id",
                     "delivery_metadata", ["workspace_id"], schema="emr")


def downgrade() -> None:
    op.drop_table("delivery_metadata", schema="emr")
    op.drop_table("delivery_errors", schema="emr")
    op.drop_table("delivery_lifecycle_events", schema="emr")
    op.drop_table("deliveries", schema="emr")
    op.execute("DROP SCHEMA IF EXISTS emr CASCADE")
