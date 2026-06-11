from app.domain.entities.execution_metrics import (
    DiagnosticsSummary,
    FailureClassEnum,
    FailureDiagnostic,
    JoinConsistencyExecutionMetrics,
    JoinConsistencyExecutionResult,
)


def test_failure_diagnostic_round_trip() -> None:
    diagnostic = FailureDiagnostic(
        failureClass=FailureClassEnum.VALUE_MISMATCH,
        rowIdentifier="row-7",
        details="Compared attribute values differ",
        affectedAttributes=["account_balance", "account_type"],
    )

    dumped = diagnostic.to_dict()

    assert dumped == {
        "failureClass": "value_mismatch",
        "rowIdentifier": "row-7",
        "details": "Compared attribute values differ",
        "affectedAttributes": ["account_balance", "account_type"],
    }

    restored = FailureDiagnostic.from_dict(dumped)

    assert restored == diagnostic


def test_diagnostics_summary_round_trip_and_default_sample_size() -> None:
    sample = FailureDiagnostic(
        failureClass=FailureClassEnum.ACTUALITY_DATE_DRIFT,
        details="Actuality-date delta exceeds contract tolerance",
    )
    summary = DiagnosticsSummary(
        failureClass=FailureClassEnum.ACTUALITY_DATE_DRIFT,
        count=1,
        sampleFailures=[sample],
    )

    dumped = summary.to_dict()

    assert dumped == {
        "failureClass": "actuality_date_drift",
        "count": 1,
        "sampleFailures": [sample.to_dict()],
        "maxSampleSize": 5,
    }

    restored = DiagnosticsSummary.from_dict(
        {
            "failureClass": "actuality_date_drift",
            "count": 1,
            "sampleFailures": [sample.to_dict()],
        }
    )

    assert restored.failureClass == FailureClassEnum.ACTUALITY_DATE_DRIFT
    assert restored.count == 1
    assert restored.sampleFailures == [sample]
    assert restored.maxSampleSize == 5


def test_execution_metrics_round_trip_and_match_rate_rounding() -> None:
    metrics = JoinConsistencyExecutionMetrics(
        matchCount=3,
        mismatchCount=1,
        eligibleJoinedRows=4,
        matchRate=75.126,
        actualityDateMismatchCount=2,
        nullOrMissingJoinKeyCount=1,
    )

    dumped = metrics.to_dict()

    assert dumped == {
        "matchCount": 3,
        "mismatchCount": 1,
        "eligibleJoinedRows": 4,
        "matchRate": 75.13,
        "actualityDateMismatchCount": 2,
        "nullOrMissingJoinKeyCount": 1,
    }

    restored = JoinConsistencyExecutionMetrics.from_dict(dumped)

    assert restored == JoinConsistencyExecutionMetrics(
        matchCount=3,
        mismatchCount=1,
        eligibleJoinedRows=4,
        matchRate=75.13,
        actualityDateMismatchCount=2,
        nullOrMissingJoinKeyCount=1,
    )


def test_execution_result_round_trip_with_and_without_full_diagnostics() -> None:
    metrics = JoinConsistencyExecutionMetrics(
        matchCount=10,
        mismatchCount=2,
        eligibleJoinedRows=12,
        matchRate=83.33,
    )
    diagnostics = [
        FailureDiagnostic(
            failureClass=FailureClassEnum.NULL_OR_MISSING_JOIN_KEY,
            rowIdentifier="row-9",
            details="Join key is null or missing; row excluded from eligible set",
        ),
    ]

    result = JoinConsistencyExecutionResult(
        passed=False,
        metrics=metrics,
        diagnosticsSummary=[
            DiagnosticsSummary(
                failureClass=FailureClassEnum.NULL_OR_MISSING_JOIN_KEY,
                count=1,
                sampleFailures=diagnostics,
            )
        ],
        allDiagnostics=diagnostics,
        executionDurationMs=250,
    )

    dumped = result.to_dict()

    assert dumped["passed"] is False
    assert dumped["metrics"] == metrics.to_dict()
    assert dumped["diagnosticsSummary"][0]["count"] == 1
    assert dumped["allDiagnostics"] == [diagnostics[0].to_dict()]
    assert dumped["executionDurationMs"] == 250

    restored = JoinConsistencyExecutionResult.from_dict(dumped)

    assert restored == result

    without_full_diagnostics = JoinConsistencyExecutionResult(
        passed=True,
        metrics=metrics,
        diagnosticsSummary=[],
        allDiagnostics=[],
        executionDurationMs=None,
    )

    dumped_without = without_full_diagnostics.to_dict()

    assert dumped_without["allDiagnostics"] is None
    assert dumped_without["executionDurationMs"] is None

    restored_without = JoinConsistencyExecutionResult.from_dict(
        {
            "passed": True,
            "metrics": metrics.to_dict(),
            "diagnosticsSummary": [],
        }
    )

    assert restored_without.allDiagnostics is None
    assert restored_without.executionDurationMs is None