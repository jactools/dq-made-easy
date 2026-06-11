from __future__ import annotations

from datetime import UTC
from datetime import datetime
from types import SimpleNamespace

import pytest

import app.api.v1.validation_run_plan_api as validation_run_plan_api
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities import build_validation_run_plan_entity


class _ReplayRepository:
    def __init__(self, plan) -> None:
        self._plan = plan
        self.dispatch_calls: list[dict[str, object]] = []

    async def get_plan(self, run_plan_id: str):
        assert run_plan_id == self._plan.runPlanId
        return self._plan

    async def record_plan_dispatch(self, **kwargs):
        self.dispatch_calls.append(kwargs)
        return self._plan


def _validation_artifact_snapshot(*, suite_id: str, suite_version: int) -> dict[str, object]:
    return build_validation_artifact_envelope_from_gx_artifact(
        {
            "suiteId": suite_id,
            "suiteVersion": suite_version,
            "artifactVersion": "v1",
            "assignmentScope": {"dataObjectId": "do-1"},
            "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
            "gxSuite": {
                "expectation_suite_name": suite_id,
                "expectations": [
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": "customer_id"},
                    }
                ],
                "meta": {},
            },
            "compiledFrom": {
                "ruleIds": ["rule-1"],
                "compilerVersion": "dq-compiler-7.3",
                "generatedAt": "2026-04-10T08:00:00Z",
            },
            "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": ["id"]},
            "executionContract": {
                "engineType": "gx",
                "engineTarget": "pyspark",
                "executionShape": "single_object",
                "traceability": {"ruleId": "rule-1", "ruleVersionId": "rule-version-1"},
            },
        }
    ).model_dump(mode="python", by_alias=False, exclude_none=True)


@pytest.fixture
def single_suite_plan():
    return build_validation_run_plan_entity(
        {
            "runPlanId": "run-plan-1",
            "businessKey": "run-plan-1",
            "workspaceId": "retail-banking",
            "scopeSelector": {"workspaceId": "retail-banking"},
            "planningMode": "single_suite",
            "currentActiveVersionId": "run-plan-version-2",
            "status": "active",
            "createdBy": "user-admin",
            "createdAt": "2026-04-10T07:00:00Z",
            "updatedAt": "2026-04-10T08:00:00Z",
            "activatedBy": "user-admin",
            "activatedAt": "2026-04-10T08:00:00Z",
            "lastDispatchedRunId": None,
            "versions": [
                {
                    "runPlanVersionId": "run-plan-version-2",
                    "runPlanId": "run-plan-1",
                    "governanceState": "active",
                    "validationArtifactSelection": {
                        "selectionMode": "explicit_refs",
                        "artifactRefs": [
                            {"artifactId": "gx-suite-1", "artifactVersion": 1, "engineType": "gx"}
                        ],
                    },
                    "artifactId": "gx-suite-1",
                    "artifactVersion": 1,
                    "artifactSnapshot": _validation_artifact_snapshot(suite_id="gx-suite-1", suite_version=1),
                    "scheduleDefinition": {"scheduledAt": "2026-04-12T08:00:00Z"},
                    "createdAt": "2026-04-10T08:00:00Z",
                }
            ],
        }
    )


@pytest.fixture
def grouped_scope_plan():
    return build_validation_run_plan_entity(
        {
            "runPlanId": "run-plan-grouped",
            "businessKey": "run-plan-grouped",
            "workspaceId": "retail-banking",
            "scopeSelector": {"dataObjectVersionId": "dov-1", "workspaceId": "retail-banking"},
            "planningMode": "grouped_scope",
            "currentActiveVersionId": "run-plan-version-9",
            "status": "active",
            "createdBy": "user-admin",
            "createdAt": "2026-04-10T07:00:00Z",
            "updatedAt": "2026-04-10T08:00:00Z",
            "activatedBy": "user-admin",
            "activatedAt": "2026-04-10T08:00:00Z",
            "lastDispatchedRunId": None,
            "versions": [
                {
                    "runPlanVersionId": "run-plan-version-9",
                    "runPlanId": "run-plan-grouped",
                    "governanceState": "active",
                    "validationArtifactSelection": {
                        "selectionMode": "grouped_scope",
                        "scopeSelector": {"dataObjectVersionId": "dov-1", "workspaceId": "retail-banking"},
                        "artifactRefs": [{"artifactId": "gx-suite-1", "artifactVersion": 1, "engineType": "gx"}],
                        "groupedExecutionPlan": {"suiteCount": 1, "batchCount": 1},
                    },
                    "artifactId": None,
                    "artifactVersion": None,
                    "artifactSnapshot": {
                        "groupedExecutionPlan": {"suiteCount": 1, "batchCount": 1},
                        "artifactEnvelopes": [_validation_artifact_snapshot(suite_id="gx-suite-1", suite_version=1)],
                    },
                    "scheduleDefinition": {"scheduledAt": "2026-04-15T09:30:00Z"},
                    "createdAt": "2026-04-10T08:00:00Z",
                }
            ],
        }
    )


