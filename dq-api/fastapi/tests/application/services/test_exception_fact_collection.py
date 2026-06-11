from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.services.exception_fact_collection import collect_exception_facts
from app.application.services.exception_fact_collection import extract_exception_fact_target_ids
from app.application.services.exception_fact_collection import emit_exception_fact_batch
from app.application.services.exception_fact_collection import normalize_reason
from app.application.services.exception_fact_collection import resolve_record_identifier
from app.application.services.exception_fact_validation import exception_fact_validation_service
from app.domain.entities import ExceptionRecordCreateEntity
from app.domain.entities.gx_execution_run import build_gx_execution_run_entity
from app.infrastructure.repositories.in_memory_exception_reason_analytics_projection_repository import InMemoryExceptionReasonAnalyticsProjectionRepository


@pytest.fixture
def gx_execution_context():
    return build_gx_execution_run_entity(
        {
            "id": "run-1",
            "suite_id": "gx-suite-1",
            "suite_version": 4,
            "rule_id": "rule-1",
            "rule_version_id": "rule-version-1",
            "correlation_id": "corr-1",
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "status": "failed",
            "submitted_at": "2026-05-08T10:00:00+00:00",
            "started_at": "2026-05-08T10:01:00+00:00",
            "completed_at": "2026-05-08T10:02:00+00:00",
            "created_at": "2026-05-08T10:00:00+00:00",
            "updated_at": "2026-05-08T10:02:00+00:00",
            "execution_contract": {
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "resolved_data_delivery_id": "delivery-1",
                "resolved_delivery_location": "s3://deliveries/delivery-1",
                "delivery_resolution_mode": "specific_delivery",
                "execution_plan_id": "plan-1",
                "execution_plan_version_id": "plan-version-3",
                "traceability": {
                    "rule_id": "rule-1",
                    "rule_version_id": "rule-version-1",
                    "gx_suite_id": "gx-suite-1",
                    "gx_suite_version": 4,
                    "data_object_version_id": "dov-1",
                    "artifact_key": "artifact-1",
                },
            },
        }
    )


@pytest.fixture
def gx_run_result():
    return SimpleNamespace(
        newStatus="failed",
        startedAt="2026-05-08T10:01:00+00:00",
        completedAt="2026-05-08T10:02:00+00:00",
        failureCode="GX_VALIDATION_FAILED",
        failureMessage="One or more expectations failed",
        resultSummary={"results": [{"dataObjectVersionId": "dov-1", "ok": False, "violationCount": 1}]},
        diagnostics=[
            {
                "dataObjectVersionId": "dov-1",
                "dataPrimaryKey": "order-1",
                "reason": "expectation_failed",
                "expectationType": "expect_column_values_to_not_be_null",
                "message": "order_id must not be null",
                "detectedAt": "2026-05-08T10:01:30+00:00",
            }
        ],
    )


def test_collect_exception_facts_builds_canonical_gx_batch(
    gx_run_result: SimpleNamespace,
    gx_execution_context,
) -> None:
    facts = collect_exception_facts(run_result=gx_run_result, execution_context=gx_execution_context)

    assert len(facts) == 1
    fact = facts[0]
    assert isinstance(fact, ExceptionRecordCreateEntity)
    assert fact.dataObjectVersionId == "dov-1"
    assert fact.executionRunId == "run-1"
    assert fact.ruleId == "rule-1"
    assert fact.recordIdentifierType == "primary_key"
    assert fact.recordIdentifierValue == "order-1"
    assert fact.reasonCode == "completeness_not_null_violation"
    assert fact.reasonText == "order_id must not be null"
    assert fact.detectedAt == "2026-05-08T10:01:30+00:00"
    assert fact.opsMetadata["validation_artifact_id"] == "gx-suite-1"
    assert fact.opsMetadata["validation_artifact_version"] == 4
    assert fact.opsMetadata["rule_version_id"] == "rule-version-1"
    assert fact.opsMetadata["engine_type"] == "gx"
    assert fact.opsMetadata["delivery_id"] == "delivery-1"
    assert fact.opsMetadata["execution_plan_id"] == "plan-1"
    assert fact.opsMetadata["execution_plan_version_id"] == "plan-version-3"


