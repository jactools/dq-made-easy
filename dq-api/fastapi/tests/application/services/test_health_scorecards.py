from __future__ import annotations

import asyncio

from types import SimpleNamespace

import pytest

from app.application.services import health_scorecards as health_scorecards_service
from app.application.services.health_scorecards import HealthScorecardsQuery


@pytest.fixture
def health_scorecard_assets() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id="asset-1",
            name="Customer Health",
            workspace_id="ws-1",
            current_version_id="asset-1-v2",
            source_object_version_ids=["dov-1"],
            business_context=SimpleNamespace(domain="Customer", data_product_id="customer-platform"),
        ),
        SimpleNamespace(
            id="asset-2",
            name="Order Health",
            workspace_id="ws-1",
            current_version_id="asset-2-v1",
            source_object_version_ids=["dov-2"],
            business_context=SimpleNamespace(domain="Customer", data_product_id="order-platform"),
        ),
    ]


@pytest.fixture
def health_scorecard_rules() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(id="rule-1", name="Completeness Rule", dimension="Completeness"),
        SimpleNamespace(id="rule-2", name="Validity Rule", dimension="Validity"),
    ]


@pytest.fixture
def health_scorecard_incidents() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id="incident-1",
            title="Failed validation run",
            status="open",
            severity="high",
            incident_kind="technical_run_error",
            assigned_to="dq-support",
            run_id="run-a",
        ),
        SimpleNamespace(
            id="incident-2",
            title="Functional violation",
            status="in_progress",
            severity="medium",
            incident_kind="functional_violation",
            assigned_to="dq-team",
            run_plan_id="plan-1",
        ),
        SimpleNamespace(
            id="incident-3",
            title="Closed incident",
            status="resolved",
            severity="low",
            incident_kind="technical_run_error",
        ),
    ]


class _DataAssetRepository:
    def __init__(self, assets: list[SimpleNamespace]) -> None:
        self._assets = assets

    def list_data_assets(self, workspace_id: str | None = None) -> list[SimpleNamespace]:
        if workspace_id is None:
            return list(self._assets)
        return [asset for asset in self._assets if str(asset.workspace_id) == str(workspace_id)]

    def get_data_asset(self, asset_id: str):
        for asset in self._assets:
            if str(asset.id) == str(asset_id):
                return asset
        return None


class _RulesRepository:
    def __init__(self, rules: list[SimpleNamespace]) -> None:
        self._rules = rules

    async def list_rule_records(self, *, workspace=None, include_deleted=False, is_template=None, query=None, limit=200, offset=0):
        _ = workspace, include_deleted, is_template, query, offset
        return list(self._rules) if offset == 0 else []


class _ProjectionRepository:
    async def summarize_reason_analytics(
        self,
        *,
        data_object_version_ids,
        execution_run_ids,
        reason_codes=None,
        detected_after=None,
        detected_before=None,
        bucket_origin=None,
        bucket_size_seconds=None,
        bucket_count=None,
    ):
        _ = execution_run_ids, reason_codes, detected_after, detected_before, bucket_origin, bucket_size_seconds, bucket_count
        scope_ids = tuple(sorted(str(value) for value in data_object_version_ids if str(value).strip()))
        if scope_ids == ("dov-1",):
            return SimpleNamespace(
                total_failed_records=3,
                runs_with_failures=1,
                trend_totals=[
                    SimpleNamespace(bucket_start="2026-05-22T18:00:00+00:00", total=1),
                    SimpleNamespace(bucket_start="2026-05-22T19:00:00+00:00", total=2),
                ],
                rule_totals=[SimpleNamespace(rule_id="rule-1", total=3)],
                reason_totals=[SimpleNamespace(reason_code="missing_value", reason_text="Missing value", total=3)],
                reason_trend_totals=[
                    SimpleNamespace(bucket_start="2026-05-22T18:00:00+00:00", reason_code="missing_value", reason_text="Missing value", total=1),
                    SimpleNamespace(bucket_start="2026-05-22T19:00:00+00:00", reason_code="missing_value", reason_text="Missing value", total=2),
                ],
            )
        if scope_ids == ("dov-2",):
            return SimpleNamespace(
                total_failed_records=1,
                runs_with_failures=0,
                trend_totals=[
                    SimpleNamespace(bucket_start="2026-05-22T19:00:00+00:00", total=1),
                ],
                rule_totals=[SimpleNamespace(rule_id="rule-2", total=1)],
                reason_totals=[SimpleNamespace(reason_code="range_mismatch", reason_text="Range mismatch", total=1)],
                reason_trend_totals=[
                    SimpleNamespace(bucket_start="2026-05-22T19:00:00+00:00", reason_code="range_mismatch", reason_text="Range mismatch", total=1),
                ],
            )
        return SimpleNamespace(
            total_failed_records=4,
            runs_with_failures=1,
            trend_totals=[
                SimpleNamespace(bucket_start="2026-05-22T18:00:00+00:00", total=1),
                SimpleNamespace(bucket_start="2026-05-22T19:00:00+00:00", total=3),
            ],
            rule_totals=[
                SimpleNamespace(rule_id="rule-1", total=3),
                SimpleNamespace(rule_id="rule-2", total=1),
            ],
            reason_totals=[
                SimpleNamespace(reason_code="missing_value", reason_text="Missing value", total=3),
                SimpleNamespace(reason_code="range_mismatch", reason_text="Range mismatch", total=1),
            ],
            reason_trend_totals=[
                SimpleNamespace(bucket_start="2026-05-22T18:00:00+00:00", reason_code="missing_value", reason_text="Missing value", total=1),
                SimpleNamespace(bucket_start="2026-05-22T19:00:00+00:00", reason_code="missing_value", reason_text="Missing value", total=2),
                SimpleNamespace(bucket_start="2026-05-22T19:00:00+00:00", reason_code="range_mismatch", reason_text="Range mismatch", total=1),
            ],
        )


