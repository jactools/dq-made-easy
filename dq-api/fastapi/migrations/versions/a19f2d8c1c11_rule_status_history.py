"""rule status history

Revision ID: a19f2d8c1c11
Revises: 724b9ef3247c
Create Date: 2026-04-06 10:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a19f2d8c1c11'
down_revision = '724b9ef3247c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'rule_status_history',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('rule_id', sa.Text(), nullable=False),
        sa.Column('from_status', sa.Text(), nullable=True),
        sa.Column('to_status', sa.Text(), nullable=False),
        sa.Column('changed_by', sa.Text(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['rule_id'], ['rules.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rule_status_history_rule_changed_at', 'rule_status_history', ['rule_id', 'changed_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_rule_status_history_rule_changed_at', table_name='rule_status_history')
    op.drop_table('rule_status_history')