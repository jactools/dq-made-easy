"""Tests for dq_plan_lowerers (Layer 2 — registry facade)."""

from __future__ import annotations

import pytest

from dq_plan_lowerers import (
    AGGREGATE_RULE_TYPES,
    ROW_RULE_TYPES,
    SUPPORTED_RUNTIME_CAPABILITIES,
    SUPPORTED_RUNTIME_ENGINES,
    _build_failure_metrics,
    _format_expectation_literal,
    _infer_rule_family,
    build_compiled_artifact_for_engine,
    build_failure_envelope,
    get_runtime_capabilities,
    get_runtime_lowerer,
    normalize_engine_type,
)


class TestNormalizeEngineType:
    def test_canonical_unchanged(self) -> None:
        assert normalize_engine_type("gx") == "gx"
        assert normalize_engine_type("trino") == "trino"
        assert normalize_engine_type("soda") == "soda"
        assert normalize_engine_type("spark_expectations") == "spark_expectations"

    def test_aliases(self) -> None:
        assert normalize_engine_type("great_expectations") == "gx"
        assert normalize_engine_type("great-expectations") == "gx"
        assert normalize_engine_type("pyspark_native") == "spark_expectations"
        assert normalize_engine_type("spark") == "spark_expectations"
        assert normalize_engine_type("sodacl") == "soda"

    def test_whitespace_and_case(self) -> None:
        assert normalize_engine_type("  Trino  ") == "trino"

    def test_none_and_empty(self) -> None:
        assert normalize_engine_type(None) == ""
        assert normalize_engine_type("") == ""


class TestInferRuleFamily:
    def test_row_rules(self) -> None:
        for rule_type in ROW_RULE_TYPES:
            assert _infer_rule_family(rule_type) == "row"

    def test_aggregate_rules(self) -> None:
        for rule_type in AGGREGATE_RULE_TYPES:
            assert _infer_rule_family(rule_type) == "aggregate"

    def test_query(self) -> None:
        assert _infer_rule_family("query") == "query"

    def test_unknown(self) -> None:
        assert _infer_rule_family("unknown_type") == "unknown"


class TestFormatExpectationLiteral:
    def test_string(self) -> None:
        assert _format_expectation_literal("hello") == "'hello'"

    def test_bool_true(self) -> None:
        assert _format_expectation_literal(True) == "TRUE"

    def test_bool_false(self) -> None:
        assert _format_expectation_literal(False) == "FALSE"

    def test_none(self) -> None:
        assert _format_expectation_literal(None) == "NULL"

    def test_number(self) -> None:
        assert _format_expectation_literal(42) == "42"


class TestSupportedRuntimeEngines:
    def test_expected_engines(self) -> None:
        assert "gx" in SUPPORTED_RUNTIME_ENGINES
        assert "trino" in SUPPORTED_RUNTIME_ENGINES
        assert "soda" in SUPPORTED_RUNTIME_ENGINES
        assert "spark_expectations" in SUPPORTED_RUNTIME_ENGINES

    def test_capabilities(self) -> None:
        assert "row_dq" in SUPPORTED_RUNTIME_CAPABILITIES["gx"]
        assert "expectation_dq" in SUPPORTED_RUNTIME_CAPABILITIES["gx"]
        assert "expectation_dq" not in SUPPORTED_RUNTIME_CAPABILITIES["trino"]


class TestGetRuntimeCapabilities:
    def test_valid_engine(self) -> None:
        caps = get_runtime_capabilities("gx")
        assert "row_dq" in caps
        assert "expectation_dq" in caps

    def test_unsupported_engine_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            get_runtime_capabilities("invalid_engine")


class TestBuildFailureEnvelope:
    def test_basic_envelope(self) -> None:
        rule = {"id": "r1", "type": "not_null", "table": "t", "column": "c"}
        envelope = build_failure_envelope(
            rule,
            engine_type="gx",
            failure_code="TEST_FAIL",
            failure_message="test failure",
        )
        assert envelope["ok"] is False
        assert envelope["failure_code"] == "TEST_FAIL"
        assert envelope["engine_type"] == "gx"

    def test_includes_trace_on_exception(self) -> None:
        rule = {"id": "r2", "type": "min", "table": "t", "column": "c"}
        try:
            raise ValueError("lowering failed")
        except ValueError as exc:
            envelope = build_failure_envelope(
                rule,
                engine_type="trino",
                failure_code="TEST",
                failure_message="test",
                exception=exc,
            )
        assert envelope["trace"]["exception_type"] == "ValueError"
        assert envelope["trace"]["message"] == "test"
        assert "lowering failed" in envelope["trace"]["traceback"]


class TestBuildFailureMetrics:
    def test_basic_metrics(self) -> None:
        metrics = _build_failure_metrics(
            rule={"id": "r1", "type": "not_null"},
            engine_type="gx",
            failure_stage="compile",
        )
        assert metrics["engine_type"] == "gx"
        assert metrics["rule_family"] == "row"
        assert metrics["failure_stage"] == "compile"


class TestBuildCompiledArtifact:
    def test_unsupported_engine_returns_failure_envelope(self) -> None:
        result = build_compiled_artifact_for_engine(
            {"id": "r1", "type": "not_null"},
            engine_type="invalid_engine",
        )
        assert result["ok"] is False
        assert result["failure_code"] == "DQ_UNSUPPORTED_RUNTIME_ENGINE"

    def test_soda_raises_returns_failure_envelope(self) -> None:
        result = build_compiled_artifact_for_engine(
            {"id": "r1", "type": "not_null"},
            engine_type="soda",
        )
        assert result["ok"] is False
        assert "NOT_IMPLEMENTED" in result["failure_code"] or "UNSUPPORTED" in result["failure_code"]
