from __future__ import annotations

import sys
from pathlib import Path
from datetime import date
from datetime import datetime
from datetime import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trino_adapter import escape_trino_identifier
from trino_adapter import format_trino_literal
from trino_adapter import lower_aggregate_rule_to_trino
from trino_adapter import lower_query_rule_to_trino
from trino_adapter import lower_row_rule_to_trino
from trino_adapter import validate_trino_compatibility


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("customer_id", "customer_id"),
        ("sales.orders", "sales.orders"),
        ("order id", '"order id"'),
        ("customer.quoted name", 'customer."quoted name"'),
        ("contains\"quote", '"contains""quote"'),
    ],
)
def test_escape_trino_identifier_quotes_only_when_needed(identifier: str, expected: str) -> None:
    assert escape_trino_identifier(identifier) == expected


@pytest.mark.parametrize("identifier", ["", "catalog..table"])
def test_escape_trino_identifier_rejects_empty_parts(identifier: str) -> None:
    with pytest.raises(ValueError):
        escape_trino_identifier(identifier)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "NULL"),
        (True, "TRUE"),
        (False, "FALSE"),
        (3, "3"),
        (2.5, "2.5"),
        ("O'Reilly", "'O''Reilly'"),
    ],
)
def test_format_trino_literal_supports_common_python_values(value: object, expected: str) -> None:
    assert format_trino_literal(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 6, 30), "'2026-06-30'"),
        (time(12, 5, 3), "'12:05:03'"),
        (datetime(2026, 6, 30, 12, 5, 3), "'2026-06-30T12:05:03'"),
        ({"quoted": "O'Reilly"}, "'{''quoted'': \"O''Reilly\"}'"),
    ],
)
def test_format_trino_literal_supports_temporal_and_fallback_values(value: object, expected: str) -> None:
    assert format_trino_literal(value) == expected


@pytest.mark.parametrize(
    ("rule_type", "params", "expected_expectation"),
    [
        ("not_null", {}, "customer_id IS NOT NULL"),
        ("is_null", {}, "customer_id IS NULL"),
        ("equals", {"expected": "active"}, "status = 'active'"),
        ("not_equal", {"expected": "inactive"}, "status != 'inactive'"),
        ("between", {"min": 10, "max": 20}, "amount BETWEEN 10 AND 20"),
        ("in", {"values": ["a", "b"]}, "status IN ('a', 'b')"),
        ("not_in", {"values": ["a", "b"]}, "status NOT IN ('a', 'b')"),
        ("min", {"min": 5}, "amount >= 5"),
        ("max", {"max": 99}, "amount <= 99"),
    ],
)
def test_lower_row_rule_to_trino_generates_expected_sql(
    rule_type: str, params: dict[str, object], expected_expectation: str
) -> None:
    rule = {
        "id": 1,
        "table": "customers",
        "column": "customer_id" if rule_type in {"not_null", "is_null"} else "status" if rule_type in {"equals", "not_equal", "in", "not_in"} else "amount",
        "type": rule_type,
        "params": params,
    }

    lowered = lower_row_rule_to_trino(rule)

    assert lowered["engine_type"] == "trino"
    assert lowered["engine_target"] == "trino_sql"
    assert lowered["rule_type"] == "row_dq"
    assert lowered["expectation"] == expected_expectation
    assert lowered["query"] == f"SELECT * FROM customers WHERE {expected_expectation}"


