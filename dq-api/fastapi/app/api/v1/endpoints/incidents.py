"""DQ-13 — Incident management endpoints.

POST /incidents      create incident + optionally dispatch Zammad ticket
GET  /incidents      list incidents (filterable by workspace_id, status, incident_kind, run_id)
GET  /incidents/{id} fetch a single incident
PATCH /incidents/{id} update status, assignment, or resolved_at
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from app.api.presenters.gx import extract_itsm_response_message
from app.api.presenters.gx import extract_itsm_ticket_id
from app.api.presenters.gx import extract_itsm_ticket_number
from app.api.presenters.support import build_zammad_incident_ticket_payload
from app.api.v1.endpoints.support import SupportRequestView
from app.api.v1.endpoints.support import create_support_request
from app.application.services.incident_governance_policy_loader import resolve_incident_governance_resolution
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_app_config_repository, get_incident_repository
from app.core.request_context import get_scopes
from app.core.request_context import get_user_id
from app.core.otel_metrics import increment_gx_failure
from app.domain.comment_governance import is_comment_admin
from app.domain.entities.incident import (
    IncidentEntity,
    IncidentRootCauseSuggestionEntity,
    INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_ACCEPTED,
    INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_PENDING,
    INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_REJECTED,
    INCIDENT_KIND_TECHNICAL,
    INCIDENT_KIND_FUNCTIONAL,
    VALID_INCIDENT_KINDS,
    VALID_INCIDENT_STATUSES,
    VALID_INCIDENT_SEVERITIES,
)
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import AppConfigRepository, IncidentRepository
from app.schemas.pydantic_base import SnakeModel

router = APIRouter(prefix="/incidents", tags=["incidents"])
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateIncidentRequest(SnakeModel):
    incident_kind: str = Field(
        description="Either 'technical_run_error' or 'functional_violation'."
    )
    title: str = Field(description="Short human-readable summary.")
    description: str | None = None
    severity: str | None = None  # low | medium | high | critical
    assigned_to: str | None = None
    run_id: str | None = None
    run_plan_id: str | None = None
    workspace_id: str | None = None
    scope_kind: str | None = None
    scope_id: str | None = None
    source_correlation_id: str | None = None
    source_parent_correlation_id: str | None = None
    source_request_id: str | None = None
    source_queue_message_id: str | None = None
    source_trace_id: str | None = None
    source_system: str | None = None
    # Technical run error fields
    failure_code: str | None = None
    failure_message: str | None = None
    # Functional violation fields
    violated_rule_ids: list[str] | None = None
    violation_count: int | None = None
    # Optional: create Zammad ticket immediately
    create_itsm_ticket: bool = False


class PatchIncidentRequest(SnakeModel):
    status: str | None = None
    assigned_to: str | None = None
    resolved_at: str | None = None  # ISO-8601 datetime string
    comment: str | None = None
    itsm_ticket_id: str | None = None
    itsm_ticket_number: str | None = None


class CreateIncidentRootCauseSuggestionRequest(SnakeModel):
    incident_ids: list[str] = Field(min_length=1)


class CreateIncidentCommentRequest(SnakeModel):
    comment: str
    comment_type: str = "general"


class UpdateIncidentCommentRequest(SnakeModel):
    comment: str


class IncidentCommentLockRequest(SnakeModel):
    locked: bool


def _normalize_incident_ids(incident_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for incident_id in incident_ids:
        normalized_incident_id = str(incident_id or "").strip()
        if not normalized_incident_id or normalized_incident_id in seen:
            continue
        seen.add(normalized_incident_id)
        normalized.append(normalized_incident_id)
    return normalized


def _build_root_cause_support_incident_summary(incident: IncidentEntity) -> dict[str, Any]:
    return {
        "id": incident.id,
        "incident_kind": incident.incident_kind,
        "status": incident.status,
        "title": incident.title,
        "severity": incident.severity,
        "run_id": incident.run_id,
        "run_plan_id": incident.run_plan_id,
        "workspace_id": incident.workspace_id,
        "scope_kind": incident.scope_kind,
        "scope_id": incident.scope_id,
        "source_correlation_id": incident.source_correlation_id,
        "source_parent_correlation_id": incident.source_parent_correlation_id,
        "source_request_id": incident.source_request_id,
        "source_queue_message_id": incident.source_queue_message_id,
        "source_trace_id": incident.source_trace_id,
        "source_system": incident.source_system,
        "failure_code": incident.failure_code,
        "failure_message": incident.failure_message,
        "violated_rule_ids": incident.violated_rule_ids or [],
        "violation_count": incident.violation_count,
        "assigned_to": incident.assigned_to,
        "created_at": incident.created_at,
        "updated_at": incident.updated_at,
    }


def _shared_value(values: list[str | None]) -> str | None:
    normalized = [str(value).strip() for value in values if str(value or "").strip()]
    unique = sorted(set(normalized))
    return unique[0] if len(unique) == 1 else None


def _shared_rule_ids(incidents: list[IncidentEntity]) -> list[str]:
    rule_sets: list[set[str]] = []
    for incident in incidents:
        rule_ids = {str(rule_id).strip() for rule_id in list(incident.violated_rule_ids or []) if str(rule_id).strip()}
        if rule_ids:
            rule_sets.append(rule_ids)
    if not rule_sets:
        return []
    shared_rule_ids = set.intersection(*rule_sets)
    return sorted(shared_rule_ids)


def _build_root_cause_suggestion_payload(incidents: list[IncidentEntity]) -> dict[str, Any]:
    source_correlation_id = _shared_value([incident.source_correlation_id for incident in incidents])
    source_parent_correlation_id = _shared_value([incident.source_parent_correlation_id for incident in incidents])
    run_id = _shared_value([incident.run_id for incident in incidents])
    run_plan_id = _shared_value([incident.run_plan_id for incident in incidents])
    failure_code = _shared_value([incident.failure_code for incident in incidents])
    source_system = _shared_value([incident.source_system for incident in incidents])
    scope_kind = _shared_value([incident.scope_kind for incident in incidents])
    scope_id = _shared_value([incident.scope_id for incident in incidents])
    shared_rule_ids = _shared_rule_ids(incidents)

    evidence: list[dict[str, str]] = []
    signals: dict[str, str] = {}
    if source_correlation_id:
        signals["source_correlation_id"] = source_correlation_id
        evidence.append({"label": "source_correlation_id", "value": source_correlation_id})
    if source_parent_correlation_id:
        signals["source_parent_correlation_id"] = source_parent_correlation_id
        evidence.append({"label": "source_parent_correlation_id", "value": source_parent_correlation_id})
    if run_id:
        signals["run_id"] = run_id
        evidence.append({"label": "run_id", "value": run_id})
    if run_plan_id:
        signals["run_plan_id"] = run_plan_id
        evidence.append({"label": "run_plan_id", "value": run_plan_id})
    if failure_code:
        signals["failure_code"] = failure_code
        evidence.append({"label": "failure_code", "value": failure_code})
    if source_system:
        signals["source_system"] = source_system
        evidence.append({"label": "source_system", "value": source_system})
    if scope_kind and scope_id:
        signals["scope"] = f"{scope_kind}/{scope_id}"
        evidence.append({"label": "scope", "value": f"{scope_kind}/{scope_id}"})
    if shared_rule_ids:
        signals["shared_rule_ids"] = ",".join(shared_rule_ids)
        evidence.append({"label": "shared_rule_ids", "value": ", ".join(shared_rule_ids)})

    if source_correlation_id:
        return {
            "kind": "shared_source_correlation",
            "title": "Shared source correlation chain",
            "summary": f"The selected incidents share source correlation {source_correlation_id}.",
            "confidence_score": 0.95 if len(incidents) > 1 else 0.88,
            "recommended_action": "Trace the upstream request path and review the shared correlation chain for the first failing event.",
            "evidence": evidence,
            "signals": signals,
        }

    if source_parent_correlation_id:
        return {
            "kind": "shared_parent_correlation",
            "title": "Shared parent correlation chain",
            "summary": f"The selected incidents share parent correlation {source_parent_correlation_id}.",
            "confidence_score": 0.92 if len(incidents) > 1 else 0.86,
            "recommended_action": "Review the shared parent correlation and compare the upstream dependency that spawned these incidents.",
            "evidence": evidence,
            "signals": signals,
        }

    if run_id:
        return {
            "kind": "shared_run_failure",
            "title": "Shared failing run",
            "summary": f"The selected incidents cluster around run {run_id}.",
            "confidence_score": 0.9 if len(incidents) > 1 else 0.84,
            "recommended_action": "Inspect the failing run and compare the execution trace, inputs, and downstream handoffs.",
            "evidence": evidence,
            "signals": signals,
        }

    if failure_code:
        return {
            "kind": "shared_failure_code",
            "title": f"Shared failure code {failure_code}",
            "summary": f"The selected incidents report the same failure code {failure_code}.",
            "confidence_score": 0.84 if len(incidents) > 1 else 0.78,
            "recommended_action": "Compare the failure payloads and confirm whether the same failing dependency or validation rule is responsible.",
            "evidence": evidence,
            "signals": signals,
        }

    if shared_rule_ids:
        return {
            "kind": "shared_rule_violation",
            "title": "Shared rule violation pattern",
            "summary": f"The selected incidents share violated rule id(s): {', '.join(shared_rule_ids)}.",
            "confidence_score": 0.82 if len(incidents) > 1 else 0.74,
            "recommended_action": "Review the affected rule definition and compare the shared violation evidence across incidents.",
            "evidence": evidence,
            "signals": signals,
        }

    if source_system:
        return {
            "kind": "shared_source_system",
            "title": f"Shared source system {source_system}",
            "summary": f"The selected incidents appear to originate from the same source system {source_system}.",
            "confidence_score": 0.68 if len(incidents) > 1 else 0.62,
            "recommended_action": "Review the common source system for a repeated upstream or handoff issue.",
            "evidence": evidence,
            "signals": signals,
        }

    return {
        "kind": "mixed_incident_cluster",
        "title": "Mixed incident cluster",
        "summary": "The selected incidents do not share one decisive signal, so the suggestion is to compare the source correlation, run context, and failure details together.",
        "confidence_score": 0.55 if len(incidents) > 1 else 0.5,
        "recommended_action": "Review the incidents side by side and look for the strongest shared operational signal.",
        "evidence": evidence,
        "signals": signals,
    }


def _build_root_cause_suggestion_event(
    *,
    event_type: str,
    correlation_id: str,
    changed_by: str | None,
    changes: dict[str, dict[str, str | None]],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_type": event_type,
        "changed_at": _utc_now_iso(),
        "changed_by": changed_by,
        "correlation_id": correlation_id,
        "changes": changes,
    }
    if details is not None:
        event["details"] = details
    return event


def _present_root_cause_suggestion(entity: IncidentRootCauseSuggestionEntity) -> dict[str, Any]:
    return {
        "id": entity.id,
        "workspace_id": entity.workspace_id,
        "incident_ids": entity.incident_ids,
        "incident_count": entity.incident_count,
        "suggested_root_cause": entity.suggested_root_cause,
        "status": entity.status,
        "events": entity.events,
        "created_by": entity.created_by,
        "created_at": entity.created_at,
        "updated_by": entity.updated_by,
        "updated_at": entity.updated_at,
        "accepted_at": entity.accepted_at,
        "rejected_at": entity.rejected_at,
        "assistance_requested_at": entity.assistance_requested_at,
        "assistance_request_reference_id": entity.assistance_request_reference_id,
        "assistance_request_ticket_id": entity.assistance_request_ticket_id,
        "assistance_request_ticket_number": entity.assistance_request_ticket_number,
        "assistance_request_ticket_url": entity.assistance_request_ticket_url,
        "assistance_request_ticket_system": entity.assistance_request_ticket_system,
        "assistance_request_delivery_modes": entity.assistance_request_delivery_modes,
        "assistance_request_payload": entity.assistance_request_payload,
    }


def _present_incident(entity: IncidentEntity) -> dict[str, Any]:
    comments_locked = _incident_comments_locked(entity)
    removed_comment_count = _incident_removed_comment_count(entity)
    return {
        "id": entity.id,
        "incident_kind": entity.incident_kind,
        "status": entity.status,
        "title": entity.title,
        "description": None,
        "severity": entity.severity,
        "run_id": entity.run_id,
        "run_plan_id": entity.run_plan_id,
        "workspace_id": entity.workspace_id,
        "scope_kind": entity.scope_kind,
        "scope_id": entity.scope_id,
        "source_correlation_id": entity.source_correlation_id,
        "source_parent_correlation_id": entity.source_parent_correlation_id,
        "source_request_id": entity.source_request_id,
        "source_queue_message_id": entity.source_queue_message_id,
        "source_trace_id": entity.source_trace_id,
        "source_system": entity.source_system,
        "failure_code": entity.failure_code,
        "failure_message": None,
        "violated_rule_ids": entity.violated_rule_ids,
        "violation_count": entity.violation_count,
        "itsm_ticket_id": entity.itsm_ticket_id,
        "itsm_ticket_number": entity.itsm_ticket_number,
        "assigned_to": entity.assigned_to,
        "resolved_at": entity.resolved_at,
        "comments": entity.comments,
        "comments_locked": comments_locked,
        "removed_comment_count": removed_comment_count,
        "resolution_history": entity.resolution_history,
        "created_by": entity.created_by,
        "created_at": entity.created_at,
        "updated_by": entity.updated_by,
        "updated_at": entity.updated_at,
    }


def _incident_get_current(incident_repository: IncidentRepository, incident_id: str) -> IncidentEntity:
    entity = incident_repository.get_incident(incident_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "incident_not_found",
                "message": f"Incident {incident_id!r} does not exist",
            },
        )
    return entity


def _root_cause_suggestion_get_current(
    incident_repository: IncidentRepository,
    suggestion_id: str,
) -> IncidentRootCauseSuggestionEntity:
    entity = incident_repository.get_root_cause_suggestion(suggestion_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "root_cause_suggestion_not_found",
                "message": f"Incident root cause suggestion {suggestion_id!r} does not exist",
            },
        )
    return entity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _dispatch_zammad_ticket(
    incident: IncidentEntity,
    *,
    correlation_id: str,
    config_repository: AppConfigRepository,
    assigned_to: str | None = None,
    escalation_label: str | None = None,
    escalate_after_minutes: int | None = None,
) -> tuple[str | None, str | None]:
    """Create a Zammad ticket for the incident. Returns (ticket_id, ticket_number).

    Raises HTTPException 503 if Zammad is unreachable.
    Raises HTTPException 400 if ITSM is not configured.
    """
    config = config_repository.get_app_config()
    it_system: str = getattr(config, "assistanceRequestItsmSystem", "") or ""
    endpoint_url: str = getattr(config, "assistanceRequestItsmEndpointUrl", "") or ""
    itsm_auth_token: str = getattr(config, "assistanceRequestItsmAuthToken", "") or ""

    if not endpoint_url:
        increment_gx_failure(surface="incidents_api", operation="create_incident", reason="itsm_endpoint_missing")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "itsm_endpoint_missing",
                "message": "ITSM endpoint URL is not configured",
                "correlation_id": correlation_id,
            },
        )

    if it_system.casefold() == "zammad" and not itsm_auth_token:
        increment_gx_failure(surface="incidents_api", operation="create_incident", reason="itsm_auth_token_missing")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "itsm_auth_token_missing",
                "message": "Zammad API token is not configured",
                "correlation_id": correlation_id,
            },
        )

    # Use the system email address as requester so the ticket is created under
    # a known agent account (no personal email required for system-generated incidents).
    requester_email: str = getattr(config, "assistanceRequestEmailAddress", "") or "dq-made-easy-support@jaccloud.nl"

    ticket_payload = build_zammad_incident_ticket_payload(
        incident,
        correlation_id,
        requester_email=requester_email,
        assigned_to=assigned_to,
        escalation_label=escalation_label,
        escalate_after_minutes=escalate_after_minutes,
    )

    request_headers: dict[str, str] = {}
    if it_system.casefold() == "zammad":
        request_headers["Authorization"] = f"Token token={itsm_auth_token}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(endpoint_url, json=ticket_payload, headers=request_headers)
    except Exception as exc:
        increment_gx_failure(surface="incidents_api", operation="create_incident", reason="itsm_unavailable")
        _log.exception("ITSM endpoint failed for incident %s", incident.id)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "itsm_unavailable",
                "message": f"Unable to reach {it_system or 'ITSM'} endpoint",
                "correlation_id": correlation_id,
            },
        ) from exc

    try:
        payload = response.json()
    except Exception:
        payload = {}

    if response.status_code >= 400:
        increment_gx_failure(surface="incidents_api", operation="create_incident", reason="itsm_rejected_request")
        detail_message = extract_itsm_response_message(payload) or "The ITSM endpoint rejected the incident ticket request"
        raise HTTPException(
            status_code=502,
            detail={
                "error": "itsm_rejected_request",
                "message": detail_message,
                "correlation_id": correlation_id,
            },
        )

    ticket_id = extract_itsm_ticket_id(payload)
    ticket_number = extract_itsm_ticket_number(payload)
    if not ticket_number:
        increment_gx_failure(surface="incidents_api", operation="create_incident", reason="itsm_ticket_missing")
        raise HTTPException(
            status_code=502,
            detail={
                "error": "itsm_ticket_missing",
                "message": f"{it_system or 'ITSM'} did not return a ticket number",
                "correlation_id": correlation_id,
            },
        )

    return ticket_id, ticket_number


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _resolve_incident_comment_author_name(request: Request, fallback: str | None = None) -> str:
    claims = getattr(request.state, "auth_claims", None)
    if isinstance(claims, dict):
        for key in ("name", "preferred_username", "email"):
            value = str(claims.get(key) or "").strip()
            if value:
                return value
    return str(fallback or "system").strip() or "system"


def _build_resolution_event(
    *,
    event_type: str,
    correlation_id: str,
    changed_by: str | None,
    changes: dict[str, dict[str, str | None]],
    comment: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_type": event_type,
        "changed_at": _utc_now_iso(),
        "changed_by": changed_by,
        "correlation_id": correlation_id,
        "changes": changes,
    }
    if comment is not None:
        event["comment"] = comment
    return event


def _build_comment_entry(*, correlation_id: str, changed_by: str | None, comment: str) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "author_id": changed_by,
        "author_name": changed_by,
        "comment": comment,
        "content": comment,
        "type": "general",
        "state": "new",
        "locked": False,
        "removed": False,
        "vote_count": 0,
        "edit_count": 0,
        "created_at": _utc_now_iso(),
        "commented_at": _utc_now_iso(),
        "commented_by": changed_by,
        "correlation_id": correlation_id,
    }


def _build_governed_comment_entry(
    *,
    comment_id: str,
    correlation_id: str,
    changed_by: str | None,
    author_name: str,
    comment: str,
    comment_type: str,
) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "id": comment_id,
        "author_id": changed_by,
        "author_name": author_name,
        "comment": comment,
        "content": comment,
        "type": comment_type,
        "state": "new",
        "locked": False,
        "removed": False,
        "removed_at": None,
        "removed_by": None,
        "removed_reason": None,
        "edited": False,
        "edited_at": None,
        "edited_by": None,
        "edit_count": 0,
        "vote_count": 0,
        "acknowledged_at": None,
        "acknowledged_by": None,
        "resolved_at": None,
        "resolved_by": None,
        "reopened_at": None,
        "reopened_by": None,
        "created_at": now,
        "commented_at": now,
        "commented_by": changed_by,
        "correlation_id": correlation_id,
    }


def _incident_record_owner_id(entity: IncidentEntity) -> str:
    return str(entity.created_by or "").strip()


def _incident_is_admin() -> bool:
    scopes = [str(scope).strip() for scope in get_scopes() if str(scope).strip()]
    return is_comment_admin(scopes)


def _incident_comments_locked(entity: IncidentEntity) -> bool:
    history = list(entity.resolution_history or [])
    locked = False
    for event in history:
        if not isinstance(event, dict):
            continue
        changes = event.get("changes") if isinstance(event.get("changes"), dict) else {}
        if "comments_locked" in changes:
            locked = bool(changes["comments_locked"].get("to"))
    return locked


def _incident_removed_comment_count(entity: IncidentEntity) -> int:
    return sum(1 for comment in list(entity.comments or []) if isinstance(comment, dict) and bool(comment.get("removed")))


def _incident_find_comment(comments: list[dict[str, Any]], comment_id: str) -> tuple[int, dict[str, Any]] | None:
    for index, comment in enumerate(comments):
        if str(comment.get("id") or "") == str(comment_id):
            return index, comment
    return None


def _incident_append_comment_event(
    *,
    entity: IncidentEntity,
    incident_repository: IncidentRepository,
    updated_by: str | None,
    author_name: str,
    comment_id: str,
    action: str,
    correlation_id: str,
    comment: str | None = None,
    comment_type: str | None = None,
    removed_reason: str | None = None,
) -> IncidentEntity:
    comments = list(entity.comments or [])
    found = _incident_find_comment(comments, comment_id)
    if action == "commented":
        if found is not None:
            raise HTTPException(status_code=409, detail={"error": "comment_exists", "message": "comment already exists"})
        comments.append(
            _build_governed_comment_entry(
                comment_id=comment_id,
                correlation_id=correlation_id,
                changed_by=updated_by,
                author_name=author_name,
                comment=str(comment or "").strip(),
                comment_type=str(comment_type or "general"),
            )
        )
    else:
        if found is None:
            raise HTTPException(status_code=404, detail="Not found")
        index, existing = found
        next_comment = dict(existing)
        now = _utc_now_iso()
        if action == "comment_updated":
            next_comment["content"] = str(comment or "").strip()
            next_comment["comment"] = str(comment or "").strip()
            next_comment["edited"] = True
            next_comment["edited_at"] = now
            next_comment["edited_by"] = updated_by
            next_comment["edit_count"] = int(next_comment.get("edit_count") or 0) + 1
        elif action == "comment_deleted":
            next_comment["removed"] = True
            next_comment["removed_at"] = now
            next_comment["removed_by"] = updated_by
            next_comment["removed_reason"] = removed_reason
            next_comment["content"] = "[removed]"
            next_comment["comment"] = "[removed]"
        elif action == "comment_resolved":
            next_comment["state"] = "resolved"
            next_comment["resolved_at"] = now
            next_comment["resolved_by"] = updated_by
        elif action == "comment_reopened":
            next_comment["state"] = "reopened"
            next_comment["reopened_at"] = now
            next_comment["reopened_by"] = updated_by
        elif action == "comment_acknowledged":
            next_comment["state"] = "acknowledged_by_owner"
            next_comment["acknowledged_at"] = now
            next_comment["acknowledged_by"] = updated_by
        elif action == "comment_voted_up":
            next_comment["state"] = "voted_up"
            next_comment["vote_count"] = int(next_comment.get("vote_count") or 0) + 1
        else:
            raise HTTPException(status_code=500, detail={"error": "unsupported_comment_action", "message": action})
        comments[index] = next_comment

    resolution_history = list(entity.resolution_history or [])
    resolution_history.append(
        _build_resolution_event(
            event_type=action,
            correlation_id=correlation_id,
            changed_by=updated_by,
            changes={"comment_id": {"from": None, "to": comment_id}},
            comment=comment,
        )
    )
    updates: dict[str, Any] = {**entity.model_dump(), "comments": comments, "resolution_history": resolution_history, "updated_by": updated_by}
    return incident_repository.update_incident(IncidentEntity(**updates))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_incident(
    body: CreateIncidentRequest,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None

    if body.incident_kind not in VALID_INCIDENT_KINDS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_incident_kind",
                "message": f"incident_kind must be one of {sorted(VALID_INCIDENT_KINDS)}",
                "correlation_id": correlation_id,
            },
        )

    if body.severity is not None and body.severity not in VALID_INCIDENT_SEVERITIES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_severity",
                "message": f"severity must be one of {sorted(VALID_INCIDENT_SEVERITIES)}",
                "correlation_id": correlation_id,
            },
        )

    incident_resolution = resolve_incident_governance_resolution(
        config_repository.get_app_config(),
        incident_kind=body.incident_kind,
        severity=body.severity,
        workspace_id=body.workspace_id,
        scope_kind=body.scope_kind,
    )

    assigned_to = _normalize_optional_text(body.assigned_to) or incident_resolution.assignedTo

    entity = IncidentEntity(
        id=str(uuid4()),
        incident_kind=body.incident_kind,
        title=body.title,
        description=body.description,
        severity=body.severity,
        run_id=body.run_id,
        run_plan_id=body.run_plan_id,
        workspace_id=body.workspace_id,
        scope_kind=body.scope_kind,
        scope_id=body.scope_id,
        source_correlation_id=body.source_correlation_id,
        source_parent_correlation_id=body.source_parent_correlation_id,
        source_request_id=body.source_request_id,
        source_queue_message_id=body.source_queue_message_id,
        source_trace_id=body.source_trace_id,
        source_system=body.source_system,
        failure_code=body.failure_code,
        failure_message=body.failure_message,
        violated_rule_ids=body.violated_rule_ids,
        violation_count=body.violation_count,
        assigned_to=assigned_to,
        comments=[],
        resolution_history=[
            _build_resolution_event(
                event_type="created",
                correlation_id=correlation_id,
                changed_by=user_id,
                changes={
                    "status": {"from": None, "to": "open"},
                    "assigned_to": {"from": None, "to": assigned_to},
                },
            )
        ],
        created_by=user_id,
    )

    saved = incident_repository.create_incident(entity)

    ticket_id: str | None = None
    ticket_number: str | None = None
    if body.create_itsm_ticket:
        ticket_id, ticket_number = await _dispatch_zammad_ticket(
            saved,
            correlation_id=correlation_id,
            config_repository=config_repository,
            assigned_to=saved.assigned_to,
            escalation_label=incident_resolution.escalationLabel,
            escalate_after_minutes=incident_resolution.escalateAfterMinutes,
        )
        if ticket_id or ticket_number:
            saved = incident_repository.update_incident(
                IncidentEntity(
                    **{
                        **saved.model_dump(),
                        "itsm_ticket_id": ticket_id,
                        "itsm_ticket_number": ticket_number,
                        "updated_by": user_id,
                    }
                )
            )

    return {
        "incident": _present_incident(saved),
        "correlation_id": correlation_id,
    }


@router.get("")
def list_incidents(
    workspace_id: str | None = Query(default=None),
    incident_kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    entities = incident_repository.list_incidents(
        workspace_id=workspace_id,
        incident_kind=incident_kind,
        status=status,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )
    return {
        "incidents": [_present_incident(e) for e in entities],
        "count": len(entities),
        "offset": offset,
        "limit": limit,
    }


@router.get("/root-cause-suggestions")
def list_root_cause_suggestions(
    workspace_id: str | None = Query(default=None),
    incident_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    entities = incident_repository.list_root_cause_suggestions(
        workspace_id=workspace_id,
        incident_id=incident_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "root_cause_suggestions": [_present_root_cause_suggestion(entity) for entity in entities],
        "count": len(entities),
        "offset": offset,
        "limit": limit,
    }


@router.get("/{incident_id}")
def get_incident(
    incident_id: str,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    entity = incident_repository.get_incident(incident_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "incident_not_found",
                "message": f"Incident {incident_id!r} does not exist",
            },
        )
    return {"incident": _present_incident(entity)}


@router.patch("/{incident_id}")
def patch_incident(
    incident_id: str,
    body: PatchIncidentRequest,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None

    entity = incident_repository.get_incident(incident_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "incident_not_found",
                "message": f"Incident {incident_id!r} does not exist",
                "correlation_id": correlation_id,
            },
        )

    if body.status is not None and body.status not in VALID_INCIDENT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_status",
                "message": f"status must be one of {sorted(VALID_INCIDENT_STATUSES)}",
                "correlation_id": correlation_id,
            },
        )

    comment = _normalize_optional_text(body.comment)
    if body.comment is not None and comment is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_comment",
                "message": "comment must not be empty",
                "correlation_id": correlation_id,
            },
        )

    assigned_to = _normalize_optional_text(body.assigned_to)
    if comment is not None and _incident_comments_locked(entity):
        raise HTTPException(
            status_code=409,
            detail={"error": "comments_locked", "message": "Comments are locked for this incident", "correlation_id": correlation_id},
        )

    updates: dict[str, Any] = {**entity.model_dump(), "updated_by": user_id}
    changes: dict[str, dict[str, str | None]] = {}

    if body.status is not None and body.status != entity.status:
        changes["status"] = {"from": entity.status, "to": body.status}
        updates["status"] = body.status
    if body.assigned_to is not None and assigned_to != entity.assigned_to:
        changes["assigned_to"] = {"from": entity.assigned_to, "to": assigned_to}
        updates["assigned_to"] = assigned_to
    if body.resolved_at is not None and body.resolved_at != entity.resolved_at:
        changes["resolved_at"] = {"from": entity.resolved_at, "to": body.resolved_at}
        updates["resolved_at"] = body.resolved_at
    if body.itsm_ticket_id is not None:
        updates["itsm_ticket_id"] = body.itsm_ticket_id
    if body.itsm_ticket_number is not None:
        updates["itsm_ticket_number"] = body.itsm_ticket_number

    if comment is not None:
        comments = list(entity.comments or [])
        comments.append(
            _build_governed_comment_entry(
                comment_id=str(uuid4()),
                correlation_id=correlation_id,
                changed_by=user_id,
                author_name=_resolve_incident_comment_author_name(request, fallback=str(user_id)),
                comment=comment,
                comment_type="general",
            )
        )
        updates["comments"] = comments

    if changes or comment is not None:
        resolution_history = list(entity.resolution_history or [])
        resolution_history.append(
            _build_resolution_event(
                event_type="updated",
                correlation_id=correlation_id,
                changed_by=user_id,
                changes=changes,
                comment=comment,
            )
        )
        updates["resolution_history"] = resolution_history

    updated = incident_repository.update_incident(IncidentEntity(**updates))
    return {
        "incident": _present_incident(updated),
        "correlation_id": correlation_id,
    }


@router.post("/{incident_id}/comments")
def create_incident_comment(
    incident_id: str,
    body: CreateIncidentCommentRequest,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _incident_get_current(incident_repository, incident_id)
    comment = _normalize_optional_text(body.comment)
    if not comment:
        raise HTTPException(status_code=422, detail={"error": "invalid_comment", "message": "comment must not be empty", "correlation_id": correlation_id})
    if _incident_comments_locked(entity):
        raise HTTPException(status_code=409, detail={"error": "comments_locked", "message": "Comments are locked for this incident", "correlation_id": correlation_id})

    updated = _incident_append_comment_event(
        entity=entity,
        incident_repository=incident_repository,
        updated_by=user_id,
        author_name=_resolve_incident_comment_author_name(request, fallback=str(user_id)),
        comment_id=str(uuid4()),
        action="commented",
        correlation_id=correlation_id,
        comment=comment,
        comment_type=str(body.comment_type or "general").strip() or "general",
    )
    return {"incident": _present_incident(updated), "correlation_id": correlation_id}


@router.patch("/{incident_id}/comments-lock")
def set_incident_comments_lock(
    incident_id: str,
    body: IncidentCommentLockRequest,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _incident_get_current(incident_repository, incident_id)
    owner_id = _incident_record_owner_id(entity)
    if owner_id and str(user_id).strip() != owner_id and not _incident_is_admin():
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Only the incident owner or an admin can lock comments", "correlation_id": correlation_id})

    current_locked = _incident_comments_locked(entity)
    if body.locked == current_locked:
        return {"incident": _present_incident(entity), "correlation_id": correlation_id}

    updates = {**entity.model_dump(), "updated_by": user_id}
    resolution_history = list(entity.resolution_history or [])
    resolution_history.append(
        _build_resolution_event(
            event_type="comments_locked" if body.locked else "comments_unlocked",
            correlation_id=correlation_id,
            changed_by=user_id,
            changes={"comments_locked": {"from": current_locked, "to": body.locked}},
        )
    )
    updates["resolution_history"] = resolution_history
    updated = incident_repository.update_incident(IncidentEntity(**updates))
    return {"incident": _present_incident(updated), "correlation_id": correlation_id}


@router.patch("/{incident_id}/comments/{comment_id}")
def update_incident_comment(
    incident_id: str,
    comment_id: str,
    body: UpdateIncidentCommentRequest,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _incident_get_current(incident_repository, incident_id)
    found = _incident_find_comment(list(entity.comments or []), comment_id)
    if found is None:
        raise HTTPException(status_code=404, detail={"error": "comment_not_found", "message": "Comment not found", "correlation_id": correlation_id})
    index, comment_row = found
    if str(comment_row.get("author_id") or "").strip() != str(user_id).strip():
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Only the comment author can edit this comment", "correlation_id": correlation_id})
    if bool(comment_row.get("removed")):
        raise HTTPException(status_code=409, detail={"error": "comment_removed", "message": "Comment has been removed", "correlation_id": correlation_id})

    comment_text = _normalize_optional_text(body.comment)
    if not comment_text:
        raise HTTPException(status_code=422, detail={"error": "invalid_comment", "message": "comment must not be empty", "correlation_id": correlation_id})

    comments = list(entity.comments or [])
    next_comment = dict(comment_row)
    now = _utc_now_iso()
    next_comment["content"] = comment_text
    next_comment["comment"] = comment_text
    next_comment["edited"] = True
    next_comment["edited_at"] = now
    next_comment["edited_by"] = user_id
    next_comment["edit_count"] = int(next_comment.get("edit_count") or 0) + 1
    comments[index] = next_comment

    updates = {**entity.model_dump(), "comments": comments, "updated_by": user_id}
    resolution_history = list(entity.resolution_history or [])
    resolution_history.append(
        _build_resolution_event(
            event_type="comment_updated",
            correlation_id=correlation_id,
            changed_by=user_id,
            changes={"comment_id": {"from": None, "to": comment_id}},
            comment=comment_text,
        )
    )
    updates["resolution_history"] = resolution_history
    updated = incident_repository.update_incident(IncidentEntity(**updates))
    return {"incident": _present_incident(updated), "correlation_id": correlation_id}


@router.delete("/{incident_id}/comments/{comment_id}")
def delete_incident_comment(
    incident_id: str,
    comment_id: str,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _incident_get_current(incident_repository, incident_id)
    found = _incident_find_comment(list(entity.comments or []), comment_id)
    if found is None:
        raise HTTPException(status_code=404, detail={"error": "comment_not_found", "message": "Comment not found", "correlation_id": correlation_id})
    index, comment_row = found
    if str(comment_row.get("author_id") or "").strip() != str(user_id).strip() and not _incident_is_admin():
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Only the comment author or an admin can remove this comment", "correlation_id": correlation_id})

    comments = list(entity.comments or [])
    next_comment = dict(comment_row)
    now = _utc_now_iso()
    next_comment["removed"] = True
    next_comment["removed_at"] = now
    next_comment["removed_by"] = user_id
    next_comment["removed_reason"] = "removed by author" if str(comment_row.get("author_id") or "").strip() == str(user_id).strip() else "removed by admin"
    next_comment["content"] = "[removed]"
    next_comment["comment"] = "[removed]"
    comments[index] = next_comment

    updates = {**entity.model_dump(), "comments": comments, "updated_by": user_id}
    resolution_history = list(entity.resolution_history or [])
    resolution_history.append(
        _build_resolution_event(
            event_type="comment_deleted",
            correlation_id=correlation_id,
            changed_by=user_id,
            changes={"comment_id": {"from": None, "to": comment_id}},
            comment=next_comment["content"],
        )
    )
    updates["resolution_history"] = resolution_history
    updated = incident_repository.update_incident(IncidentEntity(**updates))
    return {"incident": _present_incident(updated), "correlation_id": correlation_id}


@router.post("/{incident_id}/comments/{comment_id}/resolve")
def resolve_incident_comment(
    incident_id: str,
    comment_id: str,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _incident_get_current(incident_repository, incident_id)
    found = _incident_find_comment(list(entity.comments or []), comment_id)
    if found is None:
        raise HTTPException(status_code=404, detail={"error": "comment_not_found", "message": "Comment not found", "correlation_id": correlation_id})
    _, comment_row = found
    if str(comment_row.get("author_id") or "").strip() != str(user_id).strip():
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Only the comment author can resolve this comment", "correlation_id": correlation_id})

    comments = list(entity.comments or [])
    next_comment = dict(comment_row)
    now = _utc_now_iso()
    next_comment["state"] = "resolved"
    next_comment["resolved_at"] = now
    next_comment["resolved_by"] = user_id
    comments[found[0]] = next_comment

    updates = {**entity.model_dump(), "comments": comments, "updated_by": user_id}
    resolution_history = list(entity.resolution_history or [])
    resolution_history.append(
        _build_resolution_event(
            event_type="comment_resolved",
            correlation_id=correlation_id,
            changed_by=user_id,
            changes={"comment_id": {"from": None, "to": comment_id}},
            comment=next_comment["content"],
        )
    )
    updates["resolution_history"] = resolution_history
    updated = incident_repository.update_incident(IncidentEntity(**updates))
    return {"incident": _present_incident(updated), "correlation_id": correlation_id}


@router.post("/{incident_id}/comments/{comment_id}/reopen")
def reopen_incident_comment(
    incident_id: str,
    comment_id: str,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _incident_get_current(incident_repository, incident_id)
    found = _incident_find_comment(list(entity.comments or []), comment_id)
    if found is None:
        raise HTTPException(status_code=404, detail={"error": "comment_not_found", "message": "Comment not found", "correlation_id": correlation_id})
    _, comment_row = found
    if str(comment_row.get("author_id") or "").strip() != str(user_id).strip():
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Only the comment author can reopen this comment", "correlation_id": correlation_id})

    comments = list(entity.comments or [])
    next_comment = dict(comment_row)
    now = _utc_now_iso()
    next_comment["state"] = "reopened"
    next_comment["reopened_at"] = now
    next_comment["reopened_by"] = user_id
    comments[found[0]] = next_comment

    updates = {**entity.model_dump(), "comments": comments, "updated_by": user_id}
    resolution_history = list(entity.resolution_history or [])
    resolution_history.append(
        _build_resolution_event(
            event_type="comment_reopened",
            correlation_id=correlation_id,
            changed_by=user_id,
            changes={"comment_id": {"from": None, "to": comment_id}},
            comment=next_comment["content"],
        )
    )
    updates["resolution_history"] = resolution_history
    updated = incident_repository.update_incident(IncidentEntity(**updates))
    return {"incident": _present_incident(updated), "correlation_id": correlation_id}


@router.post("/{incident_id}/comments/{comment_id}/acknowledge")
def acknowledge_incident_comment(
    incident_id: str,
    comment_id: str,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _incident_get_current(incident_repository, incident_id)
    owner_id = _incident_record_owner_id(entity)
    if owner_id and str(user_id).strip() != owner_id and not _incident_is_admin():
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Only the incident owner or an admin can acknowledge comments", "correlation_id": correlation_id})

    found = _incident_find_comment(list(entity.comments or []), comment_id)
    if found is None:
        raise HTTPException(status_code=404, detail={"error": "comment_not_found", "message": "Comment not found", "correlation_id": correlation_id})

    comments = list(entity.comments or [])
    next_comment = dict(found[1])
    now = _utc_now_iso()
    next_comment["state"] = "acknowledged_by_owner"
    next_comment["acknowledged_at"] = now
    next_comment["acknowledged_by"] = user_id
    comments[found[0]] = next_comment

    updates = {**entity.model_dump(), "comments": comments, "updated_by": user_id}
    resolution_history = list(entity.resolution_history or [])
    resolution_history.append(
        _build_resolution_event(
            event_type="comment_acknowledged",
            correlation_id=correlation_id,
            changed_by=user_id,
            changes={"comment_id": {"from": None, "to": comment_id}},
            comment=next_comment["content"],
        )
    )
    updates["resolution_history"] = resolution_history
    updated = incident_repository.update_incident(IncidentEntity(**updates))
    return {"incident": _present_incident(updated), "correlation_id": correlation_id}


@router.post("/{incident_id}/comments/{comment_id}/vote-up")
def vote_up_incident_comment(
    incident_id: str,
    comment_id: str,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _incident_get_current(incident_repository, incident_id)
    found = _incident_find_comment(list(entity.comments or []), comment_id)
    if found is None:
        raise HTTPException(status_code=404, detail={"error": "comment_not_found", "message": "Comment not found", "correlation_id": correlation_id})

    comments = list(entity.comments or [])
    next_comment = dict(found[1])
    next_comment["state"] = "voted_up"
    next_comment["vote_count"] = int(next_comment.get("vote_count") or 0) + 1
    comments[found[0]] = next_comment

    updates = {**entity.model_dump(), "comments": comments, "updated_by": user_id}
    resolution_history = list(entity.resolution_history or [])
    resolution_history.append(
        _build_resolution_event(
            event_type="comment_voted_up",
            correlation_id=correlation_id,
            changed_by=user_id,
            changes={"comment_id": {"from": None, "to": comment_id}},
            comment=next_comment["content"],
        )
    )
    updates["resolution_history"] = resolution_history
    updated = incident_repository.update_incident(IncidentEntity(**updates))
    return {"incident": _present_incident(updated), "correlation_id": correlation_id}


@router.post("/root-cause-suggestions", status_code=201)
def create_root_cause_suggestion(
    body: CreateIncidentRootCauseSuggestionRequest,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    incident_ids = _normalize_incident_ids(body.incident_ids)
    if not incident_ids:
        raise HTTPException(status_code=422, detail={"error": "invalid_incident_ids", "message": "incident_ids must contain at least one incident id", "correlation_id": correlation_id})

    incidents: list[IncidentEntity] = []
    missing_incident_ids: list[str] = []
    for incident_id in incident_ids:
        incident = incident_repository.get_incident(incident_id)
        if incident is None:
            missing_incident_ids.append(incident_id)
            continue
        incidents.append(incident)

    if missing_incident_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "incident_not_found",
                "message": f"Incident(s) not found: {', '.join(missing_incident_ids)}",
                "correlation_id": correlation_id,
            },
        )

    workspace_ids = {str(incident.workspace_id).strip() for incident in incidents if str(incident.workspace_id or "").strip()}
    if len(workspace_ids) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "incident_workspace_mismatch",
                "message": "Selected incidents must belong to the same workspace",
                "correlation_id": correlation_id,
            },
        )

    workspace_id = next(iter(workspace_ids), None)
    suggested_root_cause = _build_root_cause_suggestion_payload(incidents)
    now = _utc_now_iso()
    entity = IncidentRootCauseSuggestionEntity(
        id=str(uuid4()),
        workspace_id=workspace_id,
        incident_ids=incident_ids,
        incident_count=len(incident_ids),
        suggested_root_cause=suggested_root_cause,
        status=INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_PENDING,
        events=[
            _build_root_cause_suggestion_event(
                event_type="created",
                correlation_id=correlation_id,
                changed_by=user_id,
                changes={
                    "status": {"from": None, "to": INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_PENDING},
                    "incident_ids": {"from": None, "to": ",".join(incident_ids)},
                },
                details={"incident_summaries": [_build_root_cause_support_incident_summary(incident) for incident in incidents]},
            )
        ],
        created_by=user_id,
        created_at=now,
        updated_by=user_id,
        updated_at=now,
    )

    saved = incident_repository.create_root_cause_suggestion(entity)
    return {"root_cause_suggestion": _present_root_cause_suggestion(saved), "correlation_id": correlation_id}


@router.get("/root-cause-suggestions/{suggestion_id}")
def get_root_cause_suggestion(
    suggestion_id: str,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    entity = _root_cause_suggestion_get_current(incident_repository, suggestion_id)
    return {"root_cause_suggestion": _present_root_cause_suggestion(entity)}


@router.post("/root-cause-suggestions/{suggestion_id}/accept")
def accept_root_cause_suggestion(
    suggestion_id: str,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _root_cause_suggestion_get_current(incident_repository, suggestion_id)
    if entity.status == INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_ACCEPTED:
        return {"root_cause_suggestion": _present_root_cause_suggestion(entity), "correlation_id": correlation_id}

    updated = incident_repository.update_root_cause_suggestion(
        IncidentRootCauseSuggestionEntity(
            **{
                **entity.model_dump(),
                "status": INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_ACCEPTED,
                "accepted_at": _utc_now_iso(),
                "rejected_at": None,
                "updated_by": user_id,
                "events": list(entity.events)
                + [
                    _build_root_cause_suggestion_event(
                        event_type="accepted",
                        correlation_id=correlation_id,
                        changed_by=user_id,
                        changes={"status": {"from": entity.status, "to": INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_ACCEPTED}},
                    )
                ],
            }
        )
    )
    return {"root_cause_suggestion": _present_root_cause_suggestion(updated), "correlation_id": correlation_id}


@router.post("/root-cause-suggestions/{suggestion_id}/reject")
def reject_root_cause_suggestion(
    suggestion_id: str,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _root_cause_suggestion_get_current(incident_repository, suggestion_id)
    if entity.status == INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_REJECTED:
        return {"root_cause_suggestion": _present_root_cause_suggestion(entity), "correlation_id": correlation_id}

    updated = incident_repository.update_root_cause_suggestion(
        IncidentRootCauseSuggestionEntity(
            **{
                **entity.model_dump(),
                "status": INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_REJECTED,
                "rejected_at": _utc_now_iso(),
                "accepted_at": None,
                "updated_by": user_id,
                "events": list(entity.events)
                + [
                    _build_root_cause_suggestion_event(
                        event_type="rejected",
                        correlation_id=correlation_id,
                        changed_by=user_id,
                        changes={"status": {"from": entity.status, "to": INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_REJECTED}},
                    )
                ],
            }
        )
    )
    return {"root_cause_suggestion": _present_root_cause_suggestion(updated), "correlation_id": correlation_id}


@router.post("/root-cause-suggestions/{suggestion_id}/assistance-request")
async def request_root_cause_assistance(
    suggestion_id: str,
    request: Request,
    incident_repository: IncidentRepository = Depends(get_incident_repository),
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated", "message": "Not authenticated", "correlation_id": correlation_id})

    entity = _root_cause_suggestion_get_current(incident_repository, suggestion_id)
    if entity.assistance_requested_at:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "assistance_request_already_created",
                "message": "An assistance request has already been created for this root cause suggestion",
                "correlation_id": correlation_id,
            },
        )

    incident_summaries: list[dict[str, Any]] = []
    for incident_id in entity.incident_ids:
        incident = incident_repository.get_incident(incident_id)
        if incident is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "incident_not_found",
                    "message": f"Incident {incident_id!r} does not exist",
                    "correlation_id": correlation_id,
                },
            )
        incident_summaries.append(_build_root_cause_support_incident_summary(incident))

    suggestion_payload = entity.suggested_root_cause
    support_request_view = SupportRequestView(
        referenceId=f"RCS-{entity.id.replace('-', '')[:12].upper()}",
        title=f"Incident root cause assistance: {suggestion_payload.get('title') or 'Suggested root cause'}",
        message="\n".join(
            part
            for part in [
                str(suggestion_payload.get("summary") or "Suggested root cause requires assistance.").strip(),
                f"Recommended action: {suggestion_payload.get('recommended_action') or 'Review the incident cluster and confirm the root cause.'}",
            ]
            if part
        ),
        source="incident_root_cause_suggestion",
        workspaceId=entity.workspace_id,
        details={
            "suggestion": suggestion_payload,
            "incident_ids": entity.incident_ids,
            "incident_summaries": incident_summaries,
        },
        metadata={
            "suggestion_id": entity.id,
            "incident_count": entity.incident_count,
            "status": entity.status,
        },
    )

    support_response = await create_support_request(
        request,
        support_request_view,
        app_config_repository,
        admin_repository,
    )

    supported_at = _utc_now_iso()
    updated = incident_repository.update_root_cause_suggestion(
        IncidentRootCauseSuggestionEntity(
            **{
                **entity.model_dump(),
                "assistance_requested_at": supported_at,
                "assistance_request_reference_id": support_response.referenceId,
                "assistance_request_ticket_id": None,
                "assistance_request_ticket_number": support_response.ticketNumber,
                "assistance_request_ticket_url": support_response.ticketUrl,
                "assistance_request_ticket_system": support_response.ticketSystem,
                "assistance_request_delivery_modes": list(support_response.deliveryModes),
                "assistance_request_payload": support_request_view.model_dump(by_alias=True),
                "updated_by": user_id,
                "events": list(entity.events)
                + [
                    _build_root_cause_suggestion_event(
                        event_type="assistance_requested",
                        correlation_id=correlation_id,
                        changed_by=user_id,
                        changes={
                            "assistance_requested_at": {"from": entity.assistance_requested_at, "to": supported_at},
                            "assistance_request_reference_id": {"from": entity.assistance_request_reference_id, "to": support_response.referenceId},
                        },
                        details={
                            "delivery_modes": list(support_response.deliveryModes),
                            "ticket_number": support_response.ticketNumber,
                            "ticket_system": support_response.ticketSystem,
                        },
                    )
                ],
            }
        )
    )

    return {
        "root_cause_suggestion": _present_root_cause_suggestion(updated),
        "support_request": support_response.model_dump(by_alias=True),
        "correlation_id": correlation_id,
    }
