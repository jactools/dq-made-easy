from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.presenters.data_catalog import (
    _entity_payload,
    build_catalog_materialization_targets,
    build_data_catalog_page_payload,
    build_delivery_linked_execution_note_enrichment,
    resolve_catalog_materialization_selection,
    resolve_delivery_inventory_location,
    resolve_delivery_linked_execution_delivery_id,
    resolve_delivery_linked_execution_sort_key,
)


class _ModelDumpPayload:
    def __init__(self, **payload: object) -> None:
        self._payload = payload

    def model_dump(self, exclude_none: bool = False) -> dict[str, object]:
        return dict(self._payload)


class _MaterializationRepository:
    def __init__(self) -> None:
        self._objects = {
            "obj-1": SimpleNamespace(id="obj-1", latest_version_id="ver-1", dataset_id="ds-1"),
            "obj-2": SimpleNamespace(id="obj-2", latest_version_id="", dataset_id="ds-2"),
            "obj-3": SimpleNamespace(id="obj-3", latest_version_id="", dataset_id="ds-3"),
            "obj-4": SimpleNamespace(id="obj-4", latest_version_id="ver-4", dataset_id="ds-4"),
        }
        self._versions = {
            "ver-1": SimpleNamespace(id="ver-1", data_object_id="obj-1", version=1),
            "ver-2a": SimpleNamespace(id="ver-2a", data_object_id="obj-2", version=2),
            "ver-2b": SimpleNamespace(id="ver-2b", data_object_id="obj-2", version=3),
            "ver-4": SimpleNamespace(id="ver-4", data_object_id="obj-4", version=4),
        }
        self._versions_by_object = {
            "obj-2": [self._versions["ver-2a"], self._versions["ver-2b"]],
            "obj-3": [],
        }
        self._dataset_objects = {
            "ds-1": [self._objects["obj-1"]],
            "ds-4": [self._objects["obj-4"]],
        }
        self._data_sets = {
            "dp-1": [SimpleNamespace(id="ds-1"), SimpleNamespace(id="ds-4")],
        }
        self._attributes = {
            "ver-1": [SimpleNamespace(name="status"), SimpleNamespace(name="region")],
            "ver-4": [SimpleNamespace(name="customer_id")],
        }

    def list_data_objects_catalog(self, selector_value: str | None = None) -> list[SimpleNamespace]:
        if selector_value is None:
            return list(self._objects.values())
        return list(self._dataset_objects.get(selector_value, []))

    def list_data_object_versions(self, object_id: str) -> list[SimpleNamespace]:
        return list(self._versions_by_object.get(object_id, []))

    def get_data_object_version(self, version_id: str) -> SimpleNamespace | None:
        return self._versions.get(version_id)

    def list_data_sets(self, selector_value: str) -> list[SimpleNamespace]:
        return list(self._data_sets.get(selector_value, []))

    def list_attributes_catalog(self, version_id: str) -> list[SimpleNamespace]:
        return list(self._attributes.get(version_id, []))


