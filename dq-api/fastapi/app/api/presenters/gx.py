from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict, Field

from app.api.v1.schemas import GxAssistanceRequestResponseView
from app.api.v1.schemas import GxRunPlanActivationView
from app.api.v1.schemas import GxRunPlanValidationView
from app.api.v1.schemas import GxRunPlanView
from app.api.v1.schemas import GxSuiteRunDispatchHandoffView
from app.domain.entities.base import EntityModel
from app.domain.entities.gx_suite import build_gx_suite_entity
from app.domain.entities.gx_suite import build_gx_suite_expectation_entity
from app.domain.entities.gx_suite import GxSuiteEntity
from app.domain.entities.gx_suite import GxSuiteExpectationEntity
from app.schemas.pydantic_base import to_snake_alias


class ItsmTicketEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    number: str | None = None
    id: str | None = None


class ItsmDataEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    ticketNumber: str | None = None
    ticketId: str | None = None
    id: str | None = None


class ItsmResponseEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    ticketNumber: str | None = None
    ticketId: str | None = None
    id: str | None = None
    ticket: ItsmTicketEntity | None = None
    data: ItsmDataEntity | None = None
    ticketUrl: str | None = None


def _normalize_itsm_identifier_fields(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = dict(payload)

    for field_name in ("id", "number", "ticketId", "ticket_id", "ticketNumber", "ticket_number"):
        if field_name in normalized_payload and normalized_payload[field_name] is not None:
            normalized_payload[field_name] = str(normalized_payload[field_name])

    ticket_payload = normalized_payload.get("ticket")
    if isinstance(ticket_payload, Mapping):
        normalized_payload["ticket"] = _normalize_itsm_identifier_fields(dict(ticket_payload))

    data_payload = normalized_payload.get("data")
    if isinstance(data_payload, Mapping):
        normalized_payload["data"] = _normalize_itsm_identifier_fields(dict(data_payload))

    return normalized_payload


def build_itsm_ticket_entity(payload: Any) -> ItsmTicketEntity | None:
    if isinstance(payload, ItsmTicketEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    return ItsmTicketEntity.model_validate(payload)


def build_itsm_data_entity(payload: Any) -> ItsmDataEntity | None:
    if isinstance(payload, ItsmDataEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    return ItsmDataEntity.model_validate(payload)


def build_itsm_response_entity(payload: Any) -> ItsmResponseEntity | None:
    if isinstance(payload, ItsmResponseEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    normalized_payload = _normalize_itsm_identifier_fields(dict(payload))
    normalized_payload["ticket"] = build_itsm_ticket_entity(normalized_payload.get("ticket"))
    normalized_payload["data"] = build_itsm_data_entity(normalized_payload.get("data"))
    return ItsmResponseEntity.model_validate(normalized_payload)


def extract_itsm_ticket_number(payload: Any) -> str | None:
    response = build_itsm_response_entity(payload)
    if response is None:
        return None

    candidates = [response.ticketNumber, response.ticketId, response.id]
    if response.ticket is not None:
        candidates.extend([response.ticket.number, response.ticket.id])
    if response.data is not None:
        candidates.extend([response.data.ticketNumber, response.data.ticketId, response.data.id])

    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return None


def extract_itsm_ticket_id(payload: Any) -> str | None:
    response = build_itsm_response_entity(payload)
    if response is None:
        return None

    candidates = [response.ticketId, response.id]
    if response.ticket is not None:
        candidates.append(response.ticket.id)
    if response.data is not None:
        candidates.extend([response.data.ticketId, response.data.id])

    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return None


def extract_itsm_ticket_url(payload: Any) -> str | None:
    response = build_itsm_response_entity(payload)
    if response is None:
        return None

    candidates = [response.ticketUrl]
    extra = getattr(response, "model_extra", None) or {}
    candidates.extend([extra.get("ticket_url"), extra.get("ticketUrl"), extra.get("url")])

    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return None


def extract_itsm_response_message(payload: Any) -> str | None:
    response = build_itsm_response_entity(payload)
    if response is None:
        return None

    extra = getattr(response, "model_extra", None) or {}
    for key in ("message", "detail", "error"):
        value = str(extra.get(key) or "").strip()
        if value:
            return value
    return None


def to_gx_suite_run_dispatch_handoff_view(payload: Any) -> GxSuiteRunDispatchHandoffView:
    return GxSuiteRunDispatchHandoffView.model_validate(payload)


def to_gx_suite_run_dispatch_handoff_views(payloads: list[Any]) -> list[GxSuiteRunDispatchHandoffView]:
    return [to_gx_suite_run_dispatch_handoff_view(payload) for payload in payloads]


def to_gx_run_plan_view(row: Any) -> GxRunPlanView:
    return GxRunPlanView.model_validate(row)


def _build_gx_run_plan_validation_plan_payload(result: Any) -> dict[str, Any]:
    plan = result.plan
    payload = plan.model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(plan, "model_dump") else dict(plan)
    diagnostic_codes = {
        str(getattr(item, "code", "") or (item.get("code") if isinstance(item, dict) else "")).strip()
        for item in (result.diagnostics or [])
    }
    if diagnostic_codes.isdisjoint({"invalid_suite_snapshot", "invalid_grouped_suite_snapshot"}):
        return payload

    target_version_id = payload.get("pendingVersionId")
    versions = payload.get("versions")
    if not isinstance(versions, list):
        return payload

    for version in versions:
        if not isinstance(version, dict):
            continue
        if target_version_id is not None and version.get("runPlanVersionId") != target_version_id:
            continue
        version["suiteSnapshot"] = None
    return payload


def to_gx_run_plan_validation_view(result: Any) -> GxRunPlanValidationView:
    return GxRunPlanValidationView.model_validate(
        {
            "plan": to_gx_run_plan_view(_build_gx_run_plan_validation_plan_payload(result)).model_dump(),
            "validationStatus": result.validation_status,
            "message": result.message,
            "diagnostics": [item.model_dump(by_alias=True, exclude_none=True) for item in result.diagnostics],
        }
    )


def to_gx_run_plan_activation_view(result: Any) -> GxRunPlanActivationView:
    return GxRunPlanActivationView.model_validate(
        {
            "plan": to_gx_run_plan_view(result.plan).model_dump(),
            "dispatch": result.dispatch.model_dump(by_alias=True, exclude_none=True),
        }
    )


def to_gx_assistance_request_response_view(result: Any) -> GxAssistanceRequestResponseView:
    return GxAssistanceRequestResponseView.model_validate(
        {
            "deliveryMode": result.delivery_mode,
            "message": result.message,
            "correlationId": result.correlation_id,
            "mailtoUrl": result.mailto_url,
            "recipientEmail": result.recipient_email,
            "ticketNumber": result.ticket_number,
            "ticketSystem": result.ticket_system,
            "ticketUrl": result.ticket_url,
        }
    )