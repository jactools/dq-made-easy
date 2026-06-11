"""add master records

Revision ID: 20260525_0039
Revises: 20260525_0038
Create Date: 2026-05-25 12:00:00.000000
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260525_0039"
down_revision = "20260525_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "master_records",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("business_key", sa.Text(), nullable=True),
        sa.Column("golden_record_id", sa.Text(), nullable=True),
        sa.Column("match_rule", sa.Text(), nullable=True),
        sa.Column("survivorship_rule", sa.Text(), nullable=True),
        sa.Column("resolution_status", sa.Text(), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=True),
        sa.Column("source_systems", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("merged_from_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_master_records_domain", "master_records", ["domain"], unique=False)
    op.create_index("ix_master_records_workspace_id", "master_records", ["workspace_id"], unique=False)

    op.bulk_insert(
        sa.table(
            "master_records",
            sa.column("id", sa.Text()),
            sa.column("domain", sa.Text()),
            sa.column("display_name", sa.Text()),
            sa.column("business_key", sa.Text()),
            sa.column("golden_record_id", sa.Text()),
            sa.column("match_rule", sa.Text()),
            sa.column("survivorship_rule", sa.Text()),
            sa.column("resolution_status", sa.Text()),
            sa.column("source_count", sa.Integer()),
            sa.column("source_systems", postgresql.JSONB(astext_type=sa.Text())),
            sa.column("merged_from_ids", postgresql.JSONB(astext_type=sa.Text())),
            sa.column("owner", sa.Text()),
            sa.column("workspace_id", sa.Text()),
            sa.column("created_at", sa.DateTime()),
            sa.column("updated_at", sa.DateTime()),
        ),
        [
            {
                "id": "mr-001",
                "domain": "customer",
                "display_name": "Acme Retail Holdings",
                "business_key": "cust-retail-001",
                "golden_record_id": "golden-cust-retail-001",
                "match_rule": "email_phone_tax_id",
                "survivorship_rule": "prefer_verified_source_then_most_recent",
                "resolution_status": "golden",
                "source_count": 3,
                "source_systems": ["crm", "core-banking", "support"],
                "merged_from_ids": ["crm-cust-771", "core-cust-1001"],
                "owner": "Customer Operations",
                "workspace_id": "retail-banking",
                "created_at": datetime(2026, 2, 10, 9, 0, 0),
                "updated_at": datetime(2026, 2, 21, 8, 30, 0),
            },
            {
                "id": "mr-002",
                "domain": "customer",
                "display_name": "Blue River Retail",
                "business_key": "cust-retail-002",
                "golden_record_id": "golden-cust-retail-002",
                "match_rule": "email_phone_tax_id",
                "survivorship_rule": "prefer_verified_source_then_longest_history",
                "resolution_status": "candidate",
                "source_count": 2,
                "source_systems": ["crm", "ecommerce"],
                "merged_from_ids": ["crm-cust-812"],
                "owner": "Customer Operations",
                "workspace_id": "retail-banking",
                "created_at": datetime(2026, 2, 11, 9, 0, 0),
                "updated_at": datetime(2026, 2, 20, 8, 30, 0),
            },
            {
                "id": "mr-003",
                "domain": "customer",
                "display_name": "Continental Corporate",
                "business_key": "cust-corp-001",
                "golden_record_id": "golden-cust-corp-001",
                "match_rule": "tax_id_company_name",
                "survivorship_rule": "prefer_system_of_record",
                "resolution_status": "golden",
                "source_count": 4,
                "source_systems": ["crm", "core-banking", "kyc", "support"],
                "merged_from_ids": ["kyc-cust-101", "crm-cust-303", "support-cust-44"],
                "owner": "Corporate Client Services",
                "workspace_id": "corporate-banking",
                "created_at": datetime(2026, 2, 12, 9, 0, 0),
                "updated_at": datetime(2026, 2, 21, 10, 0, 0),
            },
            {
                "id": "mr-004",
                "domain": "customer",
                "display_name": "Northwind Corporate",
                "business_key": "cust-corp-002",
                "golden_record_id": "golden-cust-corp-002",
                "match_rule": "tax_id_company_name",
                "survivorship_rule": "prefer_system_of_record",
                "resolution_status": "merged",
                "source_count": 3,
                "source_systems": ["crm", "core-banking", "kyc"],
                "merged_from_ids": ["crm-cust-404", "kyc-cust-228"],
                "owner": "Corporate Client Services",
                "workspace_id": "corporate-banking",
                "created_at": datetime(2026, 2, 13, 9, 0, 0),
                "updated_at": datetime(2026, 2, 21, 11, 0, 0),
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_master_records_workspace_id", table_name="master_records")
    op.drop_index("ix_master_records_domain", table_name="master_records")
    op.drop_table("master_records")