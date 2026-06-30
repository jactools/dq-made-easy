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
        "query": f"SELECT * FROM {table} WHERE {expectation}",
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
        expectation = f"COUNT(*) = {format_trino_literal(params['expected_count'])}"
        query = f"SELECT COUNT(*) AS dq_count FROM {table}"
    elif rule_type == "sum":
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
        escaped_column = escape_trino_identifier(column)
        expectation = f"SUM({escaped_column}) = {format_trino_literal(params['expected_value'])}"
        query = f"SELECT SUM({escaped_column}) AS dq_sum FROM {table}"
    elif rule_type == "avg":
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
        escaped_column = escape_trino_identifier(column)
        expectation = f"AVG({escaped_column}) = {format_trino_literal(params['expected_value'])}"
        query = f"SELECT AVG({escaped_column}) AS dq_avg FROM {table}"
    elif rule_type == "min":
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
        escaped_column = escape_trino_identifier(column)
        expectation = f"MIN({escaped_column}) = {format_trino_literal(params['expected_value'])}"
        query = f"SELECT MIN({escaped_column}) AS dq_min FROM {table}"
    elif rule_type == "max":
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
        escaped_column = escape_trino_identifier(column)
        expectation = f"MAX({escaped_column}) = {format_trino_literal(params['expected_value'])}"
        query = f"SELECT MAX({escaped_column}) AS dq_max FROM {table}"
    elif rule_type == "distinct_count":
        if "expected_count" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_count' parameter")
        escaped_column = escape_trino_identifier(column)
        expectation = f"COUNT(DISTINCT {escaped_column}) = {format_trino_literal(params['expected_count'])}"
        query = f"SELECT COUNT(DISTINCT {escaped_column}) AS dq_count FROM {table}"
    else:
        raise ValueError(f"Unsupported aggregate rule type: {rule_type}")

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
        "query": query_text,
    }
