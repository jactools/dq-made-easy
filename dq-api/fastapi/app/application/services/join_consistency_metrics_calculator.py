"""
Metrics calculator for JOIN_CONSISTENCY rule execution results.

Transforms raw execution data into structured metrics and diagnostics
for reporting and auditing.
"""

import time
from typing import List, Optional

from app.domain.entities.execution_metrics import (
    DiagnosticsSummary,
    FailureClassEnum,
    FailureDiagnostic,
    JoinConsistencyExecutionMetrics,
    JoinConsistencyExecutionResult,
)


class JoinConsistencyMetricsCalculator:
    """Calculates metrics and diagnostics from JOIN_CONSISTENCY execution data."""

    @staticmethod
    def calculate_metrics(
        joined_rows_count: int,
        matched_rows_count: int,
        mismatched_rows_count: int,
        null_or_missing_join_keys_count: int = 0,
        actuality_date_mismatch_count: int = 0,
    ) -> JoinConsistencyExecutionMetrics:
        """
        Calculate execution metrics from raw counts.

        Args:
            joined_rows_count: Total rows in join result
            matched_rows_count: Rows where all checks passed
            mismatched_rows_count: Rows where at least one check failed
            null_or_missing_join_keys_count: Rows excluded due to null join keys
            actuality_date_mismatch_count: Rows where only actuality date check failed

        Returns:
            Calculated metrics object
        """
        eligible_joined_rows = joined_rows_count - null_or_missing_join_keys_count

        # Calculate match rate
        match_rate = (
            (matched_rows_count / eligible_joined_rows * 100)
            if eligible_joined_rows > 0
            else 0.0
        )

        return JoinConsistencyExecutionMetrics(
            matchCount=matched_rows_count,
            mismatchCount=mismatched_rows_count,
            eligibleJoinedRows=eligible_joined_rows,
            matchRate=match_rate,
            actualityDateMismatchCount=actuality_date_mismatch_count,
            nullOrMissingJoinKeyCount=null_or_missing_join_keys_count,
        )

    @staticmethod
    def classify_failure(
        value_mismatch: bool,
        actuality_date_drift: bool,
        join_key_missing: bool = False,
        row_identifier: Optional[str] = None,
        affected_attributes: Optional[List[str]] = None,
    ) -> FailureDiagnostic:
        """
        Classify a single failure into appropriate diagnostic.

        Priority: join_key > actuality_date > value_mismatch (classifies by primary failure reason)

        Args:
            value_mismatch: Whether compared attributes differ
            actuality_date_drift: Whether actuality-date delta exceeded tolerance
            join_key_missing: Whether join key was null/missing
            row_identifier: Optional identifier for the row
            affected_attributes: Optional list of attributes involved in failure

        Returns:
            Classified FailureDiagnostic
        """
        if join_key_missing:
            failure_class = FailureClassEnum.NULL_OR_MISSING_JOIN_KEY
            detail = "Join key is null or missing; row excluded from eligible set"
        elif actuality_date_drift:
            failure_class = FailureClassEnum.ACTUALITY_DATE_DRIFT
            detail = "Actuality-date delta exceeds contract tolerance"
        elif value_mismatch:
            failure_class = FailureClassEnum.VALUE_MISMATCH
            detail = "Compared attribute values differ between left and right objects"
        else:
            failure_class = FailureClassEnum.OTHER
            detail = "Unknown failure reason"

        return FailureDiagnostic(
            failureClass=failure_class,
            rowIdentifier=row_identifier,
            details=detail,
            affectedAttributes=affected_attributes,
        )

    @staticmethod
    def build_diagnostics_summary(
        all_diagnostics: List[FailureDiagnostic], max_sample_size: int = 5
    ) -> List[DiagnosticsSummary]:
        """
        Aggregate failures by classification and build summary.

        Args:
            all_diagnostics: List of all failures from execution
            max_sample_size: Maximum number of sample failures to include per class

        Returns:
            List of DiagnosticsSummary grouped by failure class
        """
        # Group diagnostics by failure class
        failures_by_class: dict[FailureClassEnum, List[FailureDiagnostic]] = {}
        for diag in all_diagnostics:
            if diag.failureClass not in failures_by_class:
                failures_by_class[diag.failureClass] = []
            failures_by_class[diag.failureClass].append(diag)

        # Build summary with samples
        summaries = []
        for failure_class in sorted(
            failures_by_class.keys(), key=lambda x: x.value  # Sort by name for consistency
        ):
            failures = failures_by_class[failure_class]
            samples = failures[:max_sample_size]  # Take first N as samples

            summary = DiagnosticsSummary(
                failureClass=failure_class,
                count=len(failures),
                sampleFailures=samples,
                maxSampleSize=max_sample_size,
            )
            summaries.append(summary)

        return summaries

    @staticmethod
    def build_result(
        passed: bool,
        metrics: JoinConsistencyExecutionMetrics,
        all_diagnostics: Optional[List[FailureDiagnostic]] = None,
        execution_duration_ms: Optional[int] = None,
        max_sample_size: int = 5,
        include_full_diagnostics: bool = False,
    ) -> JoinConsistencyExecutionResult:
        """
        Build complete execution result with metrics and diagnostics.

        Args:
            passed: Whether the execution met the pass criterion
            metrics: Calculated metrics
            all_diagnostics: All failures from execution (optional)
            execution_duration_ms: Time taken to execute (optional)
            max_sample_size: Maximum failures per class in summary
            include_full_diagnostics: Whether to include all diagnostics (not just summary)

        Returns:
            Complete result object ready for persistence/API response
        """
        if all_diagnostics is None:
            all_diagnostics = []

        diagnostics_summary = JoinConsistencyMetricsCalculator.build_diagnostics_summary(
            all_diagnostics, max_sample_size
        )

        return JoinConsistencyExecutionResult(
            passed=passed,
            metrics=metrics,
            diagnosticsSummary=diagnostics_summary,
            allDiagnostics=all_diagnostics if include_full_diagnostics else None,
            executionDurationMs=execution_duration_ms,
        )
