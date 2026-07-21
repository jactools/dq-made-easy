from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from app.api.v1.endpoints import exception_reports as exception_reports_endpoints
from app.api.v1.endpoints import ontology as ontology_endpoints
from app.api.v1.endpoints import rules as rules_endpoints
from app.api.v1.schemas import BatchValidationRequestView
from app.api.v1.schemas import BatchValidationResponseView
from app.api.v1.schemas import DataObjectView
from app.api.v1.schemas import DeliveryExceptionSummaryView
from app.api.v1.schemas.ontology_view import OntologyGraphQueryRequestView
from app.api.v1.schemas.ontology_view import OntologyGraphQueryResultView
from app.application.services.agent_dispatch_service import AgentDispatchError
from app.application.services.agent_dispatch_service import build_webhook_payload
from app.application.services.agent_dispatch_service import dispatch_webhook
from app.core.auth import has_required_scope
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_agent_request_audit_repository
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_exception_reason_analytics_projection_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_ontology_graph_repository
from app.core.dependencies import get_rules_repository
from app.core.dependencies import get_sla_slo_repository
from app.core.dependencies import get_validation_run_repository
from app.core.request_context import get_scopes
from app.core.request_context import get_user_id
from app.domain.entities.agent_request_audit import AgentRequestAuditEntity
from app.domain.entities.agent_request_audit import build_agent_request_audit_entity
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import AgentRequestAuditRepository
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import DataAssetRepository
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import OntologyGraphRepository
from app.domain.interfaces import RulesRepository
from app.domain.interfaces import ValidationRunRepository
from app.domain.interfaces import SlaSloRepository
from app.schemas.pydantic_base import SnakeModel
from dq_domain_validation import GxExecutionStatus
from dq_domain_validation import LookbackUnit


router = APIRouter(tags=["agent"])

_HEADER_REQUEST_ID = "x-request-id"
_HEADER_CORRELATION_ID = "x-correlation-id"
_HEADER_AGENT_TYPE = "x-agent-type"
_HEADER_AGENT_SOURCE = "x-agent-source"
_HEADER_AGENT_INSTANCE_ID = "x-agent-instance-id"
_HEADER_FORWARDED_FOR = "x-forwarded-for"
_HEADER_USER_AGENT = "user-agent"

_DEFAULT_AGENT_PLATFORM_ALLOWLIST = ["mistral_ai", "microsoft_copilot"]

_AGENT_PLATFORM_CONTRACTS: dict[str, dict[str, Any]] = {
    "mistral_ai": {
        "description": "Mistral AI external assistant integration via operator-owned webhook or job dispatch.",
        "dispatch_modes": ["webhook", "job"],
        "webhook_contract": {
            "required_fields": ["webhook_url", "event_type", "payload"],
            "optional_fields": ["webhook_headers"],
        },
        "job_contract": {
            "required_fields": ["job_name", "event_type", "payload"],
            "optional_fields": ["job_arguments"],
        },
    },
    "microsoft_copilot": {
        "description": "Microsoft Copilot integration via operator-owned webhook or job dispatch.",
        "dispatch_modes": ["webhook", "job"],
        "webhook_contract": {
            "required_fields": ["webhook_url", "event_type", "payload"],
            "optional_fields": ["webhook_headers"],
        },
        "job_contract": {
            "required_fields": ["job_name", "event_type", "payload"],
            "optional_fields": ["job_arguments"],
        },
    },
    "github_copilot": {
        "description": "GitHub Copilot integration contract via operator-owned webhook or job dispatch.",
        "dispatch_modes": ["webhook", "job"],
        "webhook_contract": {
            "required_fields": ["webhook_url", "event_type", "payload"],
            "optional_fields": ["webhook_headers"],
        },
        "job_contract": {
            "required_fields": ["job_name", "event_type", "payload"],
            "optional_fields": ["job_arguments"],
        },
    },
    "slack": {
        "description": "Slack integration contract via operator-owned webhook or job dispatch.",
        "dispatch_modes": ["webhook", "job"],
        "webhook_contract": {
            "required_fields": ["webhook_url", "event_type", "payload"],
            "optional_fields": ["webhook_headers"],
        },
        "job_contract": {
            "required_fields": ["job_name", "event_type", "payload"],
            "optional_fields": ["job_arguments"],
        },
    },
    "airflow": {
        "description": "Airflow integration contract via operator-owned webhook or job dispatch.",
        "dispatch_modes": ["webhook", "job"],
        "webhook_contract": {
            "required_fields": ["webhook_url", "event_type", "payload"],
            "optional_fields": ["webhook_headers"],
        },
        "job_contract": {
            "required_fields": ["job_name", "event_type", "payload"],
            "optional_fields": ["job_arguments"],
        },
    },
    "dagster": {
        "description": "Dagster integration contract via operator-owned webhook or job dispatch.",
        "dispatch_modes": ["webhook", "job"],
        "webhook_contract": {
            "required_fields": ["webhook_url", "event_type", "payload"],
            "optional_fields": ["webhook_headers"],
        },
        "job_contract": {
            "required_fields": ["job_name", "event_type", "payload"],
            "optional_fields": ["job_arguments"],
        },
    },
}


class AgentRuleExecutionRequestView(SnakeModel):
    rule_ids: list[str] = Field(min_length=1)
    workspace: str | None = None


class AgentMetadataLookupResponseView(SnakeModel):
    data_objects: list[DataObjectView] = Field(default_factory=list)


class AgentOpenApiSpecView(SnakeModel):
    openapi: str
    info: dict[str, Any] = Field(default_factory=dict)
    paths: dict[str, Any] = Field(default_factory=dict)


class AgentAuditEventView(SnakeModel):
    id: str
    request_id: str
    timestamp: str
    action: str
    endpoint: str
    method: str
    actor_id: str | None = None
    correlation_id: str | None = None
    agent_type: str | None = None
    agent_source: str | None = None
    agent_instance_id: str | None = None
    request_origin: str | None = None
    user_agent: str | None = None
    response_type: str
    status_code: int
    success: bool
    details: dict[str, Any] = Field(default_factory=dict)
    governance_context_ref: dict[str, Any] = Field(default_factory=dict)


