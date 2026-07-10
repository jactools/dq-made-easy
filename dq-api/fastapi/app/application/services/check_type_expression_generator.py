"""DQ-4 check-type expression generator.

Converts structured :class:`RuleCheckTypeParams` into a compiler-ready filter
expression string.  The generated expression is stored in ``rules.expression``
alongside the originating ``check_type`` / ``check_type_params`` so the DQ-7
compiler can process it without knowing about the source check-type.

Each generator function is responsible for:
- Validating that required parameters are present.
- Raising :class:`ValueError` with a human-readable message when parameters
  are invalid (the endpoint converts this to HTTP 400).
- Returning a plain string that is valid according to
  :func:`~app.application.services.rule_expression.validate_filter_expression`.
"""
from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payload_dict(value: Any) -> dict[str, Any]:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    if isinstance(value, dict):
        return dict(value)
    raise ValueError("check_type_params must be a mapping-compatible payload")

def _quote_values(values: list[str], case_sensitive: bool) -> str:
    """Return a comma-separated SQL-style value list."""
    if case_sensitive:
        return ", ".join(f"'{v}'" for v in values)
    return ", ".join(f"'{v.lower()}'" for v in values)


def _quote_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value or "")
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return text
    return f"'{text.replace("'", "''")}'"


def _operator_symbol(op: str) -> str:
    mapping = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    sym = mapping.get(op)
    if sym is None:
        raise ValueError(f"Unknown operator '{op}'. Expected one of: gt, gte, lt, lte")
    return sym


def _build_simple_condition_clause(condition: dict[str, Any] | None) -> str | None:
    if not isinstance(condition, dict):
        return None

    attribute = str(condition.get("attribute") or "").strip()
    operator = str(condition.get("operator") or "equals").strip().lower()
    value = condition.get("value")
    if not attribute or value is None or str(value).strip() == "":
        raise ValueError("Conditional checks require condition.attribute and condition.value")
    if operator != "equals":
        raise ValueError("Conditional checks currently support only the 'equals' operator")
    return f"{attribute} = {_quote_literal(value)}"


def _apply_simple_condition(base_expression: str, params: dict[str, Any]) -> str:
    condition_clause = _build_simple_condition_clause(params.get("condition"))
    if not condition_clause:
        return base_expression
    return f"({condition_clause} AND ({base_expression})) OR NOT ({condition_clause})"


def _join_consistency_tolerance_unit(unit: str) -> str:
    mapping = {
        "minutes": "MINUTE",
        "hours": "HOUR",
        "days": "DAY",
    }
    normalized = mapping.get(str(unit or "").lower())
    if normalized is None:
        raise ValueError(
            "JOIN_CONSISTENCY actualityDate requires 'resolvedToleranceUnit' to be one of: "
            "minutes, hours, days"
        )
    return normalized


def _build_join_clauses(join_keys: list[dict[str, Any]], *, context_label: str) -> list[str]:
    join_clauses: list[str] = []
    for item in join_keys:
        left_attribute = str(item.get("leftAttribute") or "").strip()
        right_attribute = str(item.get("rightAttribute") or "").strip()
        if not left_attribute or not right_attribute:
            raise ValueError(
                f"{context_label} joinKeys entries require both 'leftAttribute' and 'rightAttribute'"
            )
        join_clauses.append(f"{left_attribute} = rhs.{right_attribute}")
    return join_clauses


def _build_cross_object_comparison_clause(
    item: dict[str, Any],
    *,
    context_label: str,
) -> str:
    left_attribute = str(item.get("leftAttribute") or "").strip()
    right_attribute = str(item.get("rightAttribute") or "").strip()
    mode = str(item.get("mode") or "exact").strip().lower()
    tolerance = item.get("tolerance")

    if not left_attribute or not right_attribute:
        raise ValueError(
            f"{context_label} comparison entries require both 'leftAttribute' and 'rightAttribute'"
        )
    if mode == "exact":
        return f"{left_attribute} = rhs.{right_attribute}"
    if mode == "case_insensitive":
        return f"LOWER({left_attribute}) = LOWER(rhs.{right_attribute})"
    if mode == "numeric_tolerance":
        if tolerance is None:
            raise ValueError(
                f"{context_label} numeric_tolerance comparisons require 'tolerance'"
            )
        return f"ABS({left_attribute} - rhs.{right_attribute}) <= {tolerance}"
    raise ValueError(
        f"{context_label} comparison mode must be one of: exact, case_insensitive, numeric_tolerance"
    )


