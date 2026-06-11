"""
Execution metrics and diagnostics for JOIN_CONSISTENCY rules.

This module defines the data structures for capturing and communicating
metrics (match counts, rates) and diagnostics (failure classifications)
from rule execution to API and reporting layers.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class FailureClassEnum(str, Enum):
    """Classification of rule execution failures."""

    VALUE_MISMATCH = "value_mismatch"
    ACTUALITY_DATE_DRIFT = "actuality_date_drift"
    NULL_OR_MISSING_JOIN_KEY = "null_or_missing_join_key"
    OTHER = "other"


@dataclass
class FailureDiagnostic:
    """
    Represents a single failure instance in rule execution.

    Attributes:
        failureClass: Classification of the failure reason
        rowIdentifier: Optional identifier for the failed row (e.g., join key values)
        details: Human-readable description of the failure
        affectedAttributes: Optional list of attributes involved in the failure
    """

    failureClass: FailureClassEnum
    rowIdentifier: Optional[str] = None
    details: str = ""
    affectedAttributes: Optional[List[str]] = None

    def to_dict(self) -> dict:
        """Serialize diagnostic to dictionary."""
        return {
            "failureClass": self.failureClass.value,
            "rowIdentifier": self.rowIdentifier,
            "details": self.details,
            "affectedAttributes": self.affectedAttributes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FailureDiagnostic":
        """Deserialize diagnostic from dictionary."""
        return cls(
            failureClass=FailureClassEnum(data["failureClass"]),
            rowIdentifier=data.get("rowIdentifier"),
            details=data.get("details", ""),
            affectedAttributes=data.get("affectedAttributes"),
        )


@dataclass
class DiagnosticsSummary:
    """
    Summary of failure diagnostics aggregated by failure class.

    Attributes:
        failureClass: Classification bucket
        count: Number of failures in this class
        sampleFailures: Up to N sample failures from this class for user inspection
    """

    failureClass: FailureClassEnum
    count: int
    sampleFailures: List[FailureDiagnostic] = field(default_factory=list)
    maxSampleSize: int = 5

    def to_dict(self) -> dict:
        """Serialize summary to dictionary."""
        return {
            "failureClass": self.failureClass.value,
            "count": self.count,
            "sampleFailures": [f.to_dict() for f in self.sampleFailures],
            "maxSampleSize": self.maxSampleSize,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiagnosticsSummary":
        """Deserialize summary from dictionary."""
        return cls(
            failureClass=FailureClassEnum(data["failureClass"]),
            count=data["count"],
            sampleFailures=[
                FailureDiagnostic.from_dict(f) for f in data.get("sampleFailures", [])
            ],
            maxSampleSize=data.get("maxSampleSize", 5),
        )


@dataclass
class JoinConsistencyExecutionMetrics:
    """
    Metrics from a JOIN_CONSISTENCY rule execution.

    Attributes:
        matchCount: Number of rows where all comparisons AND actuality-date check passed
        mismatchCount: Number of rows where at least one comparison OR actuality-date check failed
        eligibleJoinedRows: Total rows produced by the join
        matchRate: Percentage: (matchCount / eligibleJoinedRows) * 100 (or 0 if no eligible rows)
        actualityDateMismatchCount: Rows where actuality-date delta exceeded tolerance
        nullOrMissingJoinKeyCount: Rows excluded due to null/missing join key
    """

    matchCount: int
    mismatchCount: int
    eligibleJoinedRows: int
    matchRate: float  # 0-100
    actualityDateMismatchCount: int = 0
    nullOrMissingJoinKeyCount: int = 0

    def to_dict(self) -> dict:
        """Serialize metrics to dictionary."""
        return {
            "matchCount": self.matchCount,
            "mismatchCount": self.mismatchCount,
            "eligibleJoinedRows": self.eligibleJoinedRows,
            "matchRate": round(self.matchRate, 2),
            "actualityDateMismatchCount": self.actualityDateMismatchCount,
            "nullOrMissingJoinKeyCount": self.nullOrMissingJoinKeyCount,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JoinConsistencyExecutionMetrics":
        """Deserialize metrics from dictionary."""
        return cls(
            matchCount=data["matchCount"],
            mismatchCount=data["mismatchCount"],
            eligibleJoinedRows=data["eligibleJoinedRows"],
            matchRate=data["matchRate"],
            actualityDateMismatchCount=data.get("actualityDateMismatchCount", 0),
            nullOrMissingJoinKeyCount=data.get("nullOrMissingJoinKeyCount", 0),
        )


@dataclass
class JoinConsistencyExecutionResult:
    """
    Complete result of a JOIN_CONSISTENCY rule execution with metrics and diagnostics.

    Attributes:
        passed: Whether the rule execution met the minMatchRate threshold
        metrics: Execution metrics (counts, rates)
        diagnosticsSummary: Aggregated failure diagnostics by class
        allDiagnostics: Full list of all failures (may be large; include for detailed audit)
        executionDurationMs: Time taken to execute the rule (milliseconds)
    """

    passed: bool
    metrics: JoinConsistencyExecutionMetrics
    diagnosticsSummary: List[DiagnosticsSummary] = field(default_factory=list)
    allDiagnostics: Optional[List[FailureDiagnostic]] = None
    executionDurationMs: Optional[int] = None

    def to_dict(self) -> dict:
        """Serialize result to dictionary."""
        return {
            "passed": self.passed,
            "metrics": self.metrics.to_dict(),
            "diagnosticsSummary": [d.to_dict() for d in self.diagnosticsSummary],
            "allDiagnostics": (
                [d.to_dict() for d in self.allDiagnostics]
                if self.allDiagnostics
                else None
            ),
            "executionDurationMs": self.executionDurationMs,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JoinConsistencyExecutionResult":
        """Deserialize result from dictionary."""
        return cls(
            passed=data["passed"],
            metrics=JoinConsistencyExecutionMetrics.from_dict(data["metrics"]),
            diagnosticsSummary=[
                DiagnosticsSummary.from_dict(d) for d in data.get("diagnosticsSummary", [])
            ],
            allDiagnostics=(
                [FailureDiagnostic.from_dict(d) for d in data.get("allDiagnostics", [])]
                if data.get("allDiagnostics")
                else None
            ),
            executionDurationMs=data.get("executionDurationMs"),
        )