class AgentAuditEventCreateView(SnakeModel):
    action: str
    endpoint: str
    method: str
    actor_id: str | None = None
    correlation_id: str | None = None
    agent_type: str | None = None
    agent_source: str | None = None
    agent_instance_id: str | None = None
    request_origin: str | None = None
    user_agent: str | None = None
    response_type: str
    status_code: int
    success: bool
    request_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AgentAuditEventListView(SnakeModel):
    events: list[AgentAuditEventView] = Field(default_factory=list)
    governance_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentPlatformIntegrationContractView(SnakeModel):
    platform: str
    description: str
    dispatch_modes: list[str] = Field(default_factory=list)
    webhook_contract: dict[str, Any] | None = None
    job_contract: dict[str, Any] | None = None
    allowlisted: bool


class AgentPlatformIntegrationContractsView(SnakeModel):
    allowlisted_platforms: list[str] = Field(default_factory=list)
    contracts: list[AgentPlatformIntegrationContractView] = Field(default_factory=list)


class AgentPlatformDispatchRequestView(SnakeModel):
    platform: str
    dispatch_mode: str
    event_type: str
    webhook_url: str | None = None
    webhook_headers: dict[str, str] = Field(default_factory=dict)
    job_name: str | None = None
    job_arguments: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentPlatformDispatchResponseView(SnakeModel):
    dispatch_id: str
    status: str  # accepted, delivered, failed
    platform: str
    dispatch_mode: str
    event_type: str
    target: dict[str, Any] = Field(default_factory=dict)
    queued_at: str
    delivered_at: str | None = None
    delivery_result: dict[str, Any] | None = None
    contract_version: str = "1.0"


class AgentDecisionContextView(SnakeModel):
    rule_context: dict[str, Any] = Field(default_factory=dict)
    governance_context: dict[str, Any] = Field(default_factory=dict)
    lineage_context: dict[str, Any] = Field(default_factory=dict)
    business_context: dict[str, Any] = Field(default_factory=dict)
    sla_thresholds: list[dict[str, Any]] = Field(default_factory=list)
    explanation_payload: dict[str, Any] = Field(default_factory=dict)
    remediation_audit_trail: dict[str, Any] = Field(default_factory=dict)


def _require_any_scope(scopes: list[str], *, required_scopes: list[str]) -> None:
    if has_required_scope(scopes, required_scopes):
        return

    raise HTTPException(
        status_code=403,
        detail={
            "error": "insufficient_scope",
            "message": "Missing required scope for agent endpoint",
            "required_scopes": required_scopes,
        },
    )


def _header_value(request: Request, name: str) -> str | None:
    value = str(request.headers.get(name) or "").strip()
    return value or None


def _request_origin(request: Request) -> str | None:
    forwarded_for = _header_value(request, _HEADER_FORWARDED_FOR)
    if forwarded_for:
        return str(forwarded_for.split(",", 1)[0]).strip() or None
    if request.client is not None:
        host = str(getattr(request.client, "host", "") or "").strip()
        return host or None
    return None


def _agent_identity(request: Request) -> dict[str, str | None]:
    return {
        "agent_type": _header_value(request, _HEADER_AGENT_TYPE),
        "agent_source": _header_value(request, _HEADER_AGENT_SOURCE),
        "agent_instance_id": _header_value(request, _HEADER_AGENT_INSTANCE_ID),
        "request_origin": _request_origin(request),
    }


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_agent_access_policy(app_config: Any) -> dict[str, Any]:
    raw_policy = getattr(app_config, "agentAccessPolicy", None)
    if raw_policy is None:
        return {"defaultAction": "deny", "allowedAgents": []}
    if not isinstance(raw_policy, dict):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "invalid_agent_access_policy",
                "message": "agent_access_policy must be an object",
            },
        )

    default_action = str(raw_policy.get("defaultAction") or raw_policy.get("default_action") or "deny").strip().lower()
    if default_action not in {"deny", "allow"}:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "invalid_agent_access_policy",
                "message": "agent_access_policy.default_action must be deny or allow",
            },
        )

    allowed_agents = raw_policy.get("allowedAgents")
    if allowed_agents is None:
        allowed_agents = raw_policy.get("allowed_agents", [])
    if not isinstance(allowed_agents, list):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "invalid_agent_access_policy",
                "message": "agent_access_policy.allowed_agents must be a list",
            },
        )

    normalized_agents: list[dict[str, str]] = []
    for index, entry in enumerate(allowed_agents):
        if not isinstance(entry, dict):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "invalid_agent_access_policy",
                    "message": f"agent_access_policy.allowed_agents[{index}] must be an object",
                },
            )

        normalized_entry = {
            "agent_type": _as_str(entry.get("agent_type") or entry.get("agentType")),
            "agent_source": _as_str(entry.get("agent_source") or entry.get("agentSource")),
            "agent_instance_id": _as_str(entry.get("agent_instance_id") or entry.get("agentInstanceId")),
            "request_origin": _as_str(entry.get("request_origin") or entry.get("requestOrigin")),
        }
        if not any(normalized_entry.values()):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "invalid_agent_access_policy",
                    "message": f"agent_access_policy.allowed_agents[{index}] must define at least one selector",
                },
            )

        normalized_agents.append({k: v for k, v in normalized_entry.items() if v is not None})

    return {
        "default_action": default_action,
        "allowed_agents": normalized_agents,
    }


def _extract_agent_platform_allowlist(app_config: Any) -> list[str]:
    raw_allowlist = getattr(app_config, "agentPlatformAllowlist", None)
    if raw_allowlist is None:
        raw_allowlist = _DEFAULT_AGENT_PLATFORM_ALLOWLIST

    if not isinstance(raw_allowlist, list):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "invalid_agent_platform_allowlist",
                "message": "agent_platform_allowlist must be a list",
            },
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_allowlist):
        platform = _as_str(item)
        if platform is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "invalid_agent_platform_allowlist",
                    "message": f"agent_platform_allowlist[{index}] must be a non-empty string",
                },
            )
        canonical_platform = platform.lower()
        if canonical_platform in seen:
            continue
        seen.add(canonical_platform)
        normalized.append(canonical_platform)

    return normalized