def _build_actuality_date_tolerance_clause(
    actuality_date: dict[str, Any],
    *,
    context_label: str = "CROSS_OBJECT_ACTUALITY",
) -> str:
    """Build the actuality-date tolerance SQL clause for cross-object rules."""
    left_attr = str(actuality_date.get("leftAttribute") or "").strip()
    right_attr = str(actuality_date.get("rightAttribute") or "").strip()
    resolved_tolerance = actuality_date.get("resolvedToleranceValue")
    resolved_unit = actuality_date.get("resolvedToleranceUnit")

    if not left_attr or not right_attr:
        raise ValueError(
            f"{context_label} actualityDate requires 'leftAttribute' and 'rightAttribute'"
        )
    if resolved_tolerance is None:
        raise ValueError(
            f"{context_label} actualityDate requires 'resolvedToleranceValue'"
        )
    if resolved_unit is None:
        raise ValueError(
            f"{context_label} actualityDate requires 'resolvedToleranceUnit'"
        )

    tolerance_unit = _join_consistency_tolerance_unit(str(resolved_unit))
    return (
        f"ABS(TIMESTAMPDIFF({tolerance_unit}, {left_attr}, rhs.{right_attr})) <= {resolved_tolerance}"
    )


def _maybe_append_actuality_clause(
    clauses: list[str],
    params: dict[str, Any],
    *,
    context_label: str,
) -> None:
    """Append actuality-date clause to *clauses* when configured."""
    actuality_date = params.get("actualityDate")
    if not isinstance(actuality_date, dict) or not actuality_date:
        return
    if not actuality_date.get("resolvedToleranceValue"):
        return
    clauses.append(_build_actuality_date_tolerance_clause(
        actuality_date, context_label=context_label
    ))


# ---------------------------------------------------------------------------
# Per-check-type generators
# ---------------------------------------------------------------------------

def _generate_threshold(params: dict[str, Any]) -> str:
    """THRESHOLD — completeness percentage check.

    Generates an expression that can be read as:
    "the percentage of rows where ``attribute`` is NULL (or empty, or a
    placeholder) satisfies the given operator and threshold".

    Because the DQ-7 runtime evaluates the expression per-row the generated
    expression checks whether the *individual row* violates the constraint;
    the runtime aggregates row failures into a percentage.  The percentage
    comparison itself is expressed as a structured comment annotation that the
    runtime reads from the ``check_type_params`` field.

    For maximum DQ-7 compatibility the expression is a simple NULL / empty
    predicate that returns ``true`` for a *passing* row (i.e. the field IS
    populated).
    """
    attribute = str(params.get("attribute") or "").strip()
    if not attribute:
        raise ValueError("THRESHOLD check requires 'attribute'")

    metric = str(params.get("metric") or "null_pct")
    operator = str(params.get("operator") or "gt")
    threshold = params.get("threshold")
    if threshold is None:
        raise ValueError("THRESHOLD check requires 'threshold'")

    op_sym = _operator_symbol(operator)

    if metric == "null_pct":
        # passing row: field is NOT null
        return f"{attribute} IS NOT NULL"
    if metric == "empty_pct":
        # passing row: field is NOT NULL and not blank
        return f"{attribute} IS NOT NULL AND TRIM({attribute}) != ''"
    if metric == "default_val_pct":
        placeholder = str(params.get("expectedValue") or "N/A")
        return f"{attribute} IS NOT NULL AND {attribute} != '{placeholder}'"

    if metric == "quantile":
        quantile = params.get("quantile")
        if quantile is None:
            raise ValueError("THRESHOLD check requires 'quantile' when metric is 'quantile'")
        if operator not in {"gte", "lte"}:
            raise ValueError("THRESHOLD quantile check only supports operators gte and lte")
        try:
            quantile_value = float(quantile)
        except Exception as exc:
            raise ValueError("THRESHOLD quantile check requires numeric 'quantile'") from exc
        if quantile_value < 0.0 or quantile_value > 1.0:
            raise ValueError("THRESHOLD quantile check requires 'quantile' between 0 and 1")
        return "1 = 1"

    raise ValueError(
        f"Unknown THRESHOLD metric '{metric}'. "
        "Expected one of: null_pct, empty_pct, default_val_pct, quantile"
    )


