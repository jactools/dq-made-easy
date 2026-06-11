from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from app.api.presenters.gx import extract_itsm_ticket_number
from app.api.presenters.gx import extract_itsm_ticket_url
from app.domain.entities.dq_result_event import DqResultCorrelationEntity
from app.domain.entities.dq_result_event import DqResultDatasetEntity
from app.domain.entities.dq_result_event import DqResultDomainEntity
from app.domain.entities.dq_result_event import DqResultEventEntity
from app.domain.entities.dq_result_event import DqResultRuleEntity
from app.domain.entities.dq_result_event import DqResultRunOutcomeEntity
from app.domain.entities.dq_result_event import DqResultScoreDimensionEntity
from app.domain.entities.sla_slo import SlaSloAdherenceEntity
from app.domain.entities.sla_slo import SlaSloDefinitionEntity
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DqResultEventRepository
from app.domain.interfaces.v1.sla_slo_repository import SlaSloRepository


@dataclass(frozen=True)
class SlaSloSummaryQuery:
    workspace_id: str | None
    status: str | None = None
    scope_kind: str | None = None
    metric_kind: str | None = None


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _lookback_start(lookback_amount: int, lookback_unit: str) -> datetime:
    normalized_unit = str(lookback_unit or "day").strip().lower()
    amount = max(int(lookback_amount or 0), 0)
    if normalized_unit in {"minute", "minutes"}:
        delta = timedelta(minutes=amount)
    elif normalized_unit in {"hour", "hours"}:
        delta = timedelta(hours=amount)
    elif normalized_unit in {"week", "weeks"}:
        delta = timedelta(weeks=amount)
    else:
        delta = timedelta(days=amount)
    return datetime.now(UTC) - delta


def _event_metric_name(metric_kind: str) -> str:
    normalized = str(metric_kind or "").strip().lower()
    if normalized in {"freshness", "completeness", "validity"}:
        return f"{normalized}_score"
    return "quality_score"


def _lookup_dimension_value(event: Any, metric_name: str) -> float | int | None:
    score_dimensions = getattr(event, "scoreDimensions", None) or []
    for dimension in score_dimensions:
        if str(getattr(dimension, "name", "") or "").strip().lower() == metric_name.lower():
            value = getattr(dimension, "value", None)
            if value is None:
                value = getattr(dimension, "normalizedValue", None)
                if isinstance(value, (int, float)):
                    return round(float(value) * 100, 2)
            return value

    run_outcome = getattr(event, "runOutcome", None)
    if run_outcome is None:
        return None
    score = getattr(run_outcome, "score", None)
    if score is not None and metric_name == "quality_score":
        return score
    if score is not None and metric_name.endswith("_score"):
        return score
    return score


def _meets_target(metric_value: float | int | None, threshold_operator: str, threshold_value: float | int) -> bool | None:
    if metric_value is None:
        return None
    if threshold_operator == "lte":
        return float(metric_value) <= float(threshold_value)
    return float(metric_value) >= float(threshold_value)


def _event_timestamp(event: Any) -> datetime:
    run_outcome = getattr(event, "runOutcome", None)
    raw_value = getattr(run_outcome, "observedAt", None) or getattr(event, "emittedAt", None)
    if raw_value:
        try:
            return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def _scope_filter_kwargs(definition: SlaSloDefinitionEntity) -> dict[str, str]:
    scope_kind = str(definition.scopeKind or "").strip().lower()
    scope_id = str(definition.scopeId or "").strip()
    if scope_kind == "dataset":
        return {"dataset_id": scope_id}
    if scope_kind == "domain":
        return {"domain_id": scope_id}
    if scope_kind == "data_product":
        return {"data_product_id": scope_id}
    if scope_kind == "rule":
        return {"rule_id": scope_id}
    return {}


def _breach_severity(definition: SlaSloDefinitionEntity) -> str:
    metric_kind = str(definition.metricKind or "").strip().lower()
    if metric_kind in {"incident_rate", "critical_rule_pass_rate"}:
        return "high"
    return "warning"


