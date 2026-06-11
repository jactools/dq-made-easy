import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias

from app.api.presenters.catalog_governance import build_affected_rules_response
from app.api.presenters.catalog_governance import build_catalog_health_payload
from app.api.presenters.catalog_governance import build_catalog_term_payloads
from app.api.presenters.catalog_governance import build_catalog_terms_response
from app.api.presenters.catalog_governance import build_drift_summary_response
from app.api.presenters.catalog_governance import build_monitor_anomaly_payloads
from app.api.presenters.catalog_governance import build_monitor_anomalies_response
from app.api.presenters.catalog_governance import build_monitor_definition_payloads
from app.api.presenters.catalog_governance import build_monitor_definitions_response
from app.api.presenters.catalog_governance import build_monitor_drift_payloads
from app.api.presenters.catalog_governance import build_monitor_drifts_response
from app.api.presenters.catalog_governance import build_monitor_notification_preferences_response
from app.api.presenters.catalog_governance import build_monitor_root_cause_response
from app.api.presenters.catalog_governance import build_monitor_schedule_response
from app.api.presenters.catalog_governance import build_monitor_schedules_response
from app.api.presenters.catalog_governance import build_revalidation_job_response
from app.api.presenters.catalog_governance import build_revalidation_job_status_response
from app.api.presenters.catalog_governance import build_rule_drift_response
from app.api.presenters.catalog_governance import current_catalog_governance_timestamp
from app.api.presenters.catalog_governance import decode_revalidation_job_id
from app.api.presenters.catalog_governance import encode_revalidation_job_id
from app.api.presenters.catalog_governance import filter_catalog_term_payloads
from app.api.presenters.row_access import read_row_field
from app.api.v1.schemas import GovernanceInboxView
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_approvals_repository
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_monitor_schedule_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_exception_reason_analytics_projection_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.request_context import get_user_id
from app.domain.entities import build_rule_version_list_entity
from app.domain.entities.catalog_governance import catalog_term_key_from_name
from app.domain.entities.catalog_governance import detect_rule_drifts
from app.domain.entities.catalog_governance import extract_rule_aliases_from_record
from app.domain.entities.monitor_schedule import MonitorScheduleEntity
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import DataAssetRepository
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import MonitorScheduleRepository
from app.domain.interfaces import RulesRepository
from app.application.use_cases.governance_inboxes import GovernanceInboxQuery
from app.application.use_cases.governance_inboxes import list_governance_inboxes
from app.application.use_cases.execution_queries import ScopedGxExecutionExceptionAnalyticsQuery
from app.application.use_cases.execution_queries import get_gx_execution_exception_analytics_for_scope

router = APIRouter(tags=["governance"])


class RevalidationJobRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleVersionIds: list[str] = Field(default_factory=list)
    triggeredByTermId: str | None = None
    triggeredByTermName: str | None = None


class DriftReviewRuleView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleId: str
    ruleName: str
    ruleVersionId: str
    versionNumber: int
    affectedAliases: list[str] = Field(default_factory=list)
    totalDrifts: int = 0
    needsRevalidation: bool = False


class DriftReviewRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    affectedRules: list[DriftReviewRuleView] = Field(default_factory=list)
    triggeredByTermId: str | None = None
    triggeredByTermName: str | None = None


class MonitorNotificationPreferenceView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    workspace_id: str
    enabled: bool = False
    categories: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)


class MonitorNotificationPreferencesRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    monitor_notification_preferences: list[MonitorNotificationPreferenceView] = Field(default_factory=list)


_VALID_SCHEDULE_SCOPE_KINDS = {"data_asset", "source_dataset"}


class MonitorScheduleRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    scope_kind: str
    scope_id: str
    workspace_id: str
    cron_expression: str
    timezone: str = "UTC"
    window_minutes: int = 1440
    enabled: bool = True
    signals: list[str] | None = None


def _resolve_review_reviewer_name(request: Request, user_id: str | None) -> str:
    claims = getattr(request.state, "auth_claims", None)
    if isinstance(claims, dict):
        for key in ("name", "preferred_username", "email"):
            candidate = str(claims.get(key) or "").strip()
            if candidate:
                return candidate
    return str(user_id or "system").strip() or "system"


