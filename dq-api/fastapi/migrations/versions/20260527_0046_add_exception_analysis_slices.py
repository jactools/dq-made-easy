"""add gx exception analysis slices

Revision ID: 20260527_0046
Revises: 20260527_0045
Create Date: 2026-05-27 00:46:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260527_0046"
down_revision = "20260527_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gx_exception_analysis_slices",
        sa.Column("analysis_session_id", sa.Text(), nullable=False),
        sa.Column("analysis_slice_id", sa.Text(), nullable=False),
        sa.Column("slice_index", sa.Integer(), nullable=False),
        sa.Column("data_object_version_id", sa.Text(), nullable=False),
        sa.Column("execution_run_id", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("slice_limit", sa.Integer(), nullable=False),
        sa.Column("anchor_total_count", sa.Integer(), nullable=False),
        sa.Column("total_matching_count", sa.Integer(), nullable=False),
        sa.Column("returned_count", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("next_slice_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("analysis_pack_uri", sa.Text(), nullable=False),
        sa.Column("analysis_pack_sha256", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("analysis_session_id", "analysis_slice_id"),
    )
    op.create_index(
        "ix_gx_exception_analysis_slices_session",
        "gx_exception_analysis_slices",
        ["analysis_session_id", "slice_index"],
        unique=False,
    )
    op.create_index(
        "ix_gx_exception_analysis_slices_anchor",
        "gx_exception_analysis_slices",
        ["data_object_version_id", "execution_run_id", "rule_id", "slice_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_gx_exception_analysis_slices_anchor", table_name="gx_exception_analysis_slices")
    op.drop_index("ix_gx_exception_analysis_slices_session", table_name="gx_exception_analysis_slices")
    op.drop_table("gx_exception_analysis_slices")
