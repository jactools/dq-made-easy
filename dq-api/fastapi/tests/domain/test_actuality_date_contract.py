from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.entities.actuality_date_contract import ActualityDateContract


def _build_minimal() -> dict:
    return {
        "leftAttribute": "left_updated_at",
        "rightAttribute": "right_updated_at",
        "toleranceSource": "DELIVERY_CONTRACT",
        "contractId": "contract-1",
    }


def _build_with_resolved() -> dict:
    base = _build_minimal()
    base["resolvedToleranceValue"] = 30
    base["resolvedToleranceUnit"] = "minutes"
    return base


def _build_with_override() -> dict:
    base = _build_with_resolved()
    base["overrideToleranceValue"] = 60
    base["overrideToleranceUnit"] = "minutes"
    return base


def _build_explicit() -> dict:
    return {
        "leftAttribute": "left_effective_at",
        "rightAttribute": "right_effective_at",
        "toleranceSource": "EXPLICIT",
        "contractId": "n/a",
        "resolvedToleranceValue": 2,
        "resolvedToleranceUnit": "days",
    }


def _build_delivery_metadata() -> dict:
    return {
        "leftAttribute": "left_actuality_date",
        "rightAttribute": "right_actuality_date",
        "toleranceSource": "DELIVERY_METADATA",
        "contractId": "delivery-meta",
        "autoResolve": True,
    }


# -- Basic validation --------------------------------------------------------


def test_minimal_validates() -> None:
    model = ActualityDateContract(**_build_minimal())
    assert model.leftAttribute == "left_updated_at"
    assert model.rightAttribute == "right_updated_at"
    assert model.toleranceSource == "DELIVERY_CONTRACT"
    assert model.contractId == "contract-1"
    assert not model.has_resolved_tolerance()
    assert not model.has_override()


def test_with_resolved_tolerance() -> None:
    model = ActualityDateContract(**_build_with_resolved())
    assert model.has_resolved_tolerance()
    assert model.resolvedToleranceValue == 30
    assert model.resolvedToleranceUnit == "minutes"


def test_with_override() -> None:
    model = ActualityDateContract(**_build_with_override())
    assert model.has_override()
    assert model.overrideToleranceValue == 60


def test_explicit_source() -> None:
    model = ActualityDateContract(**_build_explicit())
    assert model.toleranceSource == "EXPLICIT"
    assert model.has_resolved_tolerance()


def test_delivery_metadata_source() -> None:
    model = ActualityDateContract(**_build_delivery_metadata())
    assert model.toleranceSource == "DELIVERY_METADATA"
    assert model.autoResolve is True


# -- Tolerance pair validation -----------------------------------------------


def test_rejects_partial_resolved_tolerance() -> None:
    data = _build_minimal()
    data["resolvedToleranceValue"] = 10  # no unit
    with pytest.raises(ValidationError, match="resolvedToleranceUnit"):
        ActualityDateContract(**data)


def test_rejects_partial_override_tolerance() -> None:
    data = _build_minimal()
    data["overrideToleranceValue"] = 5  # no unit
    with pytest.raises(ValidationError, match="overrideToleranceUnit"):
        ActualityDateContract(**data)


def test_rejects_negative_resolved_tolerance() -> None:
    data = _build_with_resolved()
    data["resolvedToleranceValue"] = -1
    with pytest.raises(ValidationError):
        ActualityDateContract(**data)


def test_rejects_negative_override_tolerance() -> None:
    data = _build_with_override()
    data["overrideToleranceValue"] = -5
    with pytest.raises(ValidationError):
        ActualityDateContract(**data)


# -- Backward compat alias ---------------------------------------------------


def test_backward_compat_alias_validates() -> None:
    from app.domain.entities.rule_check_type import JoinConsistencyActualityDateParams

    data = _build_with_resolved()
    model = JoinConsistencyActualityDateParams(**data)
    assert model.leftAttribute == "left_updated_at"
    assert model.has_resolved_tolerance()


# -- Auto-resolve flag -------------------------------------------------------


def test_auto_resolve_defaults_false() -> None:
    model = ActualityDateContract(**_build_minimal())
    assert model.autoResolve is False


def test_auto_resolve_can_be_true() -> None:
    model = ActualityDateContract(**_build_delivery_metadata())
    assert model.autoResolve is True
