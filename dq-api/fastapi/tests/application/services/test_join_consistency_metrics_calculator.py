"""
Unit tests for JOIN_CONSISTENCY metrics calculation and diagnostics.
"""

import pytest

from app.application.services.join_consistency_metrics_calculator import (
    JoinConsistencyMetricsCalculator,
)
from app.domain.entities.execution_metrics import (
    FailureClassEnum,
    FailureDiagnostic,
)


class TestMetricsCalculator:
    """Test metric calculation from raw counts."""

    def test_calculate_metrics_all_match(self):
        """Test metrics when all rows match."""
        metrics = JoinConsistencyMetricsCalculator.calculate_metrics(
            joined_rows_count=100,
            matched_rows_count=100,
            mismatched_rows_count=0,
        )
        assert metrics.matchCount == 100
        assert metrics.mismatchCount == 0
        assert metrics.eligibleJoinedRows == 100
        assert metrics.matchRate == 100.0
        assert metrics.actualityDateMismatchCount == 0
        assert metrics.nullOrMissingJoinKeyCount == 0

    def test_calculate_metrics_partial_match(self):
        """Test metrics with partial match rate."""
        metrics = JoinConsistencyMetricsCalculator.calculate_metrics(
            joined_rows_count=100,
            matched_rows_count=80,
            mismatched_rows_count=20,
        )
        assert metrics.matchCount == 80
        assert metrics.mismatchCount == 20
        assert metrics.eligibleJoinedRows == 100
        assert metrics.matchRate == 80.0

    def test_calculate_metrics_no_matches(self):
        """Test metrics when no rows match."""
        metrics = JoinConsistencyMetricsCalculator.calculate_metrics(
            joined_rows_count=100,
            matched_rows_count=0,
            mismatched_rows_count=100,
        )
        assert metrics.matchCount == 0
        assert metrics.mismatchCount == 100
        assert metrics.matchRate == 0.0

    def test_calculate_metrics_with_null_join_keys(self):
        """Test metrics excludes null join key rows from eligible count."""
        metrics = JoinConsistencyMetricsCalculator.calculate_metrics(
            joined_rows_count=110,  # Total including null keys
            matched_rows_count=80,
            mismatched_rows_count=20,
            null_or_missing_join_keys_count=10,
        )
        assert metrics.eligibleJoinedRows == 100
        assert metrics.matchRate == 80.0
        assert metrics.nullOrMissingJoinKeyCount == 10

    def test_calculate_metrics_empty_set(self):
        """Test metrics with no eligible rows."""
        metrics = JoinConsistencyMetricsCalculator.calculate_metrics(
            joined_rows_count=10,
            matched_rows_count=0,
            mismatched_rows_count=0,
            null_or_missing_join_keys_count=10,
        )
        assert metrics.eligibleJoinedRows == 0
        assert metrics.matchRate == 0.0

    def test_calculate_metrics_actuality_date_subset(self):
        """Test actuality-date mismatch is subset of total mismatches."""
        metrics = JoinConsistencyMetricsCalculator.calculate_metrics(
            joined_rows_count=100,
            matched_rows_count=80,
            mismatched_rows_count=20,
            actuality_date_mismatch_count=5,
        )
        assert metrics.actualityDateMismatchCount == 5
        assert metrics.mismatchCount == 20


class TestFailureClassification:
    """Test failure classification logic."""

    def test_classify_join_key_missing_priority(self):
        """Join key missing is highest priority."""
        diag = JoinConsistencyMetricsCalculator.classify_failure(
            value_mismatch=True,
            actuality_date_drift=True,
            join_key_missing=True,
        )
        assert diag.failureClass == FailureClassEnum.NULL_OR_MISSING_JOIN_KEY

    def test_classify_actuality_date_drift_priority(self):
        """Actuality-date drift has priority over value mismatch."""
        diag = JoinConsistencyMetricsCalculator.classify_failure(
            value_mismatch=True,
            actuality_date_drift=True,
            join_key_missing=False,
        )
        assert diag.failureClass == FailureClassEnum.ACTUALITY_DATE_DRIFT

    def test_classify_value_mismatch(self):
        """Value mismatch when no date drift."""
        diag = JoinConsistencyMetricsCalculator.classify_failure(
            value_mismatch=True,
            actuality_date_drift=False,
            join_key_missing=False,
        )
        assert diag.failureClass == FailureClassEnum.VALUE_MISMATCH

    def test_classify_with_row_identifier(self):
        """Failure can include row identifier."""
        diag = JoinConsistencyMetricsCalculator.classify_failure(
            value_mismatch=True,
            actuality_date_drift=False,
            row_identifier="id=12345",
        )
        assert diag.rowIdentifier == "id=12345"
        assert diag.failureClass == FailureClassEnum.VALUE_MISMATCH

    def test_classify_with_affected_attributes(self):
        """Failure can track affected attributes."""
        diag = JoinConsistencyMetricsCalculator.classify_failure(
            value_mismatch=True,
            actuality_date_drift=False,
            affected_attributes=["account_balance", "account_type"],
        )
        assert "account_balance" in diag.affectedAttributes
        assert "account_type" in diag.affectedAttributes

    def test_classify_other_when_no_known_failure_flags_present(self):
        """Unknown failure state falls back to OTHER classification."""
        diag = JoinConsistencyMetricsCalculator.classify_failure(
            value_mismatch=False,
            actuality_date_drift=False,
            join_key_missing=False,
        )
        assert diag.failureClass == FailureClassEnum.OTHER
        assert diag.details == "Unknown failure reason"


