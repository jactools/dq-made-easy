from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from dq_domain_validation import RuleCheckTypeAnchor
from dq_domain_validation import RuleCheckTypeComparisonMode
from dq_domain_validation import RuleCheckTypeMetric
from dq_domain_validation import RuleCheckTypeMode
from dq_domain_validation import RuleCheckTypeOperator
from dq_domain_validation import RuleCheckTypePlausibilityMode
from dq_domain_validation import RuleCheckTypeToleranceSource
from dq_domain_validation import RuleCheckTypeToleranceUnit
from dq_domain_validation import RuleCheckTypeTransferMatchMode
from app.domain.entities.base import EntityModel
from app.domain.entities.actuality_date_contract import ActualityDateContract


class RuleCheckType(str, Enum):
    """Enumeration of supported parameterised rule check-types.

    Each check-type maps a well-known data quality concern to a set of
    structured parameters from which a compiler-ready expression can be
    derived automatically (DQ-4.10).
    """

    THRESHOLD = "THRESHOLD"                          # null%, empty%, default-value% — Completeness
    ROW_COUNT = "ROW_COUNT"                          # table row count               — Volume
    REGEX = "REGEX"                                  # pattern / format match         — Accuracy
    RANGE = "RANGE"                                  # numeric / date min-max         — Validity/Timeliness
    ALLOWLIST = "ALLOWLIST"                          # must be one of                 — Accuracy/Validity
    BLOCKLIST = "BLOCKLIST"                          # must not be one of             — Accuracy/Validity
    UNIQUENESS = "UNIQUENESS"                        # no duplicate rows on key       — Uniqueness
    REFERENTIAL_INTEGRITY = "REFERENTIAL_INTEGRITY"  # FK exists in ref table         — Consistency
    FRESHNESS = "FRESHNESS"                          # data not older than N days     — Timeliness
    LAG = "LAG"                                      # processing lag within N hours  — Timeliness
    FUTURE_DATE = "FUTURE_DATE"                      # date is not in the future      — Timeliness
    CORRECT = "CORRECT"                              # matches authoritative source   — Accuracy
    PRESENT = "PRESENT"                              # populated and not placeholder  — Completeness
    RECONCILE = "RECONCILE"                          # lightweight source-target sync — Consistency
    PLAUSIBLE = "PLAUSIBLE"                          # context-aware validity checks  — Validity
    TRANSFER_MATCH = "TRANSFER_MATCH"                # replicated payload parity      — Consistency
    JOIN_CONSISTENCY = "JOIN_CONSISTENCY"            # joined objects carry same data — Consistency


class ThresholdParams(EntityModel):
    """Parameters for a completeness threshold check.

    Evaluates whether the percentage of *good* rows for ``attribute`` satisfies
    ``operator`` against ``threshold`` (0-100).
    """

    checkType: Literal["THRESHOLD"] = "THRESHOLD"
    attribute: str
    metric: RuleCheckTypeMetric = "null_pct"
    operator: RuleCheckTypeOperator = "gte"
    threshold: float
    quantile: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _validate_threshold_shape(self) -> "ThresholdParams":
        if self.metric == "quantile" and self.quantile is None:
            raise ValueError("THRESHOLD check type with metric 'quantile' requires 'quantile'")
        if self.metric != "quantile" and self.quantile is not None:
            raise ValueError("THRESHOLD check type only accepts 'quantile' when metric is 'quantile'")
        return self


class RowCountParams(EntityModel):
    """Parameters for a table row-count check.

    ``threshold`` applies to the selected comparison operator.
    ``between`` uses ``minValue`` / ``maxValue`` instead.
    """

    checkType: Literal["ROW_COUNT"] = "ROW_COUNT"
    operator: Literal["gt", "gte", "lt", "lte", "between"] = "gte"
    threshold: int | None = Field(default=None, ge=0)
    minValue: int | None = Field(default=None, ge=0)
    maxValue: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_row_count_shape(self) -> "RowCountParams":
        if self.operator == "between":
            if self.minValue is None or self.maxValue is None:
                raise ValueError("ROW_COUNT check type with operator 'between' requires 'minValue' and 'maxValue'")
            if self.threshold is not None:
                raise ValueError("ROW_COUNT check type with operator 'between' does not accept 'threshold'")
            if self.maxValue < self.minValue:
                raise ValueError("ROW_COUNT check type with operator 'between' requires maxValue >= minValue")
            return self

        if self.threshold is None:
            raise ValueError("ROW_COUNT check type requires 'threshold' when operator is not 'between'")
        if self.minValue is not None or self.maxValue is not None:
            raise ValueError("ROW_COUNT check type does not accept 'minValue' or 'maxValue' when operator is not 'between'")
        return self


class RegexParams(EntityModel):
    """Parameters for a regex / format-match check.

    Evaluates whether ``attribute`` values match ``pattern``.
    ``flags`` accepts standard regex modifiers (e.g. ``"i"`` for case-insensitive).
    """

    checkType: Literal["REGEX"] = "REGEX"
    attribute: str
    pattern: str
    flags: str = ""
    requirePresent: bool = False
    condition: "SimpleConditionParams | None" = None


