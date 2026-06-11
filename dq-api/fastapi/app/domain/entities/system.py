from __future__ import annotations

from app.domain.entities.base import EntityModel


class SystemDatabaseInfoEntity(EntityModel):
    db_schema_version: str = "unknown"
    db_schema_updated: str | None = None
    db_git_commit: str | None = None


class SuggestionsMetricsOperationEntity(EntityModel):
    operation: str
    count: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 1
    avg_duration_ms: int = 0
    min_duration_ms: int = 0
    max_duration_ms: int = 0
    last_seen_at: int = 0


class SuggestionsMetricsSummaryEntity(EntityModel):
    total: int = 0
    successful: int = 0
    failed: int = 0
    success_rate: float = 1
    operations: list[SuggestionsMetricsOperationEntity] = []