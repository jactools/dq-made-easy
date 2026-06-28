from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import compile_rule_payload
from runtime_lowerers import lower_rule_to_trino
from runtime_lowerers import normalize_engine_type
from runtime_lowerers import get_runtime_lowerer


def test_runtime_registry_treats_engine_types_as_first_class_values() -> None:
    assert normalize_engine_type("pyspark") == "spark_expectations"
    assert normalize_engine_type("sodacl") == "soda"
    assert normalize_engine_type("gx") == "gx"
    assert get_runtime_lowerer("gx") is not None
    assert get_runtime_lowerer("trino") is not None


def test_compile_rule_payload_supports_trino_engine() -> None:
    rule = {
        "id": 200,
        "table": "customers",
        "column": "customer_id",
        "type": "not_null",
        "params": {},
    }

    compiled = compile_rule_payload(rule, engine_type="trino")

    assert compiled["ok"] is True
    assert compiled["engine_type"] == "trino"
    assert compiled["lowered_rule"]["engine_type"] == "trino"
    assert compiled["lowered_rule"]["query"].startswith("SELECT")
    assert compiled["compiled_artifact"]["engine_target"] == "trino_sql"


def test_compile_rule_payload_returns_structured_failure_envelope_for_unsupported_construct() -> None:
    rule = {
        "id": 203,
        "table": "customers",
        "column": "amount",
        "type": "equals",
        "params": {"expression": "amount > 10"},
    }

    compiled = compile_rule_payload(rule, engine_type="trino")

    assert compiled["ok"] is False
    assert compiled["engine_type"] == "trino"
    assert compiled["engine_target"] == "trino_sql"
    assert compiled["failure_code"] == "DQ_LOWERER_UNSUPPORTED_CONSTRUCT"
    assert compiled["failed_check"]["check_name"] == "equals"
    assert compiled["failed_check"]["reason"] == "unsupported trino construct: custom expression"
    assert compiled["failure_metrics"]["failed_check_count"] == 1
    assert compiled["failure_metrics"]["failure_stage"] == "compile"
    assert compiled["metrics"] == compiled["failure_metrics"]
    assert compiled["observability_summary"] == compiled["failure_metrics"]
    assert compiled["trace"]["exception_type"] == "ValueError"


def test_lower_rule_to_trino_supports_basic_row_and_aggregate_checks() -> None:
    rule = {
        "id": 201,
        "table": "customers",
        "column": "customer_id",
        "type": "min",
        "params": {"min": 10},
    }

    lowered = lower_rule_to_trino(rule)

    assert lowered["engine_type"] == "trino"
    assert lowered["engine_target"] == "trino_sql"
    assert lowered["rule_type"] == "row_dq"
    assert lowered["expectation"] == "customer_id >= 10"
    assert lowered["query"].endswith("customer_id >= 10")


def test_lower_rule_to_trino_rejects_unsupported_constructs() -> None:
    rule = {
        "id": 202,
        "table": "customers",
        "column": "amount",
        "type": "equals",
        "params": {"expression": "amount > 10"},
    }

    with pytest.raises(ValueError, match="custom expression"):
        lower_rule_to_trino(rule)
