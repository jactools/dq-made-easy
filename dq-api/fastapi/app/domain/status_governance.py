from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import has_required_scope


class StatusValueDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: str
    label: str
    description: str | None = None
    isInitial: bool = False
    isTerminal: bool = False


class StatusTransitionDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    fromStatus: str
    toStatus: str
    label: str
    requiredAnyScopes: list[str] = Field(default_factory=list)


_RULE_STATUS_VALUES: list[StatusValueDefinition] = [
    StatusValueDefinition(value="draft", label="Draft", description="Rule has been authored but not tested", isInitial=True),
    StatusValueDefinition(value="testing", label="Testing", description="Tests are currently running"),
    StatusValueDefinition(value="tested", label="Tested", description="Rule has been tested and is ready for review"),
    StatusValueDefinition(value="pending-approval", label="Pending Approval", description="Awaiting reviewer decision"),
    StatusValueDefinition(value="approved", label="Approved", description="Approved and ready for activation"),
    StatusValueDefinition(value="activated", label="Activated", description="Rule is active in production"),
    StatusValueDefinition(value="deactivated", label="Deactivated", description="Rule was deactivated after approval"),
    StatusValueDefinition(value="removed", label="Removed", description="Rule was soft-deleted and can only be recovered by admin"),
    StatusValueDefinition(value="recovered", label="Recovered", description="Rule was recovered by admin and must re-enter approval flow"),
    StatusValueDefinition(value="rejected", label="Rejected", description="Rejected and requires rework"),
]

_RULE_STATUS_TRANSITIONS: list[StatusTransitionDefinition] = [
    StatusTransitionDefinition(fromStatus="draft", toStatus="testing", label="Start Test", requiredAnyScopes=["dq:rules:test", "dq:rules:write"]),
    StatusTransitionDefinition(fromStatus="testing", toStatus="tested", label="Mark Tested", requiredAnyScopes=["dq:rules:test", "dq:rules:write"]),
    StatusTransitionDefinition(fromStatus="tested", toStatus="pending-approval", label="Submit for Approval", requiredAnyScopes=["dq:rules:create", "dq:rules:write"]),
    StatusTransitionDefinition(fromStatus="draft", toStatus="pending-approval", label="Submit for Approval", requiredAnyScopes=["dq:rules:create", "dq:rules:write"]),
    StatusTransitionDefinition(fromStatus="rejected", toStatus="pending-approval", label="Resubmit for Approval", requiredAnyScopes=["dq:rules:create", "dq:rules:write"]),
    StatusTransitionDefinition(fromStatus="pending-approval", toStatus="approved", label="Approve", requiredAnyScopes=["dq:rules:approve"]),
    StatusTransitionDefinition(fromStatus="pending-approval", toStatus="rejected", label="Reject", requiredAnyScopes=["dq:rules:approve"]),
    StatusTransitionDefinition(fromStatus="approved", toStatus="activated", label="Activate", requiredAnyScopes=["dq:rules:activate"]),
    StatusTransitionDefinition(fromStatus="activated", toStatus="deactivated", label="Deactivate", requiredAnyScopes=["dq:rules:approve"]),
    StatusTransitionDefinition(fromStatus="deactivated", toStatus="draft", label="Reopen", requiredAnyScopes=["dq:rules:edit", "dq:rules:write"]),
    StatusTransitionDefinition(fromStatus="deactivated", toStatus="removed", label="Remove", requiredAnyScopes=["dq:rules:delete", "dq:rules:write"]),
    StatusTransitionDefinition(fromStatus="removed", toStatus="recovered", label="Recover", requiredAnyScopes=["dq:users:manage"]),
    StatusTransitionDefinition(fromStatus="recovered", toStatus="pending-approval", label="Submit for Approval", requiredAnyScopes=["dq:rules:create", "dq:rules:write"]),
    StatusTransitionDefinition(fromStatus="rejected", toStatus="draft", label="Reopen", requiredAnyScopes=["dq:rules:edit", "dq:rules:write"]),
]

