from typing import Any

from pydantic import ConfigDict, Field

from dq_domain_validation import GxArtifactEngineTarget
from dq_domain_validation import GxArtifactExecutionShape
from dq_domain_validation import GxExecutionStatus
from dq_domain_validation import LookbackUnit
from app.api.v1.schemas.gx_artifact_view import GxArtifactExecutionContractView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class GxExecutionRunStatusHistoryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    runId: str
    fromStatus: GxExecutionStatus | None = None
    toStatus: GxExecutionStatus
    changedBy: str | None = None
    changedAt: str
    reason: str | None = None
    details: dict[str, Any] | None = None


class GxExecutionProgressView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    percent: int
    label: str | None = None
    completedSteps: int | None = None
    totalSteps: int | None = None
    source: str | None = None
    updatedAt: str | None = None


class GxExecutionRunView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    suiteId: str | None = None
    suiteVersion: int | None = Field(default=None, ge=1)
    ruleId: str | None = None
    ruleVersionId: str | None = None
    runPlanId: str | None = None
    correlationId: str
    requestedBy: str | None = None
    engineTarget: GxArtifactEngineTarget
    executionShape: GxArtifactExecutionShape
    status: GxExecutionStatus
    submittedAt: str
    startedAt: str | None = None
    completedAt: str | None = None
    createdAt: str
    updatedAt: str
    executionContract: dict[str, Any] | None = None
    handoffPayload: dict[str, Any] | None = None
    resolvedDataDeliveryId: str | None = None
    executionProgress: GxExecutionProgressView | None = None
    resultSummary: dict[str, Any] = Field(default_factory=dict)
    performanceSummary: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    failureCode: str | None = None
    failureMessage: str | None = None
    comments: str | None = None
    statusHistory: list[GxExecutionRunStatusHistoryView] = Field(default_factory=list)


class GxExecutionRunSummaryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    suiteId: str | None = None
    suiteVersion: int | None = Field(default=None, ge=1)
    ruleId: str | None = None
    ruleName: str | None = None
    owner: str | None = None
    domain: str | None = None
    severity: str | None = None
    runPlanId: str | None = None
    dataObjectVersionId: str | None = None
    dataObjectNames: list[str] = Field(default_factory=list)
    resolvedDataDeliveryId: str | None = None
    correlationId: str
    requestedBy: str | None = None
    engineTarget: GxArtifactEngineTarget
    executionShape: GxArtifactExecutionShape
    status: GxExecutionStatus
    failedRecordCount: int = Field(default=0, ge=0)
    submittedAt: str
    startedAt: str | None = None
    completedAt: str | None = None
    createdAt: str
    updatedAt: str


class GxExecutionRunCountView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    name: str
    count: int


class GxExecutionRunStatisticsView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    lookbackAmount: int
    lookbackUnit: LookbackUnit
    recentLimit: int
    totalRuns: int
    pendingRuns: int
    runningRuns: int
    succeededRuns: int
    failedRuns: int
    cancelledRuns: int
    statusBreakdown: list[GxExecutionRunCountView] = Field(default_factory=list)
    engineTargetBreakdown: list[GxExecutionRunCountView] = Field(default_factory=list)
    executionShapeBreakdown: list[GxExecutionRunCountView] = Field(default_factory=list)
    recentRuns: list[GxExecutionRunSummaryView] = Field(default_factory=list)
