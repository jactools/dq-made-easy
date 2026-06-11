from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class DqResultDriftScopeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ruleId: str | None = None
    datasetId: str | None = None
    domainId: str | None = None
    dataProductId: str | None = None


class DqResultDriftDetectionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    detectorType: str
    severity: str
    scope: DqResultDriftScopeView
    observedAt: str
    baselineValue: float | int | None = None
    currentValue: float | int | None = None
    delta: float | int | None = None
    threshold: float | int | None = None
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class DqResultDriftSummaryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    lookbackAmount: int
    lookbackUnit: str
    totalEvents: int
    scopedGroups: int
    totalDetections: int
    detectionsByType: dict[str, int] = Field(default_factory=dict)
    detectionsBySeverity: dict[str, int] = Field(default_factory=dict)
    latestObservedAt: str | None = None
    drifts: list[DqResultDriftDetectionView] = Field(default_factory=list)