_RULE_LIFECYCLE_STATUS_VALUES: list[StatusValueDefinition] = [
    StatusValueDefinition(
        value="active",
        label="Active",
        description="Rule is available for continued use",
        isInitial=True,
    ),
    StatusValueDefinition(
        value="deprecated",
        label="Deprecated",
        description="Rule remains visible but should no longer be adopted for new use",
    ),
    StatusValueDefinition(
        value="superseded",
        label="Superseded",
        description="Rule has been replaced by a newer governed alternative",
    ),
    StatusValueDefinition(
        value="retired",
        label="Retired",
        description="Rule has been retired from governed use",
        isTerminal=True,
    ),
]

_RULE_LIFECYCLE_STATUS_TRANSITIONS: list[StatusTransitionDefinition] = [
    StatusTransitionDefinition(
        fromStatus="active",
        toStatus="deprecated",
        label="Deprecate",
        requiredAnyScopes=["dq:rules:write"],
    ),
    StatusTransitionDefinition(
        fromStatus="active",
        toStatus="superseded",
        label="Supersede",
        requiredAnyScopes=["dq:rules:write"],
    ),
    StatusTransitionDefinition(
        fromStatus="active",
        toStatus="retired",
        label="Retire",
        requiredAnyScopes=["dq:rules:delete", "dq:rules:write"],
    ),
    StatusTransitionDefinition(
        fromStatus="deprecated",
        toStatus="active",
        label="Reactivate",
        requiredAnyScopes=["dq:rules:write"],
    ),
    StatusTransitionDefinition(
        fromStatus="deprecated",
        toStatus="superseded",
        label="Supersede",
        requiredAnyScopes=["dq:rules:write"],
    ),
    StatusTransitionDefinition(
        fromStatus="deprecated",
        toStatus="retired",
        label="Retire",
        requiredAnyScopes=["dq:rules:delete", "dq:rules:write"],
    ),
    StatusTransitionDefinition(
        fromStatus="superseded",
        toStatus="retired",
        label="Retire",
        requiredAnyScopes=["dq:rules:delete", "dq:rules:write"],
    ),
]

_APPROVAL_STATUS_VALUES: list[StatusValueDefinition] = [
    StatusValueDefinition(value="pending", label="Pending", description="Approval request is waiting for review", isInitial=True),
    StatusValueDefinition(value="approved", label="Approved", description="Approval was accepted", isTerminal=True),
    StatusValueDefinition(value="rejected", label="Rejected", description="Approval was rejected", isTerminal=True),
]

_APPROVAL_STATUS_TRANSITIONS: list[StatusTransitionDefinition] = [
    StatusTransitionDefinition(fromStatus="pending", toStatus="approved", label="Approve", requiredAnyScopes=["dq:rules:approve"]),
    StatusTransitionDefinition(fromStatus="pending", toStatus="rejected", label="Reject", requiredAnyScopes=["dq:rules:approve"]),
]

_RUN_PLAN_STATUS_VALUES: list[StatusValueDefinition] = [
    StatusValueDefinition(
        value="inactive",
        label="Inactive",
        description="The plan version is not allowed to run",
        isInitial=True,
    ),
    StatusValueDefinition(
        value="activation-requested",
        label="Activation Requested",
        description="An activation approval has been requested; the plan remains inactive until it is approved",
    ),
    StatusValueDefinition(
        value="active",
        label="Active",
        description="The plan version is allowed to run",
    ),
    StatusValueDefinition(
        value="deactivation-requested",
        label="Deactivation Requested",
        description="A deactivation approval has been requested; the plan remains active until it is approved",
    ),
    StatusValueDefinition(
        value="deactivated",
        label="Deactivated",
        description="The plan version is no longer allowed to run",
        isTerminal=True,
    ),
]

