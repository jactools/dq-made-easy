from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.application.services.gx_expectations import attach_gx_row_condition_to_expectations
from app.application.services.gx_expectations import GxExpectationBuildError
from app.domain.entities.rule import RuleEntity
from app.domain.entities.rule_dsl_ir import build_rule_dsl_v2_semantic_ir
from app.domain.entities.rule_dsl_v2 import RuleDslV2Document


_DIRECT_CHECK_TYPES = {
    "THRESHOLD",
    "ROW_COUNT",
    "REGEX",
    "RANGE",
    "ALLOWLIST",
    "BLOCKLIST",
    "PLAUSIBLE",
    "UNIQUENESS",
    "REFERENTIAL_INTEGRITY",
    "FRESHNESS",
    "LAG",
    "FUTURE_DATE",
    "PRESENT",
    "CORRECT",
    "RECONCILE",
    "TRANSFER_MATCH",
    "JOIN_CONSISTENCY",
}
_TRANSLATOR_CHECK_TYPES: set[str] = set()
_UNSUPPORTED_CHECK_TYPES: set[str] = set()


def build_gx_expectations_for_rule(
    *,
    rule: RuleEntity | Any,
    intermediate_model: Mapping[str, Any] | None = None,
    rule_id: str | None = None,
    artifact_key: str | None = None,
) -> list[dict[str, Any]]:
    check_type = str(getattr(rule, "check_type", None) or getattr(rule, "checkType", None) or "").strip().upper()
    raw_params = getattr(rule, "check_type_params", None)
    if raw_params is None:
        raw_params = getattr(rule, "checkTypeParams", None)
    params = dict(raw_params or {})
    rule_identifier = str(getattr(rule, "id", "") or "unknown-rule")
    meta = _build_meta(rule_id=rule_id, artifact_key=artifact_key)

    if check_type in _DIRECT_CHECK_TYPES:
        if not params:
            raise GxExpectationBuildError(
                f"Rule '{rule_identifier}' declares check type '{check_type}' without check_type_params"
            )
        expectations = _build_direct_expectations(check_type=check_type, params=params, meta=meta)
        if check_type == "PLAUSIBLE" and str(params.get("mode") or "").strip().lower() == "conditional_allowlist":
            return expectations
        return attach_gx_row_condition_to_expectations(
            expectations,
            intermediate_model=intermediate_model,
        )

    if check_type in _TRANSLATOR_CHECK_TYPES:
        if intermediate_model is None:
            raise GxExpectationBuildError(
                f"Rule '{rule_identifier}' requires compiler intermediate model for check type '{check_type}'"
            )
        return _build_from_intermediate_model(
            intermediate_model=intermediate_model,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )

    if check_type in _UNSUPPORTED_CHECK_TYPES:
        raise GxExpectationBuildError(_unsupported_check_type_message(check_type))

    rule_kind = _resolve_rule_kind(rule)
    if rule_kind == "custom_query_assertion":
        raw_dsl = getattr(rule, "dsl", None)
        if not isinstance(raw_dsl, Mapping):
            raise GxExpectationBuildError("custom_query_assertion requires a semantic DSL payload")
        semantic_model = RuleDslV2Document.model_validate(dict(raw_dsl))
        semantic_ir = build_rule_dsl_v2_semantic_ir(semantic_model=semantic_model)
        from app.application.services.rule_dsl_gx_lowerer import build_gx_expectations_from_rule_dsl_v2

        return build_gx_expectations_from_rule_dsl_v2(
            semantic_ir=semantic_ir,
            rule_id=rule_id,
            artifact_key=artifact_key,
        )

    if intermediate_model is None:
        raise GxExpectationBuildError(
            f"Rule '{rule_identifier}' cannot build GX expectations without a supported check type or compiler intermediate model"
        )

    return _build_from_intermediate_model(
        intermediate_model=intermediate_model,
        rule_id=rule_id,
        artifact_key=artifact_key,
    )


def _resolve_rule_kind(rule: RuleEntity | Any) -> str:
    direct_kind = str(getattr(rule, "kind", None) or getattr(rule, "rule_kind", None) or "").strip()
    if direct_kind:
        return direct_kind

    raw_dsl = getattr(rule, "dsl", None)
    if isinstance(raw_dsl, Mapping):
        rule_payload = raw_dsl.get("rule")
        if isinstance(rule_payload, Mapping):
            return str(rule_payload.get("kind") or "").strip()

    return ""


