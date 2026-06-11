from __future__ import annotations

from pydantic import ConfigDict, Field

from app.api.v1.schemas.exception_fact_view import ExceptionFactView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class ExceptionAnalysisSliceRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    dataObjectVersionId: str
    executionRunId: str
    ruleId: str
    reasonCodes: list[str] = Field(default_factory=list)
    failureClass: str | None = None
    recordIdentifierType: str | None = None
    recordIdentifierValueContains: str | None = None
    search: str | None = None
    detectedAfter: str | None = None
    detectedBefore: str | None = None
    hashStripe: int | None = None
    hashStripeCount: int | None = None
    sliceLimit: int = 200
    runUntilExhausted: bool = False
    maxSlices: int | None = None
    maxRecords: int | None = None
    maxSeconds: int | None = None
    summaryOnly: bool = False


class ExceptionAnalysisSliceSuggestionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    reasonCodes: list[str] = Field(default_factory=list)
    failureClass: str | None = None
    recordIdentifierType: str | None = None
    recordIdentifierValueContains: str | None = None
    search: str | None = None
    detectedAfter: str | None = None
    detectedBefore: str | None = None
    hashStripe: int | None = None
    hashStripeCount: int | None = None
    remainingCount: int = 0
    partitionStrategy: list[str] = Field(default_factory=list)
    rationale: str


class ExceptionAnalysisSessionStatusView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    state: str
    reason: str
    progressPercent: float = 0.0
    remainingCount: int = 0
    estimatedRemainingRecordCount: int = 0
    estimatedRemainingSliceCount: int = 0
    estimatedCostImpact: str = ""
    sliceCount: int = 0
    materializedRecordCount: int = 0
    maxSlices: int | None = None
    maxRecords: int | None = None
    maxSeconds: int | None = None
    budgetHit: bool = False
    exhausted: bool = False
    stalled: bool = False


class ExceptionAnalysisSliceSummaryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    analysisSessionId: str
    analysisSliceId: str
    sliceIndex: int
    dataObjectVersionId: str
    executionRunId: str
    ruleId: str
    sliceLimit: int
    anchorTotalCount: int = 0
    totalMatchingCount: int = 0
    returnedCount: int = 0
    truncated: bool = False
    analysisPackUri: str
    analysisPackSha256: str
    analysisManifestUri: str
    analysisManifestSha256: str
    filters: ExceptionAnalysisSliceRequestView
    nextSliceSuggestion: ExceptionAnalysisSliceSuggestionView | None = None
    createdAt: str
    updatedAt: str


class ExceptionAnalysisSliceDetailView(ExceptionAnalysisSliceSummaryView):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    records: list[ExceptionFactView] = Field(default_factory=list)


class ExceptionAnalysisSessionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    analysisSessionId: str
    dataObjectVersionId: str
    executionRunId: str
    ruleId: str
    anchorTotalCount: int = 0
    sliceCount: int = 0
    createdAt: str
    updatedAt: str
    analysisStatus: ExceptionAnalysisSessionStatusView | None = None
    currentSlice: ExceptionAnalysisSliceDetailView
    slices: list[ExceptionAnalysisSliceSummaryView] = Field(default_factory=list)