class RangeParams(EntityModel):
    """Parameters for a numeric or date range check.

    At least one of ``minValue`` / ``maxValue`` must be provided.
    ``inclusive`` controls whether the boundary values themselves are valid.
    """

    checkType: Literal["RANGE"] = "RANGE"
    attribute: str
    minValue: int | float | str | None = None
    maxValue: int | float | str | None = None
    inclusive: bool = True
    condition: "SimpleConditionParams | None" = None


class AllowlistParams(EntityModel):
    """Parameters for an allowlist (must-be-one-of) check."""

    checkType: Literal["ALLOWLIST"] = "ALLOWLIST"
    attribute: str
    allowedValues: list[str]
    caseSensitive: bool = False
    condition: "SimpleConditionParams | None" = None


class BlocklistParams(EntityModel):
    """Parameters for a blocklist (must-not-be-one-of) check."""

    checkType: Literal["BLOCKLIST"] = "BLOCKLIST"
    attribute: str
    blockedValues: list[str]
    caseSensitive: bool = False


class UniquenessParams(EntityModel):
    """Parameters for a uniqueness / duplicate-detection check.

    ``attributes`` lists the columns that form the key — may be a single
    column or a composite key.
    """

    checkType: Literal["UNIQUENESS"] = "UNIQUENESS"
    attributes: list[str]


class ReferentialIntegrityParams(EntityModel):
    """Parameters for a cross-dataset referential integrity check.

    Verifies that every value of ``attribute`` exists in
    ``refDataObjectId.refAttribute``.
    """

    checkType: Literal["REFERENTIAL_INTEGRITY"] = "REFERENTIAL_INTEGRITY"
    attribute: str
    refDataObjectId: str
    refDataObjectVersionId: str
    refAttribute: str
    refWorkspaceId: str | None = None


class FreshnessParams(EntityModel):
    """Parameters for a data freshness timeliness check.

    Verifies that ``attribute`` is not older than ``maxDaysOld`` relative to
    ``anchor`` (``"now"`` or a fixed processing date).
    """

    checkType: Literal["FRESHNESS"] = "FRESHNESS"
    attribute: str
    maxDaysOld: int
    anchor: RuleCheckTypeAnchor = "now"
    condition: "SimpleConditionParams | None" = None


class LagParams(EntityModel):
    """Parameters for a processing-lag timeliness check.

    Verifies that the difference between ``endAttribute`` and ``startAttribute``
    does not exceed ``maxHours``.
    """

    checkType: Literal["LAG"] = "LAG"
    startAttribute: str
    endAttribute: str
    maxHours: int


class FutureDateParams(EntityModel):
    """Parameters for a future-date detection check.

    Verifies that ``attribute`` is not later than ``referenceDate`` (ISO-8601).
    When ``referenceDate`` is ``None`` the expression generator defaults to
    the current timestamp at run time.
    """

    checkType: Literal["FUTURE_DATE"] = "FUTURE_DATE"
    attribute: str
    referenceDate: str | None = None


class CrossObjectJoinKey(EntityModel):
    leftAttribute: str = Field(min_length=1)
    rightAttribute: str = Field(min_length=1)


class CrossObjectComparison(EntityModel):
    leftAttribute: str = Field(min_length=1)
    rightAttribute: str = Field(min_length=1)
    mode: RuleCheckTypeComparisonMode = "exact"
    tolerance: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_tolerance(self) -> "CrossObjectComparison":
        if self.mode == "numeric_tolerance" and self.tolerance is None:
            raise ValueError("Cross-object numeric_tolerance comparisons require 'tolerance'")
        if self.mode != "numeric_tolerance" and self.tolerance is not None:
            raise ValueError("Cross-object comparison 'tolerance' is only valid with mode 'numeric_tolerance'")
        return self


class PresentParams(EntityModel):
    checkType: Literal["PRESENT"] = "PRESENT"
    attribute: str
    blockedValues: list[str] = Field(default_factory=list)
    caseSensitive: bool = False
    condition: "SimpleConditionParams | None" = None


class SimpleConditionParams(EntityModel):
    attribute: str = Field(min_length=1)
    operator: Literal["equals"] = "equals"
    value: str = Field(min_length=1)


class CorrectParams(EntityModel):
    checkType: Literal["CORRECT"] = "CORRECT"
    sourceDataObjectVersionId: str = Field(min_length=1)
    referenceDataObjectVersionId: str = Field(min_length=1)
    joinKeys: list[CrossObjectJoinKey] = Field(min_length=1)
    comparison: CrossObjectComparison
    actualityDate: ActualityDateContract | None = None


class ReconcileParams(EntityModel):
    checkType: Literal["RECONCILE"] = "RECONCILE"
    leftDataObjectVersionId: str = Field(min_length=1)
    rightDataObjectVersionId: str = Field(min_length=1)
    joinKeys: list[CrossObjectJoinKey] = Field(min_length=1)
    comparisons: list[CrossObjectComparison] = Field(min_length=1)
    actualityDate: ActualityDateContract | None = None