def _generate_row_count(params: dict[str, Any]) -> str:
    operator = str(params.get("operator") or "gte").strip().lower()
    if operator == "between":
        if params.get("minValue") is None or params.get("maxValue") is None:
            raise ValueError("ROW_COUNT check requires 'minValue' and 'maxValue' when operator is 'between'")
    else:
        if params.get("threshold") is None:
            raise ValueError("ROW_COUNT check requires 'threshold'")
    return "1 = 1"


def _generate_regex(params: dict[str, Any]) -> str:
    attribute = str(params.get("attribute") or "").strip()
    pattern = str(params.get("pattern") or "").strip()
    if not attribute:
        raise ValueError("REGEX check requires 'attribute'")
    if not pattern:
        raise ValueError("REGEX check requires 'pattern'")
    flags = str(params.get("flags") or "")
    clauses: list[str] = []
    if bool(params.get("requirePresent", False)):
        clauses.extend([
            f"{attribute} IS NOT NULL",
            f"TRIM({attribute}) != ''",
        ])
    if flags:
        clauses.append(f"REGEXP_MATCHES({attribute}, '{pattern}', '{flags}')")
    else:
        clauses.append(f"REGEXP_MATCHES({attribute}, '{pattern}')")
    return _apply_simple_condition(" AND ".join(clauses), params)


def _generate_range(params: dict[str, Any]) -> str:
    attribute = str(params.get("attribute") or "").strip()
    if not attribute:
        raise ValueError("RANGE check requires 'attribute'")

    min_val = params.get("minValue")
    max_val = params.get("maxValue")
    if min_val is None and max_val is None:
        raise ValueError("RANGE check requires at least one of 'minValue' or 'maxValue'")

    inclusive = bool(params.get("inclusive", True))
    lo_op = ">=" if inclusive else ">"
    hi_op = "<=" if inclusive else "<"
    min_literal = _quote_literal(min_val) if min_val is not None else None
    max_literal = _quote_literal(max_val) if max_val is not None else None

    if min_val is not None and max_val is not None:
        return _apply_simple_condition(f"{attribute} {lo_op} {min_literal} AND {attribute} {hi_op} {max_literal}", params)
    if min_val is not None:
        return _apply_simple_condition(f"{attribute} {lo_op} {min_literal}", params)
    return _apply_simple_condition(f"{attribute} {hi_op} {max_literal}", params)


def _generate_allowlist(params: dict[str, Any]) -> str:
    attribute = str(params.get("attribute") or "").strip()
    values: list[str] = list(params.get("allowedValues") or [])
    if not attribute:
        raise ValueError("ALLOWLIST check requires 'attribute'")
    if not values:
        raise ValueError("ALLOWLIST check requires at least one 'allowedValues' entry")
    case_sensitive = bool(params.get("caseSensitive", False))
    lhs = attribute if case_sensitive else f"LOWER({attribute})"
    return _apply_simple_condition(f"{lhs} IN ({_quote_values(values, case_sensitive)})", params)


def _generate_blocklist(params: dict[str, Any]) -> str:
    attribute = str(params.get("attribute") or "").strip()
    values: list[str] = list(params.get("blockedValues") or [])
    if not attribute:
        raise ValueError("BLOCKLIST check requires 'attribute'")
    if not values:
        raise ValueError("BLOCKLIST check requires at least one 'blockedValues' entry")
    case_sensitive = bool(params.get("caseSensitive", False))
    lhs = attribute if case_sensitive else f"LOWER({attribute})"
    return f"{lhs} NOT IN ({_quote_values(values, case_sensitive)})"


