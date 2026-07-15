from __future__ import annotations

from collections.abc import Mapping, Sequence
from email.message import EmailMessage
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from dq_domain_validation import allowed_values

if TYPE_CHECKING:
    from app.domain.interfaces import AdminRepository

_SUPPORTED_DESTINATIONS = set(allowed_values("support.delivery_mode"))


def _field(payload: Any, *names: str) -> Any:
    if isinstance(payload, Mapping):
        for name in names:
            if payload.get(name) is not None:
                return payload.get(name)
        return None
    for name in names:
        value = getattr(payload, name, None)
        if value is not None:
            return value
    return None


def normalize_support_destinations(raw_destinations: Any) -> list[str]:
    values: list[str] = []

    if isinstance(raw_destinations, Sequence) and not isinstance(raw_destinations, (str, bytes, bytearray)):
        values = [str(item or "").strip().lower() for item in raw_destinations]
    elif isinstance(raw_destinations, str):
        values = [part.strip().lower() for part in raw_destinations.split(",")]

    normalized = [value for value in values if value in _SUPPORTED_DESTINATIONS]
    deduplicated: list[str] = []
    for value in normalized:
        if value not in deduplicated:
            deduplicated.append(value)
    return deduplicated


def build_support_body_lines(
    request_payload: Any,
    correlation_id: str,
    reference_id: str,
) -> list[str]:
    body_lines = [
        "Hello support team,",
        "",
        str(_field(request_payload, "message") or ""),
        "",
        f"Reference ID: {reference_id}",
        f"Correlation ID: {correlation_id}",
    ]

    source = str(_field(request_payload, "source") or "").strip()
    workspace_id = str(_field(request_payload, "workspaceId", "workspace_id") or "").strip()
    run_plan_id = str(_field(request_payload, "runPlanId", "run_plan_id") or "").strip()
    run_plan_version_id = str(_field(request_payload, "runPlanVersionId", "run_plan_version_id") or "").strip()
    details = _field(request_payload, "details")
    diagnostics = _field(request_payload, "diagnostics")
    metadata = _field(request_payload, "metadata")

    if source:
        body_lines.append(f"Source: {source}")
    if workspace_id:
        body_lines.append(f"Workspace: {workspace_id}")
    if run_plan_id:
        body_lines.append(f"Run plan: {run_plan_id}")
    if run_plan_version_id:
        body_lines.append(f"Run plan version: {run_plan_version_id}")
    if details:
        body_lines.extend(["", "Details:", json.dumps(details, indent=2, sort_keys=True)])
    if diagnostics:
        body_lines.extend(["", "Diagnostics:", json.dumps(diagnostics, indent=2, sort_keys=True)])
    if metadata:
        body_lines.extend(["", "Metadata:", json.dumps(metadata, indent=2, sort_keys=True)])

    return body_lines


def build_support_email_message(
    recipient_email: str,
    sender_email: str,
    request_payload: Any,
    correlation_id: str,
    reference_id: str,
) -> EmailMessage:
    title = str(_field(request_payload, "title") or "")
    subject = f"{title} [{reference_id}]"
    body_lines = build_support_body_lines(request_payload, correlation_id, reference_id)

    source = str(_field(request_payload, "source") or "").strip()
    workspace_id = str(_field(request_payload, "workspaceId", "workspace_id") or "").strip()
    run_plan_id = str(_field(request_payload, "runPlanId", "run_plan_id") or "").strip()
    run_plan_version_id = str(_field(request_payload, "runPlanVersionId", "run_plan_version_id") or "").strip()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = recipient_email
    message["X-Reference-ID"] = reference_id
    message["X-Correlation-ID"] = correlation_id
    if source:
        message["X-Source"] = source
    if workspace_id:
        message["X-Workspace-ID"] = workspace_id
    if run_plan_id:
        message["X-Run-Plan-ID"] = run_plan_id
    if run_plan_version_id:
        message["X-Run-Plan-Version-ID"] = run_plan_version_id
    message.set_content(chr(10).join(body_lines))
    return message


