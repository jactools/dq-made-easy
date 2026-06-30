"""
Trino Adapter Module

Centralizes Trino-specific lowering logic and SQL generation.
"""

from __future__ import annotations

from typing import Any

from trino_config import load_trino_config, validate_trino_config

ROW_RULE_TYPES = {"not_null", "is_null", "equals", "not_equal", "between", "in", "not_in", "min", "max"}
AGGREGATE_RULE_TYPES = {"count", "sum", "avg", "min", "max", "distinct_count"}
QUERY_RULE_TYPES = {"query"}


def escape_trino_identifier(identifier: str) -> str:
    """
    Escape a Trino identifier using backticks.
    
    Trino identifiers are case-insensitive and should be quoted with backticks.
    
    Args:
        identifier: The identifier to escape
        
    Returns:
        Escaped identifier with backticks
    """
    if not identifier:
        raise ValueError("Identifier cannot be empty")
    
    # Trino uses backticks for identifiers
    return f"`{identifier}`"


def format_trino_literal(value: Any, column_name: str | None = None) -> str:
    """
    Format a value as a Trino literal.
    
    Args:
        value: The value to format
        column_name: Optional column name for context (e.g., for min/max)
        
    Returns:
        Formatted string literal for Trino
    """
    if value is None:
        return "NULL"
    
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    
    if isinstance(value, (int, float)):
        return str(value)
    
    if isinstance(value, str):
        # Escape single quotes in strings
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    
    # Try to convert to string
    return str(value)


def lower_row_rule_to_trino(rule: dict[str, Any]) -> dict[str, Any]:
    """
    Lower a row-level data quality rule to Trino SQL.
    
    Args:
        rule: The rule dictionary with type, column, table, and params
        
    Returns:
        Dictionary with Trino SQL query
    """
    rule_type = str(rule.get("type") or "").strip().lower()
    column = str(rule.get("column") or "").strip()
    table = str(rule.get("table") or "source").strip() or "source"
    params = rule.get("params") or {}
    
    # Validate parameters based on rule type
    if rule_type == "min":
        if "min" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'min' parameter")
    elif rule_type == "max":
        if "max" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'max' parameter")
    elif rule_type in ("equals", "not_equal"):
        if "expected" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected' parameter")
    elif rule_type in ("between", "in", "not_in"):
        if "values" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'values' parameter")
    
    # Build the expectation SQL
    if rule_type == "not_null":
        expectation = f"{column} IS NOT NULL"
    elif rule_type == "is_null":
        expectation = f"{column} IS NULL"
    elif rule_type == "equals":
        formatted_expected = format_trino_literal(params["expected"], column)
        expectation = f"{column} == {formatted_expected}"
    elif rule_type == "not_equal":
        formatted_expected = format_trino_literal(params["expected"], column)
        expectation = f"{column} != {formatted_expected}"
    elif rule_type == "between":
        min_val = format_trino_literal(params["min"], column)
        max_val = format_trino_literal(params["max"], column)
        expectation = f"{column} BETWEEN {min_val} AND {max_val}"
    elif rule_type == "in":
        values = params["values"]
        formatted_values = ", ".join(format_trino_literal(v, column) for v in values)
        expectation = f"{column} IN ({formatted_values})"
    elif rule_type == "not_in":
        values = params["values"]
        formatted_values = ", ".join(format_trino_literal(v, column) for v in values)
        expectation = f"{column} NOT IN ({formatted_values})"
    elif rule_type == "min":
        formatted_min = format_trino_literal(params["min"], column)
        expectation = f"{column} >= {formatted_min}"
    elif rule_type == "max":
        formatted_max = format_trino_literal(params["max"], column)
        expectation = f"{column} <= {formatted_max}"
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
    """
    Lower an aggregate data quality rule to Trino SQL.
    
    Args:
        rule: The rule dictionary with type and params
        
    Returns:
        Dictionary with Trino SQL query
    """
    rule_type = str(rule.get("type") or "").strip().lower()
    column = str(rule.get("column") or "")
    table = str(rule.get("table") or "source").strip() or "source"
    params = rule.get("params") or {}
    
    # Validate parameters based on rule type
    if rule_type == "count":
        if "expected_count" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_count' parameter")
    elif rule_type == "sum":
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
    elif rule_type in ("avg", "min", "max"):
        if "expected_value" not in params:
            raise ValueError(f"Rule '{rule.get('id')}' requires 'expected_value' parameter")
    
    # Build the expectation SQL
    if rule_type == "count":
        expected_count = params["expected_count"]
        formatted_expected = format_trino_literal(expected_count)
        expectation = f"COUNT(*) == {formatted_expected}"
        query = f"SELECT COUNT(*) AS dq_count FROM {table}"
    elif rule_type == "sum":
        expected_value = params["expected_value"]
        formatted_expected = format_trino_literal(expected_value)
        expectation = f"SUM({column}) == {formatted_expected}"
        query = f"SELECT SUM({column}) AS dq_sum FROM {table}"
    elif rule_type == "avg":
        expected_value = params["expected_value"]
        formatted_expected = format_trino_literal(expected_value)
        expectation = f"AVG({column}) == {formatted_expected}"
        query = f"SELECT AVG({column}) AS dq_avg FROM {table}"
    elif rule_type == "min":
        expected_value = params["expected_value"]
        formatted_expected = format_trino_literal(expected_value)
        expectation = f"MIN({column}) == {formatted_expected}"
        query = f"SELECT MIN({column}) AS dq_min FROM {table}"
    elif rule_type == "max":
        expected_value = params["expected_value"]
        formatted_expected = format_trino_literal(expected_value)
        expectation = f"MAX({column}) == {formatted_expected}"
        query = f"SELECT MAX({column}) AS dq_max FROM {table}"
    elif rule_type == "distinct_count":
        expected_count = params["expected_count"]
        formatted_expected = format_trino_literal(expected_count)
        expectation = f"COUNT(DISTINCT {column}) == {formatted_expected}"
        query = f"SELECT COUNT(DISTINCT {column}) AS dq_count FROM {table}"
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
    """
    Lower a query data quality rule to Trino SQL.
    
    Args:
        rule: The rule dictionary with params containing query
        
    Returns:
        Dictionary with Trino SQL query
    """
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


def validate_trino_compatibility(rule: dict[str, Any]) -> list[str]:
    """
    Validate that a rule is compatible with Trino.
    
    Args:
        rule: The rule dictionary to validate
        
    Returns:
        List of unsupported constructs (empty if compatible)
    """
    unsupported = []
    rule_type = str(rule.get("type") or "").strip().lower()
    params = rule.get("params") or {}
    
    # Check for unsupported constructs
    if params.get("expression") is not None:
        unsupported.append("custom expression in params")
    
    if params.get("sql_predicate") is not None:
        unsupported.append("SQL predicate in params")
    
    if params.get("window") is not None:
        unsupported.append("window/analytic functions")
    
    if isinstance(params.get("columns"), list) and len(params.get("columns")) > 1:
        unsupported.append("multi-column predicates")
    
    # Check for unsupported rule types
    if rule_type not in ROW_RULE_TYPES and rule_type not in AGGREGATE_RULE_TYPES and rule_type not in QUERY_RULE_TYPES:
        unsupported.append(f"unsupported rule type: {rule_type}")
    
    return unsupported
