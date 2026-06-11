"""Unit tests for PostgresDataCatalogRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import app.infrastructure.repositories.postgres_data_catalog_repository as dc_mod
from app.infrastructure.repositories.postgres_data_catalog_repository import PostgresDataCatalogRepository


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, scalar_values=None, rows_values=None):
        self.scalar_values = list(scalar_values or [])
        self.rows_values = list(rows_values or [])
        self.added = []
        self.commits = 0
        self.flushes = 0

    def execute(self, stmt):
        if self.scalar_values:
            return _ScalarResult(self.scalar_values.pop(0))
        if self.rows_values:
            return _RowsResult(self.rows_values.pop(0))
        return _ScalarResult([])

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_list_data_products_maps_rows(monkeypatch, data_catalog_product_row: dict[str, object], clone_payload):
    row_payload = clone_payload(data_catalog_product_row)
    row = SimpleNamespace(
        **{**row_payload, "created_at": datetime.fromisoformat(str(row_payload["created_at"]))}
    )
    session = _Session(scalar_values=[[row]])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    out = repo.list_data_products("w1")

    assert len(out) == 1
    assert out[0].id == "p1"
    assert out[0].workspace_id == "w1"
    assert out[0].business_key == row_payload.get("business_key", "")


def test_list_data_sets_maps_rows(monkeypatch, data_catalog_set_row: dict[str, object], clone_payload):
    row_payload = clone_payload(data_catalog_set_row)
    row = SimpleNamespace(
        **{**row_payload, "created_at": datetime.fromisoformat(str(row_payload["created_at"]))}
    )
    session = _Session(scalar_values=[[row]])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    out = repo.list_data_sets(product_id="p1", workspace="w1")

    assert len(out) == 1
    assert out[0].product_id == "p1"
    assert out[0].business_key == row_payload.get("business_key", "")


def test_list_rule_attributes_maps_rows(monkeypatch, data_catalog_rule_attribute_row: dict[str, object]):
    row = SimpleNamespace(**{**data_catalog_rule_attribute_row, "threshold_override": None})
    session = _Session(scalar_values=[[row]])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    out = repo.list_rule_attributes()

    assert len(out) == 1
    assert out[0].ruleId == "r1"
    assert out[0].attributeId == "a1"


def test_add_rule_attributes_counts_added(monkeypatch, data_catalog_add_entries: list[dict[str, object]], clone_payload):
    session = _Session()
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    result = repo.add_rule_attributes(clone_payload({"rows": data_catalog_add_entries})["rows"])

    assert result.added == 2
    assert len(session.added) == 2
    assert session.commits == 2


def test_list_data_object_versions_maps_rows(
    monkeypatch,
    data_catalog_object_version_row: dict[str, object],
    clone_payload,
):
    row_payload = clone_payload(data_catalog_object_version_row)
    row = SimpleNamespace(
        **{**row_payload, "created_at": datetime.fromisoformat(str(row_payload["created_at"]))}
    )
    session = _Session(scalar_values=[[row]])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    out = repo.list_data_object_versions("o1")

    assert len(out) == 1
    assert out[0].version == 3
    assert out[0].attribute_count == 7


def test_get_attribute_rule_counts_maps_tuple_rows(monkeypatch, data_catalog_attribute_counts_rows: list[tuple[str | None, int]]):
    session = _Session(rows_values=[data_catalog_attribute_counts_rows])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    out = repo.get_attribute_rule_counts()

    assert out == {"a1": 2, "a2": 5}


def test_list_data_deliveries_maps_types(
    monkeypatch,
    data_catalog_delivery_row: dict[str, object],
    clone_payload,
):
    row_payload = clone_payload(data_catalog_delivery_row)
    row = SimpleNamespace(
        **{**row_payload, "timestamp": datetime.fromisoformat(str(row_payload["timestamp"]))}
    )
    session = _Session(scalar_values=[[row]])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    out = repo.list_data_deliveries("1")

    assert len(out) == 1
    assert out[0].data_object_version_id == "v1"
    assert out[0].delivered_at.startswith("2024-01-01")
    assert out[0].record_count == 100
    assert out[0].status == "completed"
    assert out[0].layer == "standardized"
    assert out[0].delivery_location == "standardized/bucket/schema/object/v1/LOAD_DTS=20240101T000000000Z"


def test_list_data_deliveries_filters_by_data_object_version_id(monkeypatch) -> None:
    row = SimpleNamespace(
        id="d2",
        data_object_id="o2",
        data_object_version_id="dov-3",
        version=3,
        timestamp=datetime(2026, 3, 29, tzinfo=UTC),
        layer="standardized",
        delivery_location="standardized/analytics/do-1/v3/LOAD_DTS=20260329T000000000Z",
        record_count=10,
        size_bytes=100,
        status="completed",
        attributes_count=3,
    )
    session = _Session(scalar_values=[[row]])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    out = repo.list_data_deliveries("dov-3")

    assert len(out) == 1
    assert out[0].data_object_version_id == "dov-3"
    assert out[0].layer == "standardized"
    assert out[0].delivery_location == "standardized/analytics/do-1/v3/LOAD_DTS=20260329T000000000Z"


def test_to_text_helper():
    repo = PostgresDataCatalogRepository("postgresql://example")

    assert repo._to_text(None) == ""
    assert repo._to_text(Decimal("12.5")) == "12.5"
    assert repo._to_text(datetime(2024, 1, 1, tzinfo=UTC)).startswith("2024-01-01")


def test_list_data_objects_and_catalog_and_attributes(monkeypatch) -> None:
    object_row = SimpleNamespace(id="o1", name="orders", description="Orders", business_key="orders")
    catalog_row = SimpleNamespace(
        id="doc-1",
        dataset_id="ds-1",
        name="orders_v1",
        description="Orders catalog",
        icon="table",
        created_at=datetime(2026, 3, 29, tzinfo=UTC),
        latest_version_id="ov-1",
        business_key="orders",
    )
    attribute_row = SimpleNamespace(
        id="a1",
        name="email",
        type="text",
        nullable=0,
        format="email",
        is_cde=1,
        is_primary_key=False,
        is_business_key=True,
        data_object_id="doc-1",
        version_id="ov-1",
    )

    session = _Session(scalar_values=[[object_row], [catalog_row], [attribute_row]])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")

    objects = repo.list_data_objects()
    catalogs = repo.list_data_objects_catalog()
    attrs = repo.list_attributes_catalog()

    assert objects[0].id == "o1"
    assert objects[0].business_key == "orders"
    assert catalogs[0].latest_version_id == "ov-1"
    assert catalogs[0].business_key == "orders"
    assert attrs[0].nullable is False
    assert attrs[0].is_cde is True
    assert attrs[0].is_business_key is True


def test_list_data_deliveries_without_version_filter(monkeypatch) -> None:
    row = SimpleNamespace(
        id="d2",
        data_object_id="o2",
        version=2,
        timestamp=datetime(2026, 3, 29, tzinfo=UTC),
        record_count=10,
        size_bytes=100,
        status="completed",
        attributes_count=3,
    )
    session = _Session(scalar_values=[[row]])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    out = repo.list_data_deliveries()

    assert out[0].id == "d2"
    assert out[0].version == 2


def test_get_data_delivery_note_maps_rows(monkeypatch) -> None:
    delivery_row = SimpleNamespace(
        id="d2",
        data_object_id="o2",
        data_object_version_id="dov-3",
        version=3,
        timestamp=datetime(2026, 3, 29, tzinfo=UTC),
        layer="standardized",
        delivery_location="standardized/analytics/do-1/v3/LOAD_DTS=20260329T000000000Z",
        record_count=10,
        size_bytes=100,
        status="completed",
        attributes_count=3,
    )
    note_row = SimpleNamespace(
        data_delivery_id="d2",
        storage_location="S3",
        delivery_format="parquet",
        file_count=2,
        ingestor_name="data-ingestor",
        ingestor_run_id="run-123",
        source_system="crm",
        source_snapshot_id="snap-123",
        checksum="abc123",
        checksum_algorithm="sha256",
        metadata_json={
            "ingestor": "alpha",
            "object_storage_classification": "real_evidence",
            "evidence_classification": "real_evidence",
        },
    )
    session = _Session(scalar_values=[[delivery_row], [note_row]])
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresDataCatalogRepository("postgresql://example")
    note = repo.get_data_delivery_note("d2")

    assert note is not None
    assert note.id == "note-d2"
    assert note.data_delivery_id == "d2"
    assert note.delivery_status == "completed"
    assert note.delivery_format == "parquet"
    assert note.file_count == 2
    assert note.metadata_json == {
        "ingestor": "alpha",
        "object_storage_classification": "real_evidence",
        "evidence_classification": "real_evidence",
    }
    assert note.object_storage_classification == "real_evidence"
    assert note.evidence_classification == "real_evidence"
    assert note.layer == "standardized"
    assert note.storage_location == "S3"
    assert note.delivery_location == "standardized/analytics/do-1/v3/LOAD_DTS=20260329T000000000Z"


def test_create_materialized_delivery_note_flushes_parent_delivery_before_note(monkeypatch) -> None:
    session = _Session()
    monkeypatch.setattr(dc_mod, "session_scope", lambda db_url: _Ctx(session))

    returned_note = SimpleNamespace(
        id="note-td-del-1",
        data_delivery_id="td-del-1",
        data_object_id="do-1",
        data_object_version_id="dov-3",
        version=3,
        timestamp=datetime(2026, 4, 19, tzinfo=UTC),
        layer="standardized",
        storage_location="S3",
        delivery_location="s3a://dq-test-data/data_object_version_id=dov-3/attr_hash=abc/sample_count=200/format=parquet",
        delivery_status="completed",
        delivery_format="parquet",
        record_count=200,
        size_bytes=0,
        attributes_count=7,
        file_count=None,
        ingestor_name="dq-engine-test-data-materialization-worker",
        ingestor_run_id="tdmj-1",
        source_system="test_data_materialization",
        source_snapshot_id="tdm-1",
        checksum=None,
        checksum_algorithm=None,
        object_storage_classification="synthetic_test",
        evidence_classification="synthetic_result",
        metadata_json={
            "materialization_request_id": "tdm-1",
            "object_storage_classification": "synthetic_test",
            "evidence_classification": "synthetic_result",
        },
    )

    repo = PostgresDataCatalogRepository("postgresql://example")
    monkeypatch.setattr(repo, "get_data_delivery_note", lambda delivery_id: returned_note if delivery_id == "td-del-1" else None)

    note = repo.create_materialized_delivery_note(
        {
            "data_delivery_id": "td-del-1",
            "data_object_id": "do-1",
            "data_object_version_id": "dov-3",
            "version": 3,
            "delivered_at": "2026-04-19T01:18:49Z",
            "layer": "standardized",
            "delivery_location": "s3a://dq-test-data/data_object_version_id=dov-3/attr_hash=abc/sample_count=200/format=parquet",
            "record_count": 200,
            "size_bytes": 0,
            "delivery_status": "completed",
            "attributes_count": 7,
            "storage_location": "S3",
            "delivery_format": "parquet",
            "ingestor_name": "dq-engine-test-data-materialization-worker",
            "ingestor_run_id": "tdmj-1",
            "source_system": "test_data_materialization",
            "source_snapshot_id": "tdm-1",
            "metadata_json": {
                "materialization_request_id": "tdm-1",
                "object_storage_classification": "synthetic_test",
                "evidence_classification": "synthetic_result",
            },
        }
    )

    assert note.data_delivery_id == "td-del-1"
    assert session.flushes == 1
    assert session.commits == 1
    assert len(session.added) == 2
    assert session.added[0].__class__.__name__ == "DataDeliveryRow"
    assert session.added[1].__class__.__name__ == "DataDeliveryNoteRow"


def test_add_rule_attributes_skips_duplicates_missing_existing_and_exceptions(monkeypatch) -> None:
    class _ExplodingCtx:
        def __enter__(self):
            raise RuntimeError("db error")

        def __exit__(self, exc_type, exc, tb):
            return False

    stable_session = _Session(
        scalar_values=[
            [SimpleNamespace(id="existing")],
            [],
        ]
    )

    calls = {"count": 0}

    def _scope(_db_url: str):
        calls["count"] += 1
        if calls["count"] == 3:
            return _ExplodingCtx()
        return _Ctx(stable_session)

    monkeypatch.setattr(dc_mod, "session_scope", _scope)

    repo = PostgresDataCatalogRepository("postgresql://example")
    result = repo.add_rule_attributes(
        [
            {"ruleId": "r-existing", "attributeId": "a1"},
            {"ruleId": "r-new", "attributeId": "a2"},
            {"ruleId": "r-new", "attributeId": "a2"},
            {"ruleId": "", "attributeId": "missing-rule"},
            {"ruleId": "r-fail", "attributeId": "a3"},
        ]
    )

    assert result.added == 1
    assert stable_session.commits == 1
    assert len(stable_session.added) == 1