def build_support_email_mailto_url(
    recipient_email: str,
    request_payload: Any,
    correlation_id: str,
    reference_id: str,
) -> str:
    title = str(_field(request_payload, "title") or "")
    subject = f"{title} [{reference_id}]"
    body_lines = build_support_body_lines(request_payload, correlation_id, reference_id)

    return (
        f"mailto:{quote(recipient_email, safe='@._-')}"
        f"?subject={quote(subject)}"
        f"&body={quote(chr(10).join(body_lines))}"
    )


def build_support_request_payload(
    request_payload: Any,
    reference_id: str,
    correlation_id: str,
    user_id: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_type": "application_support",
        "reference_id": reference_id,
        "correlation_id": correlation_id,
        "title": str(_field(request_payload, "title") or ""),
        "message": str(_field(request_payload, "message") or ""),
        "source": _field(request_payload, "source"),
        "workspace_id": _field(request_payload, "workspaceId", "workspace_id"),
        "run_plan_id": _field(request_payload, "runPlanId", "run_plan_id"),
        "run_plan_version_id": _field(request_payload, "runPlanVersionId", "run_plan_version_id"),
        "requested_by": user_id,
    }

    details = _field(request_payload, "details")
    diagnostics = _field(request_payload, "diagnostics")
    metadata = _field(request_payload, "metadata")
    if details is not None:
        payload["details"] = details
    if diagnostics is not None:
        payload["diagnostics"] = diagnostics
    if metadata is not None:
        payload["metadata"] = metadata

    return payload


def resolve_support_requester_email(
    admin_repository: AdminRepository,
    user_id: str | None,
    claims: dict[str, Any] | None,
) -> str | None:
    current_user = admin_repository.get_current_user(user_id, claims)
    if current_user is not None:
        email = str(getattr(current_user, "email", "") or "").strip()
        if email:
            return email

    if isinstance(claims, dict):
        for claim_key in ("email", "upn", "preferred_username"):
            claim_value = str(claims.get(claim_key) or "").strip()
            if "@" in claim_value:
                return claim_value

    return None


def build_support_teams_payload(
    request_payload: Any,
    correlation_id: str,
    reference_id: str,
) -> dict[str, str]:
    title = str(_field(request_payload, "title") or "")
    message = str(_field(request_payload, "message") or "")
    workspace_id = str(_field(request_payload, "workspaceId", "workspace_id") or "").strip()
    run_plan_id = str(_field(request_payload, "runPlanId", "run_plan_id") or "").strip()
    run_plan_version_id = str(_field(request_payload, "runPlanVersionId", "run_plan_version_id") or "").strip()

    payload = {
        "text": (
            f"[{reference_id}] {title}\n\n"
            f"{message}\n\n"
            f"Correlation ID: {correlation_id}"
        )
    }
    if workspace_id:
        payload["text"] += f"\nWorkspace: {workspace_id}"
    if run_plan_id:
        payload["text"] += f"\nRun plan: {run_plan_id}"
    if run_plan_version_id:
        payload["text"] += f"\nRun plan version: {run_plan_version_id}"
    return payload


def build_zammad_ticket_body(
    request_payload: Any,
    reference_id: str,
    correlation_id: str,
    requester_email: str,
) -> str:
    message = str(_field(request_payload, "message") or "")
    source = str(_field(request_payload, "source") or "").strip()
    workspace_id = str(_field(request_payload, "workspaceId", "workspace_id") or "").strip()
    run_plan_id = str(_field(request_payload, "runPlanId", "run_plan_id") or "").strip()
    run_plan_version_id = str(_field(request_payload, "runPlanVersionId", "run_plan_version_id") or "").strip()
    details = _field(request_payload, "details")
    diagnostics = _field(request_payload, "diagnostics")
    metadata = _field(request_payload, "metadata")

    body_lines = [
        f"Requester: {requester_email}",
        f"Reference ID: {reference_id}",
        f"Correlation ID: {correlation_id}",
        "",
        message,
    ]

    if source:
        body_lines.extend(["", f"Source: {source}"])
    if workspace_id:
        body_lines.extend(["", f"Workspace: {workspace_id}"])
    if run_plan_id:
        body_lines.extend(["", f"Run plan: {run_plan_id}"])
    if run_plan_version_id:
        body_lines.extend(["", f"Run plan version: {run_plan_version_id}"])
    if details is not None:
        body_lines.extend(["", "Details:", json.dumps(details, indent=2, sort_keys=True)])
    if diagnostics is not None:
        body_lines.extend(["", "Diagnostics:", json.dumps(diagnostics, indent=2, sort_keys=True)])
    if metadata is not None:
        body_lines.extend(["", "Metadata:", json.dumps(metadata, indent=2, sort_keys=True)])

    return "\n".join(body_lines)