def _integration_contract_views(allowlisted_platforms: list[str]) -> list[AgentPlatformIntegrationContractView]:
    allowlisted = set(allowlisted_platforms)
    contracts: list[AgentPlatformIntegrationContractView] = []

    for platform, definition in sorted(_AGENT_PLATFORM_CONTRACTS.items()):
        contracts.append(
            AgentPlatformIntegrationContractView.model_validate(
                {
                    "platform": platform,
                    "description": str(definition.get("description") or ""),
                    "dispatch_modes": list(definition.get("dispatch_modes") or []),
                    "webhook_contract": definition.get("webhook_contract"),
                    "job_contract": definition.get("job_contract"),
                    "allowlisted": platform in allowlisted,
                }
            )
        )

    return contracts


def _validate_platform_dispatch(
    *,
    request: AgentPlatformDispatchRequestView,
    allowlisted_platforms: list[str],
) -> tuple[str, str, dict[str, Any]]:
    platform = str(request.platform or "").strip().lower()
    if not platform:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_agent_platform",
                "message": "platform is required",
            },
        )

    definition = _AGENT_PLATFORM_CONTRACTS.get(platform)
    if definition is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_agent_platform",
                "message": f"Unsupported agent platform '{platform}'",
            },
        )

    if platform not in set(allowlisted_platforms):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "agent_platform_not_allowed",
                "message": f"Platform '{platform}' is not allowlisted",
            },
        )

    dispatch_mode = str(request.dispatch_mode or "").strip().lower()
    supported_dispatch_modes = set(str(item).strip().lower() for item in list(definition.get("dispatch_modes") or []))
    if dispatch_mode not in supported_dispatch_modes:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_dispatch_mode",
                "message": f"dispatch_mode must be one of {sorted(supported_dispatch_modes)}",
            },
        )

    if dispatch_mode == "webhook":
        webhook_url = str(request.webhook_url or "").strip()
        if not webhook_url:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "missing_webhook_url",
                    "message": "webhook_url is required when dispatch_mode is webhook",
                },
            )
        return platform, dispatch_mode, {
            "webhook_url": webhook_url,
            "header_keys": sorted(request.webhook_headers.keys()),
        }

    job_name = str(request.job_name or "").strip()
    if not job_name:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_job_name",
                "message": "job_name is required when dispatch_mode is job",
            },
        )
    return platform, dispatch_mode, {
        "job_name": job_name,
        "job_argument_keys": sorted(request.job_arguments.keys()),
    }


def _serialize_rule_context(rule: Any) -> dict[str, Any]:
    taxonomy = getattr(rule, "taxonomy", None)
    return {
        "id": str(getattr(rule, "id", "") or ""),
        "name": str(getattr(rule, "name", "") or ""),
        "description": getattr(rule, "description", None),
        "workspace": getattr(rule, "workspace", None),
        "active": bool(getattr(rule, "active", False)),
        "lifecycle_status": getattr(rule, "lifecycle_status", None),
        "check_type": getattr(rule, "check_type", None),
        "dimension": getattr(rule, "dimension", None),
        "taxonomy": taxonomy.model_dump(mode="python") if hasattr(taxonomy, "model_dump") else dict(taxonomy or {}),
        "tag_ids": list(getattr(rule, "tag_ids", []) or []),
    }


def _serialize_business_context(asset: Any | None, rule: Any) -> dict[str, Any]:
    business_context = getattr(asset, "business_context", None) if asset is not None else None
    business_context_payload = (
        business_context.model_dump(mode="python")
        if hasattr(business_context, "model_dump")
        else dict(business_context or {})
    )
    if not business_context_payload:
        business_context_payload = {
            "dataset_id": None,
            "data_product_id": None,
            "domain": getattr(getattr(rule, "taxonomy", None), "domain", None),
            "owner": getattr(getattr(rule, "taxonomy", None), "owner", None),
            "purpose": None,
            "steward": getattr(getattr(rule, "taxonomy", None), "data_steward", None),
            "criticality": None,
            "tags": list(getattr(rule, "tag_ids", []) or []),
            "business_definitions": [],
            "lineage_references": [],
            "validation_suites": [],
            "validation_plans": [],
            "consumers": [],
        }
    return business_context_payload


def _serialize_lineage_context(asset: Any | None, lineage_snapshots: list[Any]) -> dict[str, Any]:
    latest_snapshot = lineage_snapshots[0] if lineage_snapshots else None
    return {
        "data_asset": asset.model_dump(mode="python") if hasattr(asset, "model_dump") else (dict(asset or {}) if asset is not None else None),
        "latest_snapshot": latest_snapshot.model_dump(mode="python") if hasattr(latest_snapshot, "model_dump") else (dict(latest_snapshot or {}) if latest_snapshot is not None else None),
        "snapshot_count": len(lineage_snapshots),
        "snapshots": [
            snapshot.model_dump(mode="python") if hasattr(snapshot, "model_dump") else dict(snapshot or {})
            for snapshot in lineage_snapshots
        ],
    }


def _sort_by_timestamp_desc(items: list[Any], *, timestamp_fields: tuple[str, ...]) -> list[Any]:
    def _item_timestamp(item: Any) -> str:
        for field_name in timestamp_fields:
            value = getattr(item, field_name, None)
            if value:
                return str(value)
        return ""

    return sorted(items, key=_item_timestamp, reverse=True)


