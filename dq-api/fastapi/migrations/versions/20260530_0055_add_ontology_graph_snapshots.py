"""add ontology graph snapshots

Revision ID: 20260530_0055
Revises: 20260530_0054_rule_audit_history
Create Date: 2026-05-30 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260530_0055"
down_revision = "20260530_0054_rule_audit_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ontology_graph_snapshots",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("graph_id", sa.Text(), nullable=False),
        sa.Column("graph_name", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("data_product_id", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_by", sa.Text(), nullable=True),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("graph_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ontology_graph_snapshots_graph_id_captured_at",
        "ontology_graph_snapshots",
        ["graph_id", "captured_at"],
        unique=False,
    )
    op.create_index(
        "ix_ontology_graph_snapshots_workspace_id_captured_at",
        "ontology_graph_snapshots",
        ["workspace_id", "captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ontology_graph_snapshots_workspace_id_captured_at", table_name="ontology_graph_snapshots")
    op.drop_index("ix_ontology_graph_snapshots_graph_id_captured_at", table_name="ontology_graph_snapshots")
    op.drop_table("ontology_graph_snapshots")