def _build_from_intermediate_model(
    *,
    intermediate_model: Mapping[str, Any],
    rule_id: str | None,
    artifact_key: str | None,
) -> list[dict[str, Any]]:
    from app.application.services import build_gx_expectations_from_intermediate_model

    return build_gx_expectations_from_intermediate_model(
        dict(intermediate_model),
        rule_id=rule_id,
        artifact_key=artifact_key,
    )


def _build_meta(*, rule_id: str | None, artifact_key: str | None) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if rule_id:
        meta["dq.rule_id"] = rule_id
    if artifact_key:
        meta["dq.artifact_key"] = artifact_key
    return meta


def _unsupported_check_type_message(check_type: str) -> str:
    return (
        f"GX auto-publish does not yet support {check_type} because these rules require join-pair materialization "
        "that activation does not create"
    )


def _build_direct_expectations(
    *,
    check_type: str,
    params: Mapping[str, Any],
    meta: Mapping[str, Any],
) -> list[dict[str, Any]]:
    builders = {
        "THRESHOLD": _build_threshold_expectations,
        "ROW_COUNT": _build_row_count_expectations,
        "REGEX": _build_regex_expectations,
        "RANGE": _build_range_expectations,
        "ALLOWLIST": _build_allowlist_expectations,
        "BLOCKLIST": _build_blocklist_expectations,
        "PLAUSIBLE": _build_plausible_expectations,
        "UNIQUENESS": _build_uniqueness_expectations,
        "REFERENTIAL_INTEGRITY": _build_referential_integrity_expectations,
        "FRESHNESS": _build_freshness_expectations,
        "LAG": _build_lag_expectations,
        "FUTURE_DATE": _build_future_date_expectations,
        "PRESENT": _build_present_expectations,
        "CORRECT": _build_correct_expectations,
        "RECONCILE": _build_reconcile_expectations,
        "TRANSFER_MATCH": _build_transfer_match_expectations,
        "JOIN_CONSISTENCY": _build_join_consistency_expectations,
    }
    builder = builders.get(check_type)
    if builder is None:
        raise GxExpectationBuildError(f"No GX expectation builder is registered for check type '{check_type}'")
    expectations = builder(params=params, meta=meta)
    if not expectations:
        raise GxExpectationBuildError(f"GX expectation builder produced no expectations for check type '{check_type}'")
    return expectations