def _generate_uniqueness(params: dict[str, Any]) -> str:
    attributes: list[str] = list(params.get("attributes") or [])
    if not attributes:
        raise ValueError("UNIQUENESS check requires at least one entry in 'attributes'")
    partition_key = ", ".join(attributes)
    return f"COUNT(*) OVER (PARTITION BY {partition_key}) = 1"


def _generate_referential_integrity(params: dict[str, Any]) -> str:
    attribute = str(params.get("attribute") or "").strip()
    ref_object = str(params.get("refDataObjectId") or "").strip()
    ref_version_id = str(params.get("refDataObjectVersionId") or "").strip()
    ref_attr = str(params.get("refAttribute") or "").strip()
    if not attribute:
        raise ValueError("REFERENTIAL_INTEGRITY check requires 'attribute'")
    if not ref_object:
        raise ValueError("REFERENTIAL_INTEGRITY check requires 'refDataObjectId'")
    if not ref_version_id:
        raise ValueError("REFERENTIAL_INTEGRITY check requires 'refDataObjectVersionId'")
    if not ref_attr:
        raise ValueError("REFERENTIAL_INTEGRITY check requires 'refAttribute'")
    return f"{attribute} IN (SELECT {ref_attr} FROM {ref_object})"


def _generate_freshness(params: dict[str, Any]) -> str:
    attribute = str(params.get("attribute") or "").strip()
    max_days = params.get("maxDaysOld")
    if not attribute:
        raise ValueError("FRESHNESS check requires 'attribute'")
    if max_days is None:
        raise ValueError("FRESHNESS check requires 'maxDaysOld'")
    anchor = str(params.get("anchor") or "now")
    ref = "NOW()" if anchor == "now" else "CURRENT_DATE"
    return _apply_simple_condition(f"DATEDIFF({ref}, {attribute}) <= {max_days}", params)


def _generate_lag(params: dict[str, Any]) -> str:
    start = str(params.get("startAttribute") or "").strip()
    end = str(params.get("endAttribute") or "").strip()
    max_hours = params.get("maxHours")
    if not start:
        raise ValueError("LAG check requires 'startAttribute'")
    if not end:
        raise ValueError("LAG check requires 'endAttribute'")
    if max_hours is None:
        raise ValueError("LAG check requires 'maxHours'")
    return f"TIMESTAMPDIFF(HOUR, {start}, {end}) <= {max_hours}"


def _generate_future_date(params: dict[str, Any]) -> str:
    attribute = str(params.get("attribute") or "").strip()
    if not attribute:
        raise ValueError("FUTURE_DATE check requires 'attribute'")
    ref_date = params.get("referenceDate")
    ref = f"'{ref_date}'" if ref_date else "NOW()"
    return f"{attribute} <= {ref}"


def _generate_present(params: dict[str, Any]) -> str:
    attribute = str(params.get("attribute") or "").strip()
    if not attribute:
        raise ValueError("PRESENT check requires 'attribute'")

    clauses = [
        f"{attribute} IS NOT NULL",
        f"TRIM({attribute}) != ''",
    ]
    blocked_values: list[str] = [str(value).strip() for value in list(params.get("blockedValues") or []) if str(value).strip()]
    if blocked_values:
        case_sensitive = bool(params.get("caseSensitive", False))
        lhs = f"TRIM({attribute})" if case_sensitive else f"LOWER(TRIM({attribute}))"
        clauses.append(f"{lhs} NOT IN ({_quote_values(blocked_values, case_sensitive)})")
    return _apply_simple_condition(" AND ".join(clauses), params)


def _generate_correct(params: dict[str, Any]) -> str:
    source_version = str(params.get("sourceDataObjectVersionId") or "").strip()
    reference_version = str(params.get("referenceDataObjectVersionId") or "").strip()
    join_keys: list[dict[str, Any]] = list(params.get("joinKeys") or [])
    comparison = params.get("comparison") or {}

    if not source_version:
        raise ValueError("CORRECT check requires 'sourceDataObjectVersionId'")
    if not reference_version:
        raise ValueError("CORRECT check requires 'referenceDataObjectVersionId'")
    if not join_keys:
        raise ValueError("CORRECT check requires at least one entry in 'joinKeys'")
    if not isinstance(comparison, dict):
        raise ValueError("CORRECT check requires 'comparison'")

    clauses: list[str] = []
    clauses.extend(_build_join_clauses(join_keys, context_label="CORRECT"))
    clauses.append(_build_cross_object_comparison_clause(comparison, context_label="CORRECT"))
    _maybe_append_actuality_clause(clauses, params, context_label="CORRECT")
    return " AND ".join(clauses)


