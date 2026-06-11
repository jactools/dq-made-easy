from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


class GxExecutionViolationEntity(EntityModel):
    id: str
    dataObjectVersionId: str
    executionRunId: str
    ruleId: str
    dataPrimaryKey: str
    violationReason: str
    opsMetadata: dict[str, Any] = Field(default_factory=dict)
    detectedAt: str | None = None
    createdAt: str
    updatedAt: str


class GxExecutionViolationCreateEntity(EntityModel):
    id: str | None = None
    dataObjectVersionId: str
    executionRunId: str
    ruleId: str
    dataPrimaryKey: str
    violationReason: str
    opsMetadata: dict[str, Any] = Field(default_factory=dict)
    detectedAt: str | None = None


class GxExecutionViolationListEntity(EntityModel):
    data: list[GxExecutionViolationEntity] = Field(default_factory=list)
    total: int = 0


class GxExecutionViolationTrendTotalEntity(EntityModel):
    bucket_start: str
    total: int


class GxExecutionViolationRuleTotalEntity(EntityModel):
    rule_id: str
    total: int


class GxExecutionViolationDataObjectTotalEntity(EntityModel):
    data_object_version_id: str
    total: int


class GxExecutionViolationReasonTotalEntity(EntityModel):
    reason_code: str
    reason_text: str
    total: int

class GxExecutionViolationReasonTrendTotalEntity(EntityModel):
    bucket_start: str
    reason_code: str
    reason_text: str
    total: int


class GxExecutionExceptionTrendBucketEntity(EntityModel):
    bucketStart: str
    total: int


class GxExecutionExceptionRuleHotspotEntity(EntityModel):
    ruleId: str
    ruleName: str
    total: int


class GxExecutionExceptionDataObjectHotspotEntity(EntityModel):
    dataObjectVersionId: str
    dataObjectName: str
    total: int


class GxExecutionExceptionReasonHotspotEntity(EntityModel):
    reasonCode: str
    reasonText: str
    total: int

class GxExecutionExceptionReasonTrendBucketEntity(EntityModel):
    bucketStart: str
    reasonCode: str
    reasonText: str
    total: int


class GxExecutionExceptionReasonFluctuationEntity(EntityModel):
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


class GxExecutionExceptionAnalyticsEntity(EntityModel):
    totalFailedRecords: int = 0
    runsWithFailures: int = 0
    trendBuckets: list[GxExecutionExceptionTrendBucketEntity] = Field(default_factory=list)
    topRules: list[GxExecutionExceptionRuleHotspotEntity] = Field(default_factory=list)
    topDataObjects: list[GxExecutionExceptionDataObjectHotspotEntity] = Field(default_factory=list)
    topReasons: list[GxExecutionExceptionReasonHotspotEntity] = Field(default_factory=list)
    reasonTrendBuckets: list[GxExecutionExceptionReasonTrendBucketEntity] = Field(default_factory=list)
    reasonFluctuations: list[GxExecutionExceptionReasonFluctuationEntity] = Field(default_factory=list)


class GxExecutionViolationSummaryEntity(EntityModel):
    total_failed_records: int = 0
    runs_with_failures: int = 0
    trend_totals: list[GxExecutionViolationTrendTotalEntity] = Field(default_factory=list)
    rule_totals: list[GxExecutionViolationRuleTotalEntity] = Field(default_factory=list)
    data_object_totals: list[GxExecutionViolationDataObjectTotalEntity] = Field(default_factory=list)
    reason_totals: list[GxExecutionViolationReasonTotalEntity] = Field(default_factory=list)
    reason_trend_totals: list[GxExecutionViolationReasonTrendTotalEntity] = Field(default_factory=list)


def build_gx_execution_violation_entity(payload: Mapping[str, Any]) -> GxExecutionViolationEntity:
    return GxExecutionViolationEntity(
        id=str(payload.get("id") or ""),
        dataObjectVersionId=str(payload.get("dataObjectVersionId") or ""),
        executionRunId=str(payload.get("executionRunId") or ""),
        ruleId=str(payload.get("ruleId") or ""),
        dataPrimaryKey=str(payload.get("dataPrimaryKey") or ""),
        violationReason=str(payload.get("violationReason") or ""),
        opsMetadata=dict(payload.get("opsMetadata") or {}),
        detectedAt=(str(payload.get("detectedAt")) if payload.get("detectedAt") is not None else None),
        createdAt=str(payload.get("createdAt") or ""),
        updatedAt=str(payload.get("updatedAt") or ""),
    )


def build_gx_execution_violation_list_entity(payload: Mapping[str, Any]) -> GxExecutionViolationListEntity:
    rows = payload.get("data") if isinstance(payload.get("data"), list) else []
    return GxExecutionViolationListEntity(
        data=[build_gx_execution_violation_entity(item) for item in rows if isinstance(item, Mapping)],
        total=int(payload.get("total") or 0),
    )


