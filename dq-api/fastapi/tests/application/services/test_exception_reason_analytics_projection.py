from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.application.services.exception_reason_analytics_projection import (
    _format_iso_datetime,
    _parse_iso_datetime,
    _truncate_to_hour,
    build_reason_analytics_projection_rows,
    summarize_reason_analytics_projection_rows,
)
from app.domain.entities import ExceptionRecordCreateEntity


def test_datetime_helpers_normalize_values() -> None:
    assert _parse_iso_datetime(None) is None
    assert _parse_iso_datetime("   ") is None

    naive = _parse_iso_datetime("2024-05-01T10:15:20")
    aware = _parse_iso_datetime("2024-05-01T10:15:20+02:00")

    assert naive is not None
    assert naive.tzinfo == UTC
    assert naive.isoformat() == "2024-05-01T10:15:20+00:00"
    assert aware is not None
    assert aware.tzinfo == UTC
    assert aware.isoformat() == "2024-05-01T08:15:20+00:00"
    assert _format_iso_datetime(None) is None
    assert _format_iso_datetime(datetime(2024, 5, 1, 10, 15, 20)) == "2024-05-01T10:15:20+00:00"
    assert _truncate_to_hour(datetime(2024, 5, 1, 10, 15, 20)) == datetime(2024, 5, 1, 10, 0, tzinfo=UTC)
    assert _truncate_to_hour(datetime(2024, 5, 1, 10, 15, 20, tzinfo=UTC)) == datetime(2024, 5, 1, 10, 0, tzinfo=UTC)


def test_build_reason_analytics_projection_rows_groups_and_sorts_records() -> None:
    class _ModelDumpRecord:
        def model_dump(self, mode: str, by_alias: bool, exclude_none: bool) -> dict[str, object]:
            del mode, by_alias, exclude_none
            return {
                "dataObjectVersionId": "dov-1",
                "executionRunId": "run-1",
                "ruleId": "rule-1",
                "recordIdentifierType": "customer_id",
                "recordIdentifierValue": "A-1",
                "reasonCode": "DQ1_EMPTY_EXPRESSION",
                "reasonText": "Empty expression",
                "detectedAt": "2024-05-01T08:15:20Z",
                "opsMetadata": {
                    "engine_type": "gx",
                    "delivery_id": "delivery-1",
                    "execution_plan_id": "plan-1",
                    "execution_plan_version_id": "plan-version-1",
                    "suite_id": "suite-1",
                    "rule_version_id": "rule-version-1",
                },
            }

    first_record = _ModelDumpRecord()
    second_record = {
        "data_object_version_id": "dov-1",
        "execution_run_id": "run-1",
        "rule_id": "rule-1",
        "record_identifier_type": "customer_id",
        "record_identifier_value": "A-1",
        "reason_code": "DQ1_EMPTY_EXPRESSION",
        "reason_text": "Empty expression",
        "detectedAt": "2024-05-01T08:20:00Z",
        "opsMetadata": {
            "engineType": "gx",
            "deliveryId": "delivery-1",
            "executionPlanId": "plan-1",
            "executionPlanVersionId": "plan-version-1",
            "validation_artifact_id": "suite-1",
            "ruleVersionId": "rule-version-1",
        },
    }
    third_record = {
        "dataObjectVersionId": "dov-1",
        "executionRunId": "run-2",
        "ruleId": "rule-1",
        "recordIdentifierType": "customer_id",
        "recordIdentifierValue": "A-2",
        "reasonCode": "DQ1_EMPTY_EXPRESSION",
        "reasonText": "Empty expression",
        "detectedAt": "2024-05-01T08:05:00Z",
        "opsMetadata": {
            "engine_type": "gx",
            "delivery_id": "delivery-1",
            "execution_plan_id": "plan-1",
            "execution_plan_version_id": "plan-version-1",
            "suite_id": "suite-1",
            "rule_version_id": "rule-version-1",
        },
    }
    later_bucket_record = {
        "dataObjectVersionId": "dov-1",
        "executionRunId": "run-3",
        "ruleId": "rule-1",
        "recordIdentifierType": "customer_id",
        "recordIdentifierValue": "B-1",
        "reasonCode": "DQ2_OTHER_REASON",
        "reasonText": "Other reason",
        "detectedAt": "2024-05-01T09:15:00Z",
        "opsMetadata": {
            "engine_type": "gx",
            "delivery_id": "delivery-1",
            "execution_plan_id": "plan-1",
            "execution_plan_version_id": "plan-version-1",
            "suite_id": "suite-1",
            "rule_version_id": "rule-version-1",
        },
    }

    rows = build_reason_analytics_projection_rows(
        [first_record, second_record, third_record, later_bucket_record]
    )

    assert [row["reason_code"] for row in rows] == ["DQ1_EMPTY_EXPRESSION", "DQ2_OTHER_REASON"]
    assert rows[0]["bucket_start"] == "2024-05-01T08:00:00+00:00"
    assert rows[0]["failed_record_count"] == 3
    assert rows[0]["distinct_record_identifier_count"] == 2
    assert rows[0]["distinct_execution_run_count"] == 2
    assert rows[0]["record_identifier_values"] == ["A-1", "A-2"]
    assert rows[0]["execution_run_ids"] == ["run-1", "run-2"]
    assert rows[0]["detected_at"] == "2024-05-01T08:05:00+00:00"
    assert rows[1]["bucket_start"] == "2024-05-01T09:00:00+00:00"
    assert rows[1]["failed_record_count"] == 1


