from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException

from app.api.presenters.gx import extract_itsm_response_message
from app.api.presenters.gx import extract_itsm_ticket_number
from app.api.presenters.gx import extract_itsm_ticket_url
from dq_domain_validation import GxAssistanceDeliveryMode


@dataclass(frozen=True)
class RequestGxAssistanceCommand:
    assistance_mode: str
    recipient_email: str
    it_system: str
    endpoint_url: str
    itsm_auth_token: str
    correlation_id: str
    run_plan_id: str | None
    run_plan_version_id: str | None
    workspace_id: str | None
    error_message: str
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class GxAssistanceTransportResponse:
    status_code: int
    is_success: bool
    payload: Any
    text: str
    reason_phrase: str | None = None


@dataclass(frozen=True)
class GxAssistanceRequestResult:
    delivery_mode: GxAssistanceDeliveryMode
    message: str
    correlation_id: str
    mailto_url: str | None = None
    recipient_email: str | None = None
    ticket_number: str | None = None
    ticket_system: str | None = None
    ticket_url: str | None = None


def _resolve_run_plan_version_id(command: RequestGxAssistanceCommand) -> str | None:
    explicit_value = str(command.run_plan_version_id or "").strip()
    if explicit_value:
        return explicit_value

    match = re.search(r"run plan version '([^']+)'", str(command.error_message or ""), re.IGNORECASE)
    if not match:
        return None
    value = str(match.group(1) or "").strip()
    return value or None


def build_gx_assistance_mailto_url(
    recipient_email: str,
    *,
    run_plan_id: str | None,
    run_plan_version_id: str | None,
    workspace_id: str | None,
    error_message: str,
    diagnostics: list[dict[str, Any]] | None,
    correlation_id: str,
) -> str:
    normalized_run_plan_version_id = str(run_plan_version_id or "").strip() or "unknown-run-plan-version"
    normalized_run_plan_id = str(run_plan_id or "").strip() or "n/a"
    normalized_workspace_id = str(workspace_id or "").strip() or "n/a"
    subject = f"GX run plan validation assistance requested: {normalized_run_plan_version_id}"
    body_lines = [
        "Hello ops team,",
        "",
        "Please assist with the GX run plan validation error shown in the GX Run Plans admin screen.",
        "",
        f"Workspace: {normalized_workspace_id}",
        f"Run plan: {normalized_run_plan_id}",
        f"Run plan version: {normalized_run_plan_version_id}",
        f"Correlation ID: {correlation_id}",
        f"Error: {error_message}",
    ]
    if diagnostics:
        body_lines.extend(
            [
                "",
                "Diagnostics:",
                json.dumps(diagnostics, indent=2, sort_keys=True),
            ]
        )

    return (
        f"mailto:{quote(recipient_email, safe='@._-')}"
        f"?subject={quote(subject)}"
        f"&body={quote(chr(10).join(body_lines))}"
    )


async def request_gx_assistance(
    *,
    command: RequestGxAssistanceCommand,
    send_itsm_request: Callable[[str, dict[str, Any], dict[str, str]], Awaitable[GxAssistanceTransportResponse]],
) -> GxAssistanceRequestResult:
    assistance_mode = str(command.assistance_mode or "").strip().lower()
    correlation_id = str(command.correlation_id or "").strip()

    if assistance_mode == "email":
        recipient_email = str(command.recipient_email or "").strip()
        if not recipient_email:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "assistance_email_missing",
                    "message": "Assistance request email address is not configured",
                    "correlation_id": correlation_id,
                },
            )

        mailto_url = build_gx_assistance_mailto_url(
            recipient_email,
            run_plan_id=command.run_plan_id,
            run_plan_version_id=_resolve_run_plan_version_id(command),
            workspace_id=command.workspace_id,
            error_message=command.error_message,
            diagnostics=command.diagnostics,
            correlation_id=correlation_id,
        )
        return GxAssistanceRequestResult(
            delivery_mode="email",
            message=f"Prefilled email draft for {recipient_email}.",
            correlation_id=correlation_id,
            mailto_url=mailto_url,
            recipient_email=recipient_email,
        )

    if assistance_mode != "itsm":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_assistance_mode",
                "message": f"Unsupported assistance request mode '{assistance_mode}'",
                "correlation_id": correlation_id,
            },
        )

    it_system = str(command.it_system or "").strip()
    if not it_system:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "itsm_system_missing",
                "message": "Assistance request ITSM system is not configured",
                "correlation_id": correlation_id,
            },
        )

    endpoint_url = str(command.endpoint_url or "").strip()
    if not endpoint_url:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "itsm_endpoint_missing",
                "message": "Assistance request ITSM endpoint is not configured",
                "correlation_id": correlation_id,
            },
        )

    itsm_auth_token = str(command.itsm_auth_token or "").strip()
    if it_system.casefold() == "zammad" and not itsm_auth_token:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "itsm_auth_token_missing",
                "message": "Zammad API token is not configured",
                "correlation_id": correlation_id,
            },
        )

    request_headers: dict[str, str] = {}
    if it_system.casefold() == "zammad":
        request_headers["Authorization"] = f"Token token={itsm_auth_token}"

    request_payload = {
        "source": "dq-made-easy",
        "request_type": "gx_validation_assistance",
        "assistance_request_mode": assistance_mode,
        "it_system": it_system,
        "run_plan_id": command.run_plan_id,
        "run_plan_version_id": _resolve_run_plan_version_id(command),
        "workspace_id": command.workspace_id,
        "error_message": command.error_message,
        "diagnostics": list(command.diagnostics or []),
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
                "message": f"Unable to reach {it_system} assistance endpoint",
                "correlation_id": correlation_id,
                "exception": exc.__class__.__name__,
            },
        ) from exc

    if not response.is_success:
        detail_message = extract_itsm_response_message(response.payload)
        if detail_message is None:
            detail_message = str(response.text or response.reason_phrase or "ITSM request failed").strip() or "ITSM request failed"
        raise HTTPException(
            status_code=502,
            detail={
                "error": "itsm_request_failed",
                "message": f"{it_system} rejected the assistance request: {detail_message}",
                "correlation_id": correlation_id,
                "status_code": response.status_code,
            },
        )

    ticket_number = extract_itsm_ticket_number(response.payload)
    if not ticket_number:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "itsm_ticket_missing",
                "message": f"{it_system} did not return a ticket number",
                "correlation_id": correlation_id,
            },
        )

    return GxAssistanceRequestResult(
        delivery_mode="itsm",
        message=f"Assistance request sent to {it_system} ticket {ticket_number}.",
        correlation_id=correlation_id,
        ticket_number=ticket_number,
        ticket_system=it_system,
        ticket_url=extract_itsm_ticket_url(response.payload),
    )