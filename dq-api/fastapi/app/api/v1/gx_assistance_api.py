from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import Request
import httpx

from app.api.presenters.gx import to_gx_assistance_request_response_view
from app.api.v1.schemas import GxAssistanceRequestResponseView
from app.api.v1.schemas import GxAssistanceRequestView
from app.application.use_cases.gx_assistance_requests import GxAssistanceTransportResponse
from app.application.use_cases.gx_assistance_requests import RequestGxAssistanceCommand
from app.application.use_cases.gx_assistance_requests import request_gx_assistance as request_gx_assistance_use_case
from app.domain.interfaces import AppConfigRepository


def request_correlation_id(request: Request | None) -> str:
    return (request.headers.get("X-Correlation-ID") if request is not None else None) or f"corr-{uuid4().hex[:12]}"


def build_request_command(
    *,
    request_view: GxAssistanceRequestView,
    request: Request | None,
    app_config_repository: AppConfigRepository,
) -> RequestGxAssistanceCommand:
    app_config = app_config_repository.get_app_config()
    return RequestGxAssistanceCommand(
        assistance_mode=str(getattr(app_config, "assistanceRequestMode", "") or "").strip().lower(),
        recipient_email=str(getattr(app_config, "assistanceRequestEmailAddress", "") or "").strip(),
        it_system=str(getattr(app_config, "assistanceRequestItsmSystem", "") or "").strip(),
        endpoint_url=str(getattr(app_config, "assistanceRequestItsmEndpointUrl", "") or "").strip(),
        itsm_auth_token=str(getattr(app_config, "assistanceRequestItsmAuthToken", "") or "").strip(),
        correlation_id=request_correlation_id(request),
        run_plan_id=request_view.runPlanId,
        run_plan_version_id=request_view.runPlanVersionId,
        workspace_id=request_view.workspaceId,
        error_message=request_view.errorMessage,
        diagnostics=list(request_view.diagnostics or []),
    )


async def send_itsm_request(
    endpoint_url: str,
    request_payload: dict[str, Any],
    request_headers: dict[str, str],
) -> GxAssistanceTransportResponse:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(endpoint_url, json=request_payload, headers=request_headers)

    response_payload: Any = None
    try:
        response_payload = response.json()
    except Exception:
        response_payload = None

    return GxAssistanceTransportResponse(
        status_code=response.status_code,
        is_success=response.is_success,
        payload=response_payload,
        text=response.text,
        reason_phrase=response.reason_phrase,
    )


async def create_assistance_request(
    *,
    request_view: GxAssistanceRequestView,
    request: Request,
    app_config_repository: AppConfigRepository,
) -> GxAssistanceRequestResponseView:
    result = await request_gx_assistance_use_case(
        command=build_request_command(
            request_view=request_view,
            request=request,
            app_config_repository=app_config_repository,
        ),
        send_itsm_request=send_itsm_request,
    )
    return to_gx_assistance_request_response_view(result)