@pytest.mark.parametrize(
    ("rule_type", "params", "expected_expectation", "expected_query"),
    [
        ("count", {"expected_count": 3}, "COUNT(*) = 3", "SELECT COUNT(*) AS dq_count FROM customers"),
        ("sum", {"expected_value": 10}, "SUM(amount) = 10", "SELECT SUM(amount) AS dq_sum FROM customers"),
        ("avg", {"expected_value": 2.5}, "AVG(amount) = 2.5", "SELECT AVG(amount) AS dq_avg FROM customers"),
        ("min", {"expected_value": 1}, "MIN(amount) = 1", "SELECT MIN(amount) AS dq_min FROM customers"),
        ("max", {"expected_value": 99}, "MAX(amount) = 99", "SELECT MAX(amount) AS dq_max FROM customers"),
        (
            "distinct_count",
            {"expected_count": 2},
            "COUNT(DISTINCT customer_id) = 2",
            "SELECT COUNT(DISTINCT customer_id) AS dq_count FROM customers",
        ),
    ],
)
def test_lower_aggregate_rule_to_trino_generates_expected_sql(
    rule_type: str, params: dict[str, object], expected_expectation: str, expected_query: str
) -> None:
    rule = {
        "id": 2,
        "table": "customers",
        "column": "amount" if rule_type != "distinct_count" and rule_type != "count" else "customer_id",
        "type": rule_type,
        "params": params,
    }

    lowered = lower_aggregate_rule_to_trino(rule)

    assert lowered["engine_type"] == "trino"
    assert lowered["engine_target"] == "trino_sql"
    assert lowered["rule_type"] == "aggregate_dq"
    assert lowered["expectation"] == expected_expectation
    assert lowered["query"] == expected_query


def test_lower_query_rule_to_trino_preserves_query_text() -> None:
    rule = {
        "id": 3,
        "type": "query",
        "params": {"query": "SELECT COUNT(*) FROM customers WHERE active = TRUE"},
    }

    lowered = lower_query_rule_to_trino(rule)

    assert lowered["engine_type"] == "trino"
    assert lowered["engine_target"] == "trino_sql"
    assert lowered["rule_type"] == "query_dq"
    assert lowered["query"] == "SELECT COUNT(*) FROM customers WHERE active = TRUE"


def test_validate_trino_compatibility_reports_unsupported_constructs() -> None:
    rule = {
        "id": 4,
        "type": "equals",
        "params": {
            "expression": "amount > 10",
            "sql_predicate": "amount > 10",
            "window": "row_number() over ()",
            "columns": ["amount", "status"],
        },
    }

    unsupported = validate_trino_compatibility(rule)

    assert unsupported == [
        "custom expression",
        "SQL predicate",
        "window/analytic functions",
        "multi-column predicates",
    ]


def test_validate_trino_compatibility_reports_unknown_rule_type() -> None:
    assert validate_trino_compatibility({"type": "window_count", "params": {}}) == [
        "unsupported rule type: window_count"
    ]


@pytest.mark.parametrize(
    ("rule_type", "params", "expected_message"),
    [
        ("min", {}, "requires 'min' parameter"),
        ("max", {}, "requires 'max' parameter"),
        ("equals", {}, "requires 'expected' parameter"),
        ("not_equal", {}, "requires 'expected' parameter"),
        ("in", {}, "requires 'values' parameter"),
        ("not_in", {}, "requires 'values' parameter"),
        ("between", {"min": 1}, "requires 'min' and 'max' parameters"),
    ],
)
def test_lower_row_rule_to_trino_rejects_missing_required_params(
    rule_type: str,
    params: dict[str, object],
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        lower_row_rule_to_trino(
            {"id": 10, "table": "customers", "column": "amount", "type": rule_type, "params": params}
        )


def test_lower_row_rule_to_trino_rejects_missing_column() -> None:
    with pytest.raises(ValueError, match="requires 'column'"):
        lower_row_rule_to_trino(
            {"id": 11, "table": "customers", "type": "not_null", "params": {}}
        )


@pytest.mark.parametrize(
    ("rule_type", "params", "expected_message"),
    [
        ("count", {}, "requires 'expected_count' parameter"),
        ("sum", {}, "requires 'expected_value' parameter"),
        ("avg", {}, "requires 'expected_value' parameter"),
        ("min", {}, "requires 'expected_value' parameter"),
        ("max", {}, "requires 'expected_value' parameter"),
        ("distinct_count", {}, "requires 'expected_count' parameter"),
    ],
)
def test_lower_aggregate_rule_to_trino_rejects_missing_required_params(
    rule_type: str,
    params: dict[str, object],
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        lower_aggregate_rule_to_trino(
            {"id": 12, "table": "customers", "column": "amount", "type": rule_type, "params": params}
        )


def test_lower_query_rule_to_trino_rejects_missing_query() -> None:
    with pytest.raises(ValueError, match="requires 'query' parameter"):
        lower_query_rule_to_trino({"id": 13, "type": "query", "params": {"query": "   "}})