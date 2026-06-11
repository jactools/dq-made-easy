from __future__ import annotations

import pytest

from app.main import app
from app.api.v1.endpoints import health_scorecards as health_scorecards_endpoint
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_exception_reason_analytics_projection_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_gx_run_plan_repository
from app.core.dependencies import get_gx_suite_repository
from app.core.dependencies import get_incident_repository
from app.core.dependencies import get_rules_repository


@pytest.fixture(autouse=True)
def _override_health_scorecard_dependencies():
    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_data_asset_repository] = lambda: object()
    app.dependency_overrides[get_gx_execution_run_repository] = lambda: object()
    app.dependency_overrides[get_gx_run_plan_repository] = lambda: object()
    app.dependency_overrides[get_rules_repository] = lambda: object()
    app.dependency_overrides[get_data_catalog_repository] = lambda: object()
    app.dependency_overrides[get_gx_suite_repository] = lambda: object()
    app.dependency_overrides[get_exception_reason_analytics_projection_repository] = lambda: object()
    app.dependency_overrides[get_incident_repository] = lambda: object()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


@pytest.fixture(autouse=True)
def _mock_health_scorecard_service(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_health_scorecards(**_kwargs):
        return {
            "workspace_id": "ws-1",
            "data_asset_id": None,
            "lookback_amount": 24,
            "lookback_unit": "hours",
            "generated_at": "2026-05-22T20:00:00Z",
            "workspace_summary": {
                "workspace_id": "ws-1",
                "generated_at": "2026-05-22T20:00:00Z",
                "overall_score": 92,
                "health_label": "healthy",
                "summary": "Workspace quality remains healthy",
                "top_regressions": [
                    {
                        "bucket_start": "2026-05-22T19:00:00Z",
                        "previous_bucket_start": "2026-05-22T18:00:00Z",
                        "previous_total": 1,
                        "current_total": 3,
                        "delta": 2,
                    }
                ],
                "top_rules": [
                    {
                        "rule_id": "rule-1",
                        "rule_name": "Completeness Rule",
                        "dimension": "Completeness",
                        "total": 3,
                    }
                ],
                "ownership_rollups": [
                    {
                        "scope_kind": "domain",
                        "scope_id": "Customer",
                        "scope_name": "Customer",
                        "asset_count": 2,
                        "tracked_data_object_version_count": 2,
                        "total_runs": 3,
                        "pending_runs": 0,
                        "running_runs": 1,
                        "succeeded_runs": 1,
                        "failed_runs": 1,
                        "cancelled_runs": 0,
                        "total_failed_records": 4,
                        "runs_with_failures": 1,
                        "overall_score": 92,
                        "health_label": "healthy",
                        "summary": "2 assets across 2 tracked source versions, 1 failed runs, 4 failed records",
                    }
                ],
                "active_incident_count": 1,
                "active_incidents": [
                    {
                        "incident_id": "incident-1",
                        "title": "Failed validation run",
                        "status": "open",
                        "severity": "high",
                        "incident_kind": "technical_run_error",
                        "assigned_to": "dq-support",
                        "run_id": "run-a",
                        "run_plan_id": None,
                    }
                ],
            },
            "scorecards": [
                {
                    "scope_type": "workspace",
                    "scope_id": "ws-1",
                    "scope_name": "Workspace ws-1",
                    "workspace_id": "ws-1",
                    "lookback_amount": 24,
                    "lookback_unit": "hours",
                    "generated_at": "2026-05-22T20:00:00Z",
                    "overall_score": 92,
                    "health_label": "healthy",
                    "summary": "3 runs, 1 failed, 4 failed records",
                    "total_runs": 3,
                    "pending_runs": 0,
                    "running_runs": 1,
                    "succeeded_runs": 1,
                    "failed_runs": 1,
                    "cancelled_runs": 0,
                    "total_failed_records": 4,
                    "runs_with_failures": 1,
                    "dimension_rollups": [],
                    "top_rules": [],
                    "top_reasons": [],
                    "trend_buckets": [],
                    "reason_trend_buckets": [],
                }
            ],
        }

    monkeypatch.setattr(health_scorecards_endpoint, "get_health_scorecards", _fake_get_health_scorecards)


def test_health_scorecards_endpoint_returns_workspace_summary(client, auth_headers) -> None:
    response = client.get(
        "/rulebuilder/v1/observability/health-scorecards?workspaceId=ws-1",
        headers=auth_headers("dq:reports:*", "dq:*"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws-1"
    assert payload["workspace_summary"]["overall_score"] == 92
    assert payload["workspace_summary"]["top_regressions"][0]["delta"] == 2
    assert payload["workspace_summary"]["active_incident_count"] == 1
    assert payload["workspace_summary"]["active_incidents"][0]["title"] == "Failed validation run"
    assert payload["workspace_summary"]["ownership_rollups"][0]["scope_kind"] == "domain"
    assert payload["scorecards"][0]["summary"] == "3 runs, 1 failed, 4 failed records"
