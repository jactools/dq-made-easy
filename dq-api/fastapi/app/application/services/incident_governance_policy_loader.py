from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IncidentGovernanceRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    incidentKinds: list[str] = Field(default_factory=list)
    severities: list[str] = Field(default_factory=list)
    workspaceIds: list[str] = Field(default_factory=list)
    scopeKinds: list[str] = Field(default_factory=list)
    assignedTo: str | None = None
    escalationLabel: str | None = None
    escalateAfterMinutes: int | None = None


class IncidentGovernancePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    defaultAssignedTo: str | None = None
    defaultEscalationLabel: str | None = None
    rules: list[IncidentGovernanceRule] = Field(default_factory=list)


class IncidentGovernanceResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignedTo: str | None = None
    escalationLabel: str | None = None
    escalateAfterMinutes: int | None = None


def _extract_incident_governance_payload(source: Any) -> dict[str, Any] | None:
    if source is None:
        return None
    if hasattr(source, "incidentGovernance"):
        return getattr(source, "incidentGovernance")
    if isinstance(source, Mapping):
        if "incidentGovernance" in source:
            return source["incidentGovernance"]
        if "incident_governance" in source:
            return source["incident_governance"]
    return None


def _normalize_rule(rule: Any) -> IncidentGovernanceRule:
    if isinstance(rule, IncidentGovernanceRule):
        return rule
    if not isinstance(rule, Mapping):
        raise ValueError("incident_governance rules must be objects")

    payload = {
        "incidentKinds": rule.get("incidentKinds", rule.get("incident_kinds", [])),
        "severities": rule.get("severities", []),
        "workspaceIds": rule.get("workspaceIds", rule.get("workspace_ids", [])),
        "scopeKinds": rule.get("scopeKinds", rule.get("scope_kinds", [])),
        "assignedTo": rule.get("assignedTo", rule.get("assigned_to")),
        "escalationLabel": rule.get("escalationLabel", rule.get("escalation_label")),
        "escalateAfterMinutes": rule.get("escalateAfterMinutes", rule.get("escalate_after_minutes")),
    }
    return IncidentGovernanceRule.model_validate(payload)


def load_incident_governance_policy(source: Any) -> IncidentGovernancePolicy | None:
    raw_policy = _extract_incident_governance_payload(source)
    if raw_policy is None:
        return None
    if not isinstance(raw_policy, Mapping):
        raise ValueError("incident_governance must be an object")

    payload = {
        "defaultAssignedTo": raw_policy.get("defaultAssignedTo", raw_policy.get("default_assigned_to")),
        "defaultEscalationLabel": raw_policy.get("defaultEscalationLabel", raw_policy.get("default_escalation_label")),
        "rules": [_normalize_rule(rule) for rule in raw_policy.get("rules", [])],
    }
    return IncidentGovernancePolicy.model_validate(payload)


def _normalize_value(value: str | None) -> str:
    return str(value or "").strip().lower()


def _matches(values: list[str], candidate: str | None) -> bool:
    if not values:
        return True
    normalized_candidate = _normalize_value(candidate)
    return normalized_candidate in {_normalize_value(value) for value in values}


def resolve_incident_governance_resolution(
    source: Any,
    *,
    incident_kind: str,
    severity: str | None,
    workspace_id: str | None,
    scope_kind: str | None,
) -> IncidentGovernanceResolution:
    policy = load_incident_governance_policy(source)
    if policy is None:
        return IncidentGovernanceResolution()

    for rule in policy.rules:
        if not _matches(rule.incidentKinds, incident_kind):
            continue
        if not _matches(rule.severities, severity):
            continue
        if not _matches(rule.workspaceIds, workspace_id):
            continue
        if not _matches(rule.scopeKinds, scope_kind):
            continue
        return IncidentGovernanceResolution(
            assignedTo=rule.assignedTo or policy.defaultAssignedTo,
            escalationLabel=rule.escalationLabel or policy.defaultEscalationLabel,
            escalateAfterMinutes=rule.escalateAfterMinutes,
        )

    return IncidentGovernanceResolution(
        assignedTo=policy.defaultAssignedTo,
        escalationLabel=policy.defaultEscalationLabel,
    )
