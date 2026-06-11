from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.entities import AppConfigEntity
from app.domain.entities import DataObjectVersionEntity
from app.domain.interfaces import ExceptionFactRepository


@dataclass(frozen=True)
class ExceptionRetentionPolicy:
    fact_retention_days: int
    archive_retention_days: int
    analytics_projection_retention_days: int
    purge_batch_size: int

    def fact_cutoff(self, *, now: datetime) -> datetime:
        return _normalize_utc(now) - timedelta(days=self.fact_retention_days)

    def archive_cutoff(self, *, now: datetime) -> datetime:
        return _normalize_utc(now) - timedelta(days=self.archive_retention_days)


def resolve_exception_retention_policy(app_config: AppConfigEntity) -> ExceptionRetentionPolicy:
    return _build_exception_retention_policy(
        fact_retention_days=int(app_config.exceptionFactRetentionDays),
        archive_retention_days=int(app_config.exceptionFactArchiveRetentionDays),
        analytics_projection_retention_days=int(app_config.exceptionAnalyticsProjectionRetentionDays),
        purge_batch_size=int(app_config.exceptionFactPurgeBatchSize),
    )


def resolve_data_object_retention_policy(data_object_version: DataObjectVersionEntity) -> ExceptionRetentionPolicy:
    storage_options_json = data_object_version.storage_options_json
    if not isinstance(storage_options_json, dict):
        raise ValueError(
            f"data_object_versions.storage_options_json.retention_policy is required for data object version '{data_object_version.id}'"
        )

    retention_policy = storage_options_json.get("retention_policy")
    if not isinstance(retention_policy, dict):
        raise ValueError(
            f"data_object_versions.storage_options_json.retention_policy is required for data object version '{data_object_version.id}'"
        )

    return _build_exception_retention_policy(
        fact_retention_days=_require_positive_int(
            retention_policy,
            key="exception_fact_retention_days",
            data_object_version_id=data_object_version.id,
        ),
        archive_retention_days=_require_positive_int(
            retention_policy,
            key="exception_fact_archive_retention_days",
            data_object_version_id=data_object_version.id,
        ),
        analytics_projection_retention_days=_require_positive_int(
            retention_policy,
            key="exception_analytics_projection_retention_days",
            data_object_version_id=data_object_version.id,
        ),
        purge_batch_size=_require_positive_int(
            retention_policy,
            key="exception_fact_purge_batch_size",
            data_object_version_id=data_object_version.id,
        ),
    )


def _build_exception_retention_policy(
    *,
    fact_retention_days: int,
    archive_retention_days: int,
    analytics_projection_retention_days: int,
    purge_batch_size: int,
) -> ExceptionRetentionPolicy:
    policy = ExceptionRetentionPolicy(
        fact_retention_days=fact_retention_days,
        archive_retention_days=archive_retention_days,
        analytics_projection_retention_days=analytics_projection_retention_days,
        purge_batch_size=purge_batch_size,
    )

    if policy.fact_retention_days < 1:
        raise ValueError("exceptionFactRetentionDays must be at least 1")
    if policy.archive_retention_days < policy.fact_retention_days:
        raise ValueError(
            "exceptionFactArchiveRetentionDays must be greater than or equal to exceptionFactRetentionDays"
        )
    if policy.analytics_projection_retention_days < 1:
        raise ValueError("exceptionAnalyticsProjectionRetentionDays must be at least 1")
    if policy.purge_batch_size < 1:
        raise ValueError("exceptionFactPurgeBatchSize must be at least 1")
    return policy


def _require_positive_int(payload: dict[str, Any], *, key: str, data_object_version_id: str) -> int:
    if key not in payload:
        raise ValueError(
            f"data_object_versions.storage_options_json.retention_policy.{key} is required for data object version '{data_object_version_id}'"
        )

    value = payload[key]
    if isinstance(value, bool):
        raise ValueError(
            f"data_object_versions.storage_options_json.retention_policy.{key} must be a positive integer for data object version '{data_object_version_id}'"
        )

    try:
        normalized = int(value)
    except Exception as exc:
        raise ValueError(
            f"data_object_versions.storage_options_json.retention_policy.{key} must be a positive integer for data object version '{data_object_version_id}'"
        ) from exc

    if normalized < 1:
        raise ValueError(
            f"data_object_versions.storage_options_json.retention_policy.{key} must be at least 1 for data object version '{data_object_version_id}'"
        )
    return normalized


async def purge_repository_exception_facts(
    violation_repository: ExceptionFactRepository,
    *,
    policy: ExceptionRetentionPolicy,
    now: datetime | None = None,
) -> int:
    return await _purge_repository_exception_facts(
        violation_repository,
        policy=policy,
        now=now,
        data_object_version_id=None,
    )


async def purge_repository_exception_facts_for_data_object_version(
    violation_repository: ExceptionFactRepository,
    *,
    data_object_version_id: str,
    policy: ExceptionRetentionPolicy,
    now: datetime | None = None,
) -> int:
    normalized_data_object_version_id = str(data_object_version_id or "").strip()
    if not normalized_data_object_version_id:
        raise ValueError("data_object_version_id is required")

    return await _purge_repository_exception_facts(
        violation_repository,
        policy=policy,
        now=now,
        data_object_version_id=normalized_data_object_version_id,
    )


async def _purge_repository_exception_facts(
    violation_repository: ExceptionFactRepository,
    *,
    policy: ExceptionRetentionPolicy,
    now: datetime | None,
    data_object_version_id: str | None,
) -> int:
    effective_now = _normalize_utc(now or datetime.now(UTC))
    cutoff = policy.fact_cutoff(now=effective_now).isoformat()

    total_deleted = 0
    while True:
        deleted = await violation_repository.delete_violations_detected_before(
            detected_before=cutoff,
            limit=policy.purge_batch_size,
            data_object_version_id=data_object_version_id,
        )
        total_deleted += deleted
        if deleted < policy.purge_batch_size:
            return total_deleted


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)