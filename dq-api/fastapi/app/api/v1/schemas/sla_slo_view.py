from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class SlaSloAdherenceView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

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


class SlaSloDefinitionView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

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
    adherence: SlaSloAdherenceView | None = None


class SlaSloSummaryView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    workspaceId: str | None = Field(default=None, alias="workspace_id")
    definitions: list[SlaSloDefinitionView] = Field(default_factory=list)
    totalDefinitions: int = Field(default=0, alias="total_definitions")
    activeDefinitions: int = Field(default=0, alias="active_definitions")
    draftDefinitions: int = Field(default=0, alias="draft_definitions")
    approvedDefinitions: int = Field(default=0, alias="approved_definitions")
    deprecatedDefinitions: int = Field(default=0, alias="deprecated_definitions")
    compliantDefinitions: int = Field(default=0, alias="compliant_definitions")
    atRiskDefinitions: int = Field(default=0, alias="at_risk_definitions")


class SlaSloBreachView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    definitionId: str = Field(alias="definition_id")
    definitionName: str = Field(alias="definition_name")
    scopeKind: str = Field(alias="scope_kind")
    scopeId: str = Field(alias="scope_id")
    metricKind: str = Field(alias="metric_kind")
    thresholdValue: float | int = Field(alias="threshold_value")
    thresholdOperator: str = Field(alias="threshold_operator")
    currentValue: float | int | None = Field(default=None, alias="current_value")
    observedEventCount: int = Field(default=0, alias="observed_event_count")
    emittedAt: str = Field(alias="emitted_at")
    correlationId: str = Field(alias="correlation_id")
    severity: str
    summary: str | None = None


class SlaSloEvaluationView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    workspaceId: str = Field(alias="workspace_id")
    evaluatedAt: str = Field(alias="evaluated_at")
    evaluatedDefinitions: int = Field(alias="evaluated_definitions")
    breachedDefinitions: int = Field(alias="breached_definitions")
    breachEventsRecorded: int = Field(alias="breach_events_recorded")
    breaches: list[SlaSloBreachView] = Field(default_factory=list)


class SlaSloDefinitionUpsertView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

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


class SlaSloDefinitionReviewView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    comments: str | None = None