class PlausibleContextualRange(EntityModel):
    contextValue: str = Field(min_length=1)
    minValue: float | str | None = None
    maxValue: float | str | None = None
    inclusive: bool = True

    @model_validator(mode="after")
    def _validate_bounds(self) -> "PlausibleContextualRange":
        if self.minValue is None and self.maxValue is None:
            raise ValueError("PLAUSIBLE contextual_range entries require at least one of 'minValue' or 'maxValue'")
        return self


class PlausibleConditionalAllowlist(EntityModel):
    contextValue: str = Field(min_length=1)
    allowedValues: list[str] = Field(min_length=1)
    caseSensitive: bool = False


class PlausibleParams(EntityModel):
    checkType: Literal["PLAUSIBLE"] = "PLAUSIBLE"
    mode: RuleCheckTypePlausibilityMode = "contextual_range"
    attribute: str = Field(min_length=1)
    contextAttribute: str = Field(min_length=1)
    ranges: list[PlausibleContextualRange] = Field(default_factory=list)
    allowlists: list[PlausibleConditionalAllowlist] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_mode_payload(self) -> "PlausibleParams":
        if self.mode == "contextual_range" and not self.ranges:
            raise ValueError("PLAUSIBLE contextual_range mode requires at least one range entry")
        if self.mode == "conditional_allowlist" and not self.allowlists:
            raise ValueError("PLAUSIBLE conditional_allowlist mode requires at least one allowlist entry")
        if self.mode == "contextual_range" and self.allowlists:
            raise ValueError("PLAUSIBLE contextual_range mode does not accept allowlists")
        if self.mode == "conditional_allowlist" and self.ranges:
            raise ValueError("PLAUSIBLE conditional_allowlist mode does not accept ranges")
        return self


class TransferMatchParams(EntityModel):
    checkType: Literal["TRANSFER_MATCH"] = "TRANSFER_MATCH"
    mode: RuleCheckTypeTransferMatchMode = "row_value_match"
    leftDataObjectVersionId: str = Field(min_length=1)
    rightDataObjectVersionId: str = Field(min_length=1)
    joinKeys: list[CrossObjectJoinKey] = Field(min_length=1)
    comparisons: list[CrossObjectComparison] = Field(default_factory=list)
    leftHashAttribute: str | None = None
    rightHashAttribute: str | None = None
    actualityDate: ActualityDateContract | None = None

    @model_validator(mode="after")
    def _validate_transfer_payload(self) -> "TransferMatchParams":
        if self.mode == "row_value_match" and not self.comparisons:
            raise ValueError("TRANSFER_MATCH row_value_match mode requires at least one comparison entry")
        if self.mode == "payload_hash_match":
            if not self.leftHashAttribute or not self.rightHashAttribute:
                raise ValueError(
                    "TRANSFER_MATCH payload_hash_match mode requires both 'leftHashAttribute' and 'rightHashAttribute'"
                )
            if self.comparisons:
                raise ValueError("TRANSFER_MATCH payload_hash_match mode does not accept comparisons")
        return self


class JoinConsistencyJoinKey(EntityModel):
    """Pair of attributes that define the join between left and right objects."""

    leftAttribute: str = Field(min_length=1)
    rightAttribute: str = Field(min_length=1)


class JoinConsistencyComparison(EntityModel):
    """Pair of attributes to compare after the join has matched."""

    leftAttribute: str = Field(min_length=1)
    rightAttribute: str = Field(min_length=1)
    mode: RuleCheckTypeMode = "exact"


class JoinConsistencyActualityDateParams(ActualityDateContract):
    """Backward-compatibility alias for :class:`ActualityDateContract`.

    Existing persisted JOIN_CONSISTENCY payloads that reference
    ``JoinConsistencyActualityDateParams`` continue to validate correctly.
    """

    pass  # inherits all fields and validators from ActualityDateContract


class JoinConsistencyParams(EntityModel):
    """Parameters for contract-governed cross-object consistency checks.

    ``actualityDate`` uses the shared :class:`ActualityDateContract` model
    (via :class:`JoinConsistencyActualityDateParams` alias for backward compat).
    """

    checkType: Literal["JOIN_CONSISTENCY"] = "JOIN_CONSISTENCY"
    leftDataObjectVersionId: str = Field(min_length=1)
    rightDataObjectVersionId: str = Field(min_length=1)
    joinKeys: list[JoinConsistencyJoinKey] = Field(min_length=1)
    comparisons: list[JoinConsistencyComparison] = Field(min_length=1)
    actualityDate: JoinConsistencyActualityDateParams
    minMatchRate: float = Field(ge=0, le=100)


RuleCheckTypeParams = Annotated[
    Union[
        ThresholdParams,
        RowCountParams,
        RegexParams,
        RangeParams,
        AllowlistParams,
        BlocklistParams,
        UniquenessParams,
        ReferentialIntegrityParams,
        FreshnessParams,
        LagParams,
        FutureDateParams,
        PresentParams,
        CorrectParams,
        ReconcileParams,
        PlausibleParams,
        TransferMatchParams,
        JoinConsistencyParams,
    ],
    Field(discriminator="checkType"),
]