class TestDiagnosticsSummary:
    """Test diagnostics aggregation and summary building."""

    def test_build_summary_empty(self):
        """Empty diagnostics produces empty summary."""
        summary = JoinConsistencyMetricsCalculator.build_diagnostics_summary([])
        assert len(summary) == 0

    def test_build_summary_single_class(self):
        """Multiple failures of same class group together."""
        diags = [
            FailureDiagnostic(
                failureClass=FailureClassEnum.VALUE_MISMATCH,
                details="Account balance mismatch",
            ),
            FailureDiagnostic(
                failureClass=FailureClassEnum.VALUE_MISMATCH,
                details="Account type mismatch",
            ),
            FailureDiagnostic(
                failureClass=FailureClassEnum.VALUE_MISMATCH,
                details="Account status mismatch",
            ),
        ]
        summary = JoinConsistencyMetricsCalculator.build_diagnostics_summary(diags)
        assert len(summary) == 1
        assert summary[0].failureClass == FailureClassEnum.VALUE_MISMATCH
        assert summary[0].count == 3
        assert len(summary[0].sampleFailures) == 3

    def test_build_summary_multiple_classes(self):
        """Failures grouped by class and sorted."""
        diags = [
            FailureDiagnostic(
                failureClass=FailureClassEnum.VALUE_MISMATCH,
                details="Mismatch 1",
            ),
            FailureDiagnostic(
                failureClass=FailureClassEnum.ACTUALITY_DATE_DRIFT,
                details="Date drift 1",
            ),
            FailureDiagnostic(
                failureClass=FailureClassEnum.NULL_OR_MISSING_JOIN_KEY,
                details="Null key 1",
            ),
        ]
        summary = JoinConsistencyMetricsCalculator.build_diagnostics_summary(diags)
        assert len(summary) == 3
        # Verify sorted by failure class name
        assert (
            summary[0].failureClass == FailureClassEnum.ACTUALITY_DATE_DRIFT
        )  # Alphabetically first
        assert summary[1].failureClass == FailureClassEnum.NULL_OR_MISSING_JOIN_KEY
        assert summary[2].failureClass == FailureClassEnum.VALUE_MISMATCH

    def test_build_summary_sample_limiting(self):
        """Sample size is limited per class."""
        diags = [
            FailureDiagnostic(
                failureClass=FailureClassEnum.VALUE_MISMATCH,
                details=f"Mismatch {i}",
            )
            for i in range(20)
        ]
        summary = JoinConsistencyMetricsCalculator.build_diagnostics_summary(
            diags, max_sample_size=3
        )
        assert len(summary) == 1
        assert summary[0].count == 20
        assert len(summary[0].sampleFailures) == 3  # Limited to 3 samples


class TestExecutionResult:
    """Test complete execution result building."""

    def test_build_result_passed(self):
        """Build result for passing execution."""
        from app.domain.entities.execution_metrics import (
            JoinConsistencyExecutionMetrics,
        )

        metrics = JoinConsistencyExecutionMetrics(
            matchCount=100, mismatchCount=0, eligibleJoinedRows=100, matchRate=100.0
        )
        result = JoinConsistencyMetricsCalculator.build_result(
            passed=True,
            metrics=metrics,
            execution_duration_ms=250,
        )
        assert result.passed is True
        assert result.metrics.matchRate == 100.0
        assert result.executionDurationMs == 250
        assert len(result.diagnosticsSummary) == 0

    def test_build_result_failed_with_diagnostics(self):
        """Build result for failing execution with diagnostics."""
        from app.domain.entities.execution_metrics import (
            JoinConsistencyExecutionMetrics,
        )

        metrics = JoinConsistencyExecutionMetrics(
            matchCount=70, mismatchCount=30, eligibleJoinedRows=100, matchRate=70.0
        )
        diags = [
            FailureDiagnostic(
                failureClass=FailureClassEnum.VALUE_MISMATCH,
                details="Balance mismatch",
            ),
            FailureDiagnostic(
                failureClass=FailureClassEnum.VALUE_MISMATCH,
                details="Status mismatch",
            ),
        ]
        result = JoinConsistencyMetricsCalculator.build_result(
            passed=False,
            metrics=metrics,
            all_diagnostics=diags,
            execution_duration_ms=500,
        )
        assert result.passed is False
        assert result.metrics.matchRate == 70.0
        assert len(result.diagnosticsSummary) == 1
        assert result.diagnosticsSummary[0].count == 2
        assert result.allDiagnostics is None  # Not included by default

    def test_build_result_with_full_diagnostics(self):
        """Build result including full diagnostics for audit."""
        from app.domain.entities.execution_metrics import (
            JoinConsistencyExecutionMetrics,
        )

        metrics = JoinConsistencyExecutionMetrics(
            matchCount=99, mismatchCount=1, eligibleJoinedRows=100, matchRate=99.0
        )
        diags = [
            FailureDiagnostic(
                failureClass=FailureClassEnum.ACTUALITY_DATE_DRIFT,
                details="Date drift",
            ),
        ]
        result = JoinConsistencyMetricsCalculator.build_result(
            passed=True,
            metrics=metrics,
            all_diagnostics=diags,
            include_full_diagnostics=True,
        )
        assert result.allDiagnostics is not None
        assert len(result.allDiagnostics) == 1
