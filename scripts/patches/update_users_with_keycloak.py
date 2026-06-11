"""update external_id for users based on CSV mapping

Revision ID: 20260401_0008_update_external_ids_from_csv
Revises: 20260329_0007_add_sessions_table
Create Date: 2026-04-01 12:00:00
"""

from alembic import op
import sqlalchemy as sa
import csv
import os

revision = "20260401_0008_update_external_ids_from_csv"
down_revision = "20260329_0007_add_sessions_table"
branch_labels = None
depends_on = None

def upgrade():
    # Path to your CSV file (adjust as needed)
    csv_path = os.path.join(os.path.dirname(__file__), 'keycloak_users.csv')

    # Read the CSV and update the database
    with open(csv_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            op.execute(
                "UPDATE users SET external_id = %s WHERE email = %s",
                [row['id'], row['email']]
            )

def downgrade() -> None:
    """No-op; this is a data migration, not a schema migration."""
    pass