_RUN_PLAN_STATUS_TRANSITIONS: list[StatusTransitionDefinition] = [
    StatusTransitionDefinition(
        fromStatus="inactive",
        toStatus="activation-requested",
        label="Request Activation",
        requiredAnyScopes=["dq:rules:write"],
    ),
    StatusTransitionDefinition(
        fromStatus="draft",
        toStatus="activation-requested",
        label="Request Activation",
        requiredAnyScopes=["dq:rules:write"],
    ),
    StatusTransitionDefinition(
        fromStatus="activation-requested",
        toStatus="active",
        label="Approve Activation",
        requiredAnyScopes=["dq:rules:approve"],
    ),
    StatusTransitionDefinition(
        fromStatus="activation-requested",
        toStatus="inactive",
        label="Reject Activation",
        requiredAnyScopes=["dq:rules:approve"],
    ),
    StatusTransitionDefinition(
        fromStatus="active",
        toStatus="deactivation-requested",
        label="Request Deactivation",
        requiredAnyScopes=["dq:rules:write"],
    ),
    StatusTransitionDefinition(
        fromStatus="deactivation-requested",
        toStatus="deactivated",
        label="Approve Deactivation",
        requiredAnyScopes=["dq:rules:approve"],
    ),
    StatusTransitionDefinition(
        fromStatus="deactivation-requested",
        toStatus="active",
        label="Reject Deactivation",
        requiredAnyScopes=["dq:rules:approve"],
    ),
]

_CONNECTOR_SYNC_JOB_STATUS_VALUES: list[StatusValueDefinition] = [
    StatusValueDefinition(
        value="queued",
        label="Queued",
        description="Connector metadata sync job has been accepted and is waiting to start",
        isInitial=True,
    ),
    StatusValueDefinition(
        value="running",
        label="Running",
        description="Connector metadata sync job is currently running",
    ),
    StatusValueDefinition(
        value="completed",
        label="Completed",
        description="Connector metadata sync job completed successfully",
        isTerminal=True,
    ),
    StatusValueDefinition(
        value="failed",
        label="Failed",
        description="Connector metadata sync job failed",
        isTerminal=True,
    ),
    StatusValueDefinition(
        value="cancelled",
        label="Cancelled",
        description="Connector metadata sync job was cancelled before completion",
        isTerminal=True,
    ),
]

_CONNECTOR_SYNC_JOB_STATUS_TRANSITIONS: list[StatusTransitionDefinition] = [
    StatusTransitionDefinition(fromStatus="queued", toStatus="running", label="Start Sync"),
    StatusTransitionDefinition(fromStatus="queued", toStatus="failed", label="Fail Sync"),
    StatusTransitionDefinition(fromStatus="queued", toStatus="cancelled", label="Cancel Sync"),
    StatusTransitionDefinition(fromStatus="running", toStatus="completed", label="Complete Sync"),
    StatusTransitionDefinition(fromStatus="running", toStatus="failed", label="Fail Sync"),
    StatusTransitionDefinition(fromStatus="running", toStatus="cancelled", label="Cancel Sync"),
]

_STATUS_MODELS: dict[str, tuple[list[StatusValueDefinition], list[StatusTransitionDefinition]]] = {
    "rule": (_RULE_STATUS_VALUES, _RULE_STATUS_TRANSITIONS),
    "rule_lifecycle": (_RULE_LIFECYCLE_STATUS_VALUES, _RULE_LIFECYCLE_STATUS_TRANSITIONS),
    "approval": (_APPROVAL_STATUS_VALUES, _APPROVAL_STATUS_TRANSITIONS),
    "run_plan": (_RUN_PLAN_STATUS_VALUES, _RUN_PLAN_STATUS_TRANSITIONS),
    "connector_sync_job": (_CONNECTOR_SYNC_JOB_STATUS_VALUES, _CONNECTOR_SYNC_JOB_STATUS_TRANSITIONS),
}

_STATUS_MODEL_POLICY_OVERRIDES: dict[str, list[StatusTransitionDefinition]] = {}


def _normalize_status_value(value: str | None) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _canonicalize_status_value(*, entity: str, status: str | None) -> str:
    normalized_entity = str(entity or "").strip().lower()
    normalized_status = _normalize_status_value(status)

    if normalized_entity == "rule":
        if normalized_status == "pending":
            return "pending-approval"
        if normalized_status == "declined":
            return "rejected"
    if normalized_entity == "approval" and normalized_status == "declined":
        return "rejected"

    return normalized_status