def build_zammad_ticket_payload(
    request_payload: Any,
    reference_id: str,
    correlation_id: str,
    requester_email: str,
) -> dict[str, Any]:
    return {
        "title": str(_field(request_payload, "title") or ""),
        "group": "Users",
        "customer": requester_email,
        "state": "new",
        "priority": "2 normal",
        "article": {
            "body": build_zammad_ticket_body(request_payload, reference_id, correlation_id, requester_email),
            "content_type": "text/plain",
            "sender": "Customer",
            "type": "note",
        },
    }


def build_support_delivery_message(
    delivered_destinations: Sequence[str],
    reference_id: str,
    *,
    recipient_email: str | None = None,
    email_draft_url: str | None = None,
    ticket_system: str | None = None,
    ticket_number: str | None = None,
) -> str:
    destinations = list(delivered_destinations)
    destination_summary = ", ".join(destinations)
    if destinations == ["email"]:
        if email_draft_url:
            return f"Prepared email draft for {recipient_email}. Reference ID: {reference_id}"
        return f"Sent email assistance request to {recipient_email}. Reference ID: {reference_id}"
    if destinations == ["teams"]:
        return f"Sent the support request to Teams. Reference ID: {reference_id}"
    if destinations == ["itsm"]:
        return f"Created {ticket_system} ticket {ticket_number}. Reference ID: {reference_id}"
    return f"Routed the support request to {destination_summary}. Reference ID: {reference_id}"


# ---------------------------------------------------------------------------
# DQ-13 — incident Zammad ticket builders
# ---------------------------------------------------------------------------

def _build_technical_run_error_body(incident: Any, correlation_id: str) -> str:
    """Produce the Zammad ticket body for a technical run error incident."""
    lines = [
        f"Incident ID: {incident.id}",
        f"Correlation ID: {correlation_id}",
        f"Kind: technical_run_error",
        "",
        "A DQ engine run failed before the quality check could complete.",
        "",
    ]
    if incident.run_id:
        lines.append(f"Run ID: {incident.run_id}")
    if incident.run_plan_id:
        lines.append(f"Run plan ID: {incident.run_plan_id}")
    if incident.workspace_id:
        lines.append(f"Workspace: {incident.workspace_id}")
    if incident.scope_kind and incident.scope_id:
        lines.append(f"Scope: {incident.scope_kind}/{incident.scope_id}")
    if incident.source_correlation_id:
        lines.append(f"Source correlation ID: {incident.source_correlation_id}")
    if incident.source_parent_correlation_id:
        lines.append(f"Parent correlation ID: {incident.source_parent_correlation_id}")
    if incident.source_request_id:
        lines.append(f"Source request ID: {incident.source_request_id}")
    if incident.source_queue_message_id:
        lines.append(f"Queue message ID: {incident.source_queue_message_id}")
    if incident.source_trace_id:
        lines.append(f"Trace ID: {incident.source_trace_id}")
    if incident.source_system:
        lines.append(f"Source system: {incident.source_system}")
    if incident.failure_code:
        lines.extend(["", f"Failure code: {incident.failure_code}"])
    if incident.failure_message:
        lines.extend(["", "Failure message:", incident.failure_message])
    if incident.description:
        lines.extend(["", "Description:", incident.description])
    return "\n".join(lines)


