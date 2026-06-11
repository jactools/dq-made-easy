"""Add workspace alert routing policy.

Revision ID: 20260527_0044
Revises: 20260527_0043_sla_slo_def
Create Date: 2026-05-27 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260527_0044"
down_revision = "20260527_0043_sla_slo_def"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("alert_routing_policy", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "alert_routing_policy")