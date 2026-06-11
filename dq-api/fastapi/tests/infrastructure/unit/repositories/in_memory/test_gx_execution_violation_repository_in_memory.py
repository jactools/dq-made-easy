from __future__ import annotations

import pytest

from app.domain.entities import GxExecutionViolationCreateEntity
from app.infrastructure.repositories.in_memory_gx_execution_violation_repository import InMemoryGxExecutionViolationRepository


@pytest.mark.anyio
async def test_save_violation_is_scoped_to_data_object_version() -> None:
    repo = InMemoryGxExecutionViolationRepository()

    out = await repo.save_violation(
        data_object_version_id="dov-1",
        execution_run_id="run-1",
        rule_id="rule_1",
        data_primary_key="row-1",
        violation_reason="value mismatch",
        ops_metadata={
            "suite_id": "gx_suite_1",
            "suite_version": 1,
            "rule_version_id": "rule_version_1",
            "correlation_id": "corr-1",
            "failure_class": "value_mismatch",
        },
        detected_at="2026-04-06T12:00:00+00:00",
    )
    payload = out.model_dump()

    assert payload["dataObjectVersionId"] == "dov-1"
    assert payload["violationReason"] == "value mismatch"
    assert payload["dataPrimaryKey"] == "row-1"
    assert payload["opsMetadata"]["suite_id"] == "gx_suite_1"

    scoped = await repo.list_violations("dov-1")
    other = await repo.list_violations("dov-2")

    assert scoped.total == 1
    assert other.total == 0


@pytest.mark.anyio
async def test_get_violation_requires_matching_scope() -> None:
    repo = InMemoryGxExecutionViolationRepository()

    saved = await repo.save_violation(
        data_object_version_id="dov-1",
        execution_run_id="run-1",
        rule_id="rule_1",
        data_primary_key="row-1",
        violation_reason="value mismatch",
        ops_metadata={"suite_id": "gx_suite_1"},
    )

    assert await repo.get_violation("dov-1", saved.id) is not None
    assert await repo.get_violation("dov-2", saved.id) is None


@pytest.mark.anyio
async def test_list_violations_can_filter_by_rule_and_reason_code() -> None:
    repo = InMemoryGxExecutionViolationRepository()

    await repo.save_violations(
        [
            GxExecutionViolationCreateEntity(
                id="gx-violation-fixed-1",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule_1",
                dataPrimaryKey="row-1",
                violationReason="value mismatch",
                opsMetadata={
                    "reason_code": "missing_value",
                    "reason_text": "value mismatch",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-1",
                },
                detectedAt="2026-04-06T12:00:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="gx-violation-fixed-2",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule_2",
                dataPrimaryKey="row-2",
                violationReason="missing value",
                opsMetadata={
                    "reason_code": "type_mismatch",
                    "reason_text": "missing value",
                    "record_identifier_type": "primary_key",
                    "record_identifier_value": "row-2",
                },
                detectedAt="2026-04-06T12:01:00+00:00",
            ),
        ]
    )

    scoped = await repo.list_violations("dov-1", rule_id="rule_1", reason_codes=["missing_value"])
    other = await repo.list_violations("dov-1", rule_id="rule_1", reason_codes=["type_mismatch"])

    assert scoped.total == 1
    assert [row.id for row in scoped.data] == ["gx-violation-fixed-1"]
    assert other.total == 0


@pytest.mark.anyio
async def test_save_violations_batches_reproducible_records() -> None:
    repo = InMemoryGxExecutionViolationRepository()

    out = await repo.save_violations(
        [
            GxExecutionViolationCreateEntity(
                id="gx-violation-fixed-1",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule_1",
                dataPrimaryKey="row-1",
                violationReason="value mismatch",
                opsMetadata={
                    "suite_id": "gx_suite_1",
                    "suite_version": 1,
                    "rule_version_id": "rule_version_1",
                    "correlation_id": "corr-1",
                },
                detectedAt="2026-04-06T12:00:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="gx-violation-fixed-2",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule_1",
                dataPrimaryKey="row-2",
                violationReason="missing value",
                opsMetadata={
                    "suite_id": "gx_suite_1",
                    "suite_version": 1,
                    "rule_version_id": "rule_version_1",
                    "correlation_id": "corr-1",
                },
                detectedAt="2026-04-06T12:01:00+00:00",
            ),
        ]
    )
    payload = [row.model_dump() for row in out]

    assert [row["id"] for row in payload] == ["gx-violation-fixed-1", "gx-violation-fixed-2"]
    assert payload[0]["dataPrimaryKey"] == "row-1"
    scoped = await repo.list_violations("dov-1")
    assert scoped.total == 2


@pytest.mark.anyio
async def test_delete_violations_detected_before_removes_oldest_rows_first() -> None:
    repo = InMemoryGxExecutionViolationRepository()

    await repo.save_violations(
        [
            GxExecutionViolationCreateEntity(
                id="gx-violation-oldest",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule_1",
                dataPrimaryKey="row-1",
                violationReason="value mismatch",
                opsMetadata={"reason_code": "value_mismatch", "reason_text": "value mismatch"},
                detectedAt="2026-04-01T12:00:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="gx-violation-middle",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule_1",
                dataPrimaryKey="row-2",
                violationReason="missing value",
                opsMetadata={"reason_code": "missing_value", "reason_text": "missing value"},
                detectedAt="2026-04-02T12:00:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="gx-violation-active",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule_1",
                dataPrimaryKey="row-3",
                violationReason="active",
                opsMetadata={"reason_code": "active", "reason_text": "active"},
                detectedAt="2026-05-01T12:00:00+00:00",
            ),
        ]
    )

    deleted = await repo.delete_violations_detected_before(
        detected_before="2026-04-15T00:00:00+00:00",
        limit=1,
    )

    remaining = await repo.list_violations("dov-1")

    assert deleted == 1
    assert [row.id for row in remaining.data] == ["gx-violation-middle", "gx-violation-active"]


@pytest.mark.anyio
async def test_delete_violations_detected_before_can_scope_to_data_object_version() -> None:
    repo = InMemoryGxExecutionViolationRepository()

    await repo.save_violations(
        [
            GxExecutionViolationCreateEntity(
                id="gx-violation-old-scope-a",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule_1",
                dataPrimaryKey="row-1",
                violationReason="value mismatch",
                opsMetadata={"reason_code": "value_mismatch", "reason_text": "value mismatch"},
                detectedAt="2026-04-01T12:00:00+00:00",
            ),
            GxExecutionViolationCreateEntity(
                id="gx-violation-old-scope-b",
                dataObjectVersionId="dov-2",
                executionRunId="run-1",
                ruleId="rule_1",
                dataPrimaryKey="row-2",
                violationReason="value mismatch",
                opsMetadata={"reason_code": "value_mismatch", "reason_text": "value mismatch"},
                detectedAt="2026-04-01T12:00:00+00:00",
            ),
        ]
    )

    deleted = await repo.delete_violations_detected_before(
        detected_before="2026-04-15T00:00:00+00:00",
        limit=10,
        data_object_version_id="dov-1",
    )

    remaining_dov_1 = await repo.list_violations("dov-1")
    remaining_dov_2 = await repo.list_violations("dov-2")

    assert deleted == 1
    assert remaining_dov_1.total == 0
    assert remaining_dov_2.total == 1