def _require_text(params: Mapping[str, Any], key: str, *, check_type: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        raise GxExpectationBuildError(f"{check_type} check type requires '{key}'")
    return value


def _require_list(params: Mapping[str, Any], key: str, *, check_type: str) -> list[Any]:
    value = params.get(key)
    if not isinstance(value, list) or not value:
        raise GxExpectationBuildError(f"{check_type} check type requires a non-empty '{key}' list")
    return value


def _regex_expectation(*, column: str, regex: str, meta: Mapping[str, Any], negate: bool = False) -> dict[str, Any]:
    return {
        "expectation_type": (
            "expect_column_values_to_not_match_regex" if negate else "expect_column_values_to_match_regex"
        ),
        "kwargs": {"column": column, "regex": regex},
        "meta": dict(meta),
    }


def _in_set_expectation(
    *,
    column: str,
    values: list[Any],
    meta: Mapping[str, Any],
    negate: bool = False,
) -> dict[str, Any]:
    return {
        "expectation_type": (
            "expect_column_values_to_not_be_in_set" if negate else "expect_column_values_to_be_in_set"
        ),
        "kwargs": {"column": column, "value_set": list(values)},
        "meta": dict(meta),
    }


def _serialized_equals_row_condition(*, column: str, value: Any) -> dict[str, Any]:
    return {
        "type": "comparison",
        "column": {"name": column},
        "operator": "==",
        "parameter": value,
    }


def _require_threshold_ratio(*, params: Mapping[str, Any], metric: str) -> float:
    threshold = params.get("threshold")
    if threshold is None:
        raise GxExpectationBuildError(f"THRESHOLD {metric} requires 'threshold'")
    try:
        ratio = float(threshold) / 100.0
    except Exception as exc:
        raise GxExpectationBuildError(f"THRESHOLD {metric} requires numeric 'threshold'") from exc
    if ratio < 0.0 or ratio > 1.0:
        raise GxExpectationBuildError(f"THRESHOLD {metric} requires threshold percentage between 0 and 100")
    return ratio


def _require_non_negative_int(*, params: Mapping[str, Any], key: str, check_type: str) -> int:
    value = params.get(key)
    if value is None:
        raise GxExpectationBuildError(f"{check_type} check type requires '{key}'")
    try:
        number = float(value)
    except Exception as exc:
        raise GxExpectationBuildError(f"{check_type} check type requires numeric '{key}'") from exc
    if number < 0.0 or not number.is_integer():
        raise GxExpectationBuildError(f"{check_type} check type requires a non-negative whole-number '{key}'")
    return int(number)


def _threshold_ratio_bounds(*, operator: str, ratio: float, metric: str) -> dict[str, Any]:
    if operator == "gte":
        return {"min_value": ratio}
    if operator == "gt":
        return {"min_value": ratio, "strict_min": True}
    if operator == "lte":
        return {"max_value": ratio}
    if operator == "lt":
        return {"max_value": ratio, "strict_max": True}
    raise GxExpectationBuildError(
        f"THRESHOLD {metric} operator must be one of: gt, gte, lt, lte"
    )


def _normalize_regex_flags(flags: str, *, check_type: str) -> str:
    supported = {"i", "m", "s"}
    normalized = "".join(ch for ch in str(flags or "") if not ch.isspace())
    unsupported = [ch for ch in normalized if ch not in supported]
    if unsupported:
        raise GxExpectationBuildError(
            f"{check_type} check type only supports regex flags 'i', 'm', and 's' for GX auto-publish"
        )
    return normalized


def _compose_regex(pattern: str, *, flags: str = "", exact: bool = False) -> str:
    prefix = f"(?{flags})" if flags else ""
    body = pattern
    if exact:
        body = f"^(?:{pattern})$"
    return prefix + body


def _compose_literal_set_regex(values: list[Any], *, case_sensitive: bool) -> str:
    escaped = [re.escape(str(value)) for value in values]
    flags = "" if case_sensitive else "i"
    return _compose_regex("|".join(escaped), flags=flags, exact=True)


def _build_threshold_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    column = _require_text(params, "attribute", check_type="THRESHOLD")
    metric = str(params.get("metric") or "null_pct").strip().lower()
    operator = str(params.get("operator") or "gte").strip().lower()
    if metric == "null_pct":
        ratio = _require_threshold_ratio(params=params, metric=metric)
        return [
            {
                "expectation_type": "expect_column_proportion_of_non_null_values_to_be_between",
                "kwargs": {
                    "column": column,
                    **_threshold_ratio_bounds(operator=operator, ratio=ratio, metric=metric),
                },
                "meta": dict(meta),
            }
        ]
    if metric == "quantile":
        quantile_raw = params.get("quantile")
        if quantile_raw is None:
            raise GxExpectationBuildError("THRESHOLD quantile requires 'quantile'")
        try:
            quantile = float(quantile_raw)
        except Exception as exc:
            raise GxExpectationBuildError("THRESHOLD quantile requires numeric 'quantile'") from exc
        if quantile < 0.0 or quantile > 1.0:
            raise GxExpectationBuildError("THRESHOLD quantile requires 'quantile' between 0 and 1")
        if operator not in {"gte", "lte"}:
            raise GxExpectationBuildError("THRESHOLD quantile check type only supports operators gte and lte")

        threshold_value = params.get("threshold")
        if threshold_value is None:
            raise GxExpectationBuildError("THRESHOLD quantile requires 'threshold'")
        try:
            numeric_threshold = float(threshold_value)
        except Exception as exc:
            raise GxExpectationBuildError("THRESHOLD quantile requires numeric 'threshold'") from exc

        lower_bound: float | None = numeric_threshold if operator == "gte" else None
        upper_bound: float | None = numeric_threshold if operator == "lte" else None
        return [
            {
                "expectation_type": "expect_column_quantile_values_to_be_between",
                "kwargs": {
                    "column": column,
                    "quantile_ranges": {
                        "quantiles": [quantile],
                        "value_ranges": [[lower_bound, upper_bound]],
                    },
                    "allow_relative_error": False,
                },
                "meta": dict(meta),
            }
        ]
    raise GxExpectationBuildError(
        "THRESHOLD GX auto-publish currently supports only metrics 'null_pct' and 'quantile' because they have exact native GX aggregate mappings"
    )


def _build_row_count_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    operator = str(params.get("operator") or "gte").strip().lower()
    if operator == "between":
        min_value = _require_non_negative_int(params=params, key="minValue", check_type="ROW_COUNT")
        max_value = _require_non_negative_int(params=params, key="maxValue", check_type="ROW_COUNT")
        if max_value < min_value:
            raise GxExpectationBuildError("ROW_COUNT check type with operator 'between' requires maxValue >= minValue")
        kwargs: dict[str, Any] = {"min_value": min_value, "max_value": max_value}
    else:
        threshold = _require_non_negative_int(params=params, key="threshold", check_type="ROW_COUNT")
        if operator == "gte":
            kwargs = {"min_value": threshold}
        elif operator == "gt":
            kwargs = {"min_value": threshold + 1}
        elif operator == "lte":
            kwargs = {"max_value": threshold}
        elif operator == "lt":
            if threshold == 0:
                raise GxExpectationBuildError("ROW_COUNT check type cannot express operator 'lt' with threshold 0")
            kwargs = {"max_value": threshold - 1}
        else:
            raise GxExpectationBuildError("ROW_COUNT check type operator must be one of: gt, gte, lt, lte, between")

    return [
        {
            "expectation_type": "expect_table_row_count_to_be_between",
            "kwargs": kwargs,
            "meta": dict(meta),
        }
    ]


def _build_regex_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    column = _require_text(params, "attribute", check_type="REGEX")
    pattern = _require_text(params, "pattern", check_type="REGEX")
    flags = _normalize_regex_flags(str(params.get("flags") or ""), check_type="REGEX")
    return [_regex_expectation(column=column, regex=_compose_regex(pattern, flags=flags), meta=meta)]


def _build_range_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    column = _require_text(params, "attribute", check_type="RANGE")
    min_value = params.get("minValue")
    max_value = params.get("maxValue")
    if min_value is None and max_value is None:
        raise GxExpectationBuildError("RANGE check type requires at least one of 'minValue' or 'maxValue'")
    inclusive = bool(params.get("inclusive", True))
    kwargs: dict[str, Any] = {"column": column}
    if min_value is not None:
        kwargs["min_value"] = min_value
        if not inclusive:
            kwargs["strict_min"] = True
    if max_value is not None:
        kwargs["max_value"] = max_value
        if not inclusive:
            kwargs["strict_max"] = True
    return [{"expectation_type": "expect_column_values_to_be_between", "kwargs": kwargs, "meta": dict(meta)}]


def _build_allowlist_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    column = _require_text(params, "attribute", check_type="ALLOWLIST")
    values = _require_list(params, "allowedValues", check_type="ALLOWLIST")
    case_sensitive = bool(params.get("caseSensitive", False))
    if case_sensitive:
        return [_in_set_expectation(column=column, values=list(values), meta=meta)]
    return [_regex_expectation(column=column, regex=_compose_literal_set_regex(values, case_sensitive=False), meta=meta)]


def _build_blocklist_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    column = _require_text(params, "attribute", check_type="BLOCKLIST")
    values = _require_list(params, "blockedValues", check_type="BLOCKLIST")
    case_sensitive = bool(params.get("caseSensitive", False))
    if case_sensitive:
        return [_in_set_expectation(column=column, values=list(values), meta=meta, negate=True)]
    return [_regex_expectation(column=column, regex=_compose_literal_set_regex(values, case_sensitive=False), meta=meta, negate=True)]


def _build_plausible_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    attribute = _require_text(params, "attribute", check_type="PLAUSIBLE")
    context_attribute = _require_text(params, "contextAttribute", check_type="PLAUSIBLE")
    mode = str(params.get("mode") or "contextual_range").strip().lower()

    expectations: list[dict[str, Any]] = [
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": context_attribute},
            "meta": dict(meta),
        }
    ]

    if mode == "contextual_range":
        ranges = _require_list(params, "ranges", check_type="PLAUSIBLE")
        context_values: list[str] = []
        for item in ranges:
            if not isinstance(item, Mapping):
                raise GxExpectationBuildError("PLAUSIBLE contextual_range entries must be objects")
            context_value = _require_text(item, "contextValue", check_type="PLAUSIBLE")
            min_value = item.get("minValue")
            max_value = item.get("maxValue")
            if min_value is None and max_value is None:
                raise GxExpectationBuildError(
                    "PLAUSIBLE contextual_range entries require at least one of 'minValue' or 'maxValue'"
                )
            inclusive = bool(item.get("inclusive", True))
            if context_value not in context_values:
                context_values.append(context_value)
            kwargs: dict[str, Any] = {
                "column": attribute,
                "row_condition": _serialized_equals_row_condition(column=context_attribute, value=context_value),
            }
            if min_value is not None:
                kwargs["min_value"] = min_value
                if not inclusive:
                    kwargs["strict_min"] = True
            if max_value is not None:
                kwargs["max_value"] = max_value
                if not inclusive:
                    kwargs["strict_max"] = True
            expectations.append(
                {
                    "expectation_type": "expect_column_values_to_be_between",
                    "kwargs": kwargs,
                    "meta": dict(meta),
                }
            )

        expectations.insert(
            1,
            {
                "expectation_type": "expect_column_values_to_be_in_set",
                "kwargs": {"column": context_attribute, "value_set": context_values},
                "meta": dict(meta),
            },
        )
        return expectations

    if mode == "conditional_allowlist":
        allowlists = _require_list(params, "allowlists", check_type="PLAUSIBLE")
        context_values: list[str] = []
        for item in allowlists:
            if not isinstance(item, Mapping):
                raise GxExpectationBuildError("PLAUSIBLE conditional_allowlist entries must be objects")
            context_value = _require_text(item, "contextValue", check_type="PLAUSIBLE")
            allowed_values = _require_list(item, "allowedValues", check_type="PLAUSIBLE")
            case_sensitive = bool(item.get("caseSensitive", False))
            if context_value not in context_values:
                context_values.append(context_value)
            expectation_type = "expect_column_values_to_be_in_set_for_other_column_value"
            kwargs = {
                "column": attribute,
                "other_column": context_attribute,
                "other_value": context_value,
                "value_set": list(allowed_values),
                "case_sensitive": case_sensitive,
            }
            expectations.append(
                {
                    "expectation_type": expectation_type,
                    "kwargs": kwargs,
                    "meta": dict(meta),
                }
            )

        expectations.insert(
            1,
            {
                "expectation_type": "expect_column_values_to_be_in_set",
                "kwargs": {"column": context_attribute, "value_set": context_values},
                "meta": dict(meta),
            },
        )
        return expectations

    raise GxExpectationBuildError(
        "PLAUSIBLE mode must be one of: contextual_range, conditional_allowlist"
    )


