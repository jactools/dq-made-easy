from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.domain.entities.base import EntityModel


INCIDENT_KIND_TECHNICAL = "technical_run_error"
INCIDENT_KIND_FUNCTIONAL = "functional_violation"
VALID_INCIDENT_KINDS = {INCIDENT_KIND_TECHNICAL, INCIDENT_KIND_FUNCTIONAL}

INCIDENT_STATUS_OPEN = "open"
INCIDENT_STATUS_IN_PROGRESS = "in_progress"
INCIDENT_STATUS_RESOLVED = "resolved"
INCIDENT_STATUS_CLOSED = "closed"
VALID_INCIDENT_STATUSES = {
    INCIDENT_STATUS_OPEN,
    INCIDENT_STATUS_IN_PROGRESS,
    INCIDENT_STATUS_RESOLVED,
    INCIDENT_STATUS_CLOSED,
}

INCIDENT_SEVERITY_LOW = "low"
INCIDENT_SEVERITY_MEDIUM = "medium"
INCIDENT_SEVERITY_HIGH = "high"
INCIDENT_SEVERITY_CRITICAL = "critical"
VALID_INCIDENT_SEVERITIES = {
    INCIDENT_SEVERITY_LOW,
    INCIDENT_SEVERITY_MEDIUM,
    INCIDENT_SEVERITY_HIGH,
    INCIDENT_SEVERITY_CRITICAL,
}


class IncidentEntity(EntityModel):
    """A DQ-13 incident record.

    incident_kind distinguishes the root cause:
    - "technical_run_error"  : the DQ engine or worker failed (infrastructure/engine fault)
    - "functional_violation" : the run succeeded but data violated one or more rules
    """

    id: str
    incident_kind: str  # INCIDENT_KIND_* constants
    status: str = INCIDENT_STATUS_OPEN
    title: str
    description: str | None = None
    severity: str | None = None  # INCIDENT_SEVERITY_* constants

    # Run context
    run_id: str | None = None
    run_plan_id: str | None = None
    workspace_id: str | None = None
    scope_kind: str | None = None
    scope_id: str | None = None

    # Source correlation context
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

    # ITSM integration
    itsm_ticket_id: str | None = None
    itsm_ticket_number: str | None = None

    # Assignment / resolution
    assigned_to: str | None = None
    resolved_at: str | None = None
    comments: list[dict[str, Any]] = Field(default_factory=list)
    resolution_history: list[dict[str, Any]] = Field(default_factory=list)

    # Audit
    created_by: str | None = None
    created_at: str | None = None
    updated_by: str | None = None
    updated_at: str | None = None


INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_PENDING = "pending"
INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_ACCEPTED = "accepted"
INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_REJECTED = "rejected"
VALID_INCIDENT_ROOT_CAUSE_SUGGESTION_STATUSES = {
    INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_PENDING,
    INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_ACCEPTED,
    INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_REJECTED,
}


class IncidentRootCauseSuggestionEntity(EntityModel):
    """Persisted root-cause suggestion generated from one or more incidents."""

    id: str
    workspace_id: str | None = None
    incident_ids: list[str] = Field(default_factory=list)
    incident_count: int = 0
    suggested_root_cause: dict[str, Any]
    status: str = INCIDENT_ROOT_CAUSE_SUGGESTION_STATUS_PENDING
    events: list[dict[str, Any]] = Field(default_factory=list)
    created_by: str | None = None
    created_at: str | None = None
    updated_by: str | None = None
    updated_at: str | None = None
    accepted_at: str | None = None
    rejected_at: str | None = None
    assistance_requested_at: str | None = None
    assistance_request_reference_id: str | None = None
    assistance_request_ticket_id: str | None = None
    assistance_request_ticket_number: str | None = None
    assistance_request_ticket_url: str | None = None
    assistance_request_ticket_system: str | None = None
    assistance_request_delivery_modes: list[str] = Field(default_factory=list)
    assistance_request_payload: dict[str, Any] | None = None