def test_collect_exception_facts_preserves_high_cardinality_row_diagnostics(gx_execution_context) -> None:
    diagnostics = [
        {
            "dataObjectVersionId": "dov-1",
            "dataPrimaryKey": f"customer_id=cust-invalid-{index:03d}",
            "reason": "expectation_failed",
            "expectationType": "expect_column_values_to_match_regex",
            "message": "Expectation failed",
            "detectedAt": "2026-05-08T10:01:30+00:00",
        }
        for index in range(1, 206)
    ]
    gx_run_result = SimpleNamespace(
        newStatus="failed",
        startedAt="2026-05-08T10:01:00+00:00",
        completedAt="2026-05-08T10:02:00+00:00",
        failureCode="GX_VALIDATION_FAILED",
        failureMessage="One or more expectations failed",
        resultSummary={"results": [{"dataObjectVersionId": "dov-1", "ok": False, "violationCount": len(diagnostics)}]},
        diagnostics=diagnostics,
    )

    facts = collect_exception_facts(run_result=gx_run_result, execution_context=gx_execution_context)

    assert len(facts) == 205
    assert all(fact.dataObjectVersionId == "dov-1" for fact in facts)
    assert all(fact.recordIdentifierType == "primary_key" for fact in facts)
    assert facts[0].recordIdentifierValue == "customer_id=cust-invalid-001"
    assert facts[-1].recordIdentifierValue == "customer_id=cust-invalid-205"


def test_normalize_reason_returns_canonical_reason_shape() -> None:
    normalized = normalize_reason(
        SimpleNamespace(
            expectationType="expect_column_values_to_not_be_null",
            reason="expectation_failed",
            message="order_id must not be null",
        ),
        run_result=SimpleNamespace(
            failureCode="GX_VALIDATION_FAILED",
            failureMessage="One or more expectations failed",
        ),
    )

    assert normalized == {
        "reason_code": "completeness_not_null_violation",
        "reason_text": "order_id must not be null",
        "failure_class": "expectation_failed",
    }


def test_resolve_record_identifier_returns_canonical_identifier_shape() -> None:
    execution_context = build_gx_execution_run_entity(
        {
            "id": "run-3",
            "suite_id": "gx-suite-3",
            "suite_version": 1,
            "rule_id": "rule-3",
            "rule_version_id": "rule-version-3",
            "correlation_id": "corr-3",
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "status": "failed",
            "submitted_at": "2026-05-08T12:00:00+00:00",
            "created_at": "2026-05-08T12:00:00+00:00",
            "updated_at": "2026-05-08T12:00:00+00:00",
        }
    )

    assert resolve_record_identifier(
        SimpleNamespace(dataPrimaryKey="order-1"),
        execution_context,
    ) == {
        "record_identifier_type": "primary_key",
        "record_identifier_value": "order-1",
    }

    assert resolve_record_identifier(
        SimpleNamespace(rowIdentifier="sales_order_number=SO-2"),
        execution_context,
    ) == {
        "record_identifier_type": "business_key",
        "record_identifier_value": "sales_order_number=SO-2",
    }

    assert resolve_record_identifier(SimpleNamespace(), execution_context) == {
        "record_identifier_type": None,
        "record_identifier_value": None,
    }