def test_build_reason_analytics_projection_rows_rejects_missing_payload_values() -> None:
    with pytest.raises(ValueError, match="missing detected_at"):
        build_reason_analytics_projection_rows([SimpleNamespace()])

    with pytest.raises(ValueError, match="missing canonical projection metadata"):
        build_reason_analytics_projection_rows(
            [
                {
                    "dataObjectVersionId": "dov-1",
                    "executionRunId": "run-1",
                    "ruleId": "rule-1",
                    "recordIdentifierType": "customer_id",
                    "recordIdentifierValue": "A-1",
                    "reasonCode": "DQ1_EMPTY_EXPRESSION",
                    "reasonText": "",
                    "detectedAt": "2024-05-01T08:15:20Z",
                    "opsMetadata": {"engine_type": "gx"},
                }
            ]
        )


def test_summarize_reason_analytics_projection_rows_returns_empty_summary_for_empty_scope() -> None:
    summary = summarize_reason_analytics_projection_rows(
        rows=[
            {
                "bucket_start": "2024-05-01T08:00:00+00:00",
                "engine_type": "gx",
                "delivery_id": "delivery-1",
                "execution_plan_id": "plan-1",
                "execution_plan_version_id": "plan-version-1",
                "suite_id": "suite-1",
                "data_object_version_id": "dov-1",
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "reason_code": "DQ1_EMPTY_EXPRESSION",
                "reason_text_snapshot": "Empty expression",
                "record_identifier_values": ["A-1"],
                "execution_run_ids": ["run-1"],
                "failed_record_count": 1,
                "distinct_record_identifier_count": 1,
                "distinct_execution_run_count": 1,
                "detected_at": "2024-05-01T08:15:20+00:00",
            }
        ],
        data_object_version_ids=[],
        execution_run_ids=["run-1"],
    )

    assert summary.total_failed_records == 0
    assert summary.runs_with_failures == 0
    assert summary.trend_totals == []
    assert summary.rule_totals == []
    assert summary.data_object_totals == []
    assert summary.reason_totals == []
    assert summary.reason_trend_totals == []


