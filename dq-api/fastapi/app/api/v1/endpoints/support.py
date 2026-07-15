from __future__ import annotations

import json
import logging
import smtplib
import ssl
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ConfigDict

from dq_domain_validation import SupportDeliveryMode
from app.api.presenters.gx import extract_itsm_response_message
from app.api.presenters.gx import extract_itsm_ticket_number
from app.api.presenters.gx import extract_itsm_ticket_url
from app.api.presenters.support import build_support_delivery_message
from app.api.presenters.support import build_support_email_message
from app.api.presenters.support import build_support_email_mailto_url
from app.api.presenters.support import build_support_request_payload
from app.api.presenters.support import build_support_teams_payload
from app.api.presenters.support import build_zammad_ticket_payload
from app.api.presenters.support import normalize_support_destinations
from app.api.presenters.support import resolve_support_requester_email
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_app_config_repository
from app.core.request_context import get_user_id
from app.core.otel_metrics import increment_gx_failure
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import AppConfigRepository
from app.schemas.pydantic_base import SnakeModel, to_snake_alias

router = APIRouter(prefix="/support", tags=["support"])
_log = logging.getLogger(__name__)


class SupportRequestView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    referenceId: str | None = None
    title: str
    message: str
    source: str | None = None
    workspaceId: str | None = None
    runPlanId: str | None = None
    runPlanVersionId: str | None = None
    diagnostics: list[dict[str, Any]] | None = None
    details: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class SupportRequestResponseView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    referenceId: str
    correlationId: str
    deliveryModes: list[SupportDeliveryMode]
    message: str
    mailtoUrl: str | None = None
    recipientEmail: str | None = None
    ticketNumber: str | None = None
    ticketSystem: str | None = None
    ticketUrl: str | None = None


def _create_support_reference_id() -> str:
    return f"SUP-{uuid4().hex[:12].upper()}"


def _send_support_email(
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    message: EmailMessage,
) -> None:
    tls_context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15.0, context=tls_context) as client:
        client.login(smtp_username, smtp_password)
        refused_recipients = client.send_message(message)
        if refused_recipients:
            raise smtplib.SMTPRecipientsRefused(refused_recipients)


