from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from app.application.use_cases.execution_queries import ListGxExecutionRunsQuery
from app.application.use_cases.execution_queries import list_gx_execution_run_summaries
from app.domain.entities.incident import INCIDENT_STATUS_IN_PROGRESS
from app.domain.entities.incident import INCIDENT_STATUS_OPEN
from app.domain.interfaces import DataAssetRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import GxRunPlanRepository
from app.domain.interfaces import GxSuiteRepository
from app.domain.interfaces import IncidentRepository
from app.domain.interfaces import RulesRepository
from dq_domain_validation import LookbackUnit


@dataclass(slots=True)
class HealthScorecardsQuery:
    workspace_id: str | None = None
    data_asset_id: str | None = None
    lookback_amount: int = 24
    lookback_unit: LookbackUnit = "hours"


@dataclass(slots=True)
class _RunScope:
    scope_type: str
    scope_id: str
    scope_name: str
    data_asset_id: str | None
    data_asset_name: str | None
    data_asset_version_id: str | None
    tracked_data_object_version_ids: list[str]


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _health_label(score: int) -> str:
    if score >= 90:
        return "healthy"
    if score >= 70:
        return "watch"
    return "attention"


def _score_from_runs(total_runs: int, succeeded_runs: int, running_runs: int, failed_runs: int, cancelled_runs: int, total_failed_records: int, runs_with_failures: int) -> int:
    if total_runs <= 0:
        return 100

    completion_score = ((succeeded_runs + (running_runs * 0.5)) / total_runs) * 100
    failure_ratio = runs_with_failures / total_runs
    record_pressure = min(1.0, total_failed_records / max(total_runs * 10, 1))
    interruption_pressure = cancelled_runs / total_runs
    penalty = (failure_ratio * 45) + (record_pressure * 35) + (interruption_pressure * 20)
    score = round(max(0.0, min(100.0, completion_score - penalty + 5)))
    return int(score)


def _dimension_score(total_failed_records: int, failed_record_total: int, rule_count: int) -> int:
    if total_failed_records <= 0:
        return 100 if rule_count > 0 else 0
    failure_share = failed_record_total / total_failed_records
    score = round(max(0.0, 100.0 - (failure_share * 100.0)))
    return int(score)


async def _list_rule_records(repository: RulesRepository, workspace_id: str | None) -> list[Any]:
    collected: list[Any] = []
    offset = 0
    page_size = 500

    while True:
        rows = await repository.list_rule_records(
            workspace=workspace_id,
            include_deleted=False,
            is_template=False,
            limit=page_size,
            offset=offset,
        )
        if not rows:
            break
        collected.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    return collected


async def _build_rule_map(repository: RulesRepository, workspace_id: str | None) -> dict[str, dict[str, str]]:
    rule_map: dict[str, dict[str, str]] = {}
    for row in await _list_rule_records(repository, workspace_id):
        rule_id = _normalize_text(getattr(row, "id", None))
        if not rule_id:
            continue
        rule_map[rule_id] = {
            "name": _normalize_text(getattr(row, "name", None)) or rule_id,
            "dimension": _normalize_text(getattr(row, "dimension", None)) or "Unassigned",
        }
    return rule_map


async def _list_run_summaries(
    *,
    workspace_id: str | None,
    data_object_version_ids: list[str],
    lookback_amount: int,
    lookback_unit: LookbackUnit,
    run_repository: GxExecutionRunRepository,
    run_plan_repository: GxRunPlanRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    suite_repository: GxSuiteRepository,
) -> list[Any]:
    normalized_scope_ids = [value for value in (_normalize_text(item) for item in data_object_version_ids) if value]
    if not normalized_scope_ids:
        normalized_scope_ids = [""]

    collected_by_id: dict[str, Any] = {}
    for scope_id in normalized_scope_ids:
        query = ListGxExecutionRunsQuery(
            lookback_amount=lookback_amount,
            lookback_unit=lookback_unit,
            status=None,
            rule_name=None,
            data_object_name=None,
            search=None,
            limit=None,
            data_product_id=None,
            dataset_id=None,
            data_object_id=None,
            data_object_version_id=scope_id or None,
            delivery_id=None,
            workspace_id=workspace_id,
            run_plan_id=None,
        )
        rows = await list_gx_execution_run_summaries(
            query=query,
            repository=run_repository,
            run_plan_repository=run_plan_repository,
            rules_repository=rules_repository,
            data_catalog_repository=data_catalog_repository,
            suite_repository=suite_repository,
        )
        for row in rows:
            run_id = _normalize_text(getattr(row, "id", None))
            if run_id:
                collected_by_id[run_id] = row

    return list(collected_by_id.values())