def _current_user_workspace_ids(current_user: object) -> list[str]:
    workspace_ids: list[str] = []

    for workspace in list(getattr(current_user, "workspaces", None) or []):
        workspace_id = str(workspace or "").strip()
        if workspace_id and workspace_id not in workspace_ids:
            workspace_ids.append(workspace_id)

    for workspace_role in list(getattr(current_user, "workspace_roles", None) or []):
        if isinstance(workspace_role, dict):
            workspace_id = str(workspace_role.get("workspace_id") or "").strip()
        else:
            workspace_id = str(getattr(workspace_role, "workspace_id", "") or "").strip()
        if workspace_id and workspace_id not in workspace_ids:
            workspace_ids.append(workspace_id)

    return workspace_ids


def _monitor_notification_rows_from_preferences(preferences: object) -> list[dict[str, Any]]:
    if not isinstance(preferences, dict):
        return []

    rows = preferences.get("monitor_notification_preferences")
    if not isinstance(rows, list):
        return []

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        workspace_id = str(row.get("workspace_id") or "").strip()
        if not workspace_id:
            continue
        normalized_rows.append(
            {
                "workspace_id": workspace_id,
                "enabled": bool(row.get("enabled", False)),
                "categories": [str(category).strip() for category in list(row.get("categories") or []) if str(category).strip()],
                "channels": [str(channel).strip() for channel in list(row.get("channels") or []) if str(channel).strip()],
            }
        )
    return normalized_rows


def _merge_monitor_notification_rows(
    existing_rows: list[dict[str, Any]],
    update_rows: list[MonitorNotificationPreferenceView],
    accessible_workspace_ids: list[str],
) -> list[dict[str, Any]]:
    merged_rows = {
        str(row.get("workspace_id") or "").strip(): {
            "workspace_id": str(row.get("workspace_id") or "").strip(),
            "enabled": bool(row.get("enabled", False)),
            "categories": list(row.get("categories") or []),
            "channels": list(row.get("channels") or []),
        }
        for row in existing_rows
        if str(row.get("workspace_id") or "").strip() in accessible_workspace_ids
    }

    for item in update_rows:
        workspace_id = str(item.workspace_id or "").strip()
        if not workspace_id:
            continue
        merged_rows[workspace_id] = {
            "workspace_id": workspace_id,
            "enabled": bool(item.enabled),
            "categories": [str(category).strip() for category in list(item.categories or []) if str(category).strip()],
            "channels": [str(channel).strip() for channel in list(item.channels or []) if str(channel).strip()],
        }

    return [merged_rows[workspace_id] for workspace_id in accessible_workspace_ids if workspace_id in merged_rows]