def test_extract_exception_fact_target_ids_prefers_diagnostics_then_results_then_contract() -> None:
    execution_context = build_gx_execution_run_entity(
        {
            "id": "run-2",
            "suite_id": "gx-suite-2",
            "suite_version": 1,
            "rule_id": "rule-2",
            "rule_version_id": "rule-version-2",
            "correlation_id": "corr-2",
            "engine_type": "gx",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "status": "failed",
            "submitted_at": "2026-05-08T11:00:00+00:00",
            "created_at": "2026-05-08T11:00:00+00:00",
            "updated_at": "2026-05-08T11:00:00+00:00",
            "execution_contract": {
                "engine_type": "gx",
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "traceability": {"data_object_version_id": "dov-contract"},
            },
        }
    )

    diagnostics_result = SimpleNamespace(
        diagnostics=[
            {"dataObjectVersionId": "dov-diagnostic", "rowIdentifier": "pk-1"},
            {"dataObjectVersionId": "dov-diagnostic", "rowIdentifier": "pk-2"},
        ],
        resultSummary={"results": [{"dataObjectVersionId": "dov-result", "ok": False, "violationCount": 1}]},
    )
    assert extract_exception_fact_target_ids(
        run_result=diagnostics_result,
        execution_context=execution_context,
    ) == ["dov-diagnostic"]

    result_summary_only = SimpleNamespace(
        diagnostics=[{"rowIdentifier": "pk-3"}],
        resultSummary={"results": [{"dataObjectVersionId": "dov-result", "ok": False, "violationCount": 1}]},
    )
    assert extract_exception_fact_target_ids(
        run_result=result_summary_only,
        execution_context=execution_context,
    ) == ["dov-result"]


def test_exception_fact_validation_service_rejects_unsupported_engine_for_collection() -> None:
    execution_context = build_gx_execution_run_entity(
        {
            "id": "run-soda",
            "suite_id": "gx-suite-soda",
            "suite_version": 1,
            "rule_id": "rule-soda",
            "rule_version_id": "rule-version-soda",
            "correlation_id": "corr-soda",
            "engine_type": "soda",
            "engine_target": "pyspark",
            "execution_shape": "single_object",
            "status": "failed",
            "submitted_at": "2026-05-08T13:00:00+00:00",
            "created_at": "2026-05-08T13:00:00+00:00",
            "updated_at": "2026-05-08T13:00:00+00:00",
        }
    )

    with pytest.raises(HTTPException) as error:
        exception_fact_validation_service.require_exception_fact_collection_support(execution_context=execution_context)

    assert error.value.status_code == 503
    assert error.value.detail.get("capability_error") == "row_level_exception_facts_unsupported"


def test_exception_fact_validation_service_rejects_short_persistence_result() -> None:
    with pytest.raises(HTTPException) as error:
        exception_fact_validation_service.validate_exception_fact_persistence_result(
            expected_count=2,
            persisted_count=1,
            run_id="run-1",
        )

    assert error.value.status_code == 503
    assert error.value.detail.get("persisted_count") == 1
    assert error.value.detail.get("expected_count") == 2


@pytest.mark.anyio
async def test_emit_exception_fact_batch_chunks_and_persists_all_batches() -> None:
    persisted_batches: list[list[dict[str, object]]] = []

    class _FakeExceptionStorageService:
        async def persist_violations(self, violations):
            persisted_batches.append(list(violations))
            return len(violations)

    def _builder(**kwargs):
        assert kwargs["settings"] == {"source": "test"}
        assert kwargs["violation_repository"] == object_repository
        return _FakeExceptionStorageService()

    object_repository = object()
    violation_batch = [
        ExceptionRecordCreateEntity(
            id=f"exception-record-{index}",
            dataObjectVersionId="dov-1",
            executionRunId="run-1",
            ruleId="rule-1",
            recordIdentifierType="primary_key",
            recordIdentifierValue=f"row-{index}",
            reasonCode="completeness_not_null_violation",
            reasonText="order_id must not be null",
            detectedAt="2026-05-08T10:01:30+00:00",
            opsMetadata={
                "suite_id": "gx-suite-1",
                "suite_version": 4,
                "validation_artifact_id": "gx-suite-1",
                "validation_artifact_version": 4,
                "rule_version_id": "rule-version-1",
                "correlation_id": "corr-1",
                "engine_type": "gx",
            },
        )
        for index in range(1001)
    ]

    created = await emit_exception_fact_batch(
        violation_batch=violation_batch,
        settings_provider=lambda: {"source": "test"},
        violation_repository=object_repository,
        exception_storage_builder=_builder,
    )

    assert created == 1001
    assert len(persisted_batches) == 2
    assert len(persisted_batches[0]) == 1000
    assert len(persisted_batches[1]) == 1


