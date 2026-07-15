from __future__ import annotations

import math
from typing import Any

from pydantic import ConfigDict, Field

from app.api.v1.schemas.exception_analytics_view import ExceptionAnalyticsView
from app.api.v1.schemas.common_view import PaginationView
from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class ExceptionExecutionScopeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    deliveryId: str | None = None
    executionPlanId: str | None = None
    executionPlanVersionId: str | None = None
    executionRunId: str
    dataObjectVersionId: str
    datasetId: str | None = None
    dataProductId: str | None = None


class ExceptionArtifactScopeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    validationArtifactId: str
    validationArtifactVersion: int
    nativeArtifactId: str | None = None
    nativeArtifactVersion: str | None = None


class ExceptionRuleScopeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleId: str
    ruleVersionId: str


class ExceptionRecordReferenceView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    identifierType: str
    identifierValue: str
    identifierFields: list[str] = Field(default_factory=list)
    identifierHash: str | None = None


class ExceptionFailureView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    reasonCode: str
    reasonText: str
    failureClass: str | None = None
    detectedAt: str


class ExceptionFactView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    exceptionFactId: str
    exceptionFactContractVersion: str
    engineType: str
    executionScope: ExceptionExecutionScopeView
    artifactScope: ExceptionArtifactScopeView
    ruleScope: ExceptionRuleScopeView
    recordReference: ExceptionRecordReferenceView
    failure: ExceptionFailureView
    correlationId: str | None = None
    engineMetadata: dict[str, Any] = Field(default_factory=dict)
    opsMetadata: dict[str, Any] = Field(default_factory=dict)


class ExceptionFactsPageView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    data: list[ExceptionFactView] = Field(default_factory=list)
    pagination: PaginationView


class ExceptionReasonAnalyticsView(ExceptionAnalyticsView):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)


class DeliveryExceptionSummaryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    deliveryId: str
    dataObjectVersionId: str | None = None
    deliveryLocation: str | None = None
    objectStorageClassification: str = ""
    evidenceClassification: str = ""
    executionRunIds: list[str] = Field(default_factory=list)
    dataObjectVersionIds: list[str] = Field(default_factory=list)
    analytics: ExceptionReasonAnalyticsView


class ExecutionPlanExceptionSummaryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    executionPlanId: str
    currentActiveVersionId: str | None = None
    executionRunIds: list[str] = Field(default_factory=list)
    dataObjectVersionIds: list[str] = Field(default_factory=list)
    analytics: ExceptionReasonAnalyticsView


def build_offset_pagination(*, total: int, offset: int, limit: int) -> PaginationView:
    safe_limit = max(int(limit), 1)
    safe_offset = max(int(offset), 0)
    page = (safe_offset // safe_limit) + 1
    total_pages = math.ceil(total / safe_limit) if total else 0
    return PaginationView.model_validate(
        {
            "total": int(total),
            "page": page,
            "limit": safe_limit,
            "total_pages": total_pages,
            "has_next": safe_offset + safe_limit < total,
            "has_previous": page > 1,
        }
    )