def _serialize_sla_threshold(definition: Any) -> dict[str, Any]:
    adherence = getattr(definition, "adherence", None)
    return {
        "id": getattr(definition, "id", None),
        "name": getattr(definition, "name", None),
        "description": getattr(definition, "description", None),
        "scope_kind": getattr(definition, "scopeKind", None),
        "scope_id": getattr(definition, "scopeId", None),
        "metric_kind": getattr(definition, "metricKind", None),
        "threshold_value": getattr(definition, "thresholdValue", None),
        "threshold_operator": getattr(definition, "thresholdOperator", None),
        "lookback_amount": getattr(definition, "lookbackAmount", None),
        "lookback_unit": getattr(definition, "lookbackUnit", None),
        "lifecycle_status": getattr(definition, "lifecycleStatus", None),
        "approval_status": getattr(definition, "approvalStatus", None),
        "adherence": adherence.model_dump(mode="python") if hasattr(adherence, "model_dump") else (dict(adherence or {}) if adherence is not None else None),
    }


def _build_explanation_payload(
    *,
    rule: Any,
    business_context: dict[str, Any],
    lineage_context: dict[str, Any],
    sla_thresholds: list[dict[str, Any]],
    remediation_audit_trail: dict[str, Any],
) -> dict[str, Any]:
    signals = [
        f"rule:{getattr(rule, 'id', '')}",
        f"workspace:{getattr(rule, 'workspace', '')}",
    ]
    if business_context.get("domain"):
        signals.append(f"domain:{business_context['domain']}")
    if business_context.get("data_product_id"):
        signals.append(f"data_product:{business_context['data_product_id']}")
    if lineage_context.get("snapshot_count"):
        signals.append(f"lineage_snapshots:{lineage_context['snapshot_count']}")
    if sla_thresholds:
        signals.append(f"sla_thresholds:{len(sla_thresholds)}")
    if remediation_audit_trail.get("recent_events"):
        signals.append(f"recent_agent_events:{len(remediation_audit_trail['recent_events'])}")

    recommended_actions = [
        "Review the latest lineage snapshot before changing the rule or its upstream sources.",
        "Check the active SLA thresholds that apply to this workspace and business context.",
        "Inspect the remediation audit trail for the most recent agent-triggered actions.",
    ]
    if business_context.get("criticality") == "high":
        recommended_actions.insert(0, "Prioritize this decision because the asset criticality is high.")

    return {
        "summary": f"Decision context for rule {getattr(rule, 'name', getattr(rule, 'id', 'unknown'))}.",
        "signals": signals,
        "recommended_actions": recommended_actions,
        "evidence_counts": {
            "sla_threshold_count": len(sla_thresholds),
            "lineage_snapshot_count": lineage_context.get("snapshot_count", 0),
            "recent_agent_event_count": len(remediation_audit_trail.get("recent_events", [])),
            "rule_status_history_count": len(remediation_audit_trail.get("rule_status_history", [])),
        },
    }


def _agent_matches_allow_entry(identity: dict[str, str | None], allow_entry: dict[str, str]) -> bool:
    for key, expected in allow_entry.items():
        actual = identity.get(key)
        if actual != expected:
            return False
    return True


def _require_allowed_agent(request: Request, app_config: Any) -> None:
    policy = _extract_agent_access_policy(app_config)
    identity = _agent_identity(request)

    for allow_entry in policy["allowed_agents"]:
        if _agent_matches_allow_entry(identity, allow_entry):
            return

    if policy["default_action"] == "allow":
        return

    raise HTTPException(
        status_code=403,
        detail={
            "error": "agent_not_allowed",
            "message": "Agent request denied by app admin access policy",
            "agent_identity": identity,
        },
    )


