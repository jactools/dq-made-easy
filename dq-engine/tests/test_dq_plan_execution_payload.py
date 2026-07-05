"""Tests for dq_plan_execution_payload (Layer 3)."""

from __future__ import annotations

import pytest

from dq_plan_execution_payload import (
    coerce_int,
    coerce_str,
    normalize_execution_engine,
    parse_dispatch_payload,
)


class TestParseDispatchPayload:
    def test_valid_json_object(self) -> None:
        result = parse_dispatch_payload('{"run_id": "abc", "engine_type": "spark_expectations"}')
        assert result["run_id"] == "abc"

    def test_invalid_json(self) -> None:
        with pytest.raises(Exception) as exc_info:
            parse_dispatch_payload("not json")
        assert "not valid JSON" in str(exc_info.value)

    def test_json_array_rejected(self) -> None:
        with pytest.raises(Exception) as exc_info:
            parse_dispatch_payload('[1,2,3]')
        assert "must be a JSON object" in str(exc_info.value)


class TestCoerceStr:
    def test_first_truthy_key(self) -> None:
        payload = {"run_id": "abc", "queue_message_id": "xyz"}
        assert coerce_str(payload, "run_id", "queue_message_id") == "abc"

    def test_fallback_key(self) -> None:
        payload = {"run_id": "", "queue_message_id": "xyz"}
        assert coerce_str(payload, "run_id", "queue_message_id") == "xyz"

    def test_all_empty(self) -> None:
        payload = {"run_id": "", "other": ""}
        assert coerce_str(payload, "run_id", "other") == ""

    def test_missing_key(self) -> None:
        payload: dict = {}
        assert coerce_str(payload, "run_id") == ""


class TestCoerceInt:
    def test_positive_value(self) -> None:
        assert coerce_int({"suite_version": "42"}, "suite_version") == 42

    def test_integer_value(self) -> None:
        assert coerce_int({"suite_version": 42}, "suite_version") == 42

    def test_negative_returns_zero(self) -> None:
        assert coerce_int({"suite_version": "-1"}, "suite_version") == 0

    def test_zero_returns_zero(self) -> None:
        assert coerce_int({"suite_version": "0"}, "suite_version") == 0

    def test_invalid_returns_zero(self) -> None:
        assert coerce_int({"suite_version": "abc"}, "suite_version") == 0

    def test_missing_key(self) -> None:
        assert coerce_int({}, "suite_version") == 0


class TestNormalizeExecutionEngine:
    def test_canonical_unchanged(self) -> None:
        assert normalize_execution_engine("spark_expectations") == "spark_expectations"
        assert normalize_execution_engine("gx") == "gx"
        assert normalize_execution_engine("trino") == "trino"

    def test_aliases(self) -> None:
        assert normalize_execution_engine("great_expectations") == "gx"
        assert normalize_execution_engine("great-expectations") == "gx"
        assert normalize_execution_engine("pyspark_native") == "pyspark"
        assert normalize_execution_engine("spark") == "pyspark"

    def test_whitespace_and_case(self) -> None:
        assert normalize_execution_engine("  Spark_Expectations  ") == "spark_expectations"

    def test_none_and_empty(self) -> None:
        assert normalize_execution_engine(None) == ""
        assert normalize_execution_engine("") == ""
