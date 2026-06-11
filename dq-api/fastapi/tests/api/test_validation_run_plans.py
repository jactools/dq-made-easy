from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.v1.endpoints.validation_run_plans as validation_run_plans_endpoints
from app.api.v1.endpoints.validation_run_plans import replay_validation_run_plan
from app.api.v1.endpoints.validation_run_plans import list_validation_run_plans
import app.api.v1.validation_run_plan_api as validation_run_plan_api
from app.domain.entities import build_validation_run_plan_entity


class _Repo:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    async def list_plans(self, **kwargs):
        self.last_kwargs = kwargs
        return [
            build_validation_run_plan_entity(
                {
                    "runPlanId": "run-plan-1",
                    "businessKey": "run-plan-1",
                    "workspaceId": "retail-banking",
                    "scopeSelector": {"workspaceId": "retail-banking", "tagIds": ["gold", "regulatory"]},
                    "planningMode": "single_suite",
                    "currentActiveVersionId": "run-plan-version-2",
                    "status": "active",
                    "pendingVersionId": None,
                    "pendingVersionGovernanceState": None,
                    "createdBy": "user-admin",
                    "createdAt": "2026-04-10T07:00:00Z",
                    "updatedAt": "2026-04-10T08:00:00Z",
                    "activatedBy": "user-admin",
                    "activatedAt": "2026-04-10T08:00:00Z",
                    "lastDispatchedRunId": "run-1",
                    "versions": [
                        {
                            "runPlanVersionId": "run-plan-version-2",
                            "runPlanId": "run-plan-1",
                            "governanceState": "active",
                            "gxSuiteSelection": {},
                            "suiteId": "gx-suite-1",
                            "suiteVersion": 1,
                            "suiteSnapshot": {
                                "suiteId": "gx-suite-1",
                                "suiteVersion": 1,
                            },
                            "scheduleDefinition": {"scheduledAt": "2026-04-12T08:00:00Z"},
                            "createdAt": "2026-04-10T08:00:00Z",
                        }
                    ],
                }
            )
        ]


@pytest.mark.anyio
async def test_list_run_plans_returns_validation_summary_without_gx_snapshot_validation() -> None:
    repo = _Repo()

    result = await list_validation_run_plans(
        workspace_id="retail-banking",
        business_key=None,
        suite_id=None,
        status=None,
        repository=repo,
    )

    assert repo.last_kwargs == {
        "workspace_id": "retail-banking",
        "business_key": None,
        "status": None,
        "artifact_id": None,
    }
    assert len(result) == 1
    assert result[0].runPlanId == "run-plan-1"
    assert result[0].scopeSelector.tagIds == ["gold", "regulatory"]
    assert result[0].versions[0].runPlanVersionId == "run-plan-version-2"
    assert result[0].versions[0].scheduleDefinition.scheduledAt == "2026-04-12T08:00:00Z"


