"""Shared actuality-date contract for cross-object DQ rules.

When attached to any cross-object check type (CORRECT, RECONCILE,
TRANSFER_MATCH, JOIN_CONSISTENCY), the rule enforces that the temporal
distance between the left and right actuality attributes does not exceed
the resolved tolerance.

Tolerance sources
-----------------
DELIVERY_CONTRACT  — look up the producer-consumer delivery contract in the
                     external catalog (OpenMetadata) and read the SLA window.
DELIVERY_METADATA  — read the actuality-date values from the delivery note
                     metadata on both sides and derive tolerance from a
                     platform default or a delivery-level SLA annotation.
EXPLICIT           — the author supplies the tolerance directly; no external
                     lookup is performed.
"""
from __future__ import annotations

from typing import Any, Annotated

from pydantic import Field, model_validator

from dq_domain_validation import RuleCheckTypeToleranceSource
from dq_domain_validation import RuleCheckTypeToleranceUnit
from app.domain.entities.base import EntityModel


class ActualityDateContract(EntityModel):
    """Shared actuality-date contract for cross-object DQ rules.

    ``autoResolve`` (optional): when set to ``true`` the platform picks the
    canonical actuality-date attribute from delivery metadata or catalog
    heuristics.  Defaults to ``false`` — the author must supply attributes.
    """

    leftAttribute: str = Field(min_length=1)
    rightAttribute: str = Field(min_length=1)
    toleranceSource: RuleCheckTypeToleranceSource = "DELIVERY_CONTRACT"
    contractId: str = Field(min_length=1)
    contractVersion: str | None = None
    resolvedToleranceValue: int | None = Field(default=None, ge=0)
    resolvedToleranceUnit: RuleCheckTypeToleranceUnit | None = None
    overrideToleranceValue: int | None = Field(default=None, ge=0)
    overrideToleranceUnit: RuleCheckTypeToleranceUnit | None = None
    autoResolve: bool = False

    @model_validator(mode="after")  # type: ignore[misc]
    def _validate_tolerance_pairs(self) -> "ActualityDateContract":
        if (self.resolvedToleranceValue is None) != (self.resolvedToleranceUnit is None):
            raise ValueError(
                "actualityDate requires both 'resolvedToleranceValue' and "
                "'resolvedToleranceUnit' when either is supplied"
            )
        if (self.overrideToleranceValue is None) != (self.overrideToleranceUnit is None):
            raise ValueError(
                "actualityDate requires both 'overrideToleranceValue' and "
                "'overrideToleranceUnit' when either is supplied"
            )
        return self

    def has_resolved_tolerance(self) -> bool:
        """Return ``True`` when tolerance has been resolved."""
        return self.resolvedToleranceValue is not None and self.resolvedToleranceUnit is not None

    def has_override(self) -> bool:
        """Return ``True`` when an author override is present."""
        return self.overrideToleranceValue is not None and self.overrideToleranceUnit is not None


# Backward-compatibility alias so existing persisted payloads still validate.
# JOIN_CONSISTENCY rules that reference the old model name continue to work.
JoinConsistencyActualityDateParams = ActualityDateContract