@pytest.mark.anyio
async def test_replay_run_plan_records_pipeline_trigger_for_single_suite(
    monkeypatch: pytest.MonkeyPatch,
    single_suite_plan,
) -> None:
    repository = _ReplayRepository(single_suite_plan)
    enqueue_calls: list[dict[str, object]] = []

    async def _enqueue_suite_run(**kwargs):
        enqueue_calls.append(kwargs)
        return SimpleNamespace(
            runId="run-123",
            queueMessageId="msg-123",
            suiteId="gx-suite-1",
            suiteVersion=1,
            engineType="gx",
            engineTarget="pyspark",
            executionShape="single_object",
            dispatchMode="queued",
            queueKey="dq-gx:execution-dispatch",
            scheduledAt="2026-04-16T10:15:00+00:00",
            correlationId="corr-123",
        )

    monkeypatch.setattr(
        validation_run_plan_api._gx_runtime_api,
        "bind_scheduled_suite_run_enqueue",
        lambda **_kwargs: _enqueue_suite_run,
    )

    result = await validation_run_plan_api.replay_run_plan(
        request=SimpleNamespace(headers={}),
        run_plan_id="run-plan-1",
        repository=repository,
        execution_run_repository=SimpleNamespace(),
        data_catalog_repository=SimpleNamespace(),
        requested_by="user-1",
        correlation_id="corr-123",
        trigger_type="pipeline_run",
        source_pipeline="airflow",
        scheduled_at=datetime(2026, 4, 16, 10, 15, tzinfo=UTC),
        settings_provider=lambda: None,
        async_redis_module=SimpleNamespace(),
        sync_redis_module=SimpleNamespace(),
        logger=SimpleNamespace(),
    )

    assert result.trigger_type == "pipeline_run"
    assert result.source_pipeline == "airflow"
    assert enqueue_calls[0]["status_source"] == "validation_run_plan.pipeline_run"
    assert enqueue_calls[0]["status_reason"] == "Validation plan pipeline-run trigger requested"
    assert repository.dispatch_calls[0]["dispatched_run_id"] == "run-123"
    assert repository.dispatch_calls[0]["details"] == {
        "trigger_type": "pipeline_run",
        "source_pipeline": "airflow",
        "selection_mode": "explicit_refs",
    }


@pytest.mark.anyio
async def test_replay_run_plan_uses_schedule_definition_for_grouped_scope(
    monkeypatch: pytest.MonkeyPatch,
    grouped_scope_plan,
) -> None:
    repository = _ReplayRepository(grouped_scope_plan)
    enqueue_calls: list[dict[str, object]] = []

    async def _enqueue_grouped_scope_run(**kwargs):
        enqueue_calls.append(kwargs)
        return SimpleNamespace(
            runId="run-grouped-1",
            queueMessageId="msg-grouped-1",
            suiteId=None,
            suiteVersion=None,
            engineType="gx",
            engineTarget="pyspark",
            executionShape="grouped_scope",
            dispatchMode="queued",
            queueKey="dq-gx:execution-dispatch",
            scheduledAt="2026-04-15T09:30:00+00:00",
            correlationId="corr-grouped-1",
        )

    monkeypatch.setattr(
        validation_run_plan_api._gx_runtime_api,
        "bind_grouped_scope_run_enqueue",
        lambda **_kwargs: _enqueue_grouped_scope_run,
    )

    result = await validation_run_plan_api.replay_run_plan(
        request=SimpleNamespace(headers={}),
        run_plan_id="run-plan-grouped",
        repository=repository,
        execution_run_repository=SimpleNamespace(),
        data_catalog_repository=SimpleNamespace(),
        requested_by="scheduler",
        correlation_id="corr-grouped-1",
        trigger_type="schedule",
        source_pipeline=None,
        scheduled_at=None,
        settings_provider=lambda: None,
        async_redis_module=SimpleNamespace(),
        sync_redis_module=SimpleNamespace(),
        logger=SimpleNamespace(),
    )

    assert result.trigger_type == "schedule"
    assert enqueue_calls[0]["status_source"] == "validation_run_plan.schedule"
    assert enqueue_calls[0]["status_reason"] == "Validation plan schedule trigger requested"
    assert enqueue_calls[0]["scheduled_at"].isoformat() == "2026-04-15T09:30:00+00:00"
    assert repository.dispatch_calls[0]["details"] == {
        "trigger_type": "schedule",
        "source_pipeline": None,
        "selection_mode": "grouped_scope",
    }