def _build_summary_label(*, total_runs: int, failed_runs: int, total_failed_records: int, tracked_count: int) -> str:
    if total_runs <= 0:
        if tracked_count <= 0:
            return "No tracked source versions yet"
        return f"{tracked_count} tracked source versions with no execution history in the selected window"
    return f"{total_runs} runs, {failed_runs} failed, {total_failed_records} failed records"


def _build_ownership_rollups(*, assets: list[Any], scorecards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scorecard_by_asset_id: dict[str, dict[str, Any]] = {}
    for scorecard in scorecards:
        if _normalize_text(scorecard.get("scope_type")) != "data_asset":
            continue
        asset_id = _normalize_text(scorecard.get("data_asset_id"))
        if asset_id:
            scorecard_by_asset_id[asset_id] = scorecard

    grouped_rollups: dict[tuple[str, str], dict[str, Any]] = {}
    for asset in assets:
        asset_id = _normalize_text(getattr(asset, "id", None))
        scorecard = scorecard_by_asset_id.get(asset_id)
        if scorecard is None:
            continue

        business_context = getattr(asset, "business_context", None)
        domain_name = _normalize_text(getattr(business_context, "domain", None)) if business_context is not None else ""
        data_product_id = _normalize_text(getattr(business_context, "data_product_id", None)) if business_context is not None else ""
        tracked_ids = {
            _normalize_text(item)
            for item in (scorecard.get("tracked_data_object_version_ids") or [])
            if _normalize_text(item)
        }

        for scope_kind, scope_id in (("domain", domain_name or "Unspecified"), ("data_product", data_product_id or "Unspecified")):
            bucket = grouped_rollups.setdefault(
                (scope_kind, scope_id),
                {
                    "scope_kind": scope_kind,
                    "scope_id": scope_id,
                    "scope_name": scope_id,
                    "asset_count": 0,
                    "tracked_data_object_version_ids": set(),
                    "total_runs": 0,
                    "pending_runs": 0,
                    "running_runs": 0,
                    "succeeded_runs": 0,
                    "failed_runs": 0,
                    "cancelled_runs": 0,
                    "total_failed_records": 0,
                    "runs_with_failures": 0,
                },
            )
            bucket["asset_count"] += 1
            bucket["tracked_data_object_version_ids"].update(tracked_ids)
            bucket["total_runs"] += int(scorecard.get("total_runs", 0) or 0)
            bucket["pending_runs"] += int(scorecard.get("pending_runs", 0) or 0)
            bucket["running_runs"] += int(scorecard.get("running_runs", 0) or 0)
            bucket["succeeded_runs"] += int(scorecard.get("succeeded_runs", 0) or 0)
            bucket["failed_runs"] += int(scorecard.get("failed_runs", 0) or 0)
            bucket["cancelled_runs"] += int(scorecard.get("cancelled_runs", 0) or 0)
            bucket["total_failed_records"] += int(scorecard.get("total_failed_records", 0) or 0)
            bucket["runs_with_failures"] += int(scorecard.get("runs_with_failures", 0) or 0)

    rollups: list[dict[str, Any]] = []
    for bucket in grouped_rollups.values():
        tracked_count = len(bucket["tracked_data_object_version_ids"])
        overall_score = _score_from_runs(
            int(bucket["total_runs"]),
            int(bucket["succeeded_runs"]),
            int(bucket["running_runs"]),
            int(bucket["failed_runs"]),
            int(bucket["cancelled_runs"]),
            int(bucket["total_failed_records"]),
            int(bucket["runs_with_failures"]),
        )
        rollups.append(
            {
                "scope_kind": bucket["scope_kind"],
                "scope_id": bucket["scope_id"],
                "scope_name": bucket["scope_name"],
                "asset_count": int(bucket["asset_count"]),
                "tracked_data_object_version_count": tracked_count,
                "total_runs": int(bucket["total_runs"]),
                "pending_runs": int(bucket["pending_runs"]),
                "running_runs": int(bucket["running_runs"]),
                "succeeded_runs": int(bucket["succeeded_runs"]),
                "failed_runs": int(bucket["failed_runs"]),
                "cancelled_runs": int(bucket["cancelled_runs"]),
                "total_failed_records": int(bucket["total_failed_records"]),
                "runs_with_failures": int(bucket["runs_with_failures"]),
                "overall_score": overall_score,
                "health_label": _health_label(overall_score),
                "summary": (
                    f'{int(bucket["asset_count"])} assets across {tracked_count} tracked source versions, '
                    f'{int(bucket["failed_runs"])} failed runs, {int(bucket["total_failed_records"])} failed records'
                ),
            }
        )

    rollups.sort(key=lambda item: (str(item.get("scope_kind") or ""), -int(item.get("total_failed_records") or 0), str(item.get("scope_name") or "")))
    return rollups


def _build_dimension_rollups(
    *,
    rule_totals: list[Any],
    rule_map: dict[str, dict[str, str]],
    total_failed_records: int,
) -> list[dict[str, Any]]:
    totals_by_dimension: dict[str, int] = defaultdict(int)

    for row in rule_totals:
        rule_id = _normalize_text(getattr(row, "rule_id", None) or getattr(row, "ruleId", None))
        if not rule_id:
            continue
        total = int(getattr(row, "total", 0) or 0)
        dimension = rule_map.get(rule_id, {}).get("dimension") or "Unassigned"
        totals_by_dimension[dimension] += total

    dimension_names = sorted({entry.get("dimension") or "Unassigned" for entry in rule_map.values()} | set(totals_by_dimension.keys()))

    rollups: list[dict[str, Any]] = []
    for dimension in dimension_names:
        failed_record_total = int(totals_by_dimension.get(dimension, 0))
        rule_count = sum(1 for entry in rule_map.values() if (entry.get("dimension") or "Unassigned") == dimension)
        score = _dimension_score(total_failed_records, failed_record_total, rule_count)
        rollups.append(
            {
                "dimension": dimension,
                "rule_count": rule_count,
                "failed_record_total": failed_record_total,
                "failed_run_count": 1 if failed_record_total > 0 else 0,
                "score": score,
                "status_label": _health_label(score),
            }
        )

    rollups.sort(key=lambda item: (-int(item.get("failed_record_total") or 0), str(item.get("dimension") or "")))
    return rollups


def _build_top_rules(rule_totals: list[Any], rule_map: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    top_rules: list[dict[str, Any]] = []
    for row in rule_totals:
        rule_id = _normalize_text(getattr(row, "rule_id", None) or getattr(row, "ruleId", None))
        if not rule_id:
            continue
        top_rules.append(
            {
                "rule_id": rule_id,
                "rule_name": rule_map.get(rule_id, {}).get("name") or rule_id,
                "dimension": rule_map.get(rule_id, {}).get("dimension") or "Unassigned",
                "total": int(getattr(row, "total", 0) or 0),
            }
        )
    return top_rules


def _build_top_reasons(reason_totals: list[Any]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    for row in reason_totals:
        reason_code = _normalize_text(getattr(row, "reason_code", None) or getattr(row, "reasonCode", None))
        reason_text = _normalize_text(getattr(row, "reason_text", None) or getattr(row, "reasonText", None))
        if not reason_code and not reason_text:
            continue
        reasons.append(
            {
                "reason_code": reason_code or "unknown",
                "reason_text": reason_text or "Unknown reason",
                "total": int(getattr(row, "total", 0) or 0),
            }
        )
    return reasons


def _build_top_regressions(trend_buckets: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    regressions: list[dict[str, Any]] = []
    for previous_bucket, current_bucket in zip(trend_buckets, trend_buckets[1:]):
        previous_total = int(previous_bucket.get("total", 0) or 0)
        current_total = int(current_bucket.get("total", 0) or 0)
        delta = current_total - previous_total
        if delta <= 0:
            continue
        regressions.append(
            {
                "bucket_start": _normalize_text(current_bucket.get("bucket_start")),
                "previous_bucket_start": _normalize_text(previous_bucket.get("bucket_start")),
                "previous_total": previous_total,
                "current_total": current_total,
                "delta": delta,
            }
        )

    regressions.sort(
        key=lambda item: (
            -int(item.get("delta") or 0),
            -int(item.get("current_total") or 0),
            str(item.get("bucket_start") or ""),
        )
    )
    return regressions[:limit]


def _build_trend_buckets(trend_totals: list[Any]) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for row in trend_totals:
        bucket_start = _normalize_text(getattr(row, "bucket_start", None) or getattr(row, "bucketStart", None))
        if not bucket_start:
            continue
        buckets.append(
            {
                "bucket_start": bucket_start,
                "total": int(getattr(row, "total", 0) or 0),
            }
        )
    buckets.sort(key=lambda item: str(item.get("bucket_start") or ""))
    return buckets


def _build_reason_trend_buckets(reason_trend_totals: list[Any]) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for row in reason_trend_totals:
        bucket_start = _normalize_text(getattr(row, "bucket_start", None) or getattr(row, "bucketStart", None))
        reason_code = _normalize_text(getattr(row, "reason_code", None) or getattr(row, "reasonCode", None))
        reason_text = _normalize_text(getattr(row, "reason_text", None) or getattr(row, "reasonText", None))
        if not bucket_start or not reason_code or not reason_text:
            continue
        buckets.append(
            {
                "bucket_start": bucket_start,
                "reason_code": reason_code,
                "reason_text": reason_text,
                "total": int(getattr(row, "total", 0) or 0),
            }
        )
    buckets.sort(key=lambda item: (str(item.get("bucket_start") or ""), str(item.get("reason_code") or ""), str(item.get("reason_text") or "")))
    return buckets


def _normalize_incident_entity(entity: Any) -> dict[str, Any]:
    return {
        "incident_id": _normalize_text(getattr(entity, "id", None)),
        "title": _normalize_text(getattr(entity, "title", None)),
        "status": _normalize_text(getattr(entity, "status", None)),
        "severity": _normalize_text(getattr(entity, "severity", None)) or None,
        "incident_kind": _normalize_text(getattr(entity, "incident_kind", None)),
        "assigned_to": _normalize_text(getattr(entity, "assigned_to", None)) or None,
        "run_id": _normalize_text(getattr(entity, "run_id", None)) or None,
        "run_plan_id": _normalize_text(getattr(entity, "run_plan_id", None)) or None,
    }


def _build_workspace_summary(scorecard: dict[str, Any], active_incidents: list[Any], ownership_rollups: list[dict[str, Any]]) -> dict[str, Any]:
    trend_buckets = list(scorecard.get("trend_buckets") or [])
    return {
        "workspace_id": _normalize_text(scorecard.get("workspace_id")),
        "generated_at": _normalize_text(scorecard.get("generated_at")),
        "overall_score": int(scorecard.get("overall_score", 0) or 0),
        "health_label": _normalize_text(scorecard.get("health_label")) or "watch",
        "summary": _normalize_text(scorecard.get("summary")),
        "top_regressions": _build_top_regressions(trend_buckets),
        "top_rules": list(scorecard.get("top_rules") or [])[:5],
        "active_incident_count": len(active_incidents),
        "active_incidents": [_normalize_incident_entity(entity) for entity in active_incidents[:5]],
        "ownership_rollups": ownership_rollups,
    }


def _build_scorecard(
    *,
    scope: _RunScope,
    workspace_id: str,
    lookback_amount: int,
    lookback_unit: LookbackUnit,
    generated_at: str,
    run_summaries: list[Any],
    analytics_summary: Any,
    rule_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    status_counts = Counter(_normalize_text(getattr(row, "status", None)) for row in run_summaries)
    total_runs = sum(status_counts.values())
    pending_runs = int(status_counts.get("pending", 0))
    running_runs = int(status_counts.get("running", 0))
    succeeded_runs = int(status_counts.get("succeeded", 0))
    failed_runs = int(status_counts.get("failed", 0))
    cancelled_runs = int(status_counts.get("cancelled", 0))
    total_failed_records = int(getattr(analytics_summary, "total_failed_records", 0) or 0)
    runs_with_failures = int(getattr(analytics_summary, "runs_with_failures", 0) or 0)
    overall_score = _score_from_runs(
        total_runs,
        succeeded_runs,
        running_runs,
        failed_runs,
        cancelled_runs,
        total_failed_records,
        runs_with_failures,
    )
    rule_totals = list(getattr(analytics_summary, "rule_totals", []) or [])
    reason_totals = list(getattr(analytics_summary, "reason_totals", []) or [])
    trend_totals = list(getattr(analytics_summary, "trend_totals", []) or [])
    reason_trend_totals = list(getattr(analytics_summary, "reason_trend_totals", []) or [])
    return {
        "scope_type": scope.scope_type,
        "scope_id": scope.scope_id,
        "scope_name": scope.scope_name,
        "workspace_id": workspace_id,
        "data_asset_id": scope.data_asset_id,
        "data_asset_name": scope.data_asset_name,
        "data_asset_version_id": scope.data_asset_version_id,
        "tracked_data_object_version_ids": scope.tracked_data_object_version_ids,
        "lookback_amount": lookback_amount,
        "lookback_unit": lookback_unit,
        "generated_at": generated_at,
        "overall_score": overall_score,
        "health_label": _health_label(overall_score),
        "summary": _build_summary_label(
            total_runs=total_runs,
            failed_runs=failed_runs,
            total_failed_records=total_failed_records,
            tracked_count=len(scope.tracked_data_object_version_ids),
        ),
        "total_runs": total_runs,
        "pending_runs": pending_runs,
        "running_runs": running_runs,
        "succeeded_runs": succeeded_runs,
        "failed_runs": failed_runs,
        "cancelled_runs": cancelled_runs,
        "total_failed_records": total_failed_records,
        "runs_with_failures": runs_with_failures,
        "dimension_rollups": _build_dimension_rollups(
            rule_totals=rule_totals,
            rule_map=rule_map,
            total_failed_records=total_failed_records,
        ),
        "top_rules": _build_top_rules(rule_totals, rule_map),
        "top_reasons": _build_top_reasons(reason_totals),
        "trend_buckets": _build_trend_buckets(trend_totals),
        "reason_trend_buckets": _build_reason_trend_buckets(reason_trend_totals),
    }


async def _load_scope_summary(
    *,
    scope: _RunScope,
    workspace_id: str,
    lookback_amount: int,
    lookback_unit: LookbackUnit,
    run_repository: GxExecutionRunRepository,
    run_plan_repository: GxRunPlanRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    suite_repository: GxSuiteRepository,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository,
) -> dict[str, Any]:
    run_summaries = await _list_run_summaries(
        workspace_id=workspace_id,
        data_object_version_ids=scope.tracked_data_object_version_ids,
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        run_repository=run_repository,
        run_plan_repository=run_plan_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
        suite_repository=suite_repository,
    )
    execution_run_ids = [str(getattr(row, "id", "") or "").strip() for row in run_summaries if str(getattr(row, "id", "") or "").strip()]
    analytics_summary = await projection_repository.summarize_reason_analytics(
        data_object_version_ids=scope.tracked_data_object_version_ids,
        execution_run_ids=execution_run_ids,
    )
    rule_map = await _build_rule_map(rules_repository, workspace_id)
    return _build_scorecard(
        scope=scope,
        workspace_id=workspace_id,
        lookback_amount=lookback_amount,
        lookback_unit=lookback_unit,
        generated_at=datetime.now(UTC).isoformat(),
        run_summaries=run_summaries,
        analytics_summary=analytics_summary,
        rule_map=rule_map,
    )


def _list_active_incidents(incident_repository: IncidentRepository, workspace_id: str) -> list[Any]:
    open_incidents = incident_repository.list_incidents(workspace_id=workspace_id, status=INCIDENT_STATUS_OPEN, limit=500, offset=0)
    in_progress_incidents = incident_repository.list_incidents(
        workspace_id=workspace_id,
        status=INCIDENT_STATUS_IN_PROGRESS,
        limit=500,
        offset=0,
    )
    merged_by_id: dict[str, Any] = {}
    for incident in [*open_incidents, *in_progress_incidents]:
        incident_id = _normalize_text(getattr(incident, "id", None))
        if incident_id:
                        merged_by_id[incident_id] = incident
    return list(merged_by_id.values())


async def get_health_scorecards(
    *,
    query: HealthScorecardsQuery,
    data_asset_repository: DataAssetRepository,
    run_repository: GxExecutionRunRepository,
    run_plan_repository: GxRunPlanRepository,
    rules_repository: RulesRepository,
    data_catalog_repository: DataCatalogRepository,
    suite_repository: GxSuiteRepository,
    projection_repository: ExceptionReasonAnalyticsProjectionRepository,
    incident_repository: IncidentRepository,
) -> dict[str, Any]:
    workspace_id = _normalize_text(query.workspace_id)
    data_asset_id = _normalize_text(query.data_asset_id)

    if not workspace_id and not data_asset_id:
        raise HTTPException(status_code=400, detail={"error": "health_scorecard_scope_required", "message": "workspace_id or data_asset_id is required"})

    selected_asset = None
    if data_asset_id:
        selected_asset = data_asset_repository.get_data_asset(data_asset_id)
        if selected_asset is None:
            raise HTTPException(status_code=404, detail={"error": "health_scorecard_asset_not_found", "message": f"Data Asset '{data_asset_id}' was not found"})
        asset_workspace_id = _normalize_text(getattr(selected_asset, "workspace_id", None))
        if workspace_id and asset_workspace_id and workspace_id != asset_workspace_id:
            raise HTTPException(status_code=404, detail={"error": "health_scorecard_workspace_mismatch", "message": f"Data Asset '{data_asset_id}' does not belong to workspace '{workspace_id}'"})
        workspace_id = workspace_id or asset_workspace_id

    if not workspace_id:
        raise HTTPException(status_code=400, detail={"error": "health_scorecard_workspace_required", "message": "workspace_id is required"})

    workspace_assets = data_asset_repository.list_data_assets(workspace_id=workspace_id)
    assets = [selected_asset] if selected_asset is not None else workspace_assets

    workspace_source_version_ids: list[str] = []
    for asset in workspace_assets:
        workspace_source_version_ids.extend(
            [
                _normalize_text(item)
                for item in (getattr(asset, "source_object_version_ids", []) or [])
                if _normalize_text(item)
            ]
        )

    scorecards: list[dict[str, Any]] = []
    workspace_scope = _RunScope(
        scope_type="workspace",
        scope_id=workspace_id,
        scope_name=f"Workspace {workspace_id}",
        data_asset_id=None,
        data_asset_name=None,
        data_asset_version_id=None,
        tracked_data_object_version_ids=sorted(set(workspace_source_version_ids)),
    )
    scorecards.append(
        await _load_scope_summary(
            scope=workspace_scope,
            workspace_id=workspace_id,
            lookback_amount=query.lookback_amount,
            lookback_unit=query.lookback_unit,
            run_repository=run_repository,
            run_plan_repository=run_plan_repository,
            rules_repository=rules_repository,
            data_catalog_repository=data_catalog_repository,
            suite_repository=suite_repository,
            projection_repository=projection_repository,
        )
    )

    active_incidents = _list_active_incidents(incident_repository, workspace_id)

    for asset in assets:
        asset_id = _normalize_text(getattr(asset, "id", None))
        asset_name = _normalize_text(getattr(asset, "name", None)) or asset_id
        asset_version_id = _normalize_text(getattr(asset, "current_version_id", None)) or None
        tracked_ids = sorted({
            _normalize_text(item)
            for item in (getattr(asset, "source_object_version_ids", []) or [])
            if _normalize_text(item)
        })
        asset_scope = _RunScope(
            scope_type="data_asset",
            scope_id=asset_id,
            scope_name=asset_name,
            data_asset_id=asset_id,
            data_asset_name=asset_name,
            data_asset_version_id=asset_version_id,
            tracked_data_object_version_ids=tracked_ids,
        )
        scorecards.append(
            await _load_scope_summary(
                scope=asset_scope,
                workspace_id=workspace_id,
                lookback_amount=query.lookback_amount,
                lookback_unit=query.lookback_unit,
                run_repository=run_repository,
                run_plan_repository=run_plan_repository,
                rules_repository=rules_repository,
                data_catalog_repository=data_catalog_repository,
                suite_repository=suite_repository,
                projection_repository=projection_repository,
            )
        )

    ownership_rollups = _build_ownership_rollups(assets=workspace_assets, scorecards=scorecards[1:])
    workspace_summary = _build_workspace_summary(scorecards[0], active_incidents, ownership_rollups)

    return {
        "workspace_id": workspace_id,
        "data_asset_id": data_asset_id or None,
        "lookback_amount": query.lookback_amount,
        "lookback_unit": query.lookback_unit,
        "generated_at": datetime.now(UTC).isoformat(),
        "workspace_summary": workspace_summary,
        "scorecards": scorecards,
    }