def _error_code(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        raw = detail.get("error")
        if raw is not None:
            return str(raw).strip().lower()
    return ""


def _classify_error_response_type(exc: HTTPException) -> str:
    error_code = _error_code(exc)
    if error_code == "agent_not_allowed":
        return "agent_denied_response"
    if error_code == "insufficient_scope":
        return "insufficient_scope_response"
    if error_code == "validation_failed":
        return "validation_error_response"
    if error_code == "agent_platform_not_allowed":
        return "platform_denied_response"
    if error_code in {
        "unsupported_agent_platform",
        "unsupported_dispatch_mode",
        "missing_webhook_url",
        "missing_job_name",
        "invalid_event_type",
    }:
        return "integration_validation_error_response"
    if error_code == "webhook_dispatch_failed":
        return "integration_dispatch_failed_response"
    if error_code in {
        "repository_unavailable",
        "downstream_unavailable",
        "session_store_unavailable",
        "invalid_agent_access_policy",
        "invalid_agent_platform_allowlist",
    }:
        return "service_unavailable_response"
    if error_code == "not_found":
        return "not_found_response"

    if exc.status_code == 401:
        return "unauthorized_response"
    if exc.status_code == 403:
        return "forbidden_response"
    if exc.status_code == 404:
        return "not_found_response"
    if exc.status_code == 422:
        return "validation_error_response"
    if exc.status_code >= 500:
        return "server_error_response"
    return "error_response"


def _build_governance_context_ref(details: dict[str, Any]) -> dict[str, Any]:
    """Derive governance context references from audit event details.

    Returns enough context for auditors to navigate to the full
    governance / lineage / SLA explanation via the decision-context endpoint.
    """
    rule_ids: list[str] = []
    if isinstance(details.get("rule_ids"), list):
        rule_ids = [str(r) for r in details["rule_ids"]]
    elif details.get("rule_id"):
        rule_ids = [str(details["rule_id"])]
    workspace: str | None = details.get("workspace") or details.get("workspace_id") or None
    return {
        "rule_ids": rule_ids,
        "decision_context_endpoints": [
            f"/agent/v1/context/decisions/{rule_id}" for rule_id in rule_ids
        ],
        "workspace": workspace,
        "lineage_context_available": bool(rule_ids),
        "sla_context_available": bool(rule_ids),
        "explanation_ref": (
            f"/agent/v1/context/decisions/{rule_ids[0]}" if rule_ids else None
        ),
    }


def _build_agent_audit_event_view(event: AgentRequestAuditEntity) -> AgentAuditEventView:
    raw = event.model_dump(mode="python")
    raw["governance_context_ref"] = _build_governance_context_ref(raw.get("details") or {})
    return AgentAuditEventView.model_validate(raw)


async def _record_agent_audit_event(
    *,
    request: Request,
    repository: AgentRequestAuditRepository,
    action: str,
    response_type: str,
    status_code: int,
    success: bool,
    actor_id: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    event = build_agent_request_audit_entity(
        action=action,
        endpoint=str(request.url.path),
        method=str(request.method),
        response_type=response_type,
        status_code=status_code,
        success=success,
        request_id=_header_value(request, _HEADER_REQUEST_ID),
        actor_id=actor_id,
        correlation_id=_header_value(request, _HEADER_CORRELATION_ID),
        agent_type=_header_value(request, _HEADER_AGENT_TYPE),
        agent_source=_header_value(request, _HEADER_AGENT_SOURCE),
        agent_instance_id=_header_value(request, _HEADER_AGENT_INSTANCE_ID),
        request_origin=_request_origin(request),
        user_agent=_header_value(request, _HEADER_USER_AGENT),
        details=details,
    )
    await repository.record_event(event)


@router.post(
    "/rules/execute-batch",
    response_model=BatchValidationResponseView,
    responses={
        200: {"description": "Batch rule execution/validation response for agent workflows."},
        403: {"description": "Insufficient scope or agent not allowed."},
    },
)
async def execute_rules_batch_for_agent(
    request: Request,
    body: AgentRuleExecutionRequestView,
    scopes: list[str] = Depends(get_scopes),
    repository: RulesRepository = Depends(get_rules_repository),
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    run_repository: ValidationRunRepository = Depends(get_validation_run_repository),
    user_id: str = Depends(get_user_id),
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
) -> BatchValidationResponseView:
    try:
        _require_any_scope(scopes, required_scopes=["dq:rules:write"])
        _require_allowed_agent(request, config_repository.get_app_config())

        response = await rules_endpoints.validate_rules_batch(
            body=BatchValidationRequestView.model_validate(
                {
                    "rule_ids": body.rule_ids,
                    "workspace": body.workspace,
                }
            ),
            repository=repository,
            catalog_repository=catalog_repository,
            config_repository=config_repository,
            run_repository=run_repository,
            user_id=user_id,
        )
    except HTTPException as exc:
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="execute_rules_batch",
            response_type=_classify_error_response_type(exc),
            status_code=exc.status_code,
            success=False,
            actor_id=user_id,
            details={"workspace": body.workspace, "rule_id_count": len(body.rule_ids)},
        )
        raise

    await _record_agent_audit_event(
        request=request,
        repository=audit_repository,
        action="execute_rules_batch",
        response_type="batch_validation_response",
        status_code=200,
        success=True,
        actor_id=user_id,
        details={"workspace": body.workspace, "rule_id_count": len(body.rule_ids)},
    )
    return response


@router.get(
    "/integrations/contracts",
    response_model=AgentPlatformIntegrationContractsView,
    responses={
        200: {"description": "List external agent platform integration contracts and current allowlist."},
        403: {"description": "Insufficient scope or agent not allowed."},
        503: {"description": "Invalid or unavailable platform allowlist configuration."},
    },
)
async def list_agent_platform_integration_contracts(
    request: Request,
    scopes: list[str] = Depends(get_scopes),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    user_id: str = Depends(get_user_id),
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
) -> AgentPlatformIntegrationContractsView:
    try:
        _require_any_scope(scopes, required_scopes=["dq:rules:read"])
        app_config = config_repository.get_app_config()
        _require_allowed_agent(request, app_config)
        allowlisted_platforms = _extract_agent_platform_allowlist(app_config)

        response = AgentPlatformIntegrationContractsView.model_validate(
            {
                "allowlisted_platforms": allowlisted_platforms,
                "contracts": _integration_contract_views(allowlisted_platforms),
            }
        )
    except HTTPException as exc:
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="list_integration_contracts",
            response_type=_classify_error_response_type(exc),
            status_code=exc.status_code,
            success=False,
            actor_id=user_id,
        )
        raise

    await _record_agent_audit_event(
        request=request,
        repository=audit_repository,
        action="list_integration_contracts",
        response_type="integration_contracts_response",
        status_code=200,
        success=True,
        actor_id=user_id,
        details={
            "allowlisted_platform_count": len(response.allowlisted_platforms),
            "contract_count": len(response.contracts),
        },
    )
    return response