class _IncidentRepository:
    def __init__(self, incidents: list[SimpleNamespace]) -> None:
        self._incidents = incidents

    def list_incidents(
        self,
        *,
        workspace_id: str | None = None,
        incident_kind: str | None = None,
        status: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SimpleNamespace]:
        _ = incident_kind, run_id
        incidents = [incident for incident in self._incidents if workspace_id is None or getattr(incident, "workspace_id", None) in (None, workspace_id)]
        if status is not None:
            incidents = [incident for incident in incidents if str(getattr(incident, "status", "")) == str(status)]
        return incidents[offset : offset + limit]


class _NoopRepository:
    pass


@pytest.fixture
def health_scorecard_dependencies(health_scorecard_assets, health_scorecard_rules):
    return {
        "data_asset_repository": _DataAssetRepository(health_scorecard_assets),
        "rules_repository": _RulesRepository(health_scorecard_rules),
        "projection_repository": _ProjectionRepository(),
        "incident_repository": _IncidentRepository(
            [
                SimpleNamespace(
                    id="incident-1",
                    workspace_id="ws-1",
                    title="Failed validation run",
                    status="open",
                    severity="high",
                    incident_kind="technical_run_error",
                    assigned_to="dq-support",
                    run_id="run-a",
                ),
                SimpleNamespace(
                    id="incident-2",
                    workspace_id="ws-1",
                    title="Functional violation",
                    status="in_progress",
                    severity="medium",
                    incident_kind="functional_violation",
                    assigned_to="dq-team",
                    run_plan_id="plan-1",
                ),
                SimpleNamespace(
                    id="incident-3",
                    workspace_id="ws-1",
                    title="Closed incident",
                    status="resolved",
                    severity="low",
                    incident_kind="technical_run_error",
                ),
            ]
        ),
        "run_repository": _NoopRepository(),
        "run_plan_repository": _NoopRepository(),
        "data_catalog_repository": _NoopRepository(),
        "suite_repository": _NoopRepository(),
    }


@pytest.fixture(autouse=True)
def mock_run_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_list_gx_execution_run_summaries(*, query, repository, run_plan_repository, rules_repository, data_catalog_repository, suite_repository):
        _ = repository, run_plan_repository, rules_repository, data_catalog_repository, suite_repository
        scope_id = str(getattr(query, "data_object_version_id", None) or "")
        if scope_id == "dov-1":
            return [
                SimpleNamespace(id="run-a", status="succeeded"),
                SimpleNamespace(id="run-b", status="failed"),
            ]
        if scope_id == "dov-2":
            return [SimpleNamespace(id="run-c", status="running")]
        return []

    monkeypatch.setattr(health_scorecards_service, "list_gx_execution_run_summaries", _fake_list_gx_execution_run_summaries)


def test_get_health_scorecards_builds_workspace_and_asset_rollups(health_scorecard_dependencies) -> None:
    result = asyncio.run(health_scorecards_service.get_health_scorecards(
        query=HealthScorecardsQuery(workspace_id="ws-1", lookback_amount=24, lookback_unit="hours"),
        **health_scorecard_dependencies,
    ))

    assert result["workspace_id"] == "ws-1"
    assert result["data_asset_id"] is None
    assert len(result["scorecards"]) == 3

    workspace_card = result["scorecards"][0]
    asset_card = next(card for card in result["scorecards"] if card["data_asset_id"] == "asset-1")

    assert workspace_card["scope_type"] == "workspace"
    assert workspace_card["summary"] == "3 runs, 1 failed, 4 failed records"
    assert workspace_card["top_rules"][0]["rule_name"] == "Completeness Rule"
    assert workspace_card["dimension_rollups"][0]["dimension"] == "Completeness"
    assert len(result["workspace_summary"]["ownership_rollups"]) == 3
    domain_rollup = next(item for item in result["workspace_summary"]["ownership_rollups"] if item["scope_kind"] == "domain")
    assert domain_rollup["scope_name"] == "Customer"
    assert domain_rollup["asset_count"] == 2
    assert domain_rollup["tracked_data_object_version_count"] == 2
    assert domain_rollup["summary"] == "2 assets across 2 tracked source versions, 1 failed runs, 4 failed records"
    assert domain_rollup["health_label"] == "attention"
    assert len(workspace_card["trend_buckets"]) == 2
    assert workspace_card["trend_buckets"][1]["total"] == 3
    assert result["workspace_summary"]["overall_score"] == workspace_card["overall_score"]
    assert result["workspace_summary"]["top_regressions"][0]["delta"] == 2
    assert result["workspace_summary"]["active_incident_count"] == 2
    assert result["workspace_summary"]["active_incidents"][0]["title"] == "Failed validation run"
    assert result["workspace_summary"]["ownership_rollups"][0]["scope_kind"] in {"data_product", "domain"}
    assert asset_card["summary"] == "2 runs, 1 failed, 3 failed records"
    assert asset_card["data_asset_version_id"] == "asset-1-v2"
