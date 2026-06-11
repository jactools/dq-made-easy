"""Unit tests for PostgresMasterDataRepository."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import app.infrastructure.repositories.postgres_master_data_repository as master_mod
from app.infrastructure.repositories.postgres_master_data_repository import PostgresMasterDataRepository


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _Session:
    def __init__(self, values=None):
        self.values = values or []

    def execute(self, stmt):  # noqa: ARG002
        return _ScalarResult(self.values)


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):  # noqa: ARG002
        return False


def test_list_master_records_maps_rows(monkeypatch):
    row = SimpleNamespace(
        id="mr-1",
        domain="customer",
        display_name="Acme Retail Holdings",
        business_key="cust-retail-001",
        golden_record_id="golden-cust-retail-001",
        match_rule="email_phone_tax_id",
        survivorship_rule="prefer_verified_source_then_most_recent",
        resolution_status="golden",
        source_count=3,
        source_systems=["crm", "core-banking"],
        merged_from_ids=["crm-1"],
        owner="Customer Operations",
        workspace_id="retail-banking",
        created_at=datetime(2026, 2, 10, 9, 0, 0),
        updated_at=datetime(2026, 2, 21, 8, 30, 0),
    )
    session = _Session(values=[row])
    monkeypatch.setattr(master_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresMasterDataRepository("postgresql://example")
    records = repo.list_master_records(domain="customer", workspace_id="retail-banking")

    assert len(records) == 1
    assert records[0].id == "mr-1"
    assert records[0].workspace_id == "retail-banking"
    assert records[0].source_systems == ["crm", "core-banking"]
    assert records[0].merged_from_ids == ["crm-1"]