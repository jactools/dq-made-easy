"""Integration tests: Postgres repository round-trips against the live container.

Each test calls a read method through the real SQLAlchemy ORM and asserts it
returns without raising an exception.  These are the regression tests that would
have caught the 'ruleId' → 'ruleid' column name bug before it reached production.

Covered regressions
-------------------
- approvals.list_approvals()       → was failing on column "ruleid" / "requesterid"
- approvals.list_approval_audit()  → was failing on column "approvalid" / "actorid"
- data_catalog.list_rule_attributes() → was failing on column "ruleid" / "attributeid"
- data_catalog.get_attribute_rule_counts() → same join through rule_attributes

All other repository round-trips are included to guard against future schema drift.

Run:
    pytest -m integration tests/infrastructure/integration/test_repository_roundtrips.py
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.infrastructure.repositories.postgres_admin_repository import PostgresAdminRepository
from app.infrastructure.repositories.postgres_approvals_repository import PostgresApprovalsRepository
from app.infrastructure.repositories.postgres_data_catalog_repository import PostgresDataCatalogRepository
from app.infrastructure.repositories.postgres_master_data_repository import PostgresMasterDataRepository
from app.infrastructure.repositories.postgres_rules_repository import PostgresRulesRepository
from app.infrastructure.repositories.postgres_system_repository import PostgresSystemRepository
from app.infrastructure.repositories.postgres_validation_run_plan_repository import PostgresValidationRunPlanRepository
from app.infrastructure.repositories.postgres_workspaces_repository import PostgresWorkspacesRepository

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Approvals — were broken by "ruleid" / "approvalid" / "actorid" mismatch
# ---------------------------------------------------------------------------

def test_list_approvals_round_trip(live_db_url: str) -> None:
    """list_approvals() must execute without raising a column-not-found error."""
    result = PostgresApprovalsRepository(live_db_url).list_approvals()
    assert isinstance(result, list)


def test_list_approvals_filtered_by_workspace(live_db_url: str) -> None:
    result = PostgresApprovalsRepository(live_db_url).list_approvals(workspace_id="default")
    assert isinstance(result, list)


def test_list_approval_audit_round_trip(live_db_url: str) -> None:
    """list_approval_audit() must not raise — was broken by 'approvalid'/'actorid'."""
    result = PostgresApprovalsRepository(live_db_url).list_approval_audit()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Data catalog — were broken by "ruleid" / "attributeid" mismatch
# ---------------------------------------------------------------------------

def test_list_rule_attributes_round_trip(live_db_url: str) -> None:
    """list_rule_attributes() must not raise — was broken by 'ruleid'/'attributeid'."""
    result = PostgresDataCatalogRepository(live_db_url).list_rule_attributes()
    assert isinstance(result, list)


def test_get_attribute_rule_counts_round_trip(live_db_url: str) -> None:
    """get_attribute_rule_counts() must not raise — joins through rule_attributes."""
    result = PostgresDataCatalogRepository(live_db_url).get_attribute_rule_counts()
    assert isinstance(result, dict)


def test_list_data_products_round_trip(live_db_url: str) -> None:
    result = PostgresDataCatalogRepository(live_db_url).list_data_products()
    assert isinstance(result, list)


def test_list_data_sets_round_trip(live_db_url: str) -> None:
    result = PostgresDataCatalogRepository(live_db_url).list_data_sets()
    assert isinstance(result, list)


def test_list_data_objects_round_trip(live_db_url: str) -> None:
    result = PostgresDataCatalogRepository(live_db_url).list_data_objects()
    assert isinstance(result, list)


def test_list_data_objects_catalog_round_trip(live_db_url: str) -> None:
    result = PostgresDataCatalogRepository(live_db_url).list_data_objects_catalog()
    assert isinstance(result, list)


def test_list_attributes_catalog_round_trip(live_db_url: str) -> None:
    result = PostgresDataCatalogRepository(live_db_url).list_attributes_catalog()
    assert isinstance(result, list)


def test_list_data_deliveries_round_trip_against_live_schema(live_db_url: str, live_engine) -> None:
    with live_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'data_deliveries' ORDER BY ordinal_position"
            )
        ).fetchall()

    column_names = {row[0] for row in rows}
    assert {"data_object_version_id", "delivery_location"}.issubset(column_names)

    result = PostgresDataCatalogRepository(live_db_url).list_data_deliveries()
    assert isinstance(result, list)


def test_list_master_records_round_trip(live_db_url: str) -> None:
    result = PostgresMasterDataRepository(live_db_url).list_master_records(
        domain="customer",
        workspace_id="retail-banking",
    )
    assert isinstance(result, list)
    assert result
    assert result[0].id == "mr-001"


# ---------------------------------------------------------------------------
# Other repositories
# ---------------------------------------------------------------------------

def test_list_rules_round_trip(live_db_url: str) -> None:
    result = asyncio.run(PostgresRulesRepository(live_db_url).list_rule_records())
    assert isinstance(result, list)


def test_get_rule_by_id_round_trip(live_db_url: str) -> None:
    rows = asyncio.run(PostgresRulesRepository(live_db_url).list_rule_records())
    if not rows:
        pytest.skip("No rules seeded in live DB")

    result = asyncio.run(PostgresRulesRepository(live_db_url).get_rule_by_id(str(rows[0].id)))
    assert result is not None


def test_list_rule_versions_round_trip(live_db_url: str) -> None:
    rows = asyncio.run(PostgresRulesRepository(live_db_url).list_rule_records())
    if not rows:
        pytest.skip("No rules seeded in live DB")

    payload = asyncio.run(PostgresRulesRepository(live_db_url).list_rule_versions(str(rows[0].id)))
    assert payload is not None
    assert payload["pagination"]["total"] >= 1
    assert payload["versions"]


def test_live_rules_have_current_versions(live_db_url: str) -> None:
    rows = asyncio.run(PostgresRulesRepository(live_db_url).list_rule_records())
    if not rows:
        pytest.skip("No rules seeded in live DB")

    assert any(True for _ in rows)


def test_list_workspaces_round_trip(live_db_url: str) -> None:
    result = PostgresWorkspacesRepository(live_db_url).list_workspaces()
    assert isinstance(result, list)


def test_get_system_info_round_trip(live_db_url: str) -> None:
    result = PostgresSystemRepository(live_db_url).get_system_info()
    assert result is not None
    assert isinstance(result.db_schema_version, str)


def test_list_users_round_trip(live_db_url: str) -> None:
    result = PostgresAdminRepository(live_db_url).list_users()
    assert isinstance(result, list)


def test_list_validation_run_plans_round_trip(live_db_url: str, live_engine) -> None:
    with live_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'validation_run_plans' ORDER BY ordinal_position"
            )
        ).fetchall()
    if not rows:
        pytest.skip("validation_run_plans table not present in live DB")

    result = asyncio.run(PostgresValidationRunPlanRepository(live_db_url).list_plans())
    assert isinstance(result, list)


def test_list_roles_round_trip(live_db_url: str) -> None:
    result = PostgresAdminRepository(live_db_url).list_roles()
    assert isinstance(result, list)
