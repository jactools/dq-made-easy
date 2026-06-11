from __future__ import annotations

import pytest

from app.api.v1.execution_browse_api import get_result_history_drift_summary
from app.domain.entities import build_dq_result_event_entity
from app.infrastructure.repositories.in_memory_dq_result_event_repository import InMemoryDqResultEventRepository


pytestmark = pytest.mark.anyio


def _event_payload(*, run_id: str, emitted_at: str, total_count: int, invalid_count: int, completeness: float, distribution_score: float, extra_dimensions: list[dict[str, object]] | None = None) -> dict:
    score_dimensions = [
        {
            "name": "completeness",
            "value": completeness,
            "maximum": 100,
            "normalized_value": completeness / 100,
            "passed": completeness >= 90,
        },
        {
            "name": "distribution_score",
            "value": distribution_score,
            "maximum": 100,
            "normalized_value": distribution_score / 100,
            "passed": distribution_score >= 70,
        },
    ]
    if extra_dimensions:
        score_dimensions.extend(extra_dimensions)

    return {
        "emitted_at": emitted_at,
        "severity": "critical",
        "dataset": {
            "id": "dataset-1",
            "name": "Customer health",
            "data_product_id": "product-1",
        },
        "domain": {
            "id": "domain-1",
            "name": "Finance",
        },
        "rule": {
            "id": "rule-1",
            "name": "Completeness",
            "version_id": "rule-1-v1",
            "version_number": 1,
        },
        "run_outcome": {
            "status": "succeeded",
            "result": "succeeded",
            "passed": True,
            "total_count": total_count,
            "valid_count": total_count - invalid_count,
            "invalid_count": invalid_count,
            "warning_count": 0,
            "error_count": invalid_count,
            "score": completeness,
            "score_label": "quality_score",
            "observed_at": emitted_at,
            "duration_ms": 1200,
            "message": "Result captured",
        },
        "score_dimensions": score_dimensions,
        "correlation": {
            "correlation_id": f"corr-{run_id}",
            "run_id": run_id,
            "request_id": f"req-{run_id}",
            "queue_message_id": f"msg-{run_id}",
            "trace_id": f"trace-{run_id}",
            "source_system": "dq-api",
        },
    }


async def test_result_history_drift_summary_detects_terminal_history_changes() -> None:
    repository = InMemoryDqResultEventRepository()

    for payload in (
        _event_payload(run_id="run-1", emitted_at="2026-05-26T10:00:00Z", total_count=100, invalid_count=5, completeness=95, distribution_score=82),
        _event_payload(run_id="run-2", emitted_at="2026-05-26T11:00:00Z", total_count=102, invalid_count=6, completeness=94, distribution_score=80),
        _event_payload(
            run_id="run-3",
            emitted_at="2026-05-26T12:00:00Z",
            total_count=160,
            invalid_count=20,
            completeness=80,
            distribution_score=55,
            extra_dimensions=[
                {
                    "name": "schema_drift",
                    "value": 1,
                    "maximum": 1,
                    "normalized_value": 1,
                    "passed": False,
                }
            ],
        ),
    ):
        event = build_dq_result_event_entity(payload)
        assert event is not None
        await repository.record_result_event(event)

    summary = await get_result_history_drift_summary(
        correlation_id="corr-test",
        lookback_amount=24,
        lookback_unit="hours",
        status=None,
        rule_id=None,
        dataset_id=None,
        domain_id=None,
        data_product_id=None,
        repository=repository,
    )

    payload = summary.model_dump(mode="python", by_alias=True, exclude_none=True)

    assert payload["total_events"] == 3
    assert payload["scoped_groups"] == 1
    assert payload["total_detections"] == 4
    assert payload["detections_by_type"]["schema_change"] == 1
    assert payload["detections_by_type"]["null_rate_shift"] == 1
    assert payload["detections_by_type"]["distribution_change"] == 1
    assert payload["detections_by_type"]["volume_anomaly"] == 1

    detection_types = {row["detector_type"] for row in payload["drifts"]}
    assert detection_types == {"schema_change", "null_rate_shift", "distribution_change", "volume_anomaly"}
    assert all(row["scope"]["rule_id"] == "rule-1" for row in payload["drifts"])
    assert all(row["scope"]["dataset_id"] == "dataset-1" for row in payload["drifts"])
