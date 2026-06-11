"""add gx execution run lifecycle

Revision ID: 20260406_0004
Revises: a19f2d8c1c11
Create Date: 2026-04-06 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20260406_0004'
down_revision = 'a19f2d8c1c11'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gx_execution_runs',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('suite_id', sa.Text(), nullable=False),
        sa.Column('suite_version', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Text(), nullable=False),
        sa.Column('rule_version_id', sa.Text(), nullable=False),
        sa.Column('correlation_id', sa.Text(), nullable=False),
        sa.Column('requested_by', sa.Text(), nullable=True),
        sa.Column('engine_target', sa.Text(), nullable=False),
        sa.Column('execution_shape', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('execution_contract_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('handoff_payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('result_summary_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('diagnostics_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('failure_code', sa.Text(), nullable=True),
        sa.Column('failure_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('correlation_id', 'suite_id', 'suite_version', name='uq_gx_execution_runs_correlation_suite'),
    )
    op.create_index('ix_gx_execution_runs_correlation_id', 'gx_execution_runs', ['correlation_id'], unique=False)
    op.create_index('ix_gx_execution_runs_status', 'gx_execution_runs', ['status'], unique=False)
    op.create_index('ix_gx_execution_runs_suite', 'gx_execution_runs', ['suite_id', 'suite_version'], unique=False)
    op.create_index('ix_gx_execution_runs_submitted_at', 'gx_execution_runs', ['submitted_at'], unique=False)

    op.create_table(
        'gx_execution_run_status_history',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('run_id', sa.Text(), nullable=False),
        sa.Column('from_status', sa.Text(), nullable=True),
        sa.Column('to_status', sa.Text(), nullable=False),
        sa.Column('changed_by', sa.Text(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['gx_execution_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_gx_execution_run_status_history_changed_at', 'gx_execution_run_status_history', ['changed_at'], unique=False)
    op.create_index('ix_gx_execution_run_status_history_run', 'gx_execution_run_status_history', ['run_id', 'changed_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_gx_execution_run_status_history_run', table_name='gx_execution_run_status_history')
    op.drop_index('ix_gx_execution_run_status_history_changed_at', table_name='gx_execution_run_status_history')
    op.drop_table('gx_execution_run_status_history')
    op.drop_index('ix_gx_execution_runs_submitted_at', table_name='gx_execution_runs')
    op.drop_index('ix_gx_execution_runs_suite', table_name='gx_execution_runs')
    op.drop_index('ix_gx_execution_runs_status', table_name='gx_execution_runs')
    op.drop_index('ix_gx_execution_runs_correlation_id', table_name='gx_execution_runs')
    op.drop_table('gx_execution_runs')
