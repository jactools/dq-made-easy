from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field
from pydantic import model_validator

from app.schemas.pydantic_base import SnakeModel


class ValidationRunPlanAssignmentScopeView(SnakeModel):
    dataObjectId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)


class ValidationRunPlanScopeSelectorView(SnakeModel):
    assignmentScope: ValidationRunPlanAssignmentScopeView | None = None
    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)
    workspaceId: str | None = None


class ValidationRunPlanScheduleDefinitionView(SnakeModel):
    scheduledAt: str | None = None


class ValidationRunPlanVersionView(SnakeModel):
    runPlanVersionId: str
    governanceState: str
    scheduleDefinition: ValidationRunPlanScheduleDefinitionView = Field(default_factory=ValidationRunPlanScheduleDefinitionView)
    createdAt: str


class ValidationRunPlanView(SnakeModel):
    runPlanId: str
    businessKey: str | None = None
    workspaceId: str
    scopeSelector: ValidationRunPlanScopeSelectorView = Field(default_factory=ValidationRunPlanScopeSelectorView)
    planningMode: str
    currentActiveVersionId: str | None = None
    status: str
    pendingVersionId: str | None = None
    pendingVersionGovernanceState: str | None = None
    createdBy: str | None = None
    createdAt: str
    updatedAt: str
    activatedBy: str | None = None
    activatedAt: str | None = None
    lastDispatchedRunId: str | None = None
    versions: list[ValidationRunPlanVersionView] = Field(default_factory=list)


class ValidationRunPlanReplayView(SnakeModel):
    runId: str
    queueMessageId: str
    runPlanId: str
    runPlanVersionId: str
    triggerType: str | None = None
    sourcePipeline: str | None = None
    selectionMode: str | None = None
    suiteId: str | None = None
    suiteVersion: int | None = None
    engineType: str | None = None
    engineTarget: str | None = None
    executionShape: str | None = None
    dispatchMode: str | None = None
    queueKey: str | None = None
    scheduledAt: str
    correlationId: str | None = None


class ValidationRunPlanReplayRequestView(SnakeModel):
    triggerType: Literal["manual", "pipeline_run", "schedule"] = "manual"
    sourcePipeline: str | None = None
    scheduledAt: datetime | None = None

    @model_validator(mode="after")
    def validate_pipeline_trigger(self) -> ValidationRunPlanReplayRequestView:
        if self.triggerType == "pipeline_run" and not str(self.sourcePipeline or "").strip():
            raise ValueError("source_pipeline is required when trigger_type is pipeline_run")
        return self