def _generate_reconcile(params: dict[str, Any]) -> str:
    left_version = str(params.get("leftDataObjectVersionId") or "").strip()
    right_version = str(params.get("rightDataObjectVersionId") or "").strip()
    join_keys: list[dict[str, Any]] = list(params.get("joinKeys") or [])
    comparisons: list[dict[str, Any]] = list(params.get("comparisons") or [])

    if not left_version:
        raise ValueError("RECONCILE check requires 'leftDataObjectVersionId'")
    if not right_version:
        raise ValueError("RECONCILE check requires 'rightDataObjectVersionId'")
    if not join_keys:
        raise ValueError("RECONCILE check requires at least one entry in 'joinKeys'")
    if not comparisons:
        raise ValueError("RECONCILE check requires at least one entry in 'comparisons'")

    clauses: list[str] = []
    clauses.extend(_build_join_clauses(join_keys, context_label="RECONCILE"))
    clauses.extend(
        _build_cross_object_comparison_clause(item, context_label="RECONCILE")
        for item in comparisons
    )
    _maybe_append_actuality_clause(clauses, params, context_label="RECONCILE")
    return " AND ".join(clauses)


def _generate_plausible(params: dict[str, Any]) -> str:
    attribute = str(params.get("attribute") or "").strip()
    context_attribute = str(params.get("contextAttribute") or "").strip()
    mode = str(params.get("mode") or "contextual_range").strip().lower()

    if not attribute:
        raise ValueError("PLAUSIBLE check requires 'attribute'")
    if not context_attribute:
        raise ValueError("PLAUSIBLE check requires 'contextAttribute'")

    if mode == "contextual_range":
        ranges: list[dict[str, Any]] = list(params.get("ranges") or [])
        if not ranges:
            raise ValueError("PLAUSIBLE contextual_range mode requires at least one range entry")
        clauses: list[str] = []
        for item in ranges:
            context_value = str(item.get("contextValue") or "").strip()
            min_val = item.get("minValue")
            max_val = item.get("maxValue")
            inclusive = bool(item.get("inclusive", True))
            if not context_value:
                raise ValueError("PLAUSIBLE contextual_range entries require 'contextValue'")
            if min_val is None and max_val is None:
                raise ValueError(
                    "PLAUSIBLE contextual_range entries require at least one of 'minValue' or 'maxValue'"
                )
            lo_op = ">=" if inclusive else ">"
            hi_op = "<=" if inclusive else "<"
            range_clauses = [f"{context_attribute} = {_quote_literal(context_value)}"]
            if min_val is not None:
                range_clauses.append(f"{attribute} {lo_op} {min_val}")
            if max_val is not None:
                range_clauses.append(f"{attribute} {hi_op} {max_val}")
            clauses.append(f"({' AND '.join(range_clauses)})")
        return " OR ".join(clauses)

    if mode == "conditional_allowlist":
        allowlists: list[dict[str, Any]] = list(params.get("allowlists") or [])
        if not allowlists:
            raise ValueError("PLAUSIBLE conditional_allowlist mode requires at least one allowlist entry")
        clauses: list[str] = []
        for item in allowlists:
            context_value = str(item.get("contextValue") or "").strip()
            allowed_values: list[str] = list(item.get("allowedValues") or [])
            case_sensitive = bool(item.get("caseSensitive", False))
            if not context_value:
                raise ValueError("PLAUSIBLE conditional_allowlist entries require 'contextValue'")
            if not allowed_values:
                raise ValueError(
                    "PLAUSIBLE conditional_allowlist entries require at least one 'allowedValues' entry"
                )
            lhs = attribute if case_sensitive else f"LOWER({attribute})"
            clauses.append(
                "(" +
                f"{context_attribute} = {_quote_literal(context_value)} AND {lhs} IN ({_quote_values(allowed_values, case_sensitive)})" +
                ")"
            )
        return " OR ".join(clauses)

    raise ValueError(
        "PLAUSIBLE mode must be one of: contextual_range, conditional_allowlist"
    )