def _build_uniqueness_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    columns = [str(value).strip() for value in _require_list(params, "attributes", check_type="UNIQUENESS") if str(value).strip()]
    if not columns:
        raise GxExpectationBuildError("UNIQUENESS check type requires at least one non-empty attribute")
    if len(columns) == 1:
        return [{"expectation_type": "expect_column_values_to_be_unique", "kwargs": {"column": columns[0]}, "meta": dict(meta)}]
    return [{
        "expectation_type": "expect_compound_columns_to_be_unique",
        "kwargs": {"column": columns[0], "columns": columns},
        "meta": dict(meta),
    }]


def _rhs_column(attribute: str) -> str:
    normalized = str(attribute or "").strip()
    if not normalized:
        raise GxExpectationBuildError("Cross-object GX expectations require a non-empty right-side attribute")
    return f"rhs.{normalized}"


def _comparison_expectation(
    *,
    left_column: str,
    right_column: str,
    mode: str,
    tolerance: Any | None,
    meta: Mapping[str, Any],
    check_type: str,
) -> dict[str, Any]:
    normalized_mode = str(mode or "exact").strip().lower()
    if normalized_mode == "exact":
        return {
            "expectation_type": "expect_column_pair_values_to_be_equal",
            "kwargs": {"column_A": left_column, "column_B": right_column, "ignore_row_if": "neither"},
            "meta": dict(meta),
        }
    if normalized_mode == "case_insensitive":
        return {
            "expectation_type": "expect_column_values_to_equal_other_column_case_insensitive",
            "kwargs": {"column": left_column, "other_column": right_column},
            "meta": dict(meta),
        }
    if normalized_mode == "numeric_tolerance":
        if tolerance is None:
            raise GxExpectationBuildError(
                f"{check_type} numeric_tolerance comparisons require 'tolerance'"
            )
        return {
            "expectation_type": "expect_column_values_to_be_within_numeric_tolerance_of_other_column",
            "kwargs": {"column": left_column, "other_column": right_column, "tolerance": float(tolerance)},
            "meta": dict(meta),
        }
    raise GxExpectationBuildError(
        f"{check_type} GX auto-publish does not support comparison mode '{mode}'"
    )