@pytest.mark.anyio
async def test_replay_validation_run_plan_returns_view(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatch = SimpleNamespace(
        runId="run-1",
        queueMessageId="queue-1",
        suiteId="suite-1",
        suiteVersion=2,
        engineType="gx",
        engineTarget="pyspark",
        executionShape="single_object",
        dispatchMode="manual",
        queueKey="queue-key",
        scheduledAt="2026-04-26T10:30:00Z",
        correlationId="corr-1",
    )
    replay_result = SimpleNamespace(
        dispatch=dispatch,
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-2",
        workspace_id="retail-banking",
        trigger_type="pipeline_run",
        source_pipeline="airflow",
        selection_mode="explicit_refs",
    )
    calls: dict[str, object] = {}
    approvals_events: list[dict[str, object]] = []

    async def _fake_replay_run_plan(**kwargs):
        calls.update(kwargs)
        return replay_result

    monkeypatch.setattr(validation_run_plan_api, "replay_run_plan", _fake_replay_run_plan)
    monkeypatch.setattr(validation_run_plans_endpoints, "get_user_id", lambda: "user-1")
    monkeypatch.setattr(validation_run_plans_endpoints, "get_correlation_id", lambda: "corr-1")
    approvals_repository = SimpleNamespace(append_audit_event=lambda **kwargs: approvals_events.append(kwargs))

    result = await replay_validation_run_plan(
        request=SimpleNamespace(),
        run_plan_id="run-plan-1",
        payload=SimpleNamespace(triggerType="pipeline_run", sourcePipeline="airflow", scheduledAt=None),
        repository=SimpleNamespace(),
        execution_run_repository=SimpleNamespace(),
        data_catalog_repository=SimpleNamespace(),
        approvals_repository=approvals_repository,
    )

    assert calls["run_plan_id"] == "run-plan-1"
    assert calls["requested_by"] == "user-1"
    assert calls["correlation_id"] == "corr-1"
    assert calls["trigger_type"] == "pipeline_run"
    assert calls["source_pipeline"] == "airflow"
    assert calls["repository"] is not None
    assert approvals_events[0]["action"] == "validation_run_plan.replayed"
    assert approvals_events[0]["details"]["workspace_id"] == "retail-banking"
    assert approvals_events[0]["details"]["trigger_type"] == "pipeline_run"
    assert approvals_events[0]["details"]["source_pipeline"] == "airflow"
    assert result.runId == "run-1"
    assert result.queueMessageId == "queue-1"
    assert result.runPlanId == "run-plan-1"
    assert result.triggerType == "pipeline_run"
    assert result.sourcePipeline == "airflow"


@pytest.mark.anyio
async def test_replay_validation_run_plan_rejects_missing_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_replay_run_plan(**_kwargs):
        return SimpleNamespace(
            dispatch=None,
            run_plan_id="run-plan-1",
            run_plan_version_id="run-plan-version-2",
            workspace_id="retail-banking",
            selection_mode="explicit_refs",
        )

    monkeypatch.setattr(validation_run_plan_api, "replay_run_plan", _fake_replay_run_plan)
    monkeypatch.setattr(validation_run_plans_endpoints, "get_user_id", lambda: "user-1")
    monkeypatch.setattr(validation_run_plans_endpoints, "get_correlation_id", lambda: "corr-1")
    approvals_repository = SimpleNamespace(append_audit_event=lambda **_kwargs: None)

    with pytest.raises(HTTPException, match="Validation plan replay did not return a dispatch payload") as exc_info:
        await replay_validation_run_plan(
            request=SimpleNamespace(),
            run_plan_id="run-plan-1",
            repository=SimpleNamespace(),
            execution_run_repository=SimpleNamespace(),
            data_catalog_repository=SimpleNamespace(),
            approvals_repository=approvals_repository,
        )

    assert exc_info.value.status_code == 500


@pytest.mark.anyio
async def test_replay_run_plan_returns_404_when_no_active_version(monkeypatch: pytest.MonkeyPatch) -> None:
    class Repo:
        async def get_plan(self, run_plan_id: str):
            return build_validation_run_plan_entity(
                {
                    "runPlanId": run_plan_id,
                    "businessKey": run_plan_id,
                    "workspaceId": "retail-banking",
                    "scopeSelector": {"workspaceId": "retail-banking"},
                    "planningMode": "single_suite",
                    "currentActiveVersionId": None,
                    "status": "active",
                    "versions": [],
                }
            )

    with pytest.raises(HTTPException) as error:
        await validation_run_plan_api.replay_run_plan(
            request=SimpleNamespace(),
            run_plan_id="run-plan-1",
            repository=Repo(),
            execution_run_repository=SimpleNamespace(),
            data_catalog_repository=SimpleNamespace(),
            requested_by="user-1",
            correlation_id="corr-1",
            settings_provider=lambda: SimpleNamespace(),
            async_redis_module=SimpleNamespace(),
            sync_redis_module=SimpleNamespace(),
            logger=SimpleNamespace(),
        )

    assert error.value.status_code == 404
    assert error.value.detail["error"] == "no_active_version"
    assert error.value.detail["run_plan_id"] == "run-plan-1"
