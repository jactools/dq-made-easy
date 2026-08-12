"""Tests for gx_dispatch_expectations."""

from __future__ import annotations

from gx_dispatch_expectations import _build_rule_result


class TestBuildRuleResult:
    def test_reports_counts_for_a_filtered_failed_rule(self) -> None:
        result = _build_rule_result(
            expectation_index=2,
            passed=False,
            records_checked=8,
            records_failed=3,
            total_records=10,
        )

        assert result == {
            "expectation_index": 2,
            "result": "failed",
            "records_checked": 8,
            "records_failed": 3,
            "records_succeeded": 5,
            "records_filtered_out": 2,
        }

    def test_leaves_row_counts_unknown_for_non_row_rules(self) -> None:
        result = _build_rule_result(
            expectation_index=0,
            passed=False,
            records_checked=10,
            records_failed=None,
            total_records=10,
        )

        assert result["records_failed"] is None
        assert result["records_succeeded"] is None