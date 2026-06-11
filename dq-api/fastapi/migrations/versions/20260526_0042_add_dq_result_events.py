"""add dq result events

Revision ID: 20260526_0042
Revises: 20260525_0041
Create Date: 2026-05-26 22:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260526_0042"
down_revision = "20260525_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dq_result_events",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_version", sa.Text(), nullable=False),
        sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("dataset_name", sa.Text(), nullable=True),
        sa.Column("dataset_workspace_id", sa.Text(), nullable=True),
        sa.Column("dataset_data_product_id", sa.Text(), nullable=True),
        sa.Column("dataset_data_object_id", sa.Text(), nullable=True),
        sa.Column("dataset_data_object_version_id", sa.Text(), nullable=True),
        sa.Column("domain_id", sa.Text(), nullable=True),
        sa.Column("domain_name", sa.Text(), nullable=True),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("rule_name", sa.Text(), nullable=True),
        sa.Column("rule_version_id", sa.Text(), nullable=True),
        sa.Column("rule_version_number", sa.Integer(), nullable=True),
        sa.Column("run_status", sa.Text(), nullable=False),
        sa.Column("run_result", sa.Text(), nullable=True),
        sa.Column("run_passed", sa.Boolean(), nullable=True),
        sa.Column("run_total_count", sa.Integer(), nullable=True),
        sa.Column("run_valid_count", sa.Integer(), nullable=True),
        sa.Column("run_invalid_count", sa.Integer(), nullable=True),
        sa.Column("run_warning_count", sa.Integer(), nullable=True),
        sa.Column("run_error_count", sa.Integer(), nullable=True),
        sa.Column("run_score", sa.Numeric(), nullable=True),
        sa.Column("run_score_label", sa.Text(), nullable=True),
        sa.Column("run_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_duration_ms", sa.Integer(), nullable=True),
        sa.Column("run_message", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("queue_message_id", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("parent_correlation_id", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("score_dimensions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("event_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correlation_id", "run_id", "run_status", name="uq_dq_result_events_run_status"),
    )
    op.create_index("ix_dq_result_events_emitted_at", "dq_result_events", ["emitted_at"], unique=False)
    op.create_index("ix_dq_result_events_rule_emitted_at", "dq_result_events", ["rule_id", "emitted_at"], unique=False)
    op.create_index("ix_dq_result_events_dataset_emitted_at", "dq_result_events", ["dataset_id", "emitted_at"], unique=False)
    op.create_index("ix_dq_result_events_domain_emitted_at", "dq_result_events", ["domain_id", "emitted_at"], unique=False)
    op.create_index(
        "ix_dq_result_events_data_product_emitted_at",
        "dq_result_events",
        ["dataset_data_product_id", "emitted_at"],
        unique=False,
    )
    op.create_index("ix_dq_result_events_correlation_id", "dq_result_events", ["correlation_id"], unique=False)
    op.create_index("ix_dq_result_events_run_status", "dq_result_events", ["run_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_dq_result_events_run_status", table_name="dq_result_events")
    op.drop_index("ix_dq_result_events_correlation_id", table_name="dq_result_events")
    op.drop_index("ix_dq_result_events_data_product_emitted_at", table_name="dq_result_events")
    op.drop_index("ix_dq_result_events_domain_emitted_at", table_name="dq_result_events")
    op.drop_index("ix_dq_result_events_dataset_emitted_at", table_name="dq_result_events")
    op.drop_index("ix_dq_result_events_rule_emitted_at", table_name="dq_result_events")
    op.drop_index("ix_dq_result_events_emitted_at", table_name="dq_result_events")
    op.drop_table("dq_result_events")