def build_gx_execution_violation_summary_entity(payload: Mapping[str, Any]) -> GxExecutionViolationSummaryEntity:
    trend_rows = payload.get("trend_totals") if isinstance(payload.get("trend_totals"), list) else []
    rule_rows = payload.get("rule_totals") if isinstance(payload.get("rule_totals"), list) else []
    data_object_rows = payload.get("data_object_totals") if isinstance(payload.get("data_object_totals"), list) else []
    reason_rows = payload.get("reason_totals") if isinstance(payload.get("reason_totals"), list) else []
    reason_trend_rows = payload.get("reason_trend_totals") if isinstance(payload.get("reason_trend_totals"), list) else []

    return GxExecutionViolationSummaryEntity(
        total_failed_records=int(payload.get("total_failed_records") or 0),
        runs_with_failures=int(payload.get("runs_with_failures") or 0),
        trend_totals=[
            GxExecutionViolationTrendTotalEntity(
                bucket_start=str(item.get("bucket_start") or ""),
                total=int(item.get("total") or 0),
            )
            for item in trend_rows
            if isinstance(item, Mapping)
        ],
        rule_totals=[
            GxExecutionViolationRuleTotalEntity(
                rule_id=str(item.get("rule_id") or ""),
                total=int(item.get("total") or 0),
            )
            for item in rule_rows
            if isinstance(item, Mapping)
        ],
        data_object_totals=[
            GxExecutionViolationDataObjectTotalEntity(
                data_object_version_id=str(item.get("data_object_version_id") or ""),
                total=int(item.get("total") or 0),
            )
            for item in data_object_rows
            if isinstance(item, Mapping)
        ],
        reason_totals=[
            GxExecutionViolationReasonTotalEntity(
                reason_code=str(item.get("reason_code") or ""),
                reason_text=str(item.get("reason_text") or ""),
                total=int(item.get("total") or 0),
            )
            for item in reason_rows
            if isinstance(item, Mapping)
        ],
        reason_trend_totals=[
            GxExecutionViolationReasonTrendTotalEntity(
                bucket_start=str(item.get("bucket_start") or ""),
                reason_code=str(item.get("reason_code") or ""),
                reason_text=str(item.get("reason_text") or ""),
                total=int(item.get("total") or 0),
            )
            for item in reason_trend_rows
            if isinstance(item, Mapping)
        ],
    )


def build_gx_execution_exception_analytics_entity(payload: Mapping[str, Any]) -> GxExecutionExceptionAnalyticsEntity:
    trend_rows = payload.get("trendBuckets") if isinstance(payload.get("trendBuckets"), list) else []
    rule_rows = payload.get("topRules") if isinstance(payload.get("topRules"), list) else []
    data_object_rows = payload.get("topDataObjects") if isinstance(payload.get("topDataObjects"), list) else []
    reason_rows = payload.get("topReasons") if isinstance(payload.get("topReasons"), list) else []
    reason_trend_rows = payload.get("reasonTrendBuckets") if isinstance(payload.get("reasonTrendBuckets"), list) else []
    reason_fluctuation_rows = payload.get("reasonFluctuations") if isinstance(payload.get("reasonFluctuations"), list) else []

    return GxExecutionExceptionAnalyticsEntity(
        totalFailedRecords=int(payload.get("totalFailedRecords") or 0),
        runsWithFailures=int(payload.get("runsWithFailures") or 0),
        trendBuckets=[
            GxExecutionExceptionTrendBucketEntity(
                bucketStart=str(item.get("bucketStart") or ""),
                total=int(item.get("total") or 0),
            )
            for item in trend_rows
            if isinstance(item, Mapping)
        ],
        topRules=[
            GxExecutionExceptionRuleHotspotEntity(
                ruleId=str(item.get("ruleId") or ""),
                ruleName=str(item.get("ruleName") or ""),
                total=int(item.get("total") or 0),
            )
            for item in rule_rows
            if isinstance(item, Mapping)
        ],
        topDataObjects=[
            GxExecutionExceptionDataObjectHotspotEntity(
                dataObjectVersionId=str(item.get("dataObjectVersionId") or ""),
                dataObjectName=str(item.get("dataObjectName") or ""),
                total=int(item.get("total") or 0),
            )
            for item in data_object_rows
            if isinstance(item, Mapping)
        ],
        topReasons=[
            GxExecutionExceptionReasonHotspotEntity(
                reasonCode=str(item.get("reasonCode") or ""),
                reasonText=str(item.get("reasonText") or ""),
                total=int(item.get("total") or 0),
            )
            for item in reason_rows
            if isinstance(item, Mapping)
        ],
        reasonTrendBuckets=[
            GxExecutionExceptionReasonTrendBucketEntity(
                bucketStart=str(item.get("bucketStart") or ""),
                reasonCode=str(item.get("reasonCode") or ""),
                reasonText=str(item.get("reasonText") or ""),
                total=int(item.get("total") or 0),
            )
            for item in reason_trend_rows
            if isinstance(item, Mapping)
        ],
        reasonFluctuations=[
            GxExecutionExceptionReasonFluctuationEntity(
                reasonCode=str(item.get("reasonCode") or ""),
                reasonText=str(item.get("reasonText") or ""),
                firstBucketStart=str(item.get("firstBucketStart") or ""),
                firstTotal=int(item.get("firstTotal") or 0),
                latestBucketStart=str(item.get("latestBucketStart") or ""),
                latestTotal=int(item.get("latestTotal") or 0),
                netChange=int(item.get("netChange") or 0),
                direction=str(item.get("direction") or "flat"),
                peakBucketStart=str(item.get("peakBucketStart") or ""),
                peakTotal=int(item.get("peakTotal") or 0),
                bucketCount=int(item.get("bucketCount") or 0),
            )
            for item in reason_fluctuation_rows
            if isinstance(item, Mapping)
        ],
    )