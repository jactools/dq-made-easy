"""Trino adapter helpers for lowering canonical DQ rules to Trino SQL."""

from __future__ import annotations

import re
from datetime import date
from datetime import datetime
from datetime import time
from typing import Any

ROW_RULE_TYPES = {"not_null", "is_null", "equals", "not_equal", "between", "in", "not_in", "min", "max"}
AGGREGATE_RULE_TYPES = {"count", "sum", "avg", "min", "max", "distinct_count"}
QUERY_RULE_TYPES = {"query"}
_TRINO_SIMPLE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TRINO_COMPARISON_OPERATORS = {"=", "!=", "<>", ">", ">=", "<", "<="}
_TRINO_SET_OPERATORS = {"IN", "NOT IN"}


def escape_trino_identifier(identifier: str) -> str:
    """Return a Trino-safe identifier, quoting only when needed."""
    if not identifier:
        raise ValueError("Identifier cannot be empty")

    parts = identifier.split(".")
    escaped_parts: list[str] = []
    for part in parts:
        if not part:
            raise ValueError(f"Invalid Trino identifier: {identifier!r}")
        if _TRINO_SIMPLE_IDENTIFIER_PATTERN.fullmatch(part):
            escaped_parts.append(part)
        else:
            escaped_parts.append('"' + part.replace('"', '""') + '"')
    return ".".join(escaped_parts)