@router.post(
    "/integrations/dispatches",
    response_model=AgentPlatformDispatchResponseView,
    responses={
        200: {"description": "Queue an external agent platform dispatch through operator-owned webhook or job contract."},
        403: {"description": "Insufficient scope, agent not allowed, or platform not allowlisted."},
        422: {"description": "Unsupported platform or invalid dispatch contract payload."},
        503: {"description": "Invalid or unavailable platform allowlist configuration."},
    },
)
async def dispatch_agent_platform_integration(
    request: Request,
    body: AgentPlatformDispatchRequestView,
    scopes: list[str] = Depends(get_scopes),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    user_id: str = Depends(get_user_id),
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
) -> AgentPlatformDispatchResponseView:
    try:
        _require_any_scope(scopes, required_scopes=["dq:rules:write"])
        app_config = config_repository.get_app_config()
        _require_allowed_agent(request, app_config)
        allowlisted_platforms = _extract_agent_platform_allowlist(app_config)

        event_type = str(body.event_type or "").strip()
        if not event_type:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_event_type",
                    "message": "event_type is required",
                },
            )

        platform, dispatch_mode, target = _validate_platform_dispatch(
            request=body,
            allowlisted_platforms=allowlisted_platforms,
        )

        queued_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if dispatch_mode == "webhook":
            webhook_url = str(target.get("webhook_url") or "").strip()
            webhook_headers = dict(body.webhook_headers or {})
            dispatch_id = f"agent-dispatch-{uuid4().hex}"

            outbound_payload = build_webhook_payload(
                platform=platform,
                event_type=event_type,
                payload=body.payload,
                dispatch_id=dispatch_id,
            )

            delivery_result = await dispatch_webhook(
                webhook_url=webhook_url,
                payload=outbound_payload,
                webhook_headers=webhook_headers if webhook_headers else None,
            )

            response = AgentPlatformDispatchResponseView.model_validate(
                {
                    "dispatch_id": delivery_result.dispatch_id,
                    "status": delivery_result.status,
                    "platform": platform,
                    "dispatch_mode": dispatch_mode,
                    "event_type": event_type,
                    "target": target,
                    "queued_at": queued_at,
                    "delivered_at": queued_at if delivery_result.status == "delivered" else None,
                    "delivery_result": delivery_result.as_dict(),
                    "contract_version": "1.0",
                }
            )
        else:
            # Job dispatch mode: accept for deferred execution
            response = AgentPlatformDispatchResponseView.model_validate(
                {
                    "dispatch_id": f"agent-dispatch-{uuid4().hex}",
                    "status": "accepted",
                    "platform": platform,
                    "dispatch_mode": dispatch_mode,
                    "event_type": event_type,
                    "target": target,
                    "queued_at": queued_at,
                    "contract_version": "1.0",
                }
            )
    except AgentDispatchError as exc:
        # Webhook delivery failed after retries — return 502 so the
        # caller knows the dispatch did not complete successfully.
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="dispatch_platform_integration",
            response_type="integration_dispatch_failed_response",
            status_code=502,
            success=False,
            actor_id=user_id,
            details={
                "platform": body.platform,
                "dispatch_mode": body.dispatch_mode,
                "event_type": body.event_type,
                "dispatch_error": str(exc),
            },
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": "webhook_dispatch_failed",
                "message": "Failed to deliver dispatch to external platform",
                "detail": str(exc),
            },
        ) from exc

    except HTTPException as exc:
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="dispatch_platform_integration",
            response_type=_classify_error_response_type(exc),
            status_code=exc.status_code,
            success=False,
            actor_id=user_id,
            details={
                "platform": body.platform,
                "dispatch_mode": body.dispatch_mode,
                "event_type": body.event_type,
            },
        )
        raise

    # Record delivery details in audit trail
    delivery_details: dict[str, Any] = {
        "dispatch_id": response.dispatch_id,
        "platform": response.platform,
        "dispatch_mode": response.dispatch_mode,
        "event_type": response.event_type,
        "delivery_status": response.status,
    }
    if response.delivery_result:
        delivery_details["delivery_result"] = response.delivery_result

    await _record_agent_audit_event(
        request=request,
        repository=audit_repository,
        action="dispatch_platform_integration",
        response_type="integration_dispatch_response",
        status_code=200,
        success=True,
        actor_id=user_id,
        details=delivery_details,
    )
    return response


@router.get(
    "/context/decisions/{rule_id}",
    response_model=AgentDecisionContextView,
    responses={
        200: {"description": "Governance and observability context for an agent decision."},
        403: {"description": "Insufficient scope or agent not allowed."},
        404: {"description": "Rule not found or data asset not found."},
        503: {"description": "Invalid or unavailable policy/configuration or repository data."},
    },
)
async def get_agent_decision_context(
    request: Request,
    rule_id: str,
    data_asset_id: str | None = Query(default=None),
    recent_event_limit: int = Query(default=10, ge=1, le=100),
    lineage_snapshot_limit: int = Query(default=3, ge=1, le=10),
    scopes: list[str] = Depends(get_scopes),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_asset_repository: DataAssetRepository = Depends(get_data_asset_repository),
    sla_slo_repository: SlaSloRepository = Depends(get_sla_slo_repository),
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    user_id: str = Depends(get_user_id),
) -> AgentDecisionContextView:
    try:
        _require_any_scope(scopes, required_scopes=["dq:rules:read"])
        _require_allowed_agent(request, config_repository.get_app_config())

        rule = await rules_repository.get_rule_by_id(rule_id)
        if rule is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"Rule '{rule_id}' was not found",
                },
            )

        asset = data_asset_repository.get_data_asset(data_asset_id) if data_asset_id else None
        if data_asset_id and asset is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"Data asset '{data_asset_id}' was not found",
                },
            )

        effective_workspace_id = str(getattr(rule, "workspace", None) or getattr(asset, "workspace_id", None) or "").strip() or None
        sla_thresholds = await sla_slo_repository.list_sla_slo_definitions(
            workspace_id=effective_workspace_id,
            status="active",
        )
        sorted_thresholds = _sort_by_timestamp_desc(
            list(sla_thresholds),
            timestamp_fields=("updatedAt", "createdAt", "reviewedAt", "requestedAt"),
        )[: 20]

        lineage_snapshots = _sort_by_timestamp_desc(
            list(data_asset_repository.list_data_asset_lineage_snapshots(data_asset_id, limit=lineage_snapshot_limit) if data_asset_id else []),
            timestamp_fields=("captured_at", "capturedAt", "timestamp"),
        ) if data_asset_id else []

        business_context = _serialize_business_context(asset, rule)
        lineage_context = _serialize_lineage_context(asset, lineage_snapshots)
        rule_context = _serialize_rule_context(rule)

        recent_events = await audit_repository.list_events(limit=max(recent_event_limit * 3, recent_event_limit), offset=0)
        recent_agent_events = [
            event
            for event in _sort_by_timestamp_desc(list(recent_events), timestamp_fields=("timestamp",))
            if str(getattr(event, "action", "") or "").strip() in {
                "dispatch_platform_integration",
                "execute_rules_batch",
                "get_delivery_anomalies",
                "query_lineage_graph",
                "list_integration_contracts",
                "get_agent_openapi",
            }
        ][:recent_event_limit]

        rule_status_history = await rules_repository.list_rule_status_history(rule_id, limit=recent_event_limit, offset=0)
        remediation_audit_trail = {
            "recent_events": [event.model_dump(mode="python") if hasattr(event, "model_dump") else dict(event or {}) for event in recent_agent_events],
            "rule_status_history": list(rule_status_history or []),
        }

        response = AgentDecisionContextView.model_validate(
            {
                "rule_context": rule_context,
                "governance_context": {
                    "rule_status_history": remediation_audit_trail["rule_status_history"],
                    "recent_agent_event_count": len(remediation_audit_trail["recent_events"]),
                    "workspace_id": effective_workspace_id,
                },
                "lineage_context": lineage_context,
                "business_context": business_context,
                "sla_thresholds": [_serialize_sla_threshold(definition) for definition in sorted_thresholds],
                "explanation_payload": _build_explanation_payload(
                    rule=rule,
                    business_context=business_context,
                    lineage_context=lineage_context,
                    sla_thresholds=[_serialize_sla_threshold(definition) for definition in sorted_thresholds],
                    remediation_audit_trail=remediation_audit_trail,
                ),
                "remediation_audit_trail": remediation_audit_trail,
            }
        )
    except HTTPException as exc:
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="get_agent_decision_context",
            response_type=_classify_error_response_type(exc),
            status_code=exc.status_code,
            success=False,
            actor_id=user_id,
            details={
                "rule_id": rule_id,
                "data_asset_id": data_asset_id,
                "recent_event_limit": recent_event_limit,
                "lineage_snapshot_limit": lineage_snapshot_limit,
            },
        )
        raise

    await _record_agent_audit_event(
        request=request,
        repository=audit_repository,
        action="get_agent_decision_context",
        response_type="decision_context_response",
        status_code=200,
        success=True,
        actor_id=user_id,
        details={
            "rule_id": rule_id,
            "data_asset_id": data_asset_id,
            "sla_threshold_count": len(response.sla_thresholds),
            "lineage_snapshot_count": response.lineage_context.get("snapshot_count", 0),
        },
    )
    return response


