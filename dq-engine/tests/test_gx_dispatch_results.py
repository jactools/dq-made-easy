"""Tests for gx_dispatch_results."""

from __future__ import annotations

from gx_dispatch_results import build_summary


class TestBuildSummary:
    def test_includes_record_counts_and_rule_results(self) -> None:
        expectations = [
            {
                "rule_id": "rule-1",
                "expectation_type": "expect_table_row_count_to_be_between",
                "kwargs": {"min_value": 10, "max_value": 20, "operator": "between"},
            },
            {
                "meta": {"dq.rule_id": "rule-2"},
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "email"},
            },
        ]
        diagnostics = [
            {"expectation_index": 1, "message": "Expectation failed"},
        ]

        summary = build_summary(
            expectations=expectations,
            passed=1,
            failed=1,
            row_count=25,
            diagnostics=diagnostics,
        )

        assert summary["expectation_count"] == 2
        assert summary["passed_expectation_count"] == 1
        assert summary["failed_expectation_count"] == 1
        assert summary["passed_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["records_checked"] == 25
        assert summary["records_failed"] is None
        assert summary["records_succeeded"] is None
        assert summary["records_filtered_out"] == 0
        assert len(summary["rule_results"]) == 2
        assert summary["rule_results"][0]["rule_id"] == "rule-1"
        assert summary["rule_results"][0]["threshold"]["relation"] == "within"
        assert summary["rule_results"][1]["rule_id"] == "rule-2"
        assert summary["rule_results"][1]["result"] == "failed"
        assert summary["rule_results"][1]["diagnostic_count"] == 1
