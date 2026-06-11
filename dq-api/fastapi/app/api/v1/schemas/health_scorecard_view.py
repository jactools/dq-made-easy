from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class HealthScorecardTopRuleView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleId: str
    ruleName: str
    dimension: str | None = None
    total: int


class HealthScorecardTopReasonView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    reasonCode: str
    reasonText: str
    total: int


class HealthScorecardTrendBucketView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    bucketStart: str
    total: int


class HealthScorecardReasonTrendBucketView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    bucketStart: str
    reasonCode: str
    reasonText: str
    total: int


class HealthScorecardDimensionRollupView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    dimension: str
    ruleCount: int
    failedRecordTotal: int
    failedRunCount: int
    score: int
    statusLabel: str


class HealthScorecardOwnershipRollupView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    scopeKind: str
    scopeId: str
    scopeName: str
    assetCount: int
    trackedDataObjectVersionCount: int
    totalRuns: int
    pendingRuns: int
    runningRuns: int
    succeededRuns: int
    failedRuns: int
    cancelledRuns: int
    totalFailedRecords: int
    runsWithFailures: int
    overallScore: int
    healthLabel: str
    summary: str


class HealthScorecardRegressionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    bucketStart: str
    previousBucketStart: str
    previousTotal: int
    currentTotal: int
    delta: int


class HealthScorecardIncidentView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    incidentId: str
    title: str
    status: str
    severity: str | None = None
    incidentKind: str
    assignedTo: str | None = None
    runId: str | None = None
    runPlanId: str | None = None


class HealthScorecardWorkspaceSummaryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    workspaceId: str
    generatedAt: str
    overallScore: int
    healthLabel: str
    summary: str
    topRegressions: list[HealthScorecardRegressionView] = Field(default_factory=list)
    topRules: list[HealthScorecardTopRuleView] = Field(default_factory=list)
    ownershipRollups: list[HealthScorecardOwnershipRollupView] = Field(default_factory=list)
    activeIncidentCount: int
    activeIncidents: list[HealthScorecardIncidentView] = Field(default_factory=list)


class HealthScorecardView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    scopeType: str
    scopeId: str
    scopeName: str
    workspaceId: str
    dataAssetId: str | None = None
    dataAssetName: str | None = None
    dataAssetVersionId: str | None = None
    trackedDataObjectVersionIds: list[str] = Field(default_factory=list)
    lookbackAmount: int
    lookbackUnit: str
    generatedAt: str
    overallScore: int
    healthLabel: str
    summary: str
    totalRuns: int
    pendingRuns: int
    runningRuns: int
    succeededRuns: int
    failedRuns: int
    cancelledRuns: int
    totalFailedRecords: int
    runsWithFailures: int
    dimensionRollups: list[HealthScorecardDimensionRollupView] = Field(default_factory=list)
    topRules: list[HealthScorecardTopRuleView] = Field(default_factory=list)
    topReasons: list[HealthScorecardTopReasonView] = Field(default_factory=list)
    trendBuckets: list[HealthScorecardTrendBucketView] = Field(default_factory=list)
    reasonTrendBuckets: list[HealthScorecardReasonTrendBucketView] = Field(default_factory=list)


class HealthScorecardPageView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    workspaceId: str
    dataAssetId: str | None = None
    lookbackAmount: int
    lookbackUnit: str
    generatedAt: str
    workspaceSummary: HealthScorecardWorkspaceSummaryView | None = None
    scorecards: list[HealthScorecardView] = Field(default_factory=list)
