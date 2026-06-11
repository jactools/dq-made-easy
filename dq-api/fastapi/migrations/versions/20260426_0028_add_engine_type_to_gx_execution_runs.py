"""add engine_type to gx execution runs

Revision ID: 20260426_0028
Revises: 20260426_0027
Create Date: 2026-04-26 16:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_0028"
down_revision = "20260426_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gx_execution_runs", sa.Column("engine_type", sa.Text(), nullable=True))

    connection = op.get_bind()
    existing_rows = connection.execute(sa.text("SELECT COUNT(*) FROM gx_execution_runs")).scalar_one()
    if existing_rows:
        raise RuntimeError(
            "gx_execution_runs contains legacy rows without engine_type; clear or migrate them explicitly before applying revision 20260426_0028"
        )

    op.alter_column("gx_execution_runs", "engine_type", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    op.drop_column("gx_execution_runs", "engine_type")