def _build_breach_event(definition: SlaSloDefinitionEntity, adherence: SlaSloAdherenceEntity) -> DqResultEventEntity:
    emitted_at = _normalize_text(adherence.latestObservedAt or adherence.currentObservedAt) or datetime.now(UTC).isoformat()
    metric_value = adherence.currentValue
    observed_event_count = int(adherence.observedEventCount or 0)
    compliant_event_count = int(adherence.compliantEventCount or 0)
    non_compliant_event_count = int(adherence.nonCompliantEventCount or 0)
    metric_name = str(definition.metricKind or "quality_score").strip() or "quality_score"
    scope_kind = str(definition.scopeKind or "").strip().lower()
    scope_id = str(definition.scopeId or "").strip()

    dataset = DqResultDatasetEntity(
        id=scope_id or definition.id,
        name=definition.name,
        workspaceId=definition.workspaceId,
        dataProductId=scope_id if scope_kind == "data_product" else None,
        dataObjectId=scope_id if scope_kind == "dataset" else None,
        dataObjectVersionId=None,
    )
    domain = DqResultDomainEntity(id=scope_id, name=definition.name) if scope_kind == "domain" and scope_id else None
    summary = adherence.summary or f"{definition.name} missed its {metric_name} target."

    return DqResultEventEntity(
        emittedAt=emitted_at,
        severity=_breach_severity(definition),
        dataset=dataset,
        domain=domain,
        rule=DqResultRuleEntity(id=definition.id, name=definition.name),
        runOutcome=DqResultRunOutcomeEntity(
            status="failed",
            result="breach",
            passed=False,
            totalCount=observed_event_count,
            validCount=compliant_event_count,
            invalidCount=non_compliant_event_count,
            warningCount=0,
            errorCount=non_compliant_event_count,
            score=metric_value,
            scoreLabel=metric_name,
            observedAt=emitted_at,
            durationMs=None,
            message=summary,
        ),
        scoreDimensions=[
            DqResultScoreDimensionEntity(
                name=metric_name,
                value=metric_value,
                maximum=100,
                threshold=definition.thresholdValue,
                passed=False,
                reason=summary,
            )
        ],
        correlation=DqResultCorrelationEntity(
            correlationId=f"sla-slo:{definition.id}:{emitted_at}",
            runId=definition.id,
            requestId=definition.workspaceId,
            queueMessageId=None,
            traceId=None,
            parentCorrelationId=None,
            sourceSystem="service-levels",
        ),
    )


async def _load_events_for_definition(
    definition: SlaSloDefinitionEntity,
    repository: DqResultEventRepository,
) -> list[Any]:
    lookback_start = _lookback_start(definition.lookbackAmount, definition.lookbackUnit)
    return await repository.list_result_events(
        emitted_after=lookback_start.isoformat(),
        limit=250,
        **_scope_filter_kwargs(definition),
    )