@router.get(
    "/anomalies/deliveries/{delivery_id}",
    response_model=DeliveryExceptionSummaryView,
    responses={
        200: {"description": "Delivery-scoped anomaly summary for agent workflows."},
        403: {"description": "Insufficient scope or agent not allowed."},
        404: {"description": "Delivery not found."},
        503: {"description": "Anomaly summary unavailable."},
    },
)
async def get_delivery_anomalies_for_agent(
    request: Request,
    delivery_id: str,
    lookback_amount: int = Query(default=24, ge=1, le=720),
    lookback_unit: LookbackUnit = Query(default="hours"),
    status: GxExecutionStatus | None = Query(default=None),
    rule_name: str | None = Query(default=None),
    data_object_name: str | None = Query(default=None),
    search: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    suite_id: str | None = Query(default=None),
    data_object_version_id: str | None = Query(default=None),
    rule_version_id: str | None = Query(default=None),
    scopes: list[str] = Depends(get_scopes),
    repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
    projection_repository: ExceptionReasonAnalyticsProjectionRepository = Depends(
        get_exception_reason_analytics_projection_repository
    ),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    user_id: str = Depends(get_user_id),
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
) -> DeliveryExceptionSummaryView:
    try:
        _require_any_scope(scopes, required_scopes=["dq:rules:read"])
        _require_allowed_agent(request, config_repository.get_app_config())

        response = await exception_reports_endpoints.get_delivery_exception_summary(
            request=request,
            delivery_id=delivery_id,
            lookback_amount=lookback_amount,
            lookback_unit=lookback_unit,
            status=status,
            rule_name=rule_name,
            data_object_name=data_object_name,
            search=search,
            reason_code=reason_code,
            suite_id=suite_id,
            data_object_version_id=data_object_version_id,
            rule_version_id=rule_version_id,
            repository=repository,
            projection_repository=projection_repository,
            rules_repository=rules_repository,
            data_catalog_repository=data_catalog_repository,
            admin_repository=admin_repository,
        )
    except HTTPException as exc:
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="get_delivery_anomalies",
            response_type=_classify_error_response_type(exc),
            status_code=exc.status_code,
            success=False,
            actor_id=user_id,
            details={"delivery_id": delivery_id},
        )
        raise

    await _record_agent_audit_event(
        request=request,
        repository=audit_repository,
        action="get_delivery_anomalies",
        response_type="delivery_exception_summary_response",
        status_code=200,
        success=True,
        actor_id=user_id,
        details={"delivery_id": delivery_id},
    )
    return response


@router.get(
    "/metadata/data-objects",
    response_model=AgentMetadataLookupResponseView,
    responses={
        200: {"description": "Metadata lookup endpoint for agent-friendly data object search."},
        403: {"description": "Insufficient scope or agent not allowed."},
    },
)
async def list_data_objects_for_agent(
    request: Request,
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    scopes: list[str] = Depends(get_scopes),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    user_id: str = Depends(get_user_id),
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
) -> AgentMetadataLookupResponseView:
    try:
        _require_any_scope(scopes, required_scopes=["dq:rules:read"])
        _require_allowed_agent(request, config_repository.get_app_config())

        rows = repository.list_data_objects()
        if search:
            normalized_search = str(search).strip().lower()
            rows = [
                row
                for row in rows
                if normalized_search in str(getattr(row, "id", "") or "").lower()
                or normalized_search in str(getattr(row, "name", "") or "").lower()
                or normalized_search in str(getattr(row, "description", "") or "").lower()
            ]

        views = [DataObjectView.model_validate(row) for row in rows[:limit]]
        response = AgentMetadataLookupResponseView.model_validate({"data_objects": views})
    except HTTPException as exc:
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="list_data_objects",
            response_type=_classify_error_response_type(exc),
            status_code=exc.status_code,
            success=False,
            actor_id=user_id,
            details={"search": search, "limit": limit},
        )
        raise

    await _record_agent_audit_event(
        request=request,
        repository=audit_repository,
        action="list_data_objects",
        response_type="metadata_lookup_response",
        status_code=200,
        success=True,
        actor_id=user_id,
        details={"search": search, "limit": limit, "result_count": len(response.data_objects)},
    )
    return response


