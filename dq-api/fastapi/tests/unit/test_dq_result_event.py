from app.domain.entities import DqResultEventEntity
from app.domain.entities import build_dq_result_event_from_gx_execution_run
from app.domain.entities import build_dq_result_event_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_entity
from app.domain.entities.rule import RuleEntity


def test_build_dq_result_event_entity_serializes_canonical_contract() -> None:
    event = build_dq_result_event_entity(
        {
            "emitted_at": "2026-05-26T11:15:00Z",
            "severity": "critical",
            "dataset": {
                "id": "dataset-1",
                "name": "Customer health",
                "workspace_id": "ws-1",
                "data_product_id": "dp-1",
            },
            "domain": {
                "id": "domain-1",
                "name": "Customer",
            },
            "rule": {
                "id": "rule-1",
                "name": "Completeness",
                "workspace_id": "ws-1",
                "version_id": "rule-1-v2",
                "version_number": 2,
                "taxonomy": {
                    "type": "NULL_CHECK",
                    "severity": "critical",
                    "domain": "customer",
                    "owner": "user-1",
                    "sla_scope": "dataset",
                    "execution_target": "gx"
                },
            },
            "run_outcome": {
                "status": "failed",
                "result": "failed",
                "passed": False,
                "total_count": 100,
                "valid_count": 72,
                "invalid_count": 28,
                "warning_count": 3,
                "error_count": 4,
                "score": 72.0,
                "score_label": "quality_score",
                "duration_ms": 1200,
                "message": "Null-rate drift detected",
            },
            "score_dimensions": [
                {
                    "name": "completeness",
                    "value": 72.0,
                    "weight": 0.6,
                    "maximum": 100.0,
                    "normalized_value": 0.72,
                    "passed": False,
                },
                {
                    "name": "freshness",
                    "value": 91.0,
                    "weight": 0.4,
                    "maximum": 100.0,
                    "normalized_value": 0.91,
                    "passed": True,
                },
            ],
            "correlation": {
                "correlation_id": "corr-123",
                "run_id": "run-456",
                "request_id": "req-789",
                "queue_message_id": "msg-abc",
                "trace_id": "trace-def",
                "source_system": "dq-api",
            },
        }
    )

    assert isinstance(event, DqResultEventEntity)

    payload = event.model_dump(mode="python", by_alias=True, exclude_none=True)

    assert payload["event_type"] == "dq_result_event"
    assert payload["event_version"] == "1"
    assert payload["dataset"]["workspace_id"] == "ws-1"
    assert payload["rule"]["workspace_id"] == "ws-1"
    assert payload["rule"]["version_number"] == 2
    assert payload["rule"]["taxonomy"]["execution_target"] == "gx"
    assert payload["run_outcome"]["invalid_count"] == 28
    assert payload["score_dimensions"][0]["normalized_value"] == 0.72
    assert payload["correlation"]["correlation_id"] == "corr-123"


def test_build_dq_result_event_entity_rejects_incomplete_payload() -> None:
    assert build_dq_result_event_entity({"severity": "critical"}) is None


def test_build_dq_result_event_from_gx_execution_run_includes_rule_taxonomy_and_workspace() -> None:
    run = build_gx_execution_run_entity(
        {
            "id": "run-1",
            "rule_id": "rule-1",
            "rule_version_id": "rule-1-v3",
            "correlation_id": "corr-1",
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "status": "succeeded",
            "submitted_at": "2026-05-26T11:00:00Z",
            "completed_at": "2026-05-26T11:05:00Z",
            "result_summary": {"results": [{"ok": True}, {"ok": False}]},
        }
    )
    rule = RuleEntity.model_validate(
        {
            "id": "rule-1",
            "name": "Customer completeness",
            "description": None,
            "comments": None,
            "expression": "value IS NOT NULL",
            "dimension": "Completeness",
            "active": True,
            "workspace": "ws-1",
            "createdByUserId": "user-1",
            "tagIds": [],
            "checkType": "null_check",
            "dsl": {
                "rule": {
                    "scope": {"dataset": {"data_product_id": "product-1"}},
                    "operations": {"severity": "critical", "preferred_engines": ["gx"]},
                }
            },
            "taxonomy": {"owner": "user-1"},
        }
    )

    event = build_dq_result_event_from_gx_execution_run(run, rule=rule, report_body={"new_status": "succeeded"})

    assert event.dataset.workspaceId == "ws-1"
    assert event.rule.workspaceId == "ws-1"
    assert event.rule.taxonomy.owner == "user-1"
    assert event.rule.taxonomy.execution_target == "gx"