def test_summarize_reason_analytics_projection_rows_returns_plain_totals_without_bucket_window() -> None:
    summary = summarize_reason_analytics_projection_rows(
        rows=[
            {
                "bucket_start": "2024-05-01T08:00:00+00:00",
                "engine_type": "gx",
                "delivery_id": "delivery-1",
                "execution_plan_id": "plan-1",
                "execution_plan_version_id": "plan-version-1",
                "suite_id": "suite-1",
                "data_object_version_id": "dov-1",
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "reason_code": "DQ1_EMPTY_EXPRESSION",
                "reason_text_snapshot": "Empty expression",
                "record_identifier_values": ["A-1"],
                "execution_run_ids": ["run-1"],
                "failed_record_count": 2,
                "distinct_record_identifier_count": 1,
                "distinct_execution_run_count": 1,
                "detected_at": "2024-05-01T08:15:20+00:00",
            },
            {
                "bucket_start": "2024-05-01T09:00:00+00:00",
                "engine_type": "gx",
                "delivery_id": "delivery-1",
                "execution_plan_id": "plan-1",
                "execution_plan_version_id": "plan-version-1",
                "suite_id": "suite-1",
                "data_object_version_id": "dov-1",
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "reason_code": "DQ2_OTHER_REASON",
                "reason_text_snapshot": "Other reason",
                "record_identifier_values": ["B-1"],
                "execution_run_ids": ["run-2"],
                "failed_record_count": 3,
                "distinct_record_identifier_count": 1,
                "distinct_execution_run_count": 1,
                "detected_at": "2024-05-01T09:15:20+00:00",
            },
        ],
        data_object_version_ids=["dov-1"],
        execution_run_ids=["run-1", "run-2"],
    )

    assert summary.total_failed_records == 5
    assert summary.runs_with_failures == 2
    assert [item.bucket_start for item in summary.trend_totals] == [
        "2024-05-01T08:00:00+00:00",
        "2024-05-01T09:00:00+00:00",
    ]
    assert [item.total for item in summary.trend_totals] == [2, 3]
    assert [item.reason_code for item in summary.reason_totals] == ["DQ2_OTHER_REASON", "DQ1_EMPTY_EXPRESSION"]
    assert [item.total for item in summary.reason_trend_totals] == [2, 3]


def test_summarize_reason_analytics_projection_rows_skips_rows_outside_filters() -> None:
    base_row = {
        "bucket_start": "2024-05-01T08:00:00+00:00",
        "engine_type": "gx",
        "delivery_id": "delivery-1",
        "execution_plan_id": "plan-1",
        "execution_plan_version_id": "plan-version-1",
        "suite_id": "suite-1",
        "data_object_version_id": "dov-1",
        "rule_id": "rule-1",
        "rule_version_id": "rule-version-1",
        "reason_code": "DQ1_EMPTY_EXPRESSION",
        "reason_text_snapshot": "Empty expression",
        "record_identifier_values": ["A-1"],
        "execution_run_ids": ["run-1"],
        "failed_record_count": 1,
        "distinct_record_identifier_count": 1,
        "distinct_execution_run_count": 1,
        "detected_at": "2024-05-01T08:15:20+00:00",
    }

    after_summary = summarize_reason_analytics_projection_rows(
        rows=[base_row],
        data_object_version_ids=["dov-1"],
        execution_run_ids=["run-1"],
        detected_after="2024-05-01T09:00:00+00:00",
    )
    before_summary = summarize_reason_analytics_projection_rows(
        rows=[{**base_row, "detected_at": "2024-05-01T10:15:20+00:00"}],
        data_object_version_ids=["dov-1"],
        execution_run_ids=["run-1"],
        detected_before="2024-05-01T09:00:00+00:00",
    )
    reason_summary = summarize_reason_analytics_projection_rows(
        rows=[{**base_row, "reason_code": "DQ2_OTHER_REASON", "reason_text_snapshot": "Other reason"}],
        data_object_version_ids=["dov-1"],
        execution_run_ids=["run-1"],
        reason_codes=["DQ1_EMPTY_EXPRESSION"],
    )

    for summary in (after_summary, before_summary, reason_summary):
        assert summary.total_failed_records == 0
        assert summary.runs_with_failures == 0
        assert summary.trend_totals == []
        assert summary.rule_totals == []
        assert summary.data_object_totals == []
        assert summary.reason_totals == []
        assert summary.reason_trend_totals == []


