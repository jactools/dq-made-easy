"""Tests for actuality-date GX expectation generation on cross-object rules."""
from __future__ import annotations

import pytest

from app.application.services.gx_rule_expectations import (
    _build_correct_expectations,
    _build_reconcile_expectations,
    _build_transfer_match_expectations,
    GxExpectationBuildError,
)


def _meta() -> dict:
    return {"dq.rule_id": "rule-test"}


def _actuality_date_dict() -> dict:
    return {
        "leftAttribute": "src_updated_at",
        "rightAttribute": "ref_updated_at",
        "toleranceSource": "DELIVERY_CONTRACT",
        "contractId": "c1",
        "resolvedToleranceValue": 30,
        "resolvedToleranceUnit": "minutes",
    }


# -- CORRECT with actuality date ---------------------------------------------


def test_correct_with_actuality_date_emits_tolerance_expectation() -> None:
    expectations = _build_correct_expectations(
        params={
            "comparison": {
                "leftAttribute": "src_value",
                "rightAttribute": "ref_value",
                "mode": "exact",
            },
            "actualityDate": _actuality_date_dict(),
        },
        meta=_meta(),
    )
    types = [e["expectation_type"] for e in expectations]
    assert "expect_column_pair_values_to_be_equal" in types
    assert "expect_column_timestamps_to_be_within_tolerance_of_other_column" in types

    tolerance_exp = [e for e in expectations if "timestamps" in e["expectation_type"]][0]
    assert tolerance_exp["kwargs"]["column"] == "src_updated_at"
    assert tolerance_exp["kwargs"]["other_column"] == "rhs.ref_updated_at"
    assert tolerance_exp["kwargs"]["max_difference"] == 30
    assert tolerance_exp["kwargs"]["difference_unit"] == "minutes"


def test_correct_without_actuality_date_skips_tolerance() -> None:
    expectations = _build_correct_expectations(
        params={
            "comparison": {
                "leftAttribute": "src_value",
                "rightAttribute": "ref_value",
            },
        },
        meta=_meta(),
    )
    types = [e["expectation_type"] for e in expectations]
    assert "expect_column_pair_values_to_be_equal" in types
    assert "expect_column_timestamps_to_be_within_tolerance_of_other_column" not in types


def test_correct_with_actuality_but_no_resolved_tolerance_skips() -> None:
    expectations = _build_correct_expectations(
        params={
            "comparison": {
                "leftAttribute": "src_value",
                "rightAttribute": "ref_value",
            },
            "actualityDate": {
                "leftAttribute": "src_ts",
                "rightAttribute": "ref_ts",
                # no resolved tolerance — should be skipped
            },
        },
        meta=_meta(),
    )
    types = [e["expectation_type"] for e in expectations]
    assert "expect_column_timestamps_to_be_within_tolerance_of_other_column" not in types


# -- RECONCILE with actuality date -------------------------------------------


def test_reconcile_with_actuality_date_emits_tolerance() -> None:
    expectations = _build_reconcile_expectations(
        params={
            "comparisons": [
                {"leftAttribute": "left_amount", "rightAttribute": "right_amount"},
            ],
            "actualityDate": _actuality_date_dict(),
        },
        meta=_meta(),
    )
    types = [e["expectation_type"] for e in expectations]
    assert "expect_column_pair_values_to_be_equal" in types
    assert "expect_column_timestamps_to_be_within_tolerance_of_other_column" in types


def test_reconcile_without_actuality_date_skips_tolerance() -> None:
    expectations = _build_reconcile_expectations(
        params={
            "comparisons": [
                {"leftAttribute": "left_amount", "rightAttribute": "right_amount"},
            ],
        },
        meta=_meta(),
    )
    types = [e["expectation_type"] for e in expectations]
    assert "expect_column_timestamps_to_be_within_tolerance_of_other_column" not in types


# -- TRANSFER_MATCH with actuality date --------------------------------------


def test_transfer_match_row_value_with_actuality_emits_tolerance() -> None:
    expectations = _build_transfer_match_expectations(
        params={
            "mode": "row_value_match",
            "comparisons": [
                {"leftAttribute": "left_val", "rightAttribute": "right_val"},
            ],
            "actualityDate": _actuality_date_dict(),
        },
        meta=_meta(),
    )
    types = [e["expectation_type"] for e in expectations]
    assert "expect_column_pair_values_to_be_equal" in types
    assert "expect_column_timestamps_to_be_within_tolerance_of_other_column" in types


def test_transfer_match_payload_hash_with_actuality_emits_tolerance() -> None:
    expectations = _build_transfer_match_expectations(
        params={
            "mode": "payload_hash_match",
            "leftHashAttribute": "left_hash",
            "rightHashAttribute": "right_hash",
            "actualityDate": _actuality_date_dict(),
        },
        meta=_meta(),
    )
    types = [e["expectation_type"] for e in expectations]
    assert "expect_column_pair_values_to_be_equal" in types
    assert "expect_column_timestamps_to_be_within_tolerance_of_other_column" in types


def test_transfer_match_without_actuality_date_skips_tolerance() -> None:
    expectations = _build_transfer_match_expectations(
        params={
            "mode": "row_value_match",
            "comparisons": [
                {"leftAttribute": "left_val", "rightAttribute": "right_val"},
            ],
        },
        meta=_meta(),
    )
    types = [e["expectation_type"] for e in expectations]
    assert "expect_column_timestamps_to_be_within_tolerance_of_other_column" not in types


# -- Units -------------------------------------------------------------------


def test_actuality_tolerance_uses_hours_unit() -> None:
    expectations = _build_correct_expectations(
        params={
            "comparison": {"leftAttribute": "a", "rightAttribute": "b"},
            "actualityDate": {
                "leftAttribute": "l_ts",
                "rightAttribute": "r_ts",
                "resolvedToleranceValue": 12,
                "resolvedToleranceUnit": "hours",
            },
        },
        meta=_meta(),
    )
    tolerance_exp = [e for e in expectations if "timestamps" in e["expectation_type"]][0]
    assert tolerance_exp["kwargs"]["max_difference"] == 12
    assert tolerance_exp["kwargs"]["difference_unit"] == "hours"


def test_actuality_tolerance_uses_days_unit() -> None:
    expectations = _build_correct_expectations(
        params={
            "comparison": {"leftAttribute": "a", "rightAttribute": "b"},
            "actualityDate": {
                "leftAttribute": "l_ts",
                "rightAttribute": "r_ts",
                "resolvedToleranceValue": 3,
                "resolvedToleranceUnit": "days",
            },
        },
        meta=_meta(),
    )
    tolerance_exp = [e for e in expectations if "timestamps" in e["expectation_type"]][0]
    assert tolerance_exp["kwargs"]["max_difference"] == 3
    assert tolerance_exp["kwargs"]["difference_unit"] == "days"
