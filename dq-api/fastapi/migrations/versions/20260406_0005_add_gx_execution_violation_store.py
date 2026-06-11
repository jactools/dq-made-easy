"""add gx execution violation store

Revision ID: 20260406_0005
Revises: 20260406_0004
Create Date: 2026-04-06 13:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20260406_0005'
down_revision = '20260406_0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gx_execution_violations',
        sa.Column('data_object_version_id', sa.Text(), nullable=False),
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('execution_run_id', sa.Text(), nullable=False),
        sa.Column('suite_id', sa.Text(), nullable=False),
        sa.Column('suite_version', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Text(), nullable=False),
        sa.Column('rule_version_id', sa.Text(), nullable=False),
        sa.Column('correlation_id', sa.Text(), nullable=False),
        sa.Column('failure_class', sa.Text(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=False),
        sa.Column('row_identifier', sa.Text(), nullable=True),
        sa.Column('details_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('data_object_version_id', 'id'),
        sa.ForeignKeyConstraint(['execution_run_id'], ['gx_execution_runs.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_gx_execution_violations_data_object_detected_at', 'gx_execution_violations', ['data_object_version_id', 'detected_at'], unique=False)
    op.create_index('ix_gx_execution_violations_run', 'gx_execution_violations', ['data_object_version_id', 'execution_run_id', 'detected_at'], unique=False)
    op.create_index('ix_gx_execution_violations_rule', 'gx_execution_violations', ['data_object_version_id', 'rule_id', 'detected_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_gx_execution_violations_rule', table_name='gx_execution_violations')
    op.drop_index('ix_gx_execution_violations_run', table_name='gx_execution_violations')
    op.drop_index('ix_gx_execution_violations_data_object_detected_at', table_name='gx_execution_violations')
    op.drop_table('gx_execution_violations')
