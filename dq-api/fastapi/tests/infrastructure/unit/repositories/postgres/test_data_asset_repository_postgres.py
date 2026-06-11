from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import app.infrastructure.repositories.postgres_data_asset_repository as repo_module
from app.infrastructure.repositories.postgres_data_asset_repository import PostgresDataAssetRepository


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _Session:
    def __init__(self, get_map=None, scalar_values=None):
        self.get_map = dict(get_map or {})
        self.scalar_values = list(scalar_values or [])
        self.added = []
        self.committed = False

    def get(self, model, key):
        model_key = (getattr(model, "__name__", str(model)), str(key))
        if model_key in self.get_map:
            return self.get_map[model_key]
        if str(key) in self.get_map:
            return self.get_map[str(key)]
        for row in self.added:
            if getattr(row, "id", None) == key and row.__class__.__name__ == getattr(model, "__name__", ""):
                return row
        return None

    def execute(self, stmt):
        values = self.scalar_values.pop(0) if self.scalar_values else [row for row in self.added if row.__class__.__name__.startswith("DataAsset")]
        return _ScalarResult(values)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_create_and_list_data_asset_roundtrip(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(repo_module, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataAssetRepository("postgresql://example")
    created = repo.create_data_asset(
        {
            "id": "asset-1",
            "name": "Customer health",
            "workspace_id": "ws-1",
            "source_object_version_ids": ["dov-1"],
            "business_context": {
                "validation_suites": ["validation-suite-customer-health"],
                "validation_plans": ["validation-plan-customer-health-daily"],
            },
        }
    )

    assert created.id == "asset-1"
    assert session.committed is True
    assert len(session.added) == 1

    listed = repo.list_data_assets(workspace_id="ws-1")
    assert listed[0].id == "asset-1"
    assert listed[0].business_context.validation_suites == ["validation-suite-customer-health"]
    assert listed[0].business_context.validation_plans == ["validation-plan-customer-health-daily"]


def test_create_data_asset_version_persists_and_updates_asset(monkeypatch) -> None:
    asset_row = SimpleNamespace(
        id="asset-1",
        name="Customer health",
        description=None,
        workspace_id="ws-1",
        status="draft",
        created_at=None,
        current_version_id=None,
        source_object_version_ids_json=["dov-1"],
    )
    session = _Session(get_map={"asset-1": asset_row}, scalar_values=[[SimpleNamespace(
        id="asset-1-v1",
        data_asset_id="asset-1",
        version=1,
        created_at=None,
        source_bindings_json=[
            {
                "source_data_object_version_id": "dov-1",
                "source_field_id": "field-1",
                "source_field_name": "customer_id",
                "source_field_type": "string",
            }
        ],
        filters_json=[],
        derived_fields_json=[
            {"name": "customer_segment", "expression": "case when amount > 100 then 'gold' end"}
        ],
        upload_preview_json=None,
    )]])
    monkeypatch.setattr(repo_module, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataAssetRepository("postgresql://example")
    version = repo.create_data_asset_version(
        "asset-1",
        {
            "id": "asset-1-v1",
            "version": 1,
            "derived_fields": [
                {"name": "customer_segment", "expression": "case when amount > 100 then 'gold' end"}
            ],
            "source_bindings": [
                {
                    "source_data_object_version_id": "dov-1",
                    "source_field_id": "field-1",
                    "source_field_name": "customer_id",
                    "source_field_type": "string",
                }
            ],
        },
    )

    assert version.id == "asset-1-v1"
    assert asset_row.current_version_id == "asset-1-v1"
    assert asset_row.source_object_version_ids_json == ["dov-1"]
    assert len(session.added) == 1
    assert session.committed is True

    fetched = repo.get_data_asset_version("asset-1", "asset-1-v1")
    assert fetched is not None
    assert fetched.derived_fields[0].name == "customer_segment"


def test_delete_data_asset_removes_asset(monkeypatch) -> None:
    asset_row = SimpleNamespace(
        id="asset-1",
        name="Customer health",
        description=None,
        workspace_id="ws-1",
        status="draft",
        created_at=None,
        current_version_id=None,
        source_object_version_ids_json=[],
    )
    session = _Session(get_map={"asset-1": asset_row}, scalar_values=[])
    monkeypatch.setattr(repo_module, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataAssetRepository("postgresql://example")
    deleted = repo.delete_data_asset("asset-1")

    assert deleted is True
    assert session.committed is True


def test_save_data_asset_contract_version_versions_on_change(monkeypatch) -> None:
    asset_row = SimpleNamespace(
        id="asset-1",
        name="Customer health",
        description=None,
        workspace_id="ws-1",
        status="draft",
        created_at=None,
        current_version_id=None,
        source_object_version_ids_json=[],
    )
    session = _Session(get_map={"asset-1": asset_row}, scalar_values=[])
    monkeypatch.setattr(repo_module, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataAssetRepository("postgresql://example")
    first = repo.save_data_asset_contract_version(
        "asset-1",
        {
            "contract_yaml": "apiVersion: v3.1.0\nkind: DataContract\nid: urn:dq:contract:asset-1\n",
            "generated_by": "user-1",
            "generated_where": "/rulebuilder/v1/data-assets/asset-1/contract",
            "generated_what": "Generated ODCS contract for Data Asset 'asset-1'",
        },
    )
    second = repo.save_data_asset_contract_version(
        "asset-1",
        {
            "contract_yaml": "apiVersion: v3.1.0\nkind: DataContract\nid: urn:dq:contract:asset-1\n",
            "generated_by": "user-2",
            "generated_where": "/rulebuilder/v1/data-assets/asset-1/contract",
            "generated_what": "Generated ODCS contract for Data Asset 'asset-1'",
        },
    )
    changed = repo.save_data_asset_contract_version(
        "asset-1",
        {
            "contract_yaml": "apiVersion: v3.1.0\nkind: DataContract\nid: urn:dq:contract:asset-1\nstatus: active\n",
            "generated_by": "user-3",
            "generated_where": "/rulebuilder/v1/data-assets/asset-1/contract",
            "generated_what": "Generated ODCS contract for Data Asset 'asset-1'",
        },
    )

    assert first.version == 1
    assert second.version == 1
    assert changed.version == 2


def test_record_and_list_data_asset_lineage_snapshots(monkeypatch) -> None:
    asset_row = SimpleNamespace(
        id="asset-1",
        name="Customer health",
        description=None,
        workspace_id="ws-1",
        status="draft",
        created_at=None,
        current_version_id=None,
        source_object_version_ids_json=[],
    )
    session = _Session(get_map={"asset-1": asset_row}, scalar_values=[[SimpleNamespace(
        id="asset-1-lineage-1",
        data_asset_id="asset-1",
        snapshot_kind="lineage",
        captured_at=datetime(2026, 5, 25, 13, 0, tzinfo=UTC),
        captured_by=None,
        lineage_json={"dataAsset": {"id": "asset-1"}},
        business_context_overlay_json={"domain": "Customer"},
        classification_view_json={"classification": "internal"},
        anomaly_annotations_json=[{"kind": "contract_change"}],
    )]])
    monkeypatch.setattr(repo_module, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataAssetRepository("postgresql://example")
    snapshot = repo.record_data_asset_lineage_snapshot(
        "asset-1",
        {
            "snapshot_kind": "lineage",
            "captured_at": "2026-05-25T13:00:00Z",
            "lineage_json": {"dataAsset": {"id": "asset-1"}},
            "business_context_overlay": {"domain": "Customer"},
            "classification_view": {"classification": "internal"},
            "anomaly_annotations": [{"kind": "contract_change"}],
        },
    )

    assert snapshot.data_asset_id == "asset-1"
    assert session.committed is True
    assert len(session.added) == 1
    stored_row = session.added[0]
    assert stored_row.lineage_json == {"dataAsset": {"id": "asset-1"}}

    listed = repo.list_data_asset_lineage_snapshots("asset-1")
    assert len(listed) == 1
    assert listed[0].classification_view["classification"] == "internal"
