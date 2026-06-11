from __future__ import annotations

import pytest

from app.domain.entities.gx_execution_run import build_gx_execution_run_create_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_status_transition_entity
from app.infrastructure.repositories.in_memory_gx_execution_run_repository import InMemoryGxExecutionRunRepository


@pytest.mark.anyio
async def test_create_run_persists_pending_status_history() -> None:
    repo = InMemoryGxExecutionRunRepository()

    out = await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-1",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "rule_id": "rule_1",
                "rule_version_id": "rule_version_1",
                "correlation_id": "corr-1",
                "requested_by": "user-1",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "pending",
                "submitted_at": "2026-04-06T12:00:00+00:00",
                "execution_contract": {"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule_1", "ruleVersionId": "rule_version_1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 1}},
                "handoff_payload": {"runId": "run-1", "engineType": "gx", "run_plan_id": "run-plan-1", "run_plan_version_id": "run-plan-version-1"},
                "execution_progress": {"percent": 0, "label": "Queued for execution"},
                "status_reason": "accepted",
                "status_details": {"source": "gx.suite.run.start"},
            }
        )
    )
    payload = out.model_dump()

    assert payload["id"] == "run-1"
    assert payload["status"] == "pending"
    assert payload["executionProgress"]["percent"] == 0
    assert payload["handoffPayload"]["run_plan_id"] == "run-plan-1"
    assert payload["handoffPayload"]["run_plan_version_id"] == "run-plan-version-1"
    assert payload["statusHistory"][0]["toStatus"] == "pending"
    assert payload["statusHistory"][0]["details"]["source"] == "gx.suite.run.start"


@pytest.mark.anyio
async def test_record_run_status_transition_updates_lifecycle() -> None:
    repo = InMemoryGxExecutionRunRepository()

    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-2",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "rule_id": "rule_1",
                "rule_version_id": "rule_version_1",
                "correlation_id": "corr-2",
                "requested_by": "user-1",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "pending",
                "submitted_at": "2026-04-06T12:00:00+00:00",
                "execution_contract": {"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule_1", "ruleVersionId": "rule_version_1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 1}},
            }
        )
    )

    out = await repo.record_run_status_transition(
        build_gx_execution_run_status_transition_entity(
            {
                "run_id": "run-2",
                "new_status": "running",
                "changed_by": "worker-1",
                "reason": "picked up by executor",
            }
        )
    )
    payload = out.model_dump()

    assert payload["status"] == "running"
    assert payload["startedAt"] is not None
    assert len(payload["statusHistory"]) == 2
    assert payload["statusHistory"][1]["fromStatus"] == "pending"
    assert payload["statusHistory"][1]["toStatus"] == "running"


@pytest.mark.anyio
async def test_record_run_status_transition_updates_progress_without_history() -> None:
    repo = InMemoryGxExecutionRunRepository()

    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-3",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "rule_id": "rule_1",
                "rule_version_id": "rule_version_1",
                "correlation_id": "corr-3",
                "requested_by": "user-1",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "running",
                "submitted_at": "2026-04-06T12:00:00+00:00",
                "execution_contract": {"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule_1", "ruleVersionId": "rule_version_1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 1}},
            }
        )
    )

    out = await repo.record_run_status_transition(
        build_gx_execution_run_status_transition_entity(
            {
                "run_id": "run-3",
                "new_status": "running",
                "changed_by": "worker-1",
                "reason": "updated progress",
                "execution_progress": {"percent": 50, "label": "Halfway there"},
            }
        )
    )
    payload = out.model_dump()

    assert payload["status"] == "running"
    assert payload["executionProgress"]["percent"] == 50
    assert len(payload["statusHistory"]) == 1


@pytest.mark.anyio
async def test_record_run_status_transition_preserves_custom_result_summary_fields() -> None:
    repo = InMemoryGxExecutionRunRepository()

    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-4",
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "rule_id": "rule_1",
                "rule_version_id": "rule_version_1",
                "correlation_id": "corr-4",
                "requested_by": "user-1",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "join_pair",
                "status": "pending",
                "submitted_at": "2026-04-06T12:00:00+00:00",
                "execution_contract": {"engineType": "gx", "engineTarget": "pyspark", "executionShape": "join_pair", "traceability": {"ruleId": "rule_1", "ruleVersionId": "rule_version_1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 1}},
            }
        )
    )

    out = await repo.record_run_status_transition(
        build_gx_execution_run_status_transition_entity(
            {
                "run_id": "run-4",
                "new_status": "succeeded",
                "changed_by": "worker-1",
                "reason": "reconciliation completed",
                "result_summary": {
                    "results": [],
                    "match_rate": 99.5,
                    "sample_mismatches": [],
                    "custom_label": "reconciliation-preview",
                },
            }
        )
    )
    payload = out.model_dump()

    assert payload["status"] == "succeeded"
    assert payload["resultSummary"]["match_rate"] == 99.5
    assert payload["resultSummary"]["custom_label"] == "reconciliation-preview"


@pytest.mark.anyio
async def test_record_run_status_transition_rejects_missing_run() -> None:
    repo = InMemoryGxExecutionRunRepository()

    with pytest.raises(ValueError):
        await repo.record_run_status_transition(
            build_gx_execution_run_status_transition_entity(
                {
                    "run_id": "missing",
                    "new_status": "running",
                }
            )
        )


@pytest.mark.anyio
async def test_list_runs_accepts_artifact_alias_filters() -> None:
    repo = InMemoryGxExecutionRunRepository()

    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-artifact-1",
                "suite_id": "artifact-suite-1",
                "suite_version": 1,
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "correlation_id": "corr-artifact-1",
                "requested_by": "user-1",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "running",
                "submitted_at": "2026-04-06T12:00:00+00:00",
                "execution_contract": {"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule-1", "ruleVersionId": "rule-version-1", "gxSuiteId": "artifact-suite-1", "gxSuiteVersion": 1}},
            }
        )
    )
    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-artifact-2",
                "suite_id": "artifact-suite-2",
                "suite_version": 1,
                "rule_id": "rule-2",
                "rule_version_id": "rule-version-2",
                "correlation_id": "corr-artifact-2",
                "requested_by": "user-2",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "pending",
                "submitted_at": "2026-04-06T13:00:00+00:00",
                "execution_contract": {"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule-2", "ruleVersionId": "rule-version-2", "gxSuiteId": "artifact-suite-2", "gxSuiteVersion": 1}},
            }
        )
    )

    rows = await repo.list_runs({"artifact_id": "artifact-suite-1", "status": "running"})

    assert [item.id for item in rows] == ["run-artifact-1"]


@pytest.mark.anyio
async def test_list_runs_accepts_validation_artifact_alias_filters() -> None:
    repo = InMemoryGxExecutionRunRepository()

    await repo.create_run(
        build_gx_execution_run_create_entity(
            {
                "run_id": "run-validation-1",
                "suite_id": "validation-suite-1",
                "suite_version": 2,
                "rule_id": "rule-9",
                "rule_version_id": "rule-version-9",
                "correlation_id": "corr-validation-1",
                "requested_by": "user-9",
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "status": "failed",
                "submitted_at": "2026-04-06T14:00:00+00:00",
                "execution_contract": {"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule-9", "ruleVersionId": "rule-version-9", "gxSuiteId": "validation-suite-1", "gxSuiteVersion": 2}},
            }
        )
    )

    rows = await repo.list_runs({"validation_artifact_id": "validation-suite-1", "status": "failed"})

    assert [item.id for item in rows] == ["run-validation-1"]
