"""Tests for gx_dispatch_dispatch."""

from __future__ import annotations

from gx_dispatch_dispatch import _build_enriched_result_summary


class TestBuildEnrichedResultSummary:
    def test_delegates_to_shared_builder_shape(self) -> None:
        expectations = [
            {
                "rule_id": "rule-1",
                "expectation_type": "expect_table_row_count_to_be_between",
                "kwargs": {"min_value": 3, "max_value": 5, "operator": "between"},
            }
        ]
        summary = {
            "passed_expectation_count": 1,
            "failed_expectation_count": 0,
            "row_count": 4,
        }

        enriched = _build_enriched_result_summary(
            expectations=expectations,
            summary=summary,
            diagnostics=[],
        )

        assert enriched["records_checked"] == 4
        assert enriched["records_failed"] is None
        assert enriched["records_succeeded"] is None
        assert enriched["rule_results"][0]["rule_id"] == "rule-1"
        assert enriched["rule_results"][0]["threshold"]["relation"] == "within"
