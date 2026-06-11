from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.services.exception_retention import purge_repository_exception_facts
from app.application.services.exception_retention import purge_repository_exception_facts_for_data_object_version
from app.application.services.exception_retention import resolve_data_object_retention_policy
from app.application.services.exception_retention import resolve_exception_retention_policy
from app.domain.entities import AppConfigEntity
from app.domain.entities import DataObjectVersionEntity
from app.infrastructure.repositories.in_memory_gx_execution_violation_repository import InMemoryGxExecutionViolationRepository


@pytest.fixture
def data_object_version_with_retention_policy() -> DataObjectVersionEntity:
    return DataObjectVersionEntity(
        id="dov-1",
        data_object_id="do-1",
        version=3,
        created_at="2026-01-20T09:15:00+00:00",
        schema_hash="v3_ghi789",
        attribute_count=10,
        storage_options_json={
            "retention_policy": {
                "exception_fact_retention_days": 30,
                "exception_fact_archive_retention_days": 90,
                "exception_analytics_projection_retention_days": 365,
                "exception_fact_purge_batch_size": 1,
            }
        },
    )


def test_resolve_exception_retention_policy_uses_canonical_app_config_values() -> None:
    policy = resolve_exception_retention_policy(
        AppConfigEntity(
            exceptionFactRetentionDays=45,
            exceptionFactArchiveRetentionDays=365,
            exceptionAnalyticsProjectionRetentionDays=730,
            exceptionFactPurgeBatchSize=2500,
        )
    )

    assert policy.fact_retention_days == 45
    assert policy.archive_retention_days == 365
    assert policy.analytics_projection_retention_days == 730
    assert policy.purge_batch_size == 2500


def test_resolve_exception_retention_policy_rejects_archive_shorter_than_fact_retention() -> None:
    with pytest.raises(ValueError, match="exceptionFactArchiveRetentionDays"):
        resolve_exception_retention_policy(
            AppConfigEntity(
                exceptionFactRetentionDays=90,
                exceptionFactArchiveRetentionDays=30,
            )
        )


@pytest.mark.anyio
async def test_purge_repository_exception_facts_removes_only_expired_records() -> None:
    repo = InMemoryGxExecutionViolationRepository()
    for violation_id, detected_at in (
        ("gx-violation-old-1", "2026-03-01T00:00:00+00:00"),
        ("gx-violation-old-2", "2026-03-15T00:00:00+00:00"),
        ("gx-violation-active", "2026-05-01T00:00:00+00:00"),
    ):
        await repo.save_violation(
            data_object_version_id="dov-1",
            execution_run_id="run-1",
            rule_id="rule_1",
            data_primary_key=violation_id,
            violation_reason="value mismatch",
            ops_metadata={"reason_code": "value_mismatch", "reason_text": "value mismatch"},
            detected_at=detected_at,
            violation_id=violation_id,
        )

    deleted = await purge_repository_exception_facts(
        repo,
        policy=resolve_exception_retention_policy(
            AppConfigEntity(
                exceptionFactRetentionDays=30,
                exceptionFactArchiveRetentionDays=90,
                exceptionAnalyticsProjectionRetentionDays=365,
                exceptionFactPurgeBatchSize=1,
            )
        ),
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    remaining = await repo.list_violations("dov-1")

    assert deleted == 2
    assert remaining.total == 1
    assert remaining.data[0].id == "gx-violation-active"


def test_resolve_data_object_retention_policy_uses_version_storage_options_json(
    data_object_version_with_retention_policy: DataObjectVersionEntity,
) -> None:
    policy = resolve_data_object_retention_policy(data_object_version_with_retention_policy)

    assert policy.fact_retention_days == 30
    assert policy.archive_retention_days == 90
    assert policy.analytics_projection_retention_days == 365
    assert policy.purge_batch_size == 1


def test_resolve_data_object_retention_policy_rejects_missing_retention_policy() -> None:
    with pytest.raises(ValueError, match="retention_policy"):
        resolve_data_object_retention_policy(
            DataObjectVersionEntity(
                id="dov-missing",
                data_object_id="do-1",
                version=1,
                created_at="2026-01-20T09:15:00+00:00",
                schema_hash="missing",
                attribute_count=1,
                storage_options_json=None,
            )
        )


@pytest.mark.anyio
async def test_purge_repository_exception_facts_for_data_object_version_removes_only_expired_rows_for_scope(
    data_object_version_with_retention_policy: DataObjectVersionEntity,
) -> None:
    repo = InMemoryGxExecutionViolationRepository()
    for violation_id, detected_at, data_object_version_id in (
        ("gx-violation-old-1", "2026-03-01T00:00:00+00:00", "dov-1"),
        ("gx-violation-old-2", "2026-03-15T00:00:00+00:00", "dov-1"),
        ("gx-violation-active", "2026-05-01T00:00:00+00:00", "dov-1"),
        ("gx-violation-other-scope", "2026-03-01T00:00:00+00:00", "dov-2"),
    ):
        await repo.save_violation(
            data_object_version_id=data_object_version_id,
            execution_run_id="run-1",
            rule_id="rule_1",
            data_primary_key=violation_id,
            violation_reason="value mismatch",
            ops_metadata={"reason_code": "value_mismatch", "reason_text": "value mismatch"},
            detected_at=detected_at,
            violation_id=violation_id,
        )

    deleted = await purge_repository_exception_facts_for_data_object_version(
        repo,
        data_object_version_id="dov-1",
        policy=resolve_data_object_retention_policy(data_object_version_with_retention_policy),
        now=datetime(2026, 5, 10, tzinfo=UTC),
    )

    remaining_scoped = await repo.list_violations("dov-1")
    remaining_other = await repo.list_violations("dov-2")

    assert deleted == 2
    assert remaining_scoped.total == 1
    assert remaining_scoped.data[0].id == "gx-violation-active"
    assert remaining_other.total == 1