def test_summarize_reason_analytics_projection_rows_raises_for_missing_canonical_metadata() -> None:
    with pytest.raises(RuntimeError, match="missing canonical metadata"):
        summarize_reason_analytics_projection_rows(
            rows=[
                {
                    "bucket_start": "2024-05-01T08:00:00+00:00",
                    "engine_type": "gx",
                    "delivery_id": "delivery-1",
                    "execution_plan_id": "plan-1",
                    "execution_plan_version_id": "plan-version-1",
                    "suite_id": "suite-1",
                    "data_object_version_id": "dov-1",
                    "rule_id": "",
                    "rule_version_id": "rule-version-1",
                    "reason_code": "DQ1_EMPTY_EXPRESSION",
                    "reason_text_snapshot": "Empty expression",
                    "record_identifier_values": ["A-1"],
                    "execution_run_ids": ["run-1"],
                    "failed_record_count": 1,
                    "distinct_record_identifier_count": 1,
                    "distinct_execution_run_count": 1,
                    "detected_at": "2024-05-01T08:15:20+00:00",
                }
            ],
            data_object_version_ids=["dov-1"],
            execution_run_ids=["run-1"],
        )


def test_summarize_reason_analytics_projection_rows_filters_and_clamps_bucket_windows() -> None:
    summary = summarize_reason_analytics_projection_rows(
        rows=[
            {
                "bucket_start": "2024-05-01T12:00:00+00:00",
                "engine_type": "gx",
                "delivery_id": "delivery-1",
                "execution_plan_id": "plan-1",
                "execution_plan_version_id": "plan-version-1",
                "suite_id": "suite-1",
                "data_object_version_id": "dov-1",
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "reason_code": "DQ1_EMPTY_EXPRESSION",
                "reason_text_snapshot": "Empty expression",
                "record_identifier_values": ["A-1"],
                "execution_run_ids": ["run-1"],
                "failed_record_count": 2,
                "distinct_record_identifier_count": 1,
                "distinct_execution_run_count": 1,
                "detected_at": "2024-05-01T12:15:00+00:00",
            },
            {
                "bucket_start": "2024-05-01T12:00:00+00:00",
                "engine_type": "gx",
                "delivery_id": "delivery-1",
                "execution_plan_id": "plan-1",
                "execution_plan_version_id": "plan-version-1",
                "suite_id": "suite-1",
                "data_object_version_id": "dov-1",
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "reason_code": "DQ1_EMPTY_EXPRESSION",
                "reason_text_snapshot": "Empty expression",
                "record_identifier_values": ["A-2"],
                "execution_run_ids": ["run-2"],
                "failed_record_count": 1,
                "distinct_record_identifier_count": 1,
                "distinct_execution_run_count": 1,
                "detected_at": None,
            },
            {
                "bucket_start": "2024-05-01T11:00:00+00:00",
                "engine_type": "gx",
                "delivery_id": "delivery-1",
                "execution_plan_id": "plan-1",
                "execution_plan_version_id": "plan-version-1",
                "suite_id": "suite-1",
                "data_object_version_id": "dov-1",
                "rule_id": "rule-1",
                "rule_version_id": "rule-version-1",
                "reason_code": "DQ2_OTHER_REASON",
                "reason_text_snapshot": "Other reason",
                "record_identifier_values": ["B-1"],
                "execution_run_ids": ["run-3"],
                "failed_record_count": 4,
                "distinct_record_identifier_count": 1,
                "distinct_execution_run_count": 1,
                "detected_at": "2024-05-01T11:15:00+00:00",
            },
        ],
        data_object_version_ids=["dov-1"],
        execution_run_ids=["run-1", "run-2"],
        reason_codes=["DQ1_EMPTY_EXPRESSION"],
        bucket_origin="2024-05-01T10:00:00+00:00",
        bucket_size_seconds=3600,
        bucket_count=2,
    )

    assert summary.total_failed_records == 3
    assert summary.runs_with_failures == 2
    assert [item.bucket_start for item in summary.trend_totals] == ["2024-05-01T11:00:00+00:00"]
    assert [item.total for item in summary.trend_totals] == [2]
    assert [item.rule_id for item in summary.rule_totals] == ["rule-1"]
    assert [item.total for item in summary.data_object_totals] == [3]
    assert [item.reason_code for item in summary.reason_totals] == ["DQ1_EMPTY_EXPRESSION"]
    assert [item.total for item in summary.reason_totals] == [3]
    assert [item.total for item in summary.reason_trend_totals] == [2]
