from typing import Any

from pydantic import ConfigDict, Field

from app.api.v1.schemas.common_view import PaginationView
from app.api.v1.schemas.rule_compiler_view import CompilerExecutionTraceabilityView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class FailureDiagnosticView(SnakeModel):
    """Represents a single failure diagnostic from rule execution."""

    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    failureClass: str
    rowIdentifier: str | None = None
    details: str = ""
    affectedAttributes: list[str] | None = None


class DiagnosticsSummaryView(SnakeModel):
    """Aggregated diagnostics by failure class."""

    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    failureClass: str
    count: int
    sampleFailures: list[FailureDiagnosticView] = Field(default_factory=list)
    maxSampleSize: int = 5


class JoinConsistencyExecutionMetricsView(SnakeModel):
    """Metrics from JOIN_CONSISTENCY rule execution."""

    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    matchCount: int
    mismatchCount: int
    eligibleJoinedRows: int
    matchRate: float
    actualityDateMismatchCount: int = 0
    nullOrMissingJoinKeyCount: int = 0


class ExecutionMetricsView(SnakeModel):
    """Generic execution metrics container (union-like for different check types)."""

    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    checkType: str | None = None
    data: dict[str, Any] | None = None


class TestingExecutionContractView(SnakeModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_snake_alias,
        populate_by_name=True,
        extra="allow",
    )

    engineTarget: str | None = None
    inputFormat: str | None = None
    compatibilityPolicy: dict[str, Any] | None = None
    traceability: CompilerExecutionTraceabilityView | None = None
    requiredExecutionResultFields: list[str] = Field(default_factory=list)


class SchedulerHandoffView(SnakeModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_snake_alias,
        populate_by_name=True,
        extra="allow",
    )

    handoffId: str | None = None
    correlationId: str | None = None
    batchRequestId: str | None = None
    submittedAt: str | None = None
    executorTarget: str | None = None
    handoffStatus: str | None = None
    handoffReady: bool | None = None


class ExecutionContextView(SnakeModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_snake_alias,
        populate_by_name=True,
        extra="allow",
    )

    ruleId: str | None = None
    ruleVersionId: str | None = None
    ruleVersionNumber: int | None = None
    sourceRuleExpression: str | None = None
    compiledExpression: str | None = None
    executedExpression: str | None = None
    executedExpressionSource: str | None = None
    artifactKey: str | None = None
    compilerVersion: str | None = None
    compilerRevision: int | None = None
    compileStatus: str | None = None
    schemaVersion: str | None = None
    handoffReady: bool | None = None
    correlationId: str | None = None
    reason: str | None = None
    message: str | None = None
    executionContract: TestingExecutionContractView | None = None
    schedulerHandoff: SchedulerHandoffView | None = None
    semanticMatching: dict[str, Any] | None = None


class BatchTestRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    ruleId: str
    requestedBy: str
    requestedAt: str
    testDataConfig: dict[str, Any] = Field(default_factory=dict)
    executionCorrelationId: str | None = None
    status: str = "pending"
    workspace: str = "default"
    completedAt: str | None = None
    proofId: str | None = None


class BatchTestRequestsPageView(SnakeModel):
    data: list[BatchTestRequestView]
    pagination: PaginationView


class TestProofView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    ruleId: str = ""
    testDate: str = ""
    coverage: float = 0.0
    status: str = ""
    recordsTestedCount: int = 0
    failuresFound: int = 0
    proofData: dict[str, Any] = Field(default_factory=dict)
    executionContext: ExecutionContextView | None = None
    executionTrace: "ExecutionTraceView | None" = None
    metrics: JoinConsistencyExecutionMetricsView | None = None
    diagnostics: list[DiagnosticsSummaryView] | None = None


class ExecutionTraceView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    executionId: str = ""
    correlationId: str | None = None
    executedAt: str | None = None
    resultStatus: str = ""
    artifactKey: str | None = None
    ruleVersionId: str | None = None
    ruleVersionNumber: int | None = None
    compilerVersion: str | None = None
    compilerRevision: int | None = None
    schemaVersion: str | None = None


class TestRowResultView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    rowIndex: int
    data: dict[str, Any]
    passed: bool
    joinEvaluated: bool = False
    joinMatchedContexts: int = 0


class TestRunResultView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleId: str
    expression: str
    testDataSource: str
    totalTests: int
    passedCount: int
    failedCount: int
    successRate: float
    rulePassed: bool = False
    requiredSuccessRate: float | None = None
    timestamp: str
    results: list[TestRowResultView] = Field(default_factory=list)
    ruleDetails: dict[str, Any] = Field(default_factory=dict)
    executionContext: ExecutionContextView | None = None
    storedProof: TestProofView | None = None


class TestDataPayloadView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    versionId: str
    versionName: Any = None
    dataObjectId: Any = None
    attributeCount: int = 0
    sampleCount: int = 0
    samples: list[dict[str, Any]] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    generatedAt: str


class StoreTestProofResultView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    proofId: str
    ruleId: str
    testDate: str
    coverage: float
    passed: bool
    recordsTestedCount: int
    failuresFound: int
    successRate: float
    proofData: dict[str, Any] = Field(default_factory=dict)
    executionContext: ExecutionContextView | None = None
    executionTrace: ExecutionTraceView | None = None
    metrics: JoinConsistencyExecutionMetricsView | None = None
    diagnostics: list[DiagnosticsSummaryView] | None = None


class BatchTestRunResultView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    status: str
    executionContext: ExecutionContextView | None = None
