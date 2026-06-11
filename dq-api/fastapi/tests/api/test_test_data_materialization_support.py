from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

import app.api.v1.test_data_materialization_support as support
from app.api.v1.schemas.data_catalog_view import DataDeliveryNoteView
from app.api.v1.schemas.test_data_materialization_view import MaterializationDeliveryView


def _record_with_selection(selection: dict | None = None) -> object:
    return support.build_test_data_materialization_record(
        request_id="req-1",
        job_id="job-1",
        correlation_id="corr-1",
        request_payload={
            "data_object_version_id": "dov-1",
            "sample_count": 100,
            "output_format": "parquet",
            "output_uri": "s3://bucket/default-output",
        },
        queue_key="queue:test",
        processing_queue_key="queue:test:processing",
        selection=selection,
        target_data_object_version_ids=["dov-1"],
    )


def _delivery_view(
    *,
    version_id: str,
    delivery_id: str,
    row_count: int,
    output_uri: str,
    output_format: str,
    object_storage_classification: str,
    evidence_classification: str,
) -> MaterializationDeliveryView:
    return MaterializationDeliveryView(
        data_object_version_id=version_id,
        row_count=row_count,
        output_uri=output_uri,
        output_format=output_format,
        data_delivery_id=delivery_id,
        delivery_note=DataDeliveryNoteView(
            id=f"note-{delivery_id}",
            data_delivery_id=delivery_id,
            data_object_id="do-1",
            data_object_version_id=version_id,
            version=1,
            delivered_at="2026-04-25T12:00:00Z",
            timestamp="2026-04-25T12:00:00Z",
            layer="standardized",
            delivery_location=output_uri,
            delivery_status="completed",
            delivery_format=output_format,
            object_storage_classification=object_storage_classification,
            evidence_classification=evidence_classification,
            record_count=row_count,
        ),
    )


def test_require_test_data_materialization_record_rejects_invalid_payload() -> None:
    with pytest.raises(HTTPException) as error:
        support.require_test_data_materialization_record({"request_id": "incomplete"})

    assert error.value.status_code == 503
    assert error.value.detail["error"] == "invalid_test_data_materialization_record"


def test_expected_materialization_targets_prefers_selection_targets_and_normalizes() -> None:
    record = _record_with_selection(
        {
            "resolved": {
                "targets": [
                    {
                        "data_object_version_id": "dov-2",
                        "output_uri": "s3://bucket/target-two",
                        "output_format": "CSV",
                    },
                    {
                        "data_object_version_id": "",
                        "output_uri": "s3://bucket/ignored",
                        "output_format": "parquet",
                    },
                ]
            }
        }
    )

    targets = support.expected_materialization_targets_from_record(record)

    assert targets == [
        {
            "data_object_version_id": "dov-2",
            "output_uri": "s3a://bucket/target-two",
            "output_format": "csv",
        }
    ]


def test_expected_materialization_targets_falls_back_to_record_fields() -> None:
    record = _record_with_selection(None)

    targets = support.expected_materialization_targets_from_record(record)

    assert targets == [
        {
            "data_object_version_id": "dov-1",
            "output_uri": "s3a://bucket/default-output",
            "output_format": "parquet",
        }
    ]


def test_build_materialization_delivery_summary_aggregates_distinct_values() -> None:
    deliveries = [
        _delivery_view(
            version_id="dov-1",
            delivery_id="del-1",
            row_count=10,
            output_uri="s3a://bucket/a",
            output_format="parquet",
            object_storage_classification="synthetic_test",
            evidence_classification="synthetic_result",
        ),
        _delivery_view(
            version_id="dov-2",
            delivery_id="del-2",
            row_count=5,
            output_uri="s3a://bucket/b",
            output_format="csv",
            object_storage_classification="synthetic_test",
            evidence_classification="synthetic_result",
        ),
    ]

    summary = support.build_materialization_delivery_summary(deliveries=deliveries, reused_existing=True)

    assert summary["target_count"] == 2
    assert summary["data_delivery_count"] == 2
    assert summary["total_row_count"] == 15
    assert summary["reused_existing"] is True
    assert summary["data_delivery_ids"] == ["del-1", "del-2"]
    assert summary["output_formats"] == ["csv", "parquet"]
    assert summary["object_storage_classifications"] == ["synthetic_test"]
    assert summary["evidence_classifications"] == ["synthetic_result"]


def test_build_materialization_result_flattens_single_target_payload() -> None:
    delivery = _delivery_view(
        version_id="dov-1",
        delivery_id="del-1",
        row_count=7,
        output_uri="s3a://bucket/single",
        output_format="parquet",
        object_storage_classification="synthetic_test",
        evidence_classification="synthetic_result",
    )

    result = support.build_materialization_result_from_deliveries(
        deliveries=[delivery],
        request_output_uri="s3://bucket/request",
        output_format="PARQUET",
        reused_existing=False,
    )

    assert result["row_count"] == 7
    assert result["output_uri"] == "s3a://bucket/single"
    assert result["output_format"] == "parquet"
    assert result["data_delivery_id"] == "del-1"
    assert result["delivery_note"]["data_delivery_id"] == "del-1"
    assert result["target_results"][0]["data_delivery_id"] == "del-1"


@pytest.mark.anyio
async def test_redis_llen_prefers_async_client_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SimpleNamespace(llen=AsyncMock(return_value=4), aclose=AsyncMock())
    monkeypatch.setattr(support, "aioredis", SimpleNamespace(from_url=Mock(return_value=client)))

    length = await support.redis_llen("redis://queue", "queue:key")

    assert length == 4
    client.llen.assert_awaited_once_with("queue:key")
    client.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_redis_get_json_raises_fail_fast_when_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support, "aioredis", None)
    monkeypatch.setattr(support, "redis_sync", None)

    with pytest.raises(HTTPException) as error:
        await support.redis_get_json("redis://queue", "request:key")

    assert error.value.status_code == 503
    assert "Redis client is unavailable" in str(error.value.detail)