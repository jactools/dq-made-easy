from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import run_plan as run_plan_endpoints
from app.domain.entities import build_validation_run_plan_entity


class _CatalogRepo:
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
                    "scopeSelector": {"workspaceId": "retail-banking"},
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
                    "lastDispatchedRunId": None,
                    "versions": [
                        {
                            "runPlanVersionId": "run-plan-version-1",
                            "runPlanId": "run-plan-1",
                            "governanceState": "draft",
                            "artifactId": "suite-1",
                            "artifactVersion": 1,
                            "artifactSnapshot": {"engineType": "gx"},
                            "scheduleDefinition": {"scheduledAt": "2026-04-12T08:00:00Z"},
                            "createdAt": "2026-04-10T08:00:00Z",
                        },
                        {
                            "runPlanVersionId": "run-plan-version-2",
                            "runPlanId": "run-plan-1",
                            "governanceState": "active",
                            "artifactId": "suite-2",
                            "artifactVersion": 2,
                            "artifactSnapshot": {"engineType": "soda"},
                            "scheduleDefinition": {"scheduledAt": "2026-04-13T08:00:00Z"},
                            "createdAt": "2026-04-10T09:00:00Z",
                        },
                    ],
                    "transitionEvents": [],
                }
            )
        ]


@pytest.mark.anyio
async def test_run_plan_returns_engine_neutral_catalog() -> None:
    repository = _CatalogRepo()

    result = await run_plan_endpoints.list_run_plans(
        workspace_id="retail-banking",
        business_key=None,
        suite_id=None,
        status=None,
        repository=repository,
    )

    assert repository.last_kwargs == {
        "workspace_id": "retail-banking",
        "business_key": None,
        "status": None,
        "artifact_id": None,
    }
    assert len(result.validationRunPlans) == 1
    assert result.validationRunPlans[0].runPlanId == "run-plan-1"
    assert len(result.validationSuites) == 2
    assert result.validationSummary.runPlanCount == 1
    assert result.validationSummary.suiteCount == 2
    assert result.validationSummary.engineTypes == ["gx", "soda"]