from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict, Field, ValidationError

from app.domain.entities.base import EntityModel
from app.schemas.pydantic_base import to_snake_alias


class SlaSloAdherenceEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    metricValue: float | int | None = Field(default=None, alias="metric_value")
    thresholdValue: float | int | None = Field(default=None, alias="threshold_value")
    thresholdOperator: str = Field(default="gte", alias="threshold_operator")
    observedEventCount: int = Field(default=0, alias="observed_event_count")
    compliantEventCount: int = Field(default=0, alias="compliant_event_count")
    nonCompliantEventCount: int = Field(default=0, alias="non_compliant_event_count")
    complianceRatePct: float | int | None = Field(default=None, alias="compliance_rate_pct")
    currentValue: float | int | None = Field(default=None, alias="current_value")
    currentObservedAt: str | None = Field(default=None, alias="current_observed_at")
    latestObservedAt: str | None = Field(default=None, alias="latest_observed_at")
    meetsTarget: bool | None = Field(default=None, alias="meets_target")
    summary: str | None = None


class SlaSloDefinitionEntity(EntityModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True, extra="forbid")

    id: str
    workspaceId: str = Field(alias="workspace_id")
    name: str
    description: str | None = None
    scopeKind: str = Field(alias="scope_kind")
    scopeId: str = Field(alias="scope_id")
    metricKind: str = Field(alias="metric_kind")
    thresholdValue: float | int = Field(alias="threshold_value")
    thresholdOperator: str = Field(default="gte", alias="threshold_operator")
    lookbackAmount: int = Field(default=30, alias="lookback_amount")
    lookbackUnit: str = Field(default="day", alias="lookback_unit")
    lifecycleStatus: str = Field(default="draft", alias="lifecycle_status")
    approvalStatus: str = Field(default="draft", alias="approval_status")
    requestedBy: str | None = Field(default=None, alias="requested_by")
    requestedAt: str | None = Field(default=None, alias="requested_at")
    reviewedBy: str | None = Field(default=None, alias="reviewed_by")
    reviewedAt: str | None = Field(default=None, alias="reviewed_at")
    itsmSystem: str | None = Field(default=None, alias="itsm_system")
    itsmTicketId: str | None = Field(default=None, alias="itsm_ticket_id")
    itsmTicketNumber: str | None = Field(default=None, alias="itsm_ticket_number")
    itsmTicketUrl: str | None = Field(default=None, alias="itsm_ticket_url")
    createdAt: str | None = Field(default=None, alias="created_at")
    updatedAt: str | None = Field(default=None, alias="updated_at")
    adherence: SlaSloAdherenceEntity | None = None


def build_sla_slo_adherence_entity(payload: Any) -> SlaSloAdherenceEntity | None:
    if isinstance(payload, SlaSloAdherenceEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    try:
        return SlaSloAdherenceEntity.model_validate(payload)
    except ValidationError:
        return None


def build_sla_slo_definition_entity(payload: Any) -> SlaSloDefinitionEntity | None:
    if isinstance(payload, SlaSloDefinitionEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None

    normalized = dict(payload)
    adherence = normalized.get("adherence")
    normalized["adherence"] = build_sla_slo_adherence_entity(adherence)
    try:
        return SlaSloDefinitionEntity.model_validate(normalized)
    except ValidationError:
        return None