def _generate_transfer_match(params: dict[str, Any]) -> str:
    left_version = str(params.get("leftDataObjectVersionId") or "").strip()
    right_version = str(params.get("rightDataObjectVersionId") or "").strip()
    mode = str(params.get("mode") or "row_value_match").strip().lower()
    join_keys: list[dict[str, Any]] = list(params.get("joinKeys") or [])

    if not left_version:
        raise ValueError("TRANSFER_MATCH check requires 'leftDataObjectVersionId'")
    if not right_version:
        raise ValueError("TRANSFER_MATCH check requires 'rightDataObjectVersionId'")
    if not join_keys:
        raise ValueError("TRANSFER_MATCH check requires at least one entry in 'joinKeys'")

    clauses: list[str] = []
    clauses.extend(_build_join_clauses(join_keys, context_label="TRANSFER_MATCH"))
    if mode == "row_value_match":
        comparisons: list[dict[str, Any]] = list(params.get("comparisons") or [])
        if not comparisons:
            raise ValueError("TRANSFER_MATCH row_value_match mode requires at least one entry in 'comparisons'")
        clauses.extend(
            _build_cross_object_comparison_clause(item, context_label="TRANSFER_MATCH")
            for item in comparisons
        )
        _maybe_append_actuality_clause(clauses, params, context_label="TRANSFER_MATCH")
        return " AND ".join(clauses)

    if mode == "payload_hash_match":
        left_hash = str(params.get("leftHashAttribute") or "").strip()
        right_hash = str(params.get("rightHashAttribute") or "").strip()
        if not left_hash or not right_hash:
            raise ValueError(
                "TRANSFER_MATCH payload_hash_match mode requires both 'leftHashAttribute' and 'rightHashAttribute'"
            )
        clauses.append(f"{left_hash} = rhs.{right_hash}")
        _maybe_append_actuality_clause(clauses, params, context_label="TRANSFER_MATCH")
        return " AND ".join(clauses)

    raise ValueError("TRANSFER_MATCH mode must be one of: row_value_match, payload_hash_match")


def _generate_join_consistency(params: dict[str, Any]) -> str:
    left_version = str(params.get("leftDataObjectVersionId") or "").strip()
    right_version = str(params.get("rightDataObjectVersionId") or "").strip()
    join_keys: list[dict[str, Any]] = list(params.get("joinKeys") or [])
    comparisons: list[dict[str, Any]] = list(params.get("comparisons") or [])
    actuality_date = params.get("actualityDate") or {}

    if not left_version:
        raise ValueError("JOIN_CONSISTENCY check requires 'leftDataObjectVersionId'")
    if not right_version:
        raise ValueError("JOIN_CONSISTENCY check requires 'rightDataObjectVersionId'")
    if not join_keys:
        raise ValueError("JOIN_CONSISTENCY check requires at least one entry in 'joinKeys'")
    if not comparisons:
        raise ValueError("JOIN_CONSISTENCY check requires at least one entry in 'comparisons'")
    if not isinstance(actuality_date, dict):
        raise ValueError("JOIN_CONSISTENCY check requires 'actualityDate'")

    contract_id = str(actuality_date.get("contractId") or "").strip()
    left_actuality = str(actuality_date.get("leftAttribute") or "").strip()
    right_actuality = str(actuality_date.get("rightAttribute") or "").strip()
    resolved_tolerance = actuality_date.get("resolvedToleranceValue")
    resolved_unit = actuality_date.get("resolvedToleranceUnit")

    if not contract_id:
        raise ValueError("JOIN_CONSISTENCY actualityDate requires 'contractId'")
    if not left_actuality:
        raise ValueError("JOIN_CONSISTENCY actualityDate requires 'leftAttribute'")
    if not right_actuality:
        raise ValueError("JOIN_CONSISTENCY actualityDate requires 'rightAttribute'")
    if resolved_tolerance is None:
        raise ValueError(
            "JOIN_CONSISTENCY actualityDate requires 'resolvedToleranceValue' before expression generation"
        )
    if resolved_unit is None:
        raise ValueError(
            "JOIN_CONSISTENCY actualityDate requires 'resolvedToleranceUnit' before expression generation"
        )

    join_clauses: list[str] = []
    for item in join_keys:
        left_attribute = str(item.get("leftAttribute") or "").strip()
        right_attribute = str(item.get("rightAttribute") or "").strip()
        if not left_attribute or not right_attribute:
            raise ValueError(
                "JOIN_CONSISTENCY joinKeys entries require both 'leftAttribute' and 'rightAttribute'"
            )
        join_clauses.append(f"{left_attribute} = rhs.{right_attribute}")

    comparison_clauses: list[str] = []
    for item in comparisons:
        left_attribute = str(item.get("leftAttribute") or "").strip()
        right_attribute = str(item.get("rightAttribute") or "").strip()
        mode = str(item.get("mode") or "exact").strip().lower()
        if not left_attribute or not right_attribute:
            raise ValueError(
                "JOIN_CONSISTENCY comparisons entries require both 'leftAttribute' and 'rightAttribute'"
            )
        if mode == "exact":
            comparison_clauses.append(f"{left_attribute} = rhs.{right_attribute}")
            continue
        if mode == "case_insensitive":
            comparison_clauses.append(
                f"LOWER({left_attribute}) = LOWER(rhs.{right_attribute})"
            )
            continue
        raise ValueError(
            "JOIN_CONSISTENCY comparison mode must be one of: exact, case_insensitive"
        )

    tolerance_unit = _join_consistency_tolerance_unit(str(resolved_unit))
    tolerance_clause = (
        f"ABS(TIMESTAMPDIFF({tolerance_unit}, {left_actuality}, rhs.{right_actuality})) <= {resolved_tolerance}"
    )
    inner_predicates = join_clauses + comparison_clauses + [tolerance_clause]
    return " AND ".join(inner_predicates)


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