def _build_functional_violation_body(incident: Any, correlation_id: str) -> str:
    """Produce the Zammad ticket body for a functional data violation incident."""
    lines = [
        f"Incident ID: {incident.id}",
        f"Correlation ID: {correlation_id}",
        f"Kind: functional_violation",
        "",
        "A DQ run completed but data violated one or more rules.",
        "",
    ]
    if incident.run_id:
        lines.append(f"Run ID: {incident.run_id}")
    if incident.run_plan_id:
        lines.append(f"Run plan ID: {incident.run_plan_id}")
    if incident.workspace_id:
        lines.append(f"Workspace: {incident.workspace_id}")
    if incident.scope_kind and incident.scope_id:
        lines.append(f"Scope: {incident.scope_kind}/{incident.scope_id}")
    if incident.source_correlation_id:
        lines.append(f"Source correlation ID: {incident.source_correlation_id}")
    if incident.source_parent_correlation_id:
        lines.append(f"Parent correlation ID: {incident.source_parent_correlation_id}")
    if incident.source_request_id:
        lines.append(f"Source request ID: {incident.source_request_id}")
    if incident.source_queue_message_id:
        lines.append(f"Queue message ID: {incident.source_queue_message_id}")
    if incident.source_trace_id:
        lines.append(f"Trace ID: {incident.source_trace_id}")
    if incident.source_system:
        lines.append(f"Source system: {incident.source_system}")
    if incident.violation_count is not None:
        lines.extend(["", f"Violation count: {incident.violation_count}"])
    if incident.violated_rule_ids:
        lines.extend(["", "Violated rules:", json.dumps(incident.violated_rule_ids, indent=2)])
    if incident.severity:
        lines.extend(["", f"Severity: {incident.severity}"])
    if incident.description:
        lines.extend(["", "Description:", incident.description])
    return "\n".join(lines)


def build_zammad_incident_ticket_payload(
    incident: Any,
    correlation_id: str,
    *,
    requester_email: str,
    assigned_to: str | None = None,
    escalation_label: str | None = None,
    escalate_after_minutes: int | None = None,
) -> dict[str, Any]:
    """Build a Zammad ticket payload from a DQ-13 incident.

    - technical_run_error  → priority "3 high", title prefixed with [Technical]
    - functional_violation → priority based on severity (critical/high → "3 high", else "2 normal"),
                             title prefixed with [Functional]
    """
    from app.domain.entities.incident import (
        INCIDENT_KIND_TECHNICAL,
        INCIDENT_SEVERITY_CRITICAL,
        INCIDENT_SEVERITY_HIGH,
    )

    if incident.incident_kind == INCIDENT_KIND_TECHNICAL:
        title = f"[Technical] DQ Run Error: {incident.scope_id or incident.run_id or incident.id}"
        priority = "3 high"
        body = _build_technical_run_error_body(incident, correlation_id)
    else:
        scope_label = incident.scope_id or incident.run_id or incident.id
        vc = f" ({incident.violation_count} violations)" if incident.violation_count is not None else ""
        title = f"[Functional] Data Quality Violation: {scope_label}{vc}"
        if incident.severity in (INCIDENT_SEVERITY_CRITICAL, INCIDENT_SEVERITY_HIGH):
            priority = "3 high"
        else:
            priority = "2 normal"
        body = _build_functional_violation_body(incident, correlation_id)

    if assigned_to:
        body = "\n".join([body, "", f"Assigned to: {assigned_to}"])
    if escalation_label or escalate_after_minutes is not None:
        escalation_parts: list[str] = []
        if escalation_label:
            escalation_parts.append(escalation_label)
        if escalate_after_minutes is not None:
            escalation_parts.append(f"escalate after {escalate_after_minutes} minutes")
        body = "\n".join([body, "", f"Escalation: {', '.join(escalation_parts)}"])

    return {
        "title": title,
        "group": "Users",
        "customer": requester_email,
        "state": "new",
        "priority": priority,
        "article": {
            "body": body,
            "content_type": "text/plain",
            "sender": "Customer",
            "type": "note",
        },
    }
