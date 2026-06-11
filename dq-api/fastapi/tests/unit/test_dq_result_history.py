from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.api.v1.gx_report_api import report_execution_run
from app.domain.entities import build_dq_result_event_entity
from app.domain.entities import build_gx_artifact_envelope_entity
from app.domain.entities import build_gx_execution_run_create_entity
from app.domain.entities.rule import RuleEntity
from app.infrastructure.repositories.in_memory_dq_result_event_repository import InMemoryDqResultEventRepository
from app.infrastructure.repositories.postgres_dq_result_event_repository import PostgresDqResultEventRepository
from app.infrastructure.repositories.in_memory_gx_execution_run_repository import InMemoryGxExecutionRunRepository
from app.infrastructure.repositories.in_memory_gx_suite_repository import InMemoryGxSuiteRepository


pytestmark = pytest.mark.anyio


def _suite_envelope() -> dict:
    return {
        "suiteId": "suite-1",
        "suiteVersion": 1,
        "artifactVersion": "v1",
        "assignmentScope": {
            "dataObjectId": "obj-1",
            "datasetId": "dataset-1",
            "dataProductId": "product-1",
        },
        "resolvedExecutionScope": {
            "dataObjectVersionIds": ["dov-1"],
        },
        "gxSuite": {
            "expectation_suite_name": "suite-1_v1",
            "expectations": [],
            "meta": {"domain": "finance"},
        },
        "compiledFrom": {
            "ruleIds": ["rule-1"],
            "compilerVersion": "dq-compiler-7.3",
            "generatedAt": "2026-05-26T11:00:00Z",
        },
        "executionContract": {
            "engineType": "gx",
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "traceability": {
                "ruleId": "rule-1",
                "ruleVersionId": "rule-1-v1",
                "gxSuiteId": "suite-1",
                "gxSuiteVersion": 1,
            },
        },
    }


def _result_event_payload() -> dict:
    return {
        "emitted_at": "2026-05-26T11:15:00Z",
        "severity": "critical",
        "dataset": {
            "id": "dataset-1",
            "name": "Customer health",
            "data_product_id": "product-1",
        },
        "domain": {
            "id": "finance",
            "name": "finance",
        },
        "rule": {
            "id": "rule-1",
            "name": "Completeness",
            "version_id": "rule-1-v1",
            "version_number": 1,
        },
        "run_outcome": {
            "status": "failed",
            "result": "failed",
            "passed": False,
            "total_count": 2,
            "valid_count": 1,
            "invalid_count": 1,
            "warning_count": 0,
            "error_count": 1,
            "score": 50,
            "score_label": "quality_score",
            "observed_at": "2026-05-26T11:15:00Z",
            "duration_ms": 1200,
            "message": "Null-rate drift detected",
        },
        "score_dimensions": [
            {
                "name": "quality_score",
                "value": 50,
                "maximum": 100,
                "normalized_value": 0.5,
                "passed": False,
            }
        ],
        "correlation": {
            "correlation_id": "corr-123",
            "run_id": "run-123",
            "request_id": "req-789",
            "queue_message_id": "msg-abc",
            "trace_id": "trace-def",
            "source_system": "dq-api",
        },
    }


async def test_dq_result_event_repository_is_idempotent_and_filterable() -> None:
    repository = InMemoryDqResultEventRepository()
    event = build_dq_result_event_entity(_result_event_payload())
    assert event is not None

    recorded = await repository.record_result_event(event)
    duplicate = await repository.record_result_event(event)

    assert recorded.model_dump(by_alias=True, exclude_none=True) == duplicate.model_dump(by_alias=True, exclude_none=True)

    filtered = await repository.list_result_events(rule_id="rule-1", dataset_id="dataset-1", data_product_id="product-1")
    assert len(filtered) == 1
    assert filtered[0].runOutcome.status == "failed"
    assert filtered[0].dataset.id == "dataset-1"


async def test_report_execution_run_persists_terminal_result_event() -> None:
    suite_repository = InMemoryGxSuiteRepository()
    execution_run_repository = InMemoryGxExecutionRunRepository()
    event_repository = InMemoryDqResultEventRepository()
    rule = RuleEntity.model_validate(
        {
            "id": "rule-1",
            "name": "Completeness",
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

    class _RulesRepository:
        async def get_rule_by_id(self, rule_id: str) -> RuleEntity | None:
            if rule_id == rule.id:
                return rule
            return None

    rules_repository = _RulesRepository()

    suite = await suite_repository.save_suite(
        envelope=build_gx_artifact_envelope_entity(_suite_envelope()),
        status="active",
    )
    created_run = await execution_run_repository.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-123",
                "suite_id": suite.suiteId,
                "suite_version": suite.suiteVersion,
                "rule_id": "rule-1",
                "rule_version_id": "rule-1-v1",
                "correlation_id": "corr-123",
                "requested_by": "user-1",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "pending",
                "submitted_at": "2026-05-26T11:00:00Z",
                "execution_contract": suite.executionContract.model_dump(by_alias=True, exclude_none=True),
            }
        )
    )

    body = SimpleNamespace(
        newStatus="succeeded",
        changedBy="worker-1",
        reason="completed",
        details={"request_id": "req-1"},
        executionProgress=None,
        startedAt="2026-05-26T11:01:00Z",
        completedAt="2026-05-26T11:15:00Z",
        resultSummary={"results": [{"ok": True}, {"ok": False}]},
        diagnostics=None,
        failureCode=None,
        failureMessage=None,
    )

    updated = await report_execution_run(
        run_id=created_run.id,
        body=body,
        repository=execution_run_repository,
        suite_repository=suite_repository,
        rules_repository=rules_repository,
        dq_result_event_repository=event_repository,
        violation_repository=SimpleNamespace(),
        projection_repository=None,
        settings_provider=lambda: None,
        exception_storage_builder=lambda *args, **kwargs: None,
    )

    assert updated.status == "succeeded"

    events = await event_repository.list_result_events(rule_id="rule-1", dataset_id="dataset-1", data_product_id="product-1")
    assert len(events) == 1
    event = events[0]
    assert event.correlation.runId == "run-123"
    assert event.runOutcome.totalCount == 2
    assert event.runOutcome.validCount == 1
    assert event.runOutcome.invalidCount == 1
    assert event.runOutcome.score == 50
    assert event.dataset.id == "dataset-1"
    assert event.dataset.workspaceId == "ws-1"
    assert event.dataset.dataProductId == "product-1"
    assert event.rule.workspaceId == "ws-1"
    assert event.rule.taxonomy.owner == "user-1"
    assert event.rule.taxonomy.execution_target == "gx"


async def test_postgres_dq_result_event_repository_filters_by_dataset_data_product_id(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresDqResultEventRepository("postgresql://example")
    executed_statements: list[str] = []

    class _ScalarResult:
        def all(self) -> list[object]:
            return []

    class _ExecuteResult:
        def scalars(self) -> _ScalarResult:
            return _ScalarResult()

    class _Session:
        def execute(self, statement: object) -> _ExecuteResult:
            executed_statements.append(str(statement))
            return _ExecuteResult()

    @contextmanager
    def _session_scope(_: str):
        yield _Session()

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_dq_result_event_repository.session_scope",
        _session_scope,
    )

    events = await repository.list_result_events(data_product_id="product-1")

    assert events == []
    assert executed_statements
    assert "dataset_data_product_id" in executed_statements[0]
    assert "data_product_id" not in executed_statements[0] or "dataset_data_product_id" in executed_statements[0]