def _build_referential_integrity_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    _require_text(params, "attribute", check_type="REFERENTIAL_INTEGRITY")
    ref_attribute = _require_text(params, "refAttribute", check_type="REFERENTIAL_INTEGRITY")
    return [
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": _rhs_column(ref_attribute)},
            "meta": dict(meta),
        }
    ]


def _build_correct_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    comparison = params.get("comparison")
    if not isinstance(comparison, Mapping):
        raise GxExpectationBuildError("CORRECT check type requires 'comparison'")
    left_column = _require_text(comparison, "leftAttribute", check_type="CORRECT")
    right_column = _rhs_column(_require_text(comparison, "rightAttribute", check_type="CORRECT"))
    return [
        _comparison_expectation(
            left_column=left_column,
            right_column=right_column,
            mode=str(comparison.get("mode") or "exact"),
            tolerance=comparison.get("tolerance"),
            meta=meta,
            check_type="CORRECT",
        )
    ]


def _build_reconcile_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    comparisons = _require_list(params, "comparisons", check_type="RECONCILE")
    expectations: list[dict[str, Any]] = []
    for comparison in comparisons:
        if not isinstance(comparison, Mapping):
            raise GxExpectationBuildError("RECONCILE comparisons entries must be objects")
        expectations.append(
            _comparison_expectation(
                left_column=_require_text(comparison, "leftAttribute", check_type="RECONCILE"),
                right_column=_rhs_column(_require_text(comparison, "rightAttribute", check_type="RECONCILE")),
                mode=str(comparison.get("mode") or "exact"),
                tolerance=comparison.get("tolerance"),
                meta=meta,
                check_type="RECONCILE",
            )
        )
    return expectations


