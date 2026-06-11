from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from dq_domain_validation import GxRunPlanGovernanceState
from dq_domain_validation import GxRunPlanPlanningMode
from dq_domain_validation import GxRunPlanTargetState
from dq_domain_validation import GxRunPlanValidationStatus
from dq_domain_validation import GxArtifactArtifactVersion
from app.api.v1.schemas.gx_artifact_view import GxArtifactAssignmentScopeView
from app.api.v1.schemas.gx_artifact_view import GxArtifactCompiledFromView
from app.api.v1.schemas.gx_artifact_view import GxArtifactEnvelopeView
from app.api.v1.schemas.gx_artifact_view import GxArtifactExecutionHintsView
from app.api.v1.schemas.gx_artifact_view import GxArtifactExecutionContractView
from app.api.v1.schemas.gx_artifact_view import GxArtifactResolvedExecutionScopeView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class GxRunPlanAssignmentScopeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    dataObjectId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)


class GxRunPlanScopeSelectorView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    assignmentScope: GxRunPlanAssignmentScopeView | None = None
    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)
    workspaceId: str | None = None


class GxRunPlanScheduleDefinitionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    scheduledAt: str | None = None


class GxRunPlanGroupedExecutionPlanView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    suiteCount: int | None = None
    batchCount: int | None = None


class GxRunPlanGroupedExecutionContractSnapshotView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    selectionMode: GxRunPlanPlanningMode | None = None
    suiteCount: int | None = None
    batchCount: int | None = None


class GxRunPlanSingleSuiteSnapshotView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True, extra="allow")

    suiteId: str | None = None
    suiteVersion: int | None = Field(default=None, ge=1)
    artifactVersion: GxArtifactArtifactVersion | None = None
    assignmentScope: GxArtifactAssignmentScopeView | None = None
    resolvedExecutionScope: GxArtifactResolvedExecutionScopeView | None = None
    gxSuite: dict[str, Any] | None = None
    compiledFrom: GxArtifactCompiledFromView | None = None
    executionHints: GxArtifactExecutionHintsView | None = None
    executionContract: GxArtifactExecutionContractView | None = None
    savedBy: str | None = None
    sourcePipeline: str | None = None
    dataObjectVersionId: str | None = None


class GxRunPlanSuiteRefView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    suiteId: str | None = None
    suiteVersion: int | None = Field(default=None, ge=1)
    engineType: str | None = None


class GxRunPlanSuiteSelectionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    selectionMode: GxRunPlanPlanningMode | None = None
    scopeSelector: GxRunPlanScopeSelectorView = Field(default_factory=GxRunPlanScopeSelectorView)
    suiteRefs: list[GxRunPlanSuiteRefView] = Field(default_factory=list)
    groupedExecutionPlan: GxRunPlanGroupedExecutionPlanView | None = None


class GxRunPlanGroupedSuiteSnapshotView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    groupedExecutionPlan: GxRunPlanGroupedExecutionPlanView
    suiteEnvelopes: list[GxRunPlanSingleSuiteSnapshotView] = Field(default_factory=list)


class GxRunPlanVersionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    runPlanVersionId: str
    runPlanId: str
    governanceState: GxRunPlanGovernanceState
    gxSuiteSelection: GxRunPlanSuiteSelectionView = Field(default_factory=GxRunPlanSuiteSelectionView)
    suiteId: str | None = None
    suiteVersion: int | None = Field(default=None, ge=1)
    suiteSnapshot: GxRunPlanGroupedSuiteSnapshotView | GxRunPlanSingleSuiteSnapshotView | None = Field(default=None, union_mode="left_to_right")
    scheduleDefinition: GxRunPlanScheduleDefinitionView = Field(default_factory=GxRunPlanScheduleDefinitionView)
    executionContractSnapshot: GxArtifactExecutionContractView | GxRunPlanGroupedExecutionContractSnapshotView | None = None
    validationStatus: str | None = None
    reviewStatus: str | None = None
    effectiveFrom: str | None = None
    supersedesVersionId: str | None = None
    createdBy: str | None = None
    createdAt: str


class GxRunPlanTransitionEventView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    runPlanId: str
    runPlanVersionId: str | None = None
    action: str
    fromState: GxRunPlanGovernanceState | None = None
    toState: GxRunPlanGovernanceState | None = None
    actorId: str | None = None
    correlationId: str | None = None
    effectiveFrom: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    occurredAt: str


class GxRunPlanView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    runPlanId: str
    businessKey: str | None = None
    workspaceId: str
    scopeSelector: GxRunPlanScopeSelectorView = Field(default_factory=GxRunPlanScopeSelectorView)
    planningMode: GxRunPlanPlanningMode
    currentActiveVersionId: str | None = None
    status: GxRunPlanGovernanceState
    pendingVersionId: str | None = None
    pendingVersionGovernanceState: GxRunPlanGovernanceState | None = None
    createdBy: str | None = None
    createdAt: str
    updatedAt: str
    activatedBy: str | None = None
    activatedAt: str | None = None
    lastDispatchedRunId: str | None = None
    versions: list[GxRunPlanVersionView] = Field(default_factory=list)
    transitionEvents: list[GxRunPlanTransitionEventView] = Field(default_factory=list)


class GxRunPlanCreateRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    workspaceId: str
    planningMode: GxRunPlanPlanningMode = "single_suite"
    suiteId: str | None = None
    suiteVersion: int | None = Field(default=None, ge=1)
    scheduledAt: datetime
    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)


class GxRunPlanActivationView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    plan: GxRunPlanView
    dispatch: dict[str, Any]


class GxRunPlanValidationDiagnosticView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    scope: str
    severity: str = "error"
    code: str
    message: str
    details: Any | None = None


class GxRunPlanValidationView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    plan: GxRunPlanView
    validationStatus: GxRunPlanValidationStatus
    message: str
    diagnostics: list[GxRunPlanValidationDiagnosticView] = Field(default_factory=list)


class GxRunPlanVersionCreateRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    planningMode: GxRunPlanPlanningMode = "single_suite"
    suiteId: str | None = None
    suiteVersion: int | None = Field(default=None, ge=1)
    scheduledAt: datetime
    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = None
    tagIds: list[str] = Field(default_factory=list)


class GxRunPlanGovernanceTransitionRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    targetState: GxRunPlanTargetState
    effectiveFrom: datetime | None = None