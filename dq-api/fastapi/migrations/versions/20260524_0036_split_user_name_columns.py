"""split user name columns

Revision ID: 20260524_0036
Revises: 20260524_0035
Create Date: 2026-05-24 12:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_0036"
down_revision = "20260524_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE users
        SET
            first_name = COALESCE(
                NULLIF(BTRIM(SPLIT_PART(BTRIM(COALESCE(name, '')), ' ', 1)), ''),
                NULLIF(BTRIM(SPLIT_PART(COALESCE(email, id, 'User'), '@', 1)), ''),
                'User'
            ),
            last_name = COALESCE(
                NULLIF(
                    BTRIM(
                        CASE
                            WHEN POSITION(' ' IN BTRIM(COALESCE(name, ''))) > 0
                            THEN SUBSTRING(BTRIM(COALESCE(name, '')) FROM POSITION(' ' IN BTRIM(COALESCE(name, ''))) + 1)
                            ELSE SPLIT_PART(BTRIM(COALESCE(name, '')), ' ', 1)
                        END
                    ),
                    ''
                ),
                NULLIF(BTRIM(SPLIT_PART(COALESCE(email, id, 'User'), '@', 1)), ''),
                'User'
            )
        """
    )

    op.alter_column("users", "first_name", existing_type=sa.Text(), nullable=False)
    op.alter_column("users", "last_name", existing_type=sa.Text(), nullable=False)
    op.drop_column("users", "name")


def downgrade() -> None:
    op.add_column("users", sa.Column("name", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE users
        SET name = CASE
            WHEN BTRIM(COALESCE(last_name, '')) = '' THEN BTRIM(COALESCE(first_name, ''))
            WHEN BTRIM(COALESCE(first_name, '')) = BTRIM(COALESCE(last_name, '')) THEN BTRIM(COALESCE(first_name, ''))
            ELSE BTRIM(COALESCE(first_name, '')) || ' ' || BTRIM(COALESCE(last_name, ''))
        END
        """
    )
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")