def _build_transfer_match_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    mode = str(params.get("mode") or "row_value_match").strip().lower()
    if mode == "row_value_match":
        comparisons = _require_list(params, "comparisons", check_type="TRANSFER_MATCH")
        expectations: list[dict[str, Any]] = []
        for comparison in comparisons:
            if not isinstance(comparison, Mapping):
                raise GxExpectationBuildError("TRANSFER_MATCH comparisons entries must be objects")
            expectations.append(
                _comparison_expectation(
                    left_column=_require_text(comparison, "leftAttribute", check_type="TRANSFER_MATCH"),
                    right_column=_rhs_column(_require_text(comparison, "rightAttribute", check_type="TRANSFER_MATCH")),
                    mode=str(comparison.get("mode") or "exact"),
                    tolerance=comparison.get("tolerance"),
                    meta=meta,
                    check_type="TRANSFER_MATCH",
                )
            )
        return expectations

    if mode == "payload_hash_match":
        left_hash = _require_text(params, "leftHashAttribute", check_type="TRANSFER_MATCH")
        right_hash = _rhs_column(_require_text(params, "rightHashAttribute", check_type="TRANSFER_MATCH"))
        return [
            {
                "expectation_type": "expect_column_pair_values_to_be_equal",
                "kwargs": {"column_A": left_hash, "column_B": right_hash, "ignore_row_if": "neither"},
                "meta": dict(meta),
            }
        ]

    raise GxExpectationBuildError(
        f"TRANSFER_MATCH GX auto-publish does not support mode '{mode}'"
    )