def format_trino_literal(value: Any, column_name: str | None = None) -> str:
    """Format a Python value as a Trino SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return f"'{value.isoformat()}'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return "'" + str(value).replace("'", "''") + "'"


def validate_trino_compatibility(rule: dict[str, Any]) -> list[str]:
    """Return a list of unsupported Trino constructs for a rule."""
    unsupported: list[str] = []
    rule_type = str(rule.get("type") or "").strip().lower()
    params = rule.get("params") or {}

    if params.get("expression") is not None:
        unsupported.append("custom expression")
    if params.get("sql_predicate") is not None:
        unsupported.append("SQL predicate")
    if params.get("window") is not None:
        unsupported.append("window/analytic functions")
    if isinstance(params.get("columns"), list) and len(params.get("columns")) > 1:
        unsupported.append("multi-column predicates")
    if rule_type not in ROW_RULE_TYPES and rule_type not in AGGREGATE_RULE_TYPES and rule_type not in QUERY_RULE_TYPES:
        unsupported.append(f"unsupported rule type: {rule_type}")

    return unsupported


def _raise_for_unsupported_trino_constructs(rule: dict[str, Any]) -> None:
    unsupported = validate_trino_compatibility(rule)
    if unsupported:
        raise ValueError(f"unsupported trino construct: {unsupported[0]}")


def _escape_rule_identifier(rule: dict[str, Any], key: str, default: str | None = None) -> str:
    value = str(rule.get(key) or default or "").strip()
    if not value:
        raise ValueError(f"Rule '{rule.get('id')}' requires '{key}'")
    return escape_trino_identifier(value)


def _normalize_filter_specs(filters: Any, clause_name: str) -> list[dict[str, Any]]:
    if filters is None:
        return []
    if isinstance(filters, dict):
        return [filters]
    if isinstance(filters, list) and all(isinstance(item, dict) for item in filters):
        return filters
    raise ValueError(f"Trino '{clause_name}' filters must be a dictionary or list of dictionaries")


def _format_filter_predicate(
    filter_spec: dict[str, Any],
    *,
    clause_name: str,
    default_left_operand: str | None = None,
) -> str:
    raw_operator = str(filter_spec.get("operator") or "=").strip().upper()
    operator = "!=" if raw_operator == "<>" else raw_operator

    if default_left_operand is None:
        column = str(filter_spec.get("column") or "").strip()
        if not column:
            raise ValueError(f"Trino '{clause_name}' filter requires 'column'")
        left_operand = escape_trino_identifier(column)
    else:
        left_operand = default_left_operand
        if filter_spec.get("column") is not None:
            raise ValueError(f"Trino '{clause_name}' filter cannot specify 'column'")

    if operator in _TRINO_COMPARISON_OPERATORS:
        if "value" not in filter_spec:
            raise ValueError(f"Trino '{clause_name}' filter requires 'value'")
        return f"{left_operand} {operator} {format_trino_literal(filter_spec['value'])}"

    if operator in _TRINO_SET_OPERATORS:
        values = filter_spec.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError(f"Trino '{clause_name}' filter requires non-empty 'values'")
        return f"{left_operand} {operator} ({', '.join(format_trino_literal(value) for value in values)})"

    if operator == "BETWEEN":
        if "min" not in filter_spec or "max" not in filter_spec:
            raise ValueError(f"Trino '{clause_name}' filter requires 'min' and 'max'")
        return f"{left_operand} BETWEEN {format_trino_literal(filter_spec['min'])} AND {format_trino_literal(filter_spec['max'])}"

    if operator == "IS NULL":
        return f"{left_operand} IS NULL"

    if operator == "IS NOT NULL":
        return f"{left_operand} IS NOT NULL"

    raise ValueError(f"Unsupported Trino '{clause_name}' filter operator: {raw_operator}")


def _format_where_clause(filters: Any) -> str:
    predicates = [
        _format_filter_predicate(filter_spec, clause_name="where")
        for filter_spec in _normalize_filter_specs(filters, "where")
    ]
    return f" WHERE {' AND '.join(predicates)}" if predicates else ""


def _combine_where_predicates(filters: Any, expectation: str) -> str:
    predicates = [
        _format_filter_predicate(filter_spec, clause_name="where")
        for filter_spec in _normalize_filter_specs(filters, "where")
    ]
    predicates.append(expectation)
    return " AND ".join(predicates)


def _format_having_clause(filters: Any, aggregate_expression: str) -> str:
    predicates = [
        _format_filter_predicate(
            filter_spec,
            clause_name="having",
            default_left_operand=aggregate_expression,
        )
        for filter_spec in _normalize_filter_specs(filters, "having")
    ]
    return f" HAVING {' AND '.join(predicates)}" if predicates else ""


def lower_row_rule_to_trino(rule: dict[str, Any]) -> dict[str, Any]:
    """Lower a row-level rule to Trino SQL."""
    _raise_for_unsupported_trino_constructs(rule)

    rule_type = str(rule.get("type") or "").strip().lower()
    column = _escape_rule_identifier(rule, "column")
    table = escape_trino_identifier(str(rule.get("table") or "source").strip() or "source")
    params = rule.get("params") or {}

    if rule_type == "min" and "min" not in params:
        raise ValueError(f"Rule '{rule.get('id')}' requires 'min' parameter")
    if rule_type == "max" and "max" not in params:
        raise ValueError(f"Rule '{rule.get('id')}' requires 'max' parameter")
    if rule_type in {"equals", "not_equal"} and "expected" not in params:
        raise ValueError(f"Rule '{rule.get('id')}' requires 'expected' parameter")
    if rule_type in {"in", "not_in"} and "values" not in params:
        raise ValueError(f"Rule '{rule.get('id')}' requires 'values' parameter")
    if rule_type == "between" and ("min" not in params or "max" not in params):
        raise ValueError(f"Rule '{rule.get('id')}' requires 'min' and 'max' parameters")

    if rule_type == "not_null":
        expectation = f"{column} IS NOT NULL"
    elif rule_type == "is_null":
        expectation = f"{column} IS NULL"
    elif rule_type == "equals":
        expectation = f"{column} = {format_trino_literal(params['expected'])}"
    elif rule_type == "not_equal":
        expectation = f"{column} != {format_trino_literal(params['expected'])}"
    elif rule_type == "between":
        expectation = f"{column} BETWEEN {format_trino_literal(params['min'])} AND {format_trino_literal(params['max'])}"
    elif rule_type == "in":
        expectation = f"{column} IN ({', '.join(format_trino_literal(value) for value in params['values'])})"
    elif rule_type == "not_in":
        expectation = f"{column} NOT IN ({', '.join(format_trino_literal(value) for value in params['values'])})"
    elif rule_type == "min":
        expectation = f"{column} >= {format_trino_literal(params['min'])}"
    elif rule_type == "max":
        expectation = f"{column} <= {format_trino_literal(params['max'])}"
    else:
        raise ValueError(f"Unsupported row rule type: {rule_type}")

    return {
        "engine_type": "trino",
        "engine_target": "trino_sql",
        "rule_type": "row_dq",
        "expectation": expectation,
        "action_if_failed": "quarantine",
        "query": f"SELECT * FROM {table} WHERE {_combine_where_predicates(params.get('where'), expectation)}",
    }


def lower_aggregate_rule_to_trino(rule: dict[str, Any]) -> dict[str, Any]:
    """Lower an aggregate rule to Trino SQL."""
    _raise_for_unsupported_trino_constructs(rule)

    rule_type = str(rule.get("type") or "").strip().lower()
    column = str(rule.get("column") or "").strip()
    table = escape_trino_identifier(str(rule.get("table") or "source").strip() or "source")
    params = rule.get("params") or {}

    if rule_type == "count":
        if "expected_count" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_count' parameter")
        aggregate_expression = "COUNT(*)"
        expectation = f"{aggregate_expression} = {format_trino_literal(params['expected_count'])}"
        result_alias = "dq_count"
    elif rule_type == "sum":
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
        escaped_column = escape_trino_identifier(column)
        aggregate_expression = f"SUM({escaped_column})"
        expectation = f"{aggregate_expression} = {format_trino_literal(params['expected_value'])}"
        result_alias = "dq_sum"
    elif rule_type == "avg":
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
        escaped_column = escape_trino_identifier(column)
        aggregate_expression = f"AVG({escaped_column})"
        expectation = f"{aggregate_expression} = {format_trino_literal(params['expected_value'])}"
        result_alias = "dq_avg"
    elif rule_type == "min":
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
        escaped_column = escape_trino_identifier(column)
        aggregate_expression = f"MIN({escaped_column})"
        expectation = f"{aggregate_expression} = {format_trino_literal(params['expected_value'])}"
        result_alias = "dq_min"
    elif rule_type == "max":
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
        escaped_column = escape_trino_identifier(column)
        aggregate_expression = f"MAX({escaped_column})"
        expectation = f"{aggregate_expression} = {format_trino_literal(params['expected_value'])}"
        result_alias = "dq_max"
    elif rule_type == "distinct_count":
        if "expected_count" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_count' parameter")
        escaped_column = escape_trino_identifier(column)
        aggregate_expression = f"COUNT(DISTINCT {escaped_column})"
        expectation = f"{aggregate_expression} = {format_trino_literal(params['expected_count'])}"
        result_alias = "dq_count"
    else:
        raise ValueError(f"Unsupported aggregate rule type: {rule_type}")

    query = (
        f"SELECT {aggregate_expression} AS {result_alias} FROM {table}"
        f"{_format_where_clause(params.get('where'))}"
        f"{_format_having_clause(params.get('having'), aggregate_expression)}"
    )

    return {
        "engine_type": "trino",
        "engine_target": "trino_sql",
        "rule_type": "aggregate_dq",
        "expectation": expectation,
        "action_if_failed": "quarantine",
        "query": query,
    }


def lower_query_rule_to_trino(rule: dict[str, Any]) -> dict[str, Any]:
    """Lower a query rule to Trino SQL."""
    _raise_for_unsupported_trino_constructs(rule)

    params = rule.get("params") or {}
    query_text = str(params.get("query") or "").strip()
    if not query_text:
        raise ValueError("Query DQ rule requires 'query' parameter")

    return {
        "engine_type": "trino",
        "engine_target": "trino_sql",
        "rule_type": "query_dq",
        "expectation": "query result count == expected_count",
        "action_if_failed": "quarantine",
        "params": params,
        "query": query_text,
    }