def _build_adherence(definition: SlaSloDefinitionEntity, events: list[Any]) -> SlaSloAdherenceEntity:
    if not events:
        return SlaSloAdherenceEntity(
            thresholdValue=definition.thresholdValue,
            thresholdOperator=definition.thresholdOperator,
            observedEventCount=0,
            compliantEventCount=0,
            nonCompliantEventCount=0,
            complianceRatePct=None,
            currentValue=None,
            currentObservedAt=None,
            latestObservedAt=None,
            meetsTarget=None,
            summary="No matching history is available yet.",
        )

    metric_kind = str(definition.metricKind or "quality_score").strip().lower()
    threshold_operator = str(definition.thresholdOperator or "gte").strip().lower()
    threshold_value = float(definition.thresholdValue)

    metric_name = _event_metric_name(metric_kind)
    ordered_events = sorted(events, key=_event_timestamp)
    latest_event = ordered_events[-1]
    latest_value = _lookup_dimension_value(latest_event, metric_name)
    if latest_value is None and metric_name != "quality_score":
        latest_value = _lookup_dimension_value(latest_event, "quality_score")

    if metric_kind == "critical_rule_pass_rate":
        compliant_count = sum(1 for event in ordered_events if bool(getattr(getattr(event, "runOutcome", None), "passed", False)))
        metric_value = round((compliant_count / len(ordered_events)) * 100, 2)
        meets_target = _meets_target(metric_value, threshold_operator, threshold_value)
        non_compliant_count = len(ordered_events) - compliant_count
        summary = f"{compliant_count} of {len(ordered_events)} runs passed in the lookback window."
        return SlaSloAdherenceEntity(
            metricValue=metric_value,
            thresholdValue=definition.thresholdValue,
            thresholdOperator=definition.thresholdOperator,
            observedEventCount=len(ordered_events),
            compliantEventCount=compliant_count,
            nonCompliantEventCount=non_compliant_count,
            complianceRatePct=metric_value,
            currentValue=metric_value,
            currentObservedAt=getattr(getattr(latest_event, "runOutcome", None), "observedAt", None) or getattr(latest_event, "emittedAt", None),
            latestObservedAt=getattr(getattr(latest_event, "runOutcome", None), "observedAt", None) or getattr(latest_event, "emittedAt", None),
            meetsTarget=meets_target,
            summary=summary,
        )

    if metric_kind == "incident_rate":
        compliant_count = sum(1 for event in ordered_events if bool(getattr(getattr(event, "runOutcome", None), "passed", False)))
        non_compliant_count = len(ordered_events) - compliant_count
        metric_value = round((non_compliant_count / len(ordered_events)) * 100, 2)
        meets_target = _meets_target(metric_value, threshold_operator, threshold_value)
        summary = f"{non_compliant_count} of {len(ordered_events)} runs failed in the lookback window."
        return SlaSloAdherenceEntity(
            metricValue=metric_value,
            thresholdValue=definition.thresholdValue,
            thresholdOperator=definition.thresholdOperator,
            observedEventCount=len(ordered_events),
            compliantEventCount=compliant_count,
            nonCompliantEventCount=non_compliant_count,
            complianceRatePct=round(100 - metric_value, 2),
            currentValue=metric_value,
            currentObservedAt=getattr(getattr(latest_event, "runOutcome", None), "observedAt", None) or getattr(latest_event, "emittedAt", None),
            latestObservedAt=getattr(getattr(latest_event, "runOutcome", None), "observedAt", None) or getattr(latest_event, "emittedAt", None),
            meetsTarget=meets_target,
            summary=summary,
        )

    metric_values: list[float | int] = []
    compliant_count = 0
    for event in ordered_events:
        current_value = _lookup_dimension_value(event, metric_name)
        if current_value is None and metric_name != "quality_score":
            current_value = _lookup_dimension_value(event, "quality_score")
        if current_value is None:
            continue
        metric_values.append(current_value)
        if _meets_target(current_value, threshold_operator, threshold_value):
            compliant_count += 1

    if not metric_values:
        return SlaSloAdherenceEntity(
            metricValue=None,
            thresholdValue=definition.thresholdValue,
            thresholdOperator=definition.thresholdOperator,
            observedEventCount=len(ordered_events),
            compliantEventCount=0,
            nonCompliantEventCount=len(ordered_events),
            complianceRatePct=None,
            currentValue=None,
            currentObservedAt=None,
            latestObservedAt=getattr(getattr(latest_event, "runOutcome", None), "observedAt", None) or getattr(latest_event, "emittedAt", None),
            meetsTarget=None,
            summary=f"No metric values were available for {definition.metricKind}.",
        )

    latest_value = metric_values[-1]
    current_value = latest_value
    current_meets_target = _meets_target(current_value, threshold_operator, threshold_value)
    compliance_rate = round((compliant_count / len(metric_values)) * 100, 2)
    summary = f"{compliant_count} of {len(metric_values)} observed runs met the {definition.metricKind} target."
    return SlaSloAdherenceEntity(
        metricValue=current_value,
        thresholdValue=definition.thresholdValue,
        thresholdOperator=definition.thresholdOperator,
        observedEventCount=len(metric_values),
        compliantEventCount=compliant_count,
        nonCompliantEventCount=len(metric_values) - compliant_count,
        complianceRatePct=compliance_rate,
        currentValue=current_value,
        currentObservedAt=getattr(getattr(latest_event, "runOutcome", None), "observedAt", None) or getattr(latest_event, "emittedAt", None),
        latestObservedAt=getattr(getattr(latest_event, "runOutcome", None), "observedAt", None) or getattr(latest_event, "emittedAt", None),
        meetsTarget=current_meets_target,
        summary=summary,
    )