def _build_join_consistency_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    comparisons = _require_list(params, "comparisons", check_type="JOIN_CONSISTENCY")
    actuality_date = params.get("actualityDate")
    if not isinstance(actuality_date, Mapping):
        raise GxExpectationBuildError("JOIN_CONSISTENCY check type requires 'actualityDate'")

    expectations: list[dict[str, Any]] = []
    for comparison in comparisons:
        if not isinstance(comparison, Mapping):
            raise GxExpectationBuildError("JOIN_CONSISTENCY comparisons entries must be objects")
        expectations.append(
            _comparison_expectation(
                left_column=_require_text(comparison, "leftAttribute", check_type="JOIN_CONSISTENCY"),
                right_column=_rhs_column(_require_text(comparison, "rightAttribute", check_type="JOIN_CONSISTENCY")),
                mode=str(comparison.get("mode") or "exact"),
                tolerance=comparison.get("tolerance"),
                meta=meta,
                check_type="JOIN_CONSISTENCY",
            )
        )

    resolved_tolerance_value = actuality_date.get("resolvedToleranceValue")
    resolved_tolerance_unit = str(actuality_date.get("resolvedToleranceUnit") or "").strip().lower()
    if resolved_tolerance_value is None or not resolved_tolerance_unit:
        raise GxExpectationBuildError(
            "JOIN_CONSISTENCY actualityDate requires resolvedToleranceValue and resolvedToleranceUnit"
        )
    expectations.append(
        {
            "expectation_type": "expect_column_timestamps_to_be_within_tolerance_of_other_column",
            "kwargs": {
                "column": _require_text(actuality_date, "leftAttribute", check_type="JOIN_CONSISTENCY"),
                "other_column": _rhs_column(_require_text(actuality_date, "rightAttribute", check_type="JOIN_CONSISTENCY")),
                "max_difference": int(resolved_tolerance_value),
                "difference_unit": resolved_tolerance_unit,
            },
            "meta": dict(meta),
        }
    )
    return expectations


def _build_freshness_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    column = _require_text(params, "attribute", check_type="FRESHNESS")
    max_days_old = params.get("maxDaysOld")
    if max_days_old is None:
        raise GxExpectationBuildError("FRESHNESS check type requires 'maxDaysOld'")
    anchor = str(params.get("anchor") or "now").strip().lower()
    if anchor not in {"now"}:
        raise GxExpectationBuildError("FRESHNESS GX auto-publish currently only supports anchor='now'")
    return [{
        "expectation_type": "expect_column_values_to_be_within_past_days",
        "kwargs": {"column": column, "max_days_old": int(max_days_old), "anchor": anchor},
        "meta": dict(meta),
    }]


def _build_lag_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    start_column = _require_text(params, "startAttribute", check_type="LAG")
    end_column = _require_text(params, "endAttribute", check_type="LAG")
    max_hours = params.get("maxHours")
    if max_hours is None:
        raise GxExpectationBuildError("LAG check type requires 'maxHours'")
    return [{
        "expectation_type": "expect_column_pair_values_to_have_max_lag_hours",
        "kwargs": {"column": end_column, "start_column": start_column, "max_hours": int(max_hours)},
        "meta": dict(meta),
    }]


def _build_future_date_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    column = _require_text(params, "attribute", check_type="FUTURE_DATE")
    reference_time = str(params.get("referenceDate") or "").strip() or None
    kwargs: dict[str, Any] = {"column": column}
    if reference_time is not None:
        kwargs["reference_time"] = reference_time
    return [{
        "expectation_type": "expect_column_values_to_not_be_in_future",
        "kwargs": kwargs,
        "meta": dict(meta),
    }]


def _build_present_expectations(*, params: Mapping[str, Any], meta: Mapping[str, Any]) -> list[dict[str, Any]]:
    column = _require_text(params, "attribute", check_type="PRESENT")
    expectations: list[dict[str, Any]] = [
        {"expectation_type": "expect_column_values_to_not_be_null", "kwargs": {"column": column}, "meta": dict(meta)},
        _regex_expectation(column=column, regex=r"^\s*$", meta=meta, negate=True),
    ]
    blocked_values = [str(value).strip() for value in list(params.get("blockedValues") or []) if str(value).strip()]
    if blocked_values:
        case_sensitive = bool(params.get("caseSensitive", False))
        prefix = "" if case_sensitive else "i"
        blocked_pattern = "\\s*(?:" + "|".join(re.escape(value) for value in blocked_values) + ")\\s*"
        expectations.append(
            _regex_expectation(
                column=column,
                regex=_compose_regex(blocked_pattern, flags=prefix, exact=True),
                meta=meta,
                negate=True,
            )
        )
    return expectations