def _selection_payload(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "data_product_id": None,
        "data_set_id": None,
        "data_object_id": None,
        "data_object_version_id": None,
        "selected_attribute_names": None,
        "output_uri": None,
        "output_format": "parquet",
        "sample_count": 10,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_build_data_catalog_page_payload_normalizes_pagination_bounds() -> None:
    rows = [{"id": "row-1"}, {"id": "row-2"}, {"id": "row-3"}]

    first_page = build_data_catalog_page_payload(rows, page=0, limit=200)
    assert first_page == {
        "data": rows,
        "pagination": {
            "total": 3,
            "page": 1,
            "limit": 100,
            "total_pages": 1,
            "has_next": False,
            "has_previous": False,
        },
    }

    second_page = build_data_catalog_page_payload(rows, page=2, limit=1)
    assert second_page["data"] == [{"id": "row-2"}]
    assert second_page["pagination"] == {
        "total": 3,
        "page": 2,
        "limit": 1,
        "total_pages": 3,
        "has_next": True,
        "has_previous": True,
    }


def test_entity_payload_handles_mapping_model_dump_and_unsupported_objects() -> None:
    mapping = {"id": "row-1", "kind": "mapping"}
    dumped = _ModelDumpPayload(id="row-2", kind="model_dump")

    assert _entity_payload(mapping) == mapping
    assert _entity_payload(dumped) == {"id": "row-2", "kind": "model_dump"}
    assert _entity_payload(object()) == {}


def test_delivery_inventory_location_and_linked_execution_resolution_paths() -> None:
    assert resolve_delivery_inventory_location(
        delivery_location="s3://bucket/raw/path",
        layer=None,
        workspace=None,
        data_object_id=None,
        data_object_name=None,
    ) == "s3a://bucket/raw/path"

    assert resolve_delivery_inventory_location(
        delivery_location="s3a://bucket/raw/path",
        layer=None,
        workspace=None,
        data_object_id=None,
        data_object_name=None,
    ) == "s3a://bucket/raw/path"

    assert resolve_delivery_inventory_location(
        delivery_location="layer:obj-1/partition",
        layer="layer",
        workspace="warehouse",
        data_object_id="obj-1",
        data_object_name="object-one",
    ) == "s3a://warehouse/layer/object-one/partition"

    with pytest.raises(HTTPException, match="must not be empty"):
        resolve_delivery_inventory_location(
            delivery_location="",
            layer=None,
            workspace=None,
            data_object_id=None,
            data_object_name=None,
        )

    with pytest.raises(HTTPException, match="requires a workspace"):
        resolve_delivery_inventory_location(
            delivery_location="layer/object",
            layer="layer",
            workspace=None,
            data_object_id=None,
            data_object_name=None,
        )

    with pytest.raises(HTTPException, match="could not be resolved"):
        resolve_delivery_inventory_location(
            delivery_location="layer:",
            layer="layer",
            workspace="warehouse",
            data_object_id=None,
            data_object_name=None,
        )

    assert resolve_delivery_linked_execution_delivery_id(
        {"executionContract": {"resolvedDataDeliveryId": "delivery-1"}}
    ) == "delivery-1"

    assert resolve_delivery_linked_execution_delivery_id(
        {"handoffPayload": {"delivery_snapshot": {"resolved_data_delivery_id": "delivery-2"}}}
    ) == "delivery-2"

    assert resolve_delivery_linked_execution_delivery_id(
        {},
        dispatch_payload_builder=lambda _payload: SimpleNamespace(
            deliverySnapshot=SimpleNamespace(resolvedDataDeliveryId="delivery-3")
        ),
    ) == "delivery-3"

    assert resolve_delivery_linked_execution_delivery_id(
        {},
        dispatch_payload_builder=lambda _payload: SimpleNamespace(deliverySnapshot=None),
    ) == ""

    assert resolve_delivery_linked_execution_sort_key(
        {
            "completedAt": "2026-05-22T10:00:00Z",
            "submittedAt": "2026-05-22T09:00:00Z",
            "createdAt": "2026-05-22T08:00:00Z",
            "id": "run-1",
        }
    ) == ("2026-05-22T10:00:00Z", "2026-05-22T09:00:00Z", "2026-05-22T08:00:00Z", "run-1")

    runs = [
        {
            "id": "run-1",
            "status": "failed",
            "completedAt": "2026-05-21T10:00:00Z",
            "submittedAt": "2026-05-21T09:00:00Z",
            "createdAt": "2026-05-21T08:00:00Z",
            "executionContract": {"resolvedDataDeliveryId": "delivery-1"},
        },
        {
            "id": "run-2",
            "status": "passed",
            "completedAt": "2026-05-22T10:00:00Z",
            "submittedAt": "2026-05-22T09:00:00Z",
            "createdAt": "2026-05-22T08:00:00Z",
            "executionContract": {"resolvedDataDeliveryId": "delivery-1"},
            "requestedBy": "tester",
        },
    ]

    enrichment = build_delivery_linked_execution_note_enrichment(delivery_id="delivery-1", runs=runs)
    assert enrichment["execution_summary"] == {
        "total_execution_runs": 2,
        "status_counts": {"passed": 1, "failed": 1},
        "latest_execution_run_id": "run-2",
        "latest_execution_status": "passed",
        "latest_execution_submitted_at": "2026-05-22T09:00:00Z",
        "latest_execution_completed_at": "2026-05-22T10:00:00Z",
    }
    assert enrichment["execution_references"][0]["execution_run_id"] == "run-2"
    assert build_delivery_linked_execution_note_enrichment(delivery_id="missing", runs=runs) == {}


def test_resolve_catalog_materialization_selection_covers_success_and_error_paths() -> None:
    repository = _MaterializationRepository()

    with pytest.raises(HTTPException, match="Provide exactly one"):
        resolve_catalog_materialization_selection(
            _selection_payload(data_product_id="dp-1", data_set_id="ds-1"),
            repository,
        )

    version_targets, version_selection = resolve_catalog_materialization_selection(
        _selection_payload(data_object_version_id="ver-1"),
        repository,
    )
    assert version_targets == [{"data_object_version_id": "ver-1", "data_object_id": "obj-1", "version": 1}]
    assert version_selection["resolved"]["target_count"] == 1

    object_targets, object_selection = resolve_catalog_materialization_selection(
        _selection_payload(data_object_id="obj-1"),
        repository,
    )
    assert object_targets == [{"data_product_id": None, "data_set_id": "ds-1", "data_object_id": "obj-1", "data_object_version_id": "ver-1", "version": 1}]
    assert object_selection["resolved"]["data_object_version_id"] == "ver-1"

    with pytest.raises(HTTPException, match="does not resolve unambiguously"):
        resolve_catalog_materialization_selection(_selection_payload(data_object_id="obj-2"), repository)

    with pytest.raises(HTTPException, match="has no versions to materialize"):
        resolve_catalog_materialization_selection(_selection_payload(data_object_id="obj-3"), repository)

    data_set_targets, data_set_selection = resolve_catalog_materialization_selection(
        _selection_payload(data_set_id="ds-1"),
        repository,
    )
    assert data_set_targets == [{"data_product_id": None, "data_set_id": "ds-1", "data_object_id": "obj-1", "data_object_version_id": "ver-1", "version": 1}]
    assert data_set_selection["resolved"]["data_set_id"] == "ds-1"

    with pytest.raises(HTTPException, match="was not found or has no data objects"):
        resolve_catalog_materialization_selection(_selection_payload(data_set_id="missing"), repository)

    product_targets, product_selection = resolve_catalog_materialization_selection(
        _selection_payload(data_product_id="dp-1"),
        repository,
    )
    assert len(product_targets) == 2
    assert product_selection["resolved"]["target_count"] == 2
    assert product_selection["resolved"]["data_set_ids"] == ["ds-1", "ds-4"]

    with pytest.raises(HTTPException, match="was not found or has no data sets"):
        resolve_catalog_materialization_selection(_selection_payload(data_product_id="missing"), repository)


def test_build_catalog_materialization_targets_covers_selection_and_output_paths() -> None:
    repository = _MaterializationRepository()
    base_calls: list[tuple[str, str, str, int, str]] = []

    def default_output_uri(*, output_prefix: str, version_id: str, output_format: str, sample_count: int, attribute_hash: str) -> str:
        base_calls.append((output_prefix, version_id, output_format, sample_count, attribute_hash))
        return f"{output_prefix}/{version_id}/{attribute_hash}/{output_format}/{sample_count}"

    payload = _selection_payload(
        data_object_version_id="ver-1",
        output_uri="",
        output_format="CSV",
        sample_count=25,
        selected_attribute_names=None,
    )
    resolved_targets = [{"data_object_version_id": "ver-1", "data_object_id": "obj-1", "data_set_id": "ds-1", "data_product_id": "dp-1", "version": 1}]
    selection = {"selector_type": "data_object_version_id", "requested": {"data_object_version_id": "ver-1"}, "resolved": {}}

    queue_targets, normalized_selection, request_output_uri = build_catalog_materialization_targets(
        payload=payload,
        resolved_targets=resolved_targets,
        selection=selection,
        repository=repository,
        build_attribute_payloads=lambda rows: [{"name": row.name} for row in rows],
        normalize_s3_uri=lambda value: value.replace("s3://", "s3a://") if value.startswith("s3://") else "",
        resolve_test_data_output_prefix=lambda: "s3a://default-prefix",
        default_materialization_output_uri=default_output_uri,
    )

    assert request_output_uri == "s3a://default-prefix/ver-1/all/CSV/25"
    assert queue_targets[0]["output_uri"] == request_output_uri
    assert queue_targets[0]["attributes"] == [{"name": "status"}, {"name": "region"}]
    assert normalized_selection["resolved"]["target_count"] == 1
    assert base_calls == [("s3a://default-prefix", "ver-1", "CSV", 25, "all")]

    direct_payload = _selection_payload(
        data_object_version_id="ver-1",
        output_uri="s3://custom/output",
        output_format="parquet",
        sample_count=10,
        selected_attribute_names=["status"],
    )

    queue_targets, normalized_selection, request_output_uri = build_catalog_materialization_targets(
        payload=direct_payload,
        resolved_targets=resolved_targets,
        selection=selection,
        repository=repository,
        build_attribute_payloads=lambda rows: [{"name": row.name} for row in rows],
        normalize_s3_uri=lambda value: value.replace("s3://", "s3a://") if value.startswith("s3://") else "",
        resolve_test_data_output_prefix=lambda: "s3a://default-prefix",
        default_materialization_output_uri=lambda **_: (_ for _ in ()).throw(AssertionError("default output path should not be used")),
    )

    assert request_output_uri == "s3a://custom/output"
    assert queue_targets[0]["output_uri"] == "s3a://custom/output"
    assert queue_targets[0]["attributes"] == [{"name": "status"}]
    assert normalized_selection["resolved"]["targets"][0]["selected_attribute_names"] == ["status"]

    with pytest.raises(HTTPException, match="missing_attributes"):
        build_catalog_materialization_targets(
            payload=_selection_payload(data_object_version_id="ver-empty"),
            resolved_targets=[{"data_object_version_id": "ver-empty", "data_object_id": "obj-empty", "data_set_id": "ds-empty", "data_product_id": "dp-empty", "version": 1}],
            selection=selection,
            repository=repository,
            build_attribute_payloads=lambda rows: [{"name": row.name} for row in rows],
            normalize_s3_uri=lambda value: value if value.startswith("s3a://") else "",
            resolve_test_data_output_prefix=lambda: "s3a://default-prefix",
            default_materialization_output_uri=default_output_uri,
        )

    with pytest.raises(HTTPException, match="unknown_attributes"):
        build_catalog_materialization_targets(
            payload=_selection_payload(data_object_version_id="ver-1", selected_attribute_names=["missing"]),
            resolved_targets=resolved_targets,
            selection=selection,
            repository=repository,
            build_attribute_payloads=lambda rows: [{"name": row.name} for row in rows],
            normalize_s3_uri=lambda value: value if value.startswith("s3a://") else "",
            resolve_test_data_output_prefix=lambda: "s3a://default-prefix",
            default_materialization_output_uri=default_output_uri,
        )