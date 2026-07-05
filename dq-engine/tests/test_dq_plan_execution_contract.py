"""Tests for dq_plan_execution_contract (Layer 1)."""

from __future__ import annotations

import pytest

from dq_plan_execution_contract import (
    build_execution_metadata,
    build_observability_summary,
)


class TestBuildExecutionMetadata:
    def test_basic(self) -> None:
        meta = build_execution_metadata(
            rule_id="r1",
            engine_type="spark_expectations",
            runtime="pyspark",
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
            duration_ms=1234.567,
            source_row_count=1000,
            execution_name="test",
        )
        assert meta["rule_id"] == "r1"
        assert meta["duration_ms"] == 1234.567
        assert meta["guardrails"] == {}

    def test_guardrails(self) -> None:
        meta = build_execution_metadata(
            rule_id="r1",
            engine_type="gx",
            runtime="pyspark",
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
            duration_ms=100,
            source_row_count=10,
            execution_name="test",
            guardrails={"max_rows": 100},
        )
        assert meta["guardrails"] == {"max_rows": 100}


class TestBuildObservabilitySummary:
    def test_basic(self) -> None:
        obs = build_observability_summary(
            engine_type="trino",
            result="succeeded",
            passed_count=5,
            failed_count=0,
            rule_family="row",
            duration_ms=500.0,
            storage_kind="s3",
            storage_uri="s3://bucket/out",
        )
        assert obs["engine_type"] == "trino"
        assert obs["result"] == "succeeded"
        assert obs["passed_count"] == 5
