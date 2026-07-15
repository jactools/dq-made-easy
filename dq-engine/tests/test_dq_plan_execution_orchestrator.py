"""Tests for dq_plan_execution_orchestrator (Layer 3) — report shaping and engine routing."""

from __future__ import annotations

from dq_plan_execution_orchestrator import (
    SUPPORTED_EXECUTION_ENGINES,
    build_execution_report_details,
    build_execution_report_summary,
    execute_engine_rule_payload,
    _result_status,
)


class TestSupportedEngines:
    def test_expected_engines(self) -> None:
        assert "spark_expectations" in SUPPORTED_EXECUTION_ENGINES
        assert "gx" in SUPPORTED_EXECUTION_ENGINES
        assert "trino" in SUPPORTED_EXECUTION_ENGINES
        assert "soda" in SUPPORTED_EXECUTION_ENGINES
        assert "sql" in SUPPORTED_EXECUTION_ENGINES
        assert "pyspark" in SUPPORTED_EXECUTION_ENGINES


class TestResultStatus:
    def test_explicit_result_status(self) -> None:
        assert _result_status({"result_status": "failed"}) == "failed"
        assert _result_status({"result_status": "Passed  "}) == "passed"

    def test_observability_summary_result(self) -> None:
        payload = {
            "observability_summary": {"result": "succeeded"},
        }
        assert _result_status(payload) == "succeeded"

    def test_result_string(self) -> None:
        assert _result_status({"result": "failed"}) == "failed"

    def test_result_dict_passed(self) -> None:
        assert _result_status({"result": {"passed": True}}) == "passed"

    def test_result_dict_failed(self) -> None:
        assert _result_status({"result": {"passed": False}}) == "failed"

    def test_ok_fallback(self) -> None:
        assert _result_status({"ok": True}) == "passed"
        assert _result_status({"ok": False}) == "failed"


class TestBuildExecutionReportSummary:
    def test_basic_summary(self) -> None:
        payload = {
            "engine_type": "spark_expectations",
            "rule_id": "r1",
            "ok": True,
            "passed_count": 3,
            "failed_count": 1,
        }
        summary = build_execution_report_summary(payload)
        assert summary["engine_type"] == "spark_expectations"
        assert summary["rule_id"] == "r1"
        assert summary["result"] == "passed"
        assert summary["passed_count"] == 3
        assert summary["failed_count"] == 1


class TestBuildExecutionReportDetails:
    def test_ok_payload_omits_failure_fields(self) -> None:
        payload = {"ok": True, "engine_type": "trino", "rule_id": "r2"}
        details = build_execution_report_details(payload)
        assert details["result"] == "passed"
        assert "failure_code" not in details

    def test_failed_payload_includes_failure_fields(self) -> None:
        payload = {
            "ok": False,
            "engine_type": "gx",
            "rule_id": "r3",
            "failure_code": "GX_FAIL",
            "failure_message": "bad",
            "failed_check": {"col": "x"},
            "failure_metrics": {"x": 1},
            "trace": {"tb": "..."},
        }
        details = build_execution_report_details(payload)
        assert details["result"] == "failed"
        assert details["failure_code"] == "GX_FAIL"
        assert details["failure_message"] == "bad"
        assert details["failed_check"] == {"col": "x"}


class TestExecuteEngineRulePayload:
    def test_unsupported_engine_returns_failure_envelope(self) -> None:
        result = execute_engine_rule_payload(
            engine_type="unknown_engine",
            rule_payload={"id": "x", "type": "not_null"},
        )
        assert result["ok"] is False
        assert result["failure_code"] == "DQ_EXECUTION_UNSUPPORTED_ENGINE"

    def test_not_implemented_engine_returns_failure_envelope(self) -> None:
        result = execute_engine_rule_payload(
            engine_type="soda",
            rule_payload={"id": "x", "type": "not_null"},
        )
        assert result["ok"] is False
        assert result["failure_code"] == "DQ_EXECUTION_NOT_IMPLEMENTED"