@pytest.mark.anyio
async def test_emit_exception_fact_batch_persists_projection_rows_after_raw_write() -> None:
    class _FakeExceptionStorageService:
        async def persist_violations(self, violations):
            return len(list(violations))

    projection_repository = InMemoryExceptionReasonAnalyticsProjectionRepository()

    created = await emit_exception_fact_batch(
        violation_batch=[
            ExceptionRecordCreateEntity(
                id="exception-record-1",
                dataObjectVersionId="dov-1",
                executionRunId="run-1",
                ruleId="rule-1",
                recordIdentifierType="primary_key",
                recordIdentifierValue="order-1",
                reasonCode="completeness_not_null_violation",
                reasonText="order_id must not be null",
                failureClass="expectation_failed",
                detectedAt="2026-05-08T10:01:30+00:00",
                opsMetadata={
                    "suite_id": "gx-suite-1",
                    "suite_version": 4,
                    "validation_artifact_id": "gx-suite-1",
                    "validation_artifact_version": 4,
                    "rule_version_id": "rule-version-1",
                    "correlation_id": "corr-1",
                    "engine_type": "gx",
                    "engine_target": "pyspark",
                    "execution_shape": "single_object",
                    "delivery_id": "delivery-1",
                    "execution_plan_id": "plan-1",
                    "execution_plan_version_id": "plan-version-3",
                },
            )
        ],
        settings_provider=lambda: {"source": "test"},
        violation_repository=object(),
        exception_storage_builder=lambda **kwargs: _FakeExceptionStorageService(),
        projection_repository=projection_repository,
    )

    summary = await projection_repository.summarize_reason_analytics(
        data_object_version_ids=["dov-1"],
        execution_run_ids=["run-1"],
    )

    assert created == 1
    assert summary.total_failed_records == 1
    assert summary.runs_with_failures == 1
    assert [item.reason_code for item in summary.reason_totals] == ["completeness_not_null_violation"]


@pytest.mark.anyio
async def test_emit_exception_fact_batch_rejects_short_write() -> None:
    class _FakeExceptionStorageService:
        async def persist_violations(self, violations):
            return max(len(list(violations)) - 1, 0)

    def _builder(**kwargs):
        return _FakeExceptionStorageService()

    with pytest.raises(HTTPException) as error:
        await emit_exception_fact_batch(
            violation_batch=[
                ExceptionRecordCreateEntity(
                    id="exception-record-1",
                    dataObjectVersionId="dov-1",
                    executionRunId="run-1",
                    ruleId="rule-1",
                    recordIdentifierType="primary_key",
                    recordIdentifierValue="row-1",
                    reasonCode="completeness_not_null_violation",
                    reasonText="order_id must not be null",
                    detectedAt="2026-05-08T10:01:30+00:00",
                    opsMetadata={
                        "suite_id": "gx-suite-1",
                        "suite_version": 4,
                        "validation_artifact_id": "gx-suite-1",
                        "validation_artifact_version": 4,
                        "rule_version_id": "rule-version-1",
                        "correlation_id": "corr-1",
                        "engine_type": "gx",
                    },
                ),
                ExceptionRecordCreateEntity(
                    id="exception-record-2",
                    dataObjectVersionId="dov-1",
                    executionRunId="run-1",
                    ruleId="rule-1",
                    recordIdentifierType="primary_key",
                    recordIdentifierValue="row-2",
                    reasonCode="completeness_not_null_violation",
                    reasonText="order_id must not be null",
                    detectedAt="2026-05-08T10:01:31+00:00",
                    opsMetadata={
                        "suite_id": "gx-suite-1",
                        "suite_version": 4,
                        "validation_artifact_id": "gx-suite-1",
                        "validation_artifact_version": 4,
                        "rule_version_id": "rule-version-1",
                        "correlation_id": "corr-1",
                        "engine_type": "gx",
                    },
                ),
            ],
            settings_provider=lambda: {"source": "test"},
            violation_repository=object(),
            exception_storage_builder=_builder,
        )

    assert error.value.status_code == 503
    assert error.value.detail.get("persisted_count") == 1