def _is_transition_defined_for_entity(
    *,
    entity: str,
    from_status: str,
    to_status: str,
    transitions: list[StatusTransitionDefinition],
) -> bool:
    expected_from = _canonicalize_status_value(entity=entity, status=from_status)
    expected_to = _canonicalize_status_value(entity=entity, status=to_status)
    for transition in transitions:
        transition_from = _canonicalize_status_value(entity=entity, status=transition.fromStatus)
        transition_to = _canonicalize_status_value(entity=entity, status=transition.toStatus)
        if transition_from == expected_from and transition_to == expected_to:
            return True
    return False


def _is_transition_allowed_for_entity(
    *,
    entity: str,
    from_status: str,
    to_status: str,
    transitions: list[StatusTransitionDefinition],
    granted_scopes: list[str],
) -> bool:
    expected_from = _canonicalize_status_value(entity=entity, status=from_status)
    expected_to = _canonicalize_status_value(entity=entity, status=to_status)
    for transition in transitions:
        transition_from = _canonicalize_status_value(entity=entity, status=transition.fromStatus)
        transition_to = _canonicalize_status_value(entity=entity, status=transition.toStatus)
        if transition_from != expected_from or transition_to != expected_to:
            continue

        required = list(transition.requiredAnyScopes or [])
        return (not required) or has_required_scope(granted_scopes, required)
    return False


def _build_allowed_transitions_by_status(
    *,
    transitions: list[StatusTransitionDefinition],
    granted_scopes: list[str],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for transition in transitions:
        required = list(transition.requiredAnyScopes or [])
        if required and not has_required_scope(granted_scopes, required):
            continue
        targets = grouped.setdefault(transition.fromStatus, [])
        if transition.toStatus not in targets:
            targets.append(transition.toStatus)
    return grouped


def normalize_status(value: str | None) -> str:
    return _normalize_status_value(value)


def canonicalize_status(*, entity: str, status: str | None) -> str:
    return _canonicalize_status_value(entity=entity, status=status)


def get_supported_status_model_entities() -> set[str]:
    return set(_STATUS_MODELS.keys())


def get_status_model_definition(entity: str) -> tuple[list[StatusValueDefinition], list[StatusTransitionDefinition]] | None:
    normalized_entity = str(entity or "").strip().lower()
    model_definition = _STATUS_MODELS.get(normalized_entity)
    if model_definition is None:
        return None

    statuses, default_transitions = model_definition
    transitions = _STATUS_MODEL_POLICY_OVERRIDES.get(normalized_entity, default_transitions)
    return statuses, transitions


def set_status_model_policy_overrides(
    policy_overrides: dict[str, list[StatusTransitionDefinition]] | None,
) -> None:
    if policy_overrides is None:
        _STATUS_MODEL_POLICY_OVERRIDES.clear()
        return

    _STATUS_MODEL_POLICY_OVERRIDES.clear()
    _STATUS_MODEL_POLICY_OVERRIDES.update(policy_overrides)


def is_transition_defined(
    *,
    entity: str,
    from_status: str,
    to_status: str,
) -> bool:
    model_definition = get_status_model_definition(entity)
    if model_definition is None:
        return False

    _, transitions = model_definition
    return _is_transition_defined_for_entity(entity=entity, from_status=from_status, to_status=to_status, transitions=transitions)


def is_transition_allowed(
    *,
    entity: str,
    from_status: str,
    to_status: str,
    granted_scopes: list[str],
) -> bool:
    model_definition = get_status_model_definition(entity)
    if model_definition is None:
        return False

    _, transitions = model_definition
    return _is_transition_allowed_for_entity(
        entity=entity,
        from_status=from_status,
        to_status=to_status,
        transitions=transitions,
        granted_scopes=granted_scopes,
    )


def build_allowed_transitions_by_status_map(
    *,
    transitions: list[StatusTransitionDefinition],
    granted_scopes: list[str],
) -> dict[str, list[str]]:
    return _build_allowed_transitions_by_status(transitions=transitions, granted_scopes=granted_scopes)