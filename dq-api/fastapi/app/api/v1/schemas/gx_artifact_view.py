from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field, model_validator

from dq_domain_validation import GxArtifactArtifactVersion
from dq_domain_validation import GxArtifactDispatchMode
from dq_domain_validation import GxArtifactEngineTarget
from dq_domain_validation import GxArtifactExecutionShape
from dq_domain_validation import GxArtifactExecutorTarget
from dq_domain_validation import GxArtifactHandoffStatus
from dq_domain_validation import GxArtifactJoinType
from dq_domain_validation import GxArtifactStatus
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


DATA_PRODUCT_ID_PATTERN = r"^(odcs\..+|prod-.+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})$"


class GxArtifactAssignmentScopeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    dataObjectId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = Field(default=None, pattern=DATA_PRODUCT_ID_PATTERN)
    tagIds: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_assignment_scope(self) -> "GxArtifactAssignmentScopeView":
        if any(
            value
            for value in (
                self.dataObjectId,
                self.datasetId,
                self.dataProductId,
                self.tagIds,
            )
        ):
            return self
        raise ValueError(
            "At least one assignment scope identifier is required: "
            "dataObjectId, datasetId, dataProductId, or tagIds"
        )


class GxArtifactResolvedExecutionScopeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    dataObjectVersionIds: list[str] = Field(min_length=1)


class GxArtifactCompiledFromView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleIds: list[str] = Field(default_factory=list)
    compilerVersion: str
    generatedAt: str


class GxArtifactFailedRowsPolicyView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    mode: str | None = None
    limit: int | None = None
    includeRowIdentifier: bool | None = None
    includePrimaryKey: bool | None = None


class GxArtifactEvidencePolicyView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    failedRows: GxArtifactFailedRowsPolicyView | None = None
    emitCompiledArtifact: bool | None = None
    emitGeneratedSql: bool | None = None


class GxArtifactExecutionHintsView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    recommendedEngine: GxArtifactEngineTarget
    primaryKeyFields: list[str] = Field(default_factory=list)
    businessKeyFields: list[str] = Field(default_factory=list)
    evidence: GxArtifactEvidencePolicyView | None = None


class GxArtifactSourceTargetView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    dataObjectId: str
    dataObjectVersionId: str
    datasetId: str | None = None
    dataProductId: str | None = Field(default=None, pattern=DATA_PRODUCT_ID_PATTERN)


class GxArtifactLandingZoneMaterializationView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    landingZoneArtifactId: str
    landingZoneVersionId: str
    outputLocation: str
    joinType: GxArtifactJoinType = "inner"
    joinKeys: list[str] = Field(default_factory=list)
    joinKeyPairs: list[dict[str, str]] = Field(default_factory=list)
    leftSource: GxArtifactSourceTargetView
    rightSource: GxArtifactSourceTargetView


class GxArtifactExecutionTraceabilityView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleId: str
    ruleVersionId: str
    gxSuiteId: str
    gxSuiteVersion: int = Field(ge=1)
    dataObjectVersionId: str | None = None
    sourceRuleExpression: str | None = None
    compiledExpression: str | None = None
    artifactKey: str | None = None


class GxArtifactExecutionContractView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    engineType: str
    engineTarget: GxArtifactEngineTarget
    executionShape: GxArtifactExecutionShape
    traceability: GxArtifactExecutionTraceabilityView
    sourceMaterialization: GxArtifactLandingZoneMaterializationView | None = None
    resolvedDataObjectVersionId: str | None = None
    resolvedDataDeliveryId: str | None = None
    resolvedDeliveryLocation: str | None = None
    deliveryResolutionMode: str | None = None

    @model_validator(mode="after")
    def validate_execution_contract(self) -> "GxArtifactExecutionContractView":
        if self.executionShape == "single_object":
            if self.sourceMaterialization is not None:
                raise ValueError("single_object execution must not define sourceMaterialization")
            return self

        if self.sourceMaterialization is None:
            raise ValueError("join_pair execution requires sourceMaterialization")
        return self


class GxArtifactEnvelopeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    suiteId: str
    suiteVersion: int = Field(ge=1)
    artifactVersion: GxArtifactArtifactVersion
    assignmentScope: GxArtifactAssignmentScopeView
    resolvedExecutionScope: GxArtifactResolvedExecutionScopeView
    gxSuite: dict[str, Any]
    compiledFrom: GxArtifactCompiledFromView
    executionHints: GxArtifactExecutionHintsView
    executionContract: GxArtifactExecutionContractView | None = None
    savedBy: str | None = None
    sourcePipeline: str | None = None


class GxSuiteRunHandoffView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    runId: str = Field(exclude=True)
    suiteId: str
    suiteVersion: int = Field(ge=1)
    correlationId: str
    businessKey: str | None = None
    requestedBy: str | None = None
    engineType: str | None = None
    engineTarget: GxArtifactEngineTarget
    executionShape: GxArtifactExecutionShape
    handoffStatus: GxArtifactHandoffStatus
    handoffReady: bool
    submittedAt: str
    executionContract: GxArtifactExecutionContractView

    @model_validator(mode="after")
    def derive_business_key(self) -> "GxSuiteRunHandoffView":
        if self.businessKey is None:
            self.businessKey = self.correlationId
        return self


class GxSuiteRunDispatchHandoffView(GxSuiteRunHandoffView):
    runId: str
    dispatchMode: GxArtifactDispatchMode
    executorTarget: GxArtifactExecutorTarget
    queueKey: str
    queueMessageId: str = Field(exclude=True)
    scheduledAt: str


class GxSuiteRunScheduleRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    scheduledAt: datetime


class GxSuiteRetrievalQueryView(SnakeModel):
    dataObjectId: str | None = None
    dataObjectVersionId: str | None = None
    datasetId: str | None = None
    dataProductId: str | None = Field(default=None, pattern=DATA_PRODUCT_ID_PATTERN)
    status: GxArtifactStatus = "active"
    latestOnly: bool = True

    @model_validator(mode="after")
    def validate_primary_scope(self) -> "GxSuiteRetrievalQueryView":
        primary_scope_count = sum(
            bool(value)
            for value in (
                self.dataObjectId,
                self.dataObjectVersionId,
                self.datasetId,
                self.dataProductId,
            )
        )
        if primary_scope_count == 1:
            return self
        raise ValueError(
            "Exactly one primary scope filter is required: dataObjectId, "
            "dataObjectVersionId, datasetId, or dataProductId"
        )


class GxSuiteDirectFetchQueryView(SnakeModel):
    suiteVersion: int | None = Field(default=None, ge=1)


class GxSuiteStatusHistoryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    suiteId: str
    suiteVersion: int
    fromStatus: str | None = None
    toStatus: str
    changedBy: str | None = None
    changedAt: str
    reason: str | None = None