async def get_sla_slo_summary(
    *,
    query: SlaSloSummaryQuery,
    repository: SlaSloRepository,
    dq_result_event_repository: DqResultEventRepository,
) -> dict[str, Any]:
    definitions = await repository.list_sla_slo_definitions(
        workspace_id=query.workspace_id,
        status=query.status,
        scope_kind=query.scope_kind,
        metric_kind=query.metric_kind,
    )

    enriched_definitions: list[SlaSloDefinitionEntity] = []
    for definition in definitions:
        events = await _load_events_for_definition(definition, dq_result_event_repository)
        adherence = _build_adherence(definition, events)
        enriched_definitions.append(definition.model_copy(update={"adherence": adherence}))

    total_definitions = len(enriched_definitions)
    active_definitions = sum(1 for definition in enriched_definitions if definition.lifecycleStatus == "active")
    draft_definitions = sum(1 for definition in enriched_definitions if definition.lifecycleStatus == "draft")
    deprecated_definitions = sum(1 for definition in enriched_definitions if definition.lifecycleStatus == "deprecated")
    approved_definitions = sum(1 for definition in enriched_definitions if definition.approvalStatus == "approved")
    compliant_definitions = sum(1 for definition in enriched_definitions if definition.adherence and definition.adherence.meetsTarget is True)
    at_risk_definitions = sum(
        1
        for definition in enriched_definitions
        if definition.lifecycleStatus == "active" and (definition.adherence is None or definition.adherence.meetsTarget is False)
    )

    return {
        "workspace_id": query.workspace_id,
        "definitions": [definition.model_dump(by_alias=True, exclude_none=True) for definition in enriched_definitions],
        "total_definitions": total_definitions,
        "active_definitions": active_definitions,
        "draft_definitions": draft_definitions,
        "approved_definitions": approved_definitions,
        "deprecated_definitions": deprecated_definitions,
        "compliant_definitions": compliant_definitions,
        "at_risk_definitions": at_risk_definitions,
    }


async def evaluate_sla_slo_breaches(
    *,
    workspace_id: str,
    repository: SlaSloRepository,
    dq_result_event_repository: DqResultEventRepository,
) -> dict[str, Any]:
    definitions = await repository.list_sla_slo_definitions(workspace_id=workspace_id, status="active")
    breaches: list[dict[str, Any]] = []
    evaluated_at = datetime.now(UTC).isoformat()

    for definition in definitions:
        events = await _load_events_for_definition(definition, dq_result_event_repository)
        adherence = _build_adherence(definition, events)
        if adherence.meetsTarget is not False:
            continue

        breach_event = await dq_result_event_repository.record_result_event(_build_breach_event(definition, adherence))
        breaches.append(
            {
                "definition_id": definition.id,
                "definition_name": definition.name,
                "scope_kind": definition.scopeKind,
                "scope_id": definition.scopeId,
                "metric_kind": definition.metricKind,
                "threshold_value": definition.thresholdValue,
                "threshold_operator": definition.thresholdOperator,
                "current_value": adherence.currentValue,
                "observed_event_count": adherence.observedEventCount,
                "emitted_at": breach_event.emittedAt,
                "correlation_id": breach_event.correlation.correlationId,
                "severity": breach_event.severity,
                "summary": adherence.summary,
            }
        )

    return {
        "workspace_id": workspace_id,
        "evaluated_at": evaluated_at,
        "evaluated_definitions": len(definitions),
        "breached_definitions": len(breaches),
        "breach_events_recorded": len(breaches),
        "breaches": breaches,
    }


async def create_sla_slo_definition(
    *,
    payload: dict[str, Any],
    repository: SlaSloRepository,
    actor_id: str | None = None,
) -> SlaSloDefinitionEntity:
    return await repository.create_sla_slo_definition(payload, actor_id=actor_id)


async def update_sla_slo_definition(
    *,
    definition_id: str,
    payload: dict[str, Any],
    repository: SlaSloRepository,
    actor_id: str | None = None,
) -> SlaSloDefinitionEntity:
    updated = await repository.update_sla_slo_definition(definition_id, payload, actor_id=actor_id)
    if updated is None:
        raise HTTPException(status_code=404, detail={"error": "sla_slo_definition_not_found", "message": "SLA/SLO definition not found"})
    return updated


