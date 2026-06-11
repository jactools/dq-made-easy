"""rule audit history

Revision ID: 20260530_0054_rule_audit_history
Revises: 20260530_0053_rule_ownership
Create Date: 2026-05-30 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260530_0054_rule_audit_history"
down_revision = "20260530_0053_rule_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rule_status_history", sa.Column("action", sa.Text(), nullable=True))
    op.add_column("rule_status_history", sa.Column("details", sa.Text(), nullable=True))
    op.execute("UPDATE rule_status_history SET action = 'transition' WHERE action IS NULL OR action = ''")
    op.alter_column("rule_status_history", "action", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    op.drop_column("rule_status_history", "details")
    op.drop_column("rule_status_history", "action")
