"""Tests for dq_plan_execution (Layer 4 — facade re-exports).

Verifies every public symbol is importable from the facade.
"""

from __future__ import annotations

from dq_plan_execution import (
    SUPPORTED_EXECUTION_ENGINES,
    ExecutePayloadFn,
    ReportProgressFn,
    ReportRunFn,
    TokenProviderFactory,
    api_request,
    build_execution_progress,
    build_execution_report_details,
    build_execution_report_summary,
    build_token_provider,
    coerce_int,
    coerce_str,
    execute_engine_rule_payload,
    normalize_execution_engine,
    parse_dispatch_payload,
    process_engine_dispatch_message,
    report_execution_progress,
    report_run,
)


class TestFacadeReExports:
    def test_payload_helpers(self) -> None:
        assert callable(parse_dispatch_payload)
        assert callable(coerce_str)
        assert callable(coerce_int)
        assert callable(normalize_execution_engine)

    def test_api_helpers(self) -> None:
        assert callable(build_token_provider)
        assert callable(api_request)
        assert callable(report_run)
        assert callable(report_execution_progress)
        assert callable(build_execution_progress)

    def test_orchestrator_helpers(self) -> None:
        assert callable(execute_engine_rule_payload)
        assert callable(process_engine_dispatch_message)
        assert callable(build_execution_report_summary)
        assert callable(build_execution_report_details)
        assert "spark_expectations" in SUPPORTED_EXECUTION_ENGINES

    def test_type_aliases(self) -> None:
        # Just verify they exist; these are type aliases so we can't call them
        assert ReportRunFn is not None
        assert ReportProgressFn is not None
        assert TokenProviderFactory is not None
        assert ExecutePayloadFn is not None