_GENERATORS = {
    "THRESHOLD":             _generate_threshold,
    "ROW_COUNT":             _generate_row_count,
    "REGEX":                 _generate_regex,
    "RANGE":                 _generate_range,
    "ALLOWLIST":             _generate_allowlist,
    "BLOCKLIST":             _generate_blocklist,
    "UNIQUENESS":            _generate_uniqueness,
    "REFERENTIAL_INTEGRITY": _generate_referential_integrity,
    "FRESHNESS":             _generate_freshness,
    "LAG":                   _generate_lag,
    "FUTURE_DATE":           _generate_future_date,
    "CORRECT":               _generate_correct,
    "PRESENT":               _generate_present,
    "RECONCILE":             _generate_reconcile,
    "PLAUSIBLE":             _generate_plausible,
    "TRANSFER_MATCH":        _generate_transfer_match,
    "JOIN_CONSISTENCY":      _generate_join_consistency,
}


def generate_expression_from_check_type(
    check_type: str,
    check_type_params: dict[str, Any],
    *,
    threshold_override: float | None = None,
) -> str:
    """Derive a compiler-ready filter expression from a structured check-type.

    Args:
        check_type: One of the :class:`~app.domain.entities.rule_check_type.RuleCheckType`
            string values (e.g. ``"THRESHOLD"``).
        check_type_params: Raw parameter dict (normally from the parsed request body).
        threshold_override: When provided and ``check_type`` is ``"THRESHOLD"``,
            this value replaces the ``threshold`` in ``check_type_params``,
            allowing a per-attribute threshold to override the rule-level default.

    Returns:
        A filter expression string that passes
        :func:`~app.application.services.rule_expression.validate_filter_expression`.

    Raises:
        ValueError: If ``check_type`` is unknown or required parameters are missing.
    """
    generator = _GENERATORS.get(str(check_type).upper())
    if generator is None:
        known = ", ".join(sorted(_GENERATORS))
        raise ValueError(
            f"Unknown checkType '{check_type}'. Known types: {known}"
        )
    effective_params = _payload_dict(check_type_params)
    if threshold_override is not None and str(check_type).upper() == "THRESHOLD":
        effective_params = {**check_type_params, "threshold": threshold_override}
    return generator(effective_params)
