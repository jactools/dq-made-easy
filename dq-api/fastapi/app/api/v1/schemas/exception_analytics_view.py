from typing import Any

from pydantic import ConfigDict

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class ExceptionStoreRecordView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    dataObjectVersionId: str
    executionRunId: str
    ruleId: str
    dataPrimaryKey: str
    violationReason: str
    opsMetadata: dict[str, Any] | None = None
    detectedAt: str
    createdAt: str
    updatedAt: str


class ExceptionTrendBucketView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    bucketStart: str
    total: int


class ExceptionRuleHotspotView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleId: str
    ruleName: str
    total: int


class ExceptionDataObjectHotspotView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    dataObjectVersionId: str
    dataObjectName: str
    total: int


class ExceptionReasonHotspotView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    reasonCode: str
    reasonText: str
    total: int


class ExceptionReasonTrendBucketView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    bucketStart: str
    reasonCode: str
    reasonText: str
    total: int


class ExceptionReasonFluctuationView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    reasonCode: str
    reasonText: str
    firstBucketStart: str
    firstTotal: int
    latestBucketStart: str
    latestTotal: int
    netChange: int
    direction: str
    peakBucketStart: str
    peakTotal: int
    bucketCount: int


class ExceptionAnalyticsView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    totalFailedRecords: int
    runsWithFailures: int
    trendBuckets: list[ExceptionTrendBucketView]
    topRules: list[ExceptionRuleHotspotView]
    topDataObjects: list[ExceptionDataObjectHotspotView]
    topReasons: list[ExceptionReasonHotspotView]
    reasonTrendBuckets: list[ExceptionReasonTrendBucketView]
    reasonFluctuations: list[ExceptionReasonFluctuationView]