@router.post(
    "/metadata/lineage/query",
    response_model=OntologyGraphQueryResultView,
    responses={
        200: {"description": "Lineage graph query endpoint for agent workflows."},
        403: {"description": "Insufficient scope or agent not allowed."},
        404: {"description": "No ontology graph snapshot exists for the requested scope."},
    },
)
async def query_lineage_graph_for_agent(
    request: Request,
    body: OntologyGraphQueryRequestView,
    scopes: list[str] = Depends(get_scopes),
    ontology_graph_repository: OntologyGraphRepository = Depends(get_ontology_graph_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    user_id: str = Depends(get_user_id),
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
) -> OntologyGraphQueryResultView:
    try:
        _require_any_scope(scopes, required_scopes=["dq:rules:read"])
        _require_allowed_agent(request, config_repository.get_app_config())

        response = await ontology_endpoints.query_graph(
            request=body,
            ontology_graph_repository=ontology_graph_repository,
        )
    except HTTPException as exc:
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="query_lineage_graph",
            response_type=_classify_error_response_type(exc),
            status_code=exc.status_code,
            success=False,
            actor_id=user_id,
            details={
                "workspace_id": body.workspace_id,
                "data_product_id": body.data_product_id,
                "limit": body.limit,
                "offset": body.offset,
            },
        )
        raise

    await _record_agent_audit_event(
        request=request,
        repository=audit_repository,
        action="query_lineage_graph",
        response_type="lineage_graph_query_response",
        status_code=200,
        success=True,
        actor_id=user_id,
        details={
            "workspace_id": body.workspace_id,
            "data_product_id": body.data_product_id,
            "matched_node_count": len(response.matched_node_ids),
        },
    )
    return response


@router.get(
    "/openapi",
    response_model=AgentOpenApiSpecView,
    responses={
        200: {"description": "Published OpenAPI spec subset for agent endpoints."},
        403: {"description": "Insufficient scope or agent not allowed."},
    },
)
async def get_agent_openapi_spec(
    request: Request,
    scopes: list[str] = Depends(get_scopes),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
    user_id: str = Depends(get_user_id),
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
) -> AgentOpenApiSpecView:
    try:
        _require_any_scope(scopes, required_scopes=["dq:rules:read"])
        _require_allowed_agent(request, config_repository.get_app_config())

        spec = request.app.openapi()
        filtered_paths: dict[str, Any] = {}
        for path, path_item in dict(spec.get("paths") or {}).items():
            normalized_path = str(path)
            if normalized_path.startswith("/api/agent/v1/"):
                normalized_path = normalized_path[len("/api"):]
            if normalized_path.startswith("/agent/v1/"):
                filtered_paths[normalized_path] = path_item

        response = AgentOpenApiSpecView.model_validate(
            {
                "openapi": str(spec.get("openapi") or ""),
                "info": dict(spec.get("info") or {}),
                "paths": filtered_paths,
            }
        )
    except HTTPException as exc:
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="get_agent_openapi",
            response_type=_classify_error_response_type(exc),
            status_code=exc.status_code,
            success=False,
            actor_id=user_id,
        )
        raise

    await _record_agent_audit_event(
        request=request,
        repository=audit_repository,
        action="get_agent_openapi",
        response_type="openapi_spec_response",
        status_code=200,
        success=True,
        actor_id=user_id,
        details={"path_count": len(response.paths)},
    )
    return response


@router.get(
    "/audit/events",
    response_model=AgentAuditEventListView,
    responses={
        200: {"description": "List registered agent request audit events."},
        403: {"description": "Insufficient scope."},
    },
)
async def list_agent_audit_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    scopes: list[str] = Depends(get_scopes),
    user_id: str = Depends(get_user_id),
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
    config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> AgentAuditEventListView:
    try:
        _require_any_scope(scopes, required_scopes=["dq:admin:read"])
        events = await audit_repository.list_events(limit=limit, offset=offset)
        app_config = config_repository.get_app_config()
        access_policy = getattr(app_config, "agentAccessPolicy", {}) or {}
        platform_allowlist = list(getattr(app_config, "agentPlatformAllowlist", []) or [])
        governance_metadata: dict[str, Any] = {
            "access_policy_default_action": access_policy.get("defaultAction", "deny"),
            "allowed_platforms": platform_allowlist,
            "audit_policy_version": "1.0",
            "explainability_endpoint_template": "/agent/v1/context/decisions/{rule_id}",
            "governance_aware": True,
        }
        response = AgentAuditEventListView.model_validate(
            {
                "events": [_build_agent_audit_event_view(item) for item in events],
                "governance_metadata": governance_metadata,
            }
        )
    except HTTPException as exc:
        await _record_agent_audit_event(
            request=request,
            repository=audit_repository,
            action="list_agent_audit_events",
            response_type=_classify_error_response_type(exc),
            status_code=exc.status_code,
            success=False,
            actor_id=user_id,
            details={"limit": limit, "offset": offset},
        )
        raise

    await _record_agent_audit_event(
        request=request,
        repository=audit_repository,
        action="list_agent_audit_events",
        response_type="agent_audit_list_response",
        status_code=200,
        success=True,
        actor_id=user_id,
        details={"limit": limit, "offset": offset, "result_count": len(response.events)},
    )
    return response


@router.post(
    "/audit/events",
    response_model=AgentAuditEventView,
    responses={
        200: {"description": "Record an agent request audit event."},
        503: {"description": "The agent request audit repository is unavailable."},
    },
)
async def record_agent_audit_event(
    body: AgentAuditEventCreateView,
    audit_repository: AgentRequestAuditRepository = Depends(get_agent_request_audit_repository),
) -> AgentAuditEventView:
    event = build_agent_request_audit_entity(
        action=body.action,
        endpoint=body.endpoint,
        method=body.method,
        response_type=body.response_type,
        status_code=body.status_code,
        success=body.success,
        request_id=body.request_id,
        actor_id=body.actor_id,
        correlation_id=body.correlation_id,
        agent_type=body.agent_type,
        agent_source=body.agent_source,
        agent_instance_id=body.agent_instance_id,
        request_origin=body.request_origin,
        user_agent=body.user_agent,
        details=body.details,
    )
    recorded = await audit_repository.record_event(event)
    return _build_agent_audit_event_view(recorded)
