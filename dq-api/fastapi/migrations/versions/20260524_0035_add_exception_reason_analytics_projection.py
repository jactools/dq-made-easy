"""add exception reason analytics projection

Revision ID: 20260524_0035
Revises: 20260523_0034
Create Date: 2026-05-24 11:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260524_0035"
down_revision = "20260523_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exception_reason_analytics_projection",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_type", sa.Text(), nullable=False),
        sa.Column("delivery_id", sa.Text(), nullable=True),
        sa.Column("execution_plan_id", sa.Text(), nullable=True),
        sa.Column("execution_plan_version_id", sa.Text(), nullable=True),
        sa.Column("suite_id", sa.Text(), nullable=True),
        sa.Column("data_object_version_id", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("rule_version_id", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("reason_text_snapshot", sa.Text(), nullable=False),
        sa.Column("failed_record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("distinct_record_identifier_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("distinct_execution_run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("record_identifier_values_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("execution_run_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_exception_reason_analytics_projection_bucket",
        "exception_reason_analytics_projection",
        ["bucket_start"],
        unique=False,
    )
    op.create_index(
        "ix_exception_reason_analytics_projection_scope",
        "exception_reason_analytics_projection",
        ["data_object_version_id", "bucket_start"],
        unique=False,
    )
    op.create_index(
        "ix_exception_reason_analytics_projection_reason",
        "exception_reason_analytics_projection",
        ["reason_code", "bucket_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_exception_reason_analytics_projection_reason",
        table_name="exception_reason_analytics_projection",
    )
    op.drop_index(
        "ix_exception_reason_analytics_projection_scope",
        table_name="exception_reason_analytics_projection",
    )
    op.drop_index(
        "ix_exception_reason_analytics_projection_bucket",
        table_name="exception_reason_analytics_projection",
    )
    op.drop_table("exception_reason_analytics_projection")