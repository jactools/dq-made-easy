from __future__ import annotations

from app.application.services.exception_reason_taxonomy import normalize_exception_reason_code


def test_normalize_exception_reason_code_maps_gx_expectation_type() -> None:
    assert normalize_exception_reason_code(
        "expect_column_values_to_not_be_null",
        engine_type="gx",
        reason_text="customer_id must not be null",
        failure_class="expectation_failed",
    ) == "completeness_not_null_violation"


def test_normalize_exception_reason_code_maps_known_consistency_alias() -> None:
    assert normalize_exception_reason_code(
        "value_mismatch",
        engine_type="gx",
        reason_text="customer_id differs from golden source",
        failure_class="value_mismatch",
    ) == "consistency_value_mismatch"


def test_normalize_exception_reason_code_prefixes_unknown_codes_as_custom() -> None:
    assert normalize_exception_reason_code(
        "GX_VALIDATION_FAILED",
        engine_type="gx",
        reason_text="One or more expectations failed",
        failure_class="GX_VALIDATION_FAILED",
    ) == "custom_gx_validation_failed"


def test_normalize_exception_reason_code_preserves_controlled_codes() -> None:
    assert normalize_exception_reason_code(
        "freshness_stale_data",
        engine_type="gx",
    ) == "freshness_stale_data"