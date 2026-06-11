from __future__ import annotations

import re


_CONTROLLED_REASON_PREFIXES = (
    "completeness_",
    "uniqueness_",
    "validity_",
    "consistency_",
    "referential_integrity_",
    "range_",
    "freshness_",
    "volume_",
    "custom_",
)

_GX_REASON_CODE_ALIASES = {
    "expect_column_values_to_not_be_null": "completeness_not_null_violation",
    "not_null_violation": "completeness_not_null_violation",
    "missing_value": "completeness_missing_value",
    "missing_required_value": "completeness_missing_value",
    "expect_column_values_to_be_unique": "uniqueness_duplicate_value",
    "expect_compound_columns_to_be_unique": "uniqueness_duplicate_combination",
    "expect_column_pair_values_to_be_equal": "consistency_value_mismatch",
    "value_mismatch": "consistency_value_mismatch",
    "expect_column_values_to_match_regex": "validity_format_mismatch",
    "expect_column_values_to_match_regex_list": "validity_format_mismatch",
    "expect_column_values_to_be_in_set": "validity_domain_mismatch",
    "expect_column_values_to_be_between": "range_out_of_bounds",
    "expect_column_min_to_be_between": "range_out_of_bounds",
    "expect_column_max_to_be_between": "range_out_of_bounds",
    "expect_column_mean_to_be_between": "range_out_of_bounds",
    "expect_table_row_count_to_be_between": "volume_row_count_out_of_bounds",
    "stale_data": "freshness_stale_data",
    "freshness_violation": "freshness_stale_data",
}


def _slug(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def normalize_exception_reason_code(
    raw_reason_code: str | None,
    *,
    engine_type: str | None,
    reason_text: str | None = None,
    failure_class: str | None = None,
) -> str | None:
    normalized_candidates = [_slug(value) for value in (raw_reason_code, failure_class, reason_text)]
    normalized_candidates = [candidate for candidate in normalized_candidates if candidate]
    if not normalized_candidates:
        return None

    for candidate in normalized_candidates:
        if candidate.startswith(_CONTROLLED_REASON_PREFIXES):
            return candidate

    if _slug(engine_type) == "gx":
        for candidate in normalized_candidates:
            mapped = _GX_REASON_CODE_ALIASES.get(candidate)
            if mapped is not None:
                return mapped

    fallback = normalized_candidates[0]
    if fallback.startswith("custom_"):
        return fallback
    return f"custom_{fallback}"