@router.post("/requests", response_model=SupportRequestResponseView)
async def create_support_request(
    request: Request,
    request_view: SupportRequestView,
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> SupportRequestResponseView:
    app_config = app_config_repository.get_app_config()
    reference_id = str(request_view.referenceId or "").strip() or _create_support_reference_id()
    correlation_id = str(request.headers.get("x-correlation-id") or "").strip() or f"corr-{uuid4().hex[:12]}"
    user_id = str(getattr(request.state, "user_id", None) or get_user_id() or "").strip() or None
    auth_claims = getattr(request.state, "auth_claims", None)

    configured_destinations = normalize_support_destinations(getattr(app_config, "assistanceRequestDestinations", None))

    if not configured_destinations:
        increment_gx_failure(surface="support_api", operation="request_support", reason="invalid_assistance_destinations")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_assistance_destinations",
                "message": "No support request destinations are configured",
                "reference_id": reference_id,
                "correlation_id": correlation_id,
            },
        )

    recipient_email = str(getattr(app_config, "assistanceRequestEmailAddress", "") or "").strip()
    it_system = str(getattr(app_config, "assistanceRequestItsmSystem", "") or "").strip()
    endpoint_url = str(getattr(app_config, "assistanceRequestItsmEndpointUrl", "") or "").strip()
    itsm_auth_token = str(getattr(app_config, "assistanceRequestItsmAuthToken", "") or "").strip()
    teams_webhook_url = str(getattr(app_config, "assistanceRequestTeamsWebhookUrl", "") or "").strip()
    delivered_destinations: list[str] = []
    mailto_url: str | None = None
    ticket_number: str | None = None
    ticket_url: str | None = None

    if "email" in configured_destinations:
        if not recipient_email:
            increment_gx_failure(surface="support_api", operation="request_support", reason="email_recipient_missing")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "email_recipient_missing",
                    "message": "Assistance request email address is not configured",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            )
        smtp_host = str(getattr(app_config, "supportEmailSmtpHost", "") or "").strip()
        smtp_port_value = getattr(app_config, "supportEmailSmtpPort", 587)
        smtp_username = str(getattr(app_config, "supportEmailSmtpUsername", "") or "").strip()
        smtp_password = str(getattr(app_config, "supportEmailSmtpPassword", "") or "").strip()
        smtp_from_address = str(getattr(app_config, "supportEmailFromAddress", "") or "").strip() or smtp_username
        email_mailto_url = build_support_email_mailto_url(recipient_email, request_view, correlation_id, reference_id)

        try:
            smtp_port = int(smtp_port_value)
        except (TypeError, ValueError):
            increment_gx_failure(surface="support_api", operation="request_support", reason="email_transport_invalid")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "email_transport_invalid",
                    "message": "Support email SMTP port is invalid",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            )

        if not smtp_host or not smtp_username or not smtp_password or not smtp_from_address:
            mailto_url = email_mailto_url
        else:
            email_message = build_support_email_message(
                recipient_email=recipient_email,
                sender_email=smtp_from_address,
                request_payload=request_view,
                correlation_id=correlation_id,
                reference_id=reference_id,
            )
            try:
                _send_support_email(
                    smtp_host=smtp_host,
                    smtp_port=smtp_port,
                    smtp_username=smtp_username,
                    smtp_password=smtp_password,
                    message=email_message,
                )
            except (OSError, smtplib.SMTPException) as exc:
                increment_gx_failure(surface="support_api", operation="request_support", reason="email_delivery_failed")
                _log.exception("Support email delivery failed")
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "email_delivery_failed",
                        "message": "Unable to send the support email through the configured SMTP relay",
                        "reference_id": reference_id,
                        "correlation_id": correlation_id,
                    },
                ) from exc
            mailto_url = None
        delivered_destinations.append("email")

    support_payload = build_support_request_payload(request_view, reference_id, correlation_id, user_id)

    if "teams" in configured_destinations:
        if not teams_webhook_url:
            increment_gx_failure(surface="support_api", operation="request_support", reason="teams_webhook_missing")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "teams_webhook_missing",
                    "message": "Assistance request Teams workflow webhook URL is not configured",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            )

        teams_payload = build_support_teams_payload(request_view, correlation_id, reference_id)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(teams_webhook_url, json=teams_payload)
        except Exception as exc:
            increment_gx_failure(surface="support_api", operation="request_support", reason="teams_unavailable")
            _log.exception("Teams support workflow failed")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "teams_unavailable",
                    "message": "Unable to reach the configured Teams support channel",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            ) from exc

        if response.status_code >= 400:
            increment_gx_failure(surface="support_api", operation="request_support", reason="teams_rejected_request")
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "teams_rejected_request",
                    "message": f"Teams rejected the assistance request ({response.status_code})",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            )

        delivered_destinations.append("teams")

    if "itsm" in configured_destinations:
        if not it_system:
            increment_gx_failure(surface="support_api", operation="request_support", reason="itsm_system_missing")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "itsm_system_missing",
                    "message": "Assistance request ITSM system is not configured",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            )

        if not endpoint_url:
            increment_gx_failure(surface="support_api", operation="request_support", reason="itsm_endpoint_missing")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "itsm_endpoint_missing",
                    "message": "Assistance request ITSM endpoint is not configured",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            )

        if it_system.casefold() == "zammad" and not itsm_auth_token:
            increment_gx_failure(surface="support_api", operation="request_support", reason="itsm_auth_token_missing")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "itsm_auth_token_missing",
                    "message": "Zammad API token is not configured",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            )

        ticket_payload = support_payload
        if it_system.casefold() == "zammad":
            requester_email = resolve_support_requester_email(admin_repository, user_id, auth_claims)
            if not requester_email:
                increment_gx_failure(surface="support_api", operation="request_support", reason="itsm_requester_missing")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "itsm_requester_missing",
                        "message": "Unable to resolve the requester email for the Zammad ticket",
                        "reference_id": reference_id,
                        "correlation_id": correlation_id,
                    },
                )
            ticket_payload = build_zammad_ticket_payload(request_view, reference_id, correlation_id, requester_email)

        request_headers: dict[str, str] = {}
        if it_system.casefold() == "zammad":
            request_headers["Authorization"] = f"Token token={itsm_auth_token}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(endpoint_url, json=ticket_payload, headers=request_headers)
        except Exception as exc:
            increment_gx_failure(surface="support_api", operation="request_support", reason="itsm_unavailable")
            _log.exception("ITSM support endpoint failed")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "itsm_unavailable",
                    "message": f"Unable to reach {it_system} assistance endpoint",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            ) from exc

        try:
            payload = response.json()
        except Exception:
            payload = None

        if response.status_code >= 400:
            increment_gx_failure(surface="support_api", operation="request_support", reason="itsm_rejected_request")
            detail_message = extract_itsm_response_message(payload) or "The ITSM endpoint rejected the assistance request"
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "itsm_rejected_request",
                    "message": detail_message,
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            )

        ticket_number = extract_itsm_ticket_number(payload)
        ticket_url = extract_itsm_ticket_url(payload)

        if not ticket_number:
            increment_gx_failure(surface="support_api", operation="request_support", reason="itsm_ticket_missing")
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "itsm_ticket_missing",
                    "message": f"{it_system} did not return a ticket number",
                    "reference_id": reference_id,
                    "correlation_id": correlation_id,
                },
            )

        delivered_destinations.append("itsm")

    if not delivered_destinations:
        increment_gx_failure(surface="support_api", operation="request_support", reason="invalid_assistance_destinations")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_assistance_destinations",
                "message": "No supported assistance destinations were selected",
                "reference_id": reference_id,
                "correlation_id": correlation_id,
            },
        )

    message = build_support_delivery_message(
        delivered_destinations,
        reference_id,
        recipient_email=recipient_email,
        email_draft_url=mailto_url,
        ticket_system=it_system,
        ticket_number=ticket_number,
    )

    return SupportRequestResponseView.model_validate(
        {
            "reference_id": reference_id,
            "correlation_id": correlation_id,
            "delivery_modes": delivered_destinations,
            "message": message,
            "mailto_url": mailto_url,
            "recipient_email": recipient_email if "email" in delivered_destinations else None,
            "ticket_number": ticket_number,
            "ticket_system": it_system if ticket_number else None,
            "ticket_url": ticket_url,
        }
    )