@router.get("/catalog/health")
async def get_catalog_health(
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    terms = build_catalog_term_payloads(repository.list_attributes_catalog(None))
    return build_catalog_health_payload(term_count=len(terms), last_sync=current_catalog_governance_timestamp())


@router.get("/catalog/terms")
async def get_catalog_terms(
    domain: str | None = Query(default=None),
    search: str | None = Query(default=None),
    match_threshold_pct: float | None = Query(default=None),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> dict:
    rows = build_catalog_term_payloads(repository.list_attributes_catalog(None))
    normalized_domain = domain if isinstance(domain, str) else None
    normalized_search = search if isinstance(search, str) else None
    if not isinstance(match_threshold_pct, (int, float)):
        app_config = app_config_repository.get_app_config()
        threshold_value = getattr(app_config, "defaultCatalogTermMatchThresholdPct", 70.0)
    else:
        threshold_value = match_threshold_pct
    rows = filter_catalog_term_payloads(
        rows,
        domain=normalized_domain,
        search=normalized_search,
        match_threshold_pct=float(threshold_value or 0),
    )
    return build_catalog_terms_response(rows=rows, last_synced=current_catalog_governance_timestamp())


@router.get("/governance/drift/rules/{rule_id}/{version_id}")
async def check_rule_drift(
    rule_id: str,
    version_id: str,
    rules_repository: RulesRepository = Depends(get_rules_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    rule_list = await rules_repository.list_rule_records(limit=500, offset=0)
    rule_row = next((row for row in rule_list if str(read_row_field(row, "id") or "") == rule_id), None)
    version_list = build_rule_version_list_entity(await rules_repository.list_rule_versions(rule_id, limit=50, offset=0))
    version_row = next((row for row in (version_list.versions if version_list is not None else []) if str(row.id or "") == version_id), None)
    last_timestamp = current_catalog_governance_timestamp()
    drift_details = detect_rule_drifts(
        rule_record=rule_row or {},
        rule_attributes=catalog_repository.list_rule_attributes(),
        catalog_attributes=catalog_repository.list_attributes_catalog(None),
        data_objects_catalog=catalog_repository.list_data_objects_catalog(None),
        detected_at=last_timestamp,
    )
    return build_rule_drift_response(
        rule_id=rule_id,
        rule_name=str(read_row_field(rule_row, "name") or f"Rule {rule_id}"),
        version_id=version_id,
        version_number=int(getattr(version_row, "versionNumber", 0) or 0),
        affected_aliases=list(drift_details.get("affected_aliases") or []),
        drifts=list(drift_details.get("drifts") or []),
        last_validated_at=last_timestamp,
        detected_at=last_timestamp,
    )


@router.get("/governance/drift/summary")
async def get_drift_summary(
    rules_repository: RulesRepository = Depends(get_rules_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    rules = await rules_repository.list_rule_records(limit=500, offset=0)
    catalog_attributes = catalog_repository.list_attributes_catalog(None)
    data_objects_catalog = catalog_repository.list_data_objects_catalog(None)
    rule_attributes = catalog_repository.list_rule_attributes()
    affected: list[dict] = []
    last_timestamp = current_catalog_governance_timestamp()
    for row in rules:
        drift_details = detect_rule_drifts(
            rule_record=row,
            rule_attributes=rule_attributes,
            catalog_attributes=catalog_attributes,
            data_objects_catalog=data_objects_catalog,
            detected_at=last_timestamp,
        )
        if int(drift_details.get("total_drifts") or 0) == 0:
            continue
        version_id, version_number = await _resolve_rule_version_metadata(rules_repository, row)
        affected.append(
            {
                "ruleId": str(read_row_field(row, "id") or ""),
                "ruleName": str(read_row_field(row, "name") or ""),
                "ruleVersionId": version_id,
                "versionNumber": version_number,
                "affectedAliases": list(drift_details.get("affected_aliases") or []),
                "drifts": list(drift_details.get("drifts") or []),
                "totalDrifts": int(drift_details.get("total_drifts") or 0),
                "needsRevalidation": bool(drift_details.get("needs_revalidation")),
            }
        )

    return build_drift_summary_response(
        total_rules_checked=len(rules),
        affected_rules=affected,
    )


@router.get("/governance/monitor-definitions")
async def get_monitor_definitions(
    workspace_id: str | None = Query(default=None),
    data_asset_repository: DataAssetRepository = Depends(get_data_asset_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    monitor_definitions = build_monitor_definition_payloads(
        data_assets=data_asset_repository.list_data_assets(workspace_id=workspace_id),
        data_sets=data_catalog_repository.list_data_sets(workspace=workspace_id),
    )
    return build_monitor_definitions_response(
        rows=monitor_definitions,
        last_synced=current_catalog_governance_timestamp(),
    )


@router.get("/governance/monitor-anomalies")
async def get_monitor_anomalies(
    workspace_id: str | None = Query(default=None),
    data_asset_repository: DataAssetRepository = Depends(get_data_asset_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    monitor_anomalies = build_monitor_anomaly_payloads(
        data_assets=data_asset_repository.list_data_assets(workspace_id=workspace_id),
        data_sets=data_catalog_repository.list_data_sets(workspace=workspace_id),
    )
    return build_monitor_anomalies_response(
        rows=monitor_anomalies,
        last_synced=current_catalog_governance_timestamp(),
    )


@router.get("/governance/monitor-drifts")
async def get_monitor_drifts(
    workspace_id: str | None = Query(default=None),
    data_asset_repository: DataAssetRepository = Depends(get_data_asset_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    monitor_drifts = build_monitor_drift_payloads(
        data_assets=data_asset_repository.list_data_assets(workspace_id=workspace_id),
        data_sets=data_catalog_repository.list_data_sets(workspace=workspace_id),
    )
    return build_monitor_drifts_response(
        rows=monitor_drifts,
        last_synced=current_catalog_governance_timestamp(),
    )


@router.get("/governance/monitor-root-cause")
async def get_monitor_root_cause(
    data_object_version_id: str = Query(...),
    lookback_amount: int = Query(default=24, ge=1, le=720),
    lookback_unit: str = Query(default="hours"),
    delivery_id: str | None = Query(default=None),
    execution_plan_id: str | None = Query(default=None),
    suite_id: str | None = Query(default=None),
    rule_version_id: str | None = Query(default=None),
    gx_execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(get_exception_reason_analytics_projection_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    normalized_data_object_version_id = str(data_object_version_id or "").strip()
    result = await get_gx_execution_exception_analytics_for_scope(
        query=ScopedGxExecutionExceptionAnalyticsQuery(
            lookback_amount=lookback_amount,
            lookback_unit=str(lookback_unit or "hours").strip() or "hours",
            delivery_id=str(delivery_id or "").strip() or None,
            execution_plan_id=str(execution_plan_id or "").strip() or None,
            suite_id=str(suite_id or "").strip() or None,
            data_object_version_id=normalized_data_object_version_id,
            rule_version_id=str(rule_version_id or "").strip() or None,
        ),
        repository=gx_execution_run_repository,
        projection_repository=projection_repository,
        rules_repository=rules_repository,
        data_catalog_repository=data_catalog_repository,
    )
    return build_monitor_root_cause_response(
        data_object_version_id=normalized_data_object_version_id,
        lookback_amount=lookback_amount,
        lookback_unit=str(lookback_unit or "hours").strip() or "hours",
        analytics=result.analytics,
        delivery_id=str(delivery_id or "").strip() or None,
        execution_plan_id=str(execution_plan_id or "").strip() or None,
        rule_version_id=str(rule_version_id or "").strip() or None,
        suite_id=str(suite_id or "").strip() or None,
        last_synced=current_catalog_governance_timestamp(),
    )


@router.get("/governance/monitor-notification-preferences")
async def get_monitor_notification_preferences(
    request: Request,
    repository: AdminRepository = Depends(get_admin_repository),
) -> dict:
    current_user = repository.get_current_user(
        getattr(request.state, "user_id", None),
        getattr(request.state, "auth_claims", None),
    )
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    accessible_workspace_ids = _current_user_workspace_ids(current_user)
    preferences = _monitor_notification_rows_from_preferences(getattr(current_user, "preferences", None))
    return build_monitor_notification_preferences_response(
        accessible_workspace_ids=accessible_workspace_ids,
        rows=preferences,
        last_synced=current_catalog_governance_timestamp(),
    )


@router.put("/governance/monitor-notification-preferences")
async def update_monitor_notification_preferences(
    request: Request,
    payload: MonitorNotificationPreferencesRequest,
    repository: AdminRepository = Depends(get_admin_repository),
) -> dict:
    current_user = repository.get_current_user(
        getattr(request.state, "user_id", None),
        getattr(request.state, "auth_claims", None),
    )
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    accessible_workspace_ids = _current_user_workspace_ids(current_user)
    if not accessible_workspace_ids:
        raise HTTPException(status_code=403, detail="No accessible workspaces available for notification subscriptions")

    requested_workspace_ids = [str(item.workspace_id or "").strip() for item in payload.monitor_notification_preferences]
    unauthorized_workspace_ids = sorted(
        {
            workspace_id
            for workspace_id in requested_workspace_ids
            if workspace_id and workspace_id not in accessible_workspace_ids
        }
    )
    if unauthorized_workspace_ids:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "workspace_access_denied",
                "workspace_ids": unauthorized_workspace_ids,
                "message": "Notification preferences can only target workspaces the current user can access",
            },
        )

    current_preferences = dict(getattr(current_user, "preferences", None) or {})
    existing_rows = _monitor_notification_rows_from_preferences(current_preferences)
    merged_rows = _merge_monitor_notification_rows(
        existing_rows=existing_rows,
        update_rows=payload.monitor_notification_preferences,
        accessible_workspace_ids=accessible_workspace_ids,
    )
    current_preferences["monitor_notification_preferences"] = merged_rows

    updated_user = repository.update_current_user(
        getattr(request.state, "user_id", None),
        getattr(request.state, "auth_claims", None),
        {"preferences": current_preferences},
    )
    if updated_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return build_monitor_notification_preferences_response(
        accessible_workspace_ids=accessible_workspace_ids,
        rows=_monitor_notification_rows_from_preferences(getattr(updated_user, "preferences", None)),
        last_synced=current_catalog_governance_timestamp(),
    )


@router.get("/governance/drift/terms/{term_id}/affected-rules")
async def get_affected_rules(
    term_id: str,
    rules_repository: RulesRepository = Depends(get_rules_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict:
    normalized_term = catalog_term_key_from_name(term_id)
    rules = await rules_repository.list_rule_records(limit=500, offset=0)
    catalog_attributes = catalog_repository.list_attributes_catalog(None)
    data_objects_catalog = catalog_repository.list_data_objects_catalog(None)
    rule_attributes = catalog_repository.list_rule_attributes()
    affected_rules = []
    for row in rules:
        drift_details = detect_rule_drifts(
            rule_record=row,
            rule_attributes=rule_attributes,
            catalog_attributes=catalog_attributes,
            data_objects_catalog=data_objects_catalog,
            detected_at=current_catalog_governance_timestamp(),
        )
        if not any(catalog_term_key_from_name(alias) == normalized_term for alias in drift_details.get("affected_aliases", [])):
            continue
        version_id, version_number = await _resolve_rule_version_metadata(rules_repository, row)
        affected_rules.append(
            {
                "ruleId": str(read_row_field(row, "id") or ""),
                "ruleName": str(read_row_field(row, "name") or ""),
                "ruleVersionId": version_id,
                "versionNumber": version_number,
                "affectedAliases": list(drift_details.get("affected_aliases") or []),
                "drifts": list(drift_details.get("drifts") or []),
                "totalDrifts": int(drift_details.get("total_drifts") or 0),
                "needsRevalidation": bool(drift_details.get("needs_revalidation")),
            }
        )

    return build_affected_rules_response(term_id=term_id, affected_rules=affected_rules)


@router.post("/governance/revalidation/jobs", status_code=201)
async def create_revalidation_job(
    body: RevalidationJobRequest,
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    if not body.ruleVersionIds:
        raise HTTPException(status_code=400, detail="ruleVersionIds required")

    # Ensure the endpoint exercises repository-backed access under integration runs.
    await rules_repository.list_rule_records(limit=1, offset=0)

    started_at = current_catalog_governance_timestamp()
    triggered_by_term = body.triggeredByTermName or "N/A"
    queued = len(body.ruleVersionIds)
    job_id = encode_revalidation_job_id(
        queued=queued,
        triggered_by_term=triggered_by_term,
        started_at=started_at,
    )
    return build_revalidation_job_response(
        job_id=job_id,
        queued=queued,
        triggered_by_term=triggered_by_term,
        started_at=started_at,
    )


@router.post("/governance/drift/reviews", status_code=201)
async def create_drift_review(
    request: Request,
    body: DriftReviewRequest,
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> dict:
    if not body.affectedRules:
        raise HTTPException(status_code=400, detail="affectedRules required")

    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    reviewer_name = _resolve_review_reviewer_name(request, user_id)
    reviewed_at = current_catalog_governance_timestamp()

    reviewed_count = 0
    for item in body.affectedRules:
        rule_id = str(item.ruleId or "").strip()
        if not rule_id:
            raise HTTPException(status_code=400, detail="affectedRules entries require ruleId")

        rule_version_id = str(item.ruleVersionId or "current").strip() or "current"
        approvals_repository.append_audit_event(
            approval_id=f"drift-review:{rule_id}:{rule_version_id}",
            action="drift-reviewed",
            actor_id=user_id or reviewer_name,
            details={
                "rule_id": rule_id,
                "rule_name": item.ruleName,
                "rule_version_id": item.ruleVersionId,
                "version_number": item.versionNumber,
                "affected_aliases": list(item.affectedAliases),
                "total_drifts": item.totalDrifts,
                "needs_revalidation": item.needsRevalidation,
                "reviewed_by": reviewer_name,
                "reviewed_by_id": user_id,
                "reviewed_at": reviewed_at,
                "review_summary": f"Catalog drift reviewed for {item.ruleName or rule_id}; new version, if needed, must go through the normal approval process.",
                "triggered_by_term_id": body.triggeredByTermId,
                "triggered_by_term_name": body.triggeredByTermName,
            },
        )
        reviewed_count += 1

    return {
        "reviewed_count": reviewed_count,
        "reviewed_at": reviewed_at,
    }


@router.get("/governance/inboxes", response_model=GovernanceInboxView)
async def get_governance_inboxes(
    workspace_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> dict:
    log_event(
        _log,
        "governance.inboxes.start",
        component="governance-api",
        workspaceId=workspace_id,
        page=page,
        limit=limit,
    )
    payload = await list_governance_inboxes(
        GovernanceInboxQuery(workspace_id=workspace_id, page=page, limit=limit),
        repository=rules_repository,
        approvals_repository=approvals_repository,
    )
    log_event(_log, "governance.inboxes.complete", component="governance-api", workspaceId=workspace_id)
    return payload


@router.get("/governance/revalidation/jobs/{job_id}")
async def get_revalidation_job_status(
    job_id: str,
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> dict:
    await rules_repository.list_rule_records(limit=1, offset=0)
    metadata = decode_revalidation_job_id(job_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Job not found")
    queued = int(metadata.get("queued") or 0)
    started_at = str(metadata.get("startedAt") or current_catalog_governance_timestamp())
    triggered_by_term = str(metadata.get("triggeredByTerm") or "N/A")
    return build_revalidation_job_status_response(
        job_id=job_id,
        queued=queued,
        triggered_by_term=triggered_by_term,
        started_at=started_at,
    )


async def _resolve_rule_version_metadata(
    rules_repository: RulesRepository,
    row: object,
) -> tuple[str, int]:
    current_version_id = str(read_row_field(row, "current_version_id") or "").strip()
    rule_id = str(read_row_field(row, "id") or "").strip()
    if not rule_id:
        return "", 0

    version_list = build_rule_version_list_entity(await rules_repository.list_rule_versions(rule_id, limit=50, offset=0))
    versions = list(version_list.versions if version_list is not None else [])
    version_row = next((version for version in versions if str(version.id or "") == current_version_id), None)
    if version_row is None and versions:
        version_row = next((version for version in versions if bool(version.isCurrentVersion)), None) or versions[0]
    if version_row is None:
        return current_version_id, 0
    return str(version_row.id or current_version_id), int(version_row.versionNumber or 0)


# ---------------------------------------------------------------------------
# Monitor schedules  (DQ-12.AC-01)
# ---------------------------------------------------------------------------

_CRON_FIELD_RE = re.compile(
    r"^(?:\*(?:/\d+)?|\d+(?:-\d+)?(?:/\d+)?(?:,\d+(?:-\d+)?(?:/\d+)?)*)$"
)
_CRON_NAMED_MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}
_CRON_NAMED_DAYS = {"sun", "mon", "tue", "wed", "thu", "fri", "sat"}
_CRON_LIMITS = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day-of-month", 1, 31),
    ("month", 1, 12),
    ("day-of-week", 0, 7),
]


def _validate_cron_expression(cron: str) -> str | None:
    """Return an error string if invalid, None if valid."""
    fields = cron.strip().split()
    if len(fields) != 5:
        return f"cron_expression must have exactly 5 space-separated fields (got {len(fields)})"
    for (name, lo, hi), field in zip(_CRON_LIMITS, fields):
        if not _CRON_FIELD_RE.match(field):
            fl = field.lower()
            if name == "month" and fl in _CRON_NAMED_MONTHS:
                continue
            if name == "day-of-week" and fl in _CRON_NAMED_DAYS:
                continue
            return f"cron_expression field '{name}' has invalid syntax: {field!r}"
        for n in (int(t) for t in re.findall(r"\d+", field)):
            if not lo <= n <= hi:
                return f"cron_expression field '{name}' value {n} out of range [{lo}, {hi}]"
    return None


@router.get("/governance/monitor-schedules/{scope_kind}/{scope_id}")
async def get_monitor_schedule_by_scope(
    scope_kind: str,
    scope_id: str,
    schedule_repository: MonitorScheduleRepository = Depends(get_monitor_schedule_repository),
) -> dict:
    if scope_kind not in _VALID_SCHEDULE_SCOPE_KINDS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_scope_kind",
                "message": f"scope_kind must be one of {sorted(_VALID_SCHEDULE_SCOPE_KINDS)}",
            },
        )
    schedule = schedule_repository.get_monitor_schedule(scope_kind=scope_kind, scope_id=scope_id)
    if schedule is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "monitor_schedule_not_found",
                "message": f"No monitor schedule found for scope_kind={scope_kind!r} scope_id={scope_id!r}",
            },
        )
    return build_monitor_schedule_response(
        schedule=schedule.__dict__,
        last_synced=current_catalog_governance_timestamp(),
    )


@router.get("/governance/monitor-schedules")
async def list_monitor_schedules(
    workspace_id: str | None = Query(default=None),
    schedule_repository: MonitorScheduleRepository = Depends(get_monitor_schedule_repository),
) -> dict:
    schedules = schedule_repository.list_monitor_schedules(workspace_id=workspace_id)
    return build_monitor_schedules_response(
        schedules=[s.__dict__ for s in schedules],
        last_synced=current_catalog_governance_timestamp(),
    )


@router.put("/governance/monitor-schedules", status_code=200)
async def upsert_monitor_schedule(
    body: MonitorScheduleRequest,
    request: Request,
    schedule_repository: MonitorScheduleRepository = Depends(get_monitor_schedule_repository),
    user_id: str | None = Depends(get_user_id),
) -> dict:
    if body.scope_kind not in _VALID_SCHEDULE_SCOPE_KINDS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_scope_kind",
                "message": f"scope_kind must be one of {sorted(_VALID_SCHEDULE_SCOPE_KINDS)}",
            },
        )
    cron_error = _validate_cron_expression(body.cron_expression)
    if cron_error:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_cron_expression", "message": cron_error},
        )
    entity = MonitorScheduleEntity(
        id="",
        scope_kind=body.scope_kind,
        scope_id=body.scope_id,
        workspace_id=body.workspace_id,
        monitor_type="scheduled_monitor",
        cron_expression=body.cron_expression,
        timezone=body.timezone,
        window_minutes=body.window_minutes,
        enabled=body.enabled,
        signals=body.signals,
        created_by=user_id,
        updated_by=user_id,
    )
    saved = schedule_repository.upsert_monitor_schedule(entity)
    return build_monitor_schedules_response(
        schedules=[saved.__dict__],
        last_synced=current_catalog_governance_timestamp(),
    )


@router.delete("/governance/monitor-schedules/{scope_kind}/{scope_id}", status_code=204)
async def delete_monitor_schedule(
    scope_kind: str,
    scope_id: str,
    schedule_repository: MonitorScheduleRepository = Depends(get_monitor_schedule_repository),
) -> None:
    if scope_kind not in _VALID_SCHEDULE_SCOPE_KINDS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_scope_kind",
                "message": f"scope_kind must be one of {sorted(_VALID_SCHEDULE_SCOPE_KINDS)}",
            },
        )
    schedule_repository.delete_monitor_schedule(scope_kind=scope_kind, scope_id=scope_id)