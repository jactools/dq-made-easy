"""add analysis manifest storage to gx exception analysis slices

Revision ID: 20260527_0047
Revises: 20260527_0046
Create Date: 2026-05-27 01:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_0047"
down_revision = "20260527_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gx_exception_analysis_slices", sa.Column("analysis_manifest_uri", sa.Text(), nullable=False, server_default=sa.text("''")))
    op.add_column("gx_exception_analysis_slices", sa.Column("analysis_manifest_sha256", sa.Text(), nullable=False, server_default=sa.text("''")))
    op.alter_column("gx_exception_analysis_slices", "analysis_manifest_uri", server_default=None)
    op.alter_column("gx_exception_analysis_slices", "analysis_manifest_sha256", server_default=None)


def downgrade() -> None:
    op.drop_column("gx_exception_analysis_slices", "analysis_manifest_sha256")
    op.drop_column("gx_exception_analysis_slices", "analysis_manifest_uri")