async def approve_sla_slo_definition(
    *,
    definition_id: str,
    payload: dict[str, Any],
    repository: SlaSloRepository,
    app_config_repository: AppConfigRepository,
    send_itsm_request: Callable[[str, dict[str, Any], dict[str, str]], Awaitable[Any]],
    correlation_id: str,
    actor_id: str | None = None,
) -> SlaSloDefinitionEntity:
    definition = await repository.get_sla_slo_definition(definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail={"error": "sla_slo_definition_not_found", "message": "SLA/SLO definition not found"})

    app_config = app_config_repository.get_app_config()
    it_system = str(getattr(app_config, "assistanceRequestItsmSystem", "") or "").strip()
    endpoint_url = str(getattr(app_config, "assistanceRequestItsmEndpointUrl", "") or "").strip()
    itsm_auth_token = str(getattr(app_config, "assistanceRequestItsmAuthToken", "") or "").strip()

    if not it_system:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "itsm_system_missing",
                "message": "SLA/SLO ITSM system is not configured",
                "correlation_id": correlation_id,
            },
        )
    if not endpoint_url:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "itsm_endpoint_missing",
                "message": "SLA/SLO ITSM endpoint is not configured",
                "correlation_id": correlation_id,
            },
        )
    if it_system.casefold() == "zammad" and not itsm_auth_token:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "itsm_auth_token_missing",
                "message": "SLA/SLO Zammad API token is not configured",
                "correlation_id": correlation_id,
            },
        )

    if it_system.casefold() == "zammad":
        request_headers = {"Authorization": f"Token token={itsm_auth_token}"}
    else:
        request_headers = {}

    request_payload = {
        "source": "dq-made-easy",
        "request_type": "sla_slo_definition",
        "title": f"[SLA/SLO] {definition.name}",
        "body": {
            "workspace_id": definition.workspaceId,
            "scope_kind": definition.scopeKind,
            "scope_id": definition.scopeId,
            "metric_kind": definition.metricKind,
            "threshold_value": definition.thresholdValue,
            "threshold_operator": definition.thresholdOperator,
            "lookback_amount": definition.lookbackAmount,
            "lookback_unit": definition.lookbackUnit,
            "requested_by": definition.requestedBy,
            "review_notes": _normalize_text(payload.get("comments") or payload.get("review_notes") or payload.get("reviewNotes")),
            "correlation_id": correlation_id,
        },
        "correlation_id": correlation_id,
    }

    try:
        response = await send_itsm_request(endpoint_url, request_payload, request_headers)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "itsm_unavailable",
                "message": f"Unable to reach {it_system} ITSM endpoint",
                "correlation_id": correlation_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    if not getattr(response, "is_success", False):
        raise HTTPException(
            status_code=502,
            detail={
                "error": "itsm_request_failed",
                "message": f"{it_system} rejected the SLA/SLO synchronization request",
                "correlation_id": correlation_id,
                "status_code": getattr(response, "status_code", None),
            },
        )

    ticket_number = extract_itsm_ticket_number(getattr(response, "payload", None))
    if not ticket_number:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "itsm_ticket_missing",
                "message": f"{it_system} did not return a ticket number for the SLA/SLO approval",
                "correlation_id": correlation_id,
            },
        )

    ticket_url = extract_itsm_ticket_url(getattr(response, "payload", None))
    approved = await repository.approve_sla_slo_definition(
        definition_id,
        {
            "reviewed_by": actor_id,
            "reviewed_at": datetime.now(UTC).isoformat(),
            "approval_status": "approved",
            "lifecycle_status": "active",
            "itsm_system": it_system,
            "itsm_ticket_number": ticket_number,
            "itsm_ticket_url": ticket_url,
            "itsm_ticket_id": ticket_number,
            "approved_by": actor_id,
            "approved_at": datetime.now(UTC).isoformat(),
            "comments": payload.get("comments") or payload.get("review_notes") or payload.get("reviewNotes"),
        },
        actor_id=actor_id,
    )
    if approved is None:
        raise HTTPException(status_code=404, detail={"error": "sla_slo_definition_not_found", "message": "SLA/SLO definition not found"})
    return approved
