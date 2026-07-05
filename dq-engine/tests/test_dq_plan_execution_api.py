"""Tests for dq_plan_execution_api (Layer 3) — progress and reporting helpers."""

from __future__ import annotations

from dq_plan_execution_api import build_execution_progress


class TestBuildExecutionProgress:
    def test_zero_progress(self) -> None:
        result = build_execution_progress(completed_steps=0, total_steps=5, label="starting")
        assert result["percent"] == 0
        assert result["completed_steps"] == 0
        assert result["total_steps"] == 5
        assert result["label"] == "starting"
        assert result["source"] == "dq-engine-execution-worker"

    def test_full_progress(self) -> None:
        result = build_execution_progress(completed_steps=5, total_steps=5, label="done")
        assert result["percent"] == 100

    def test_mid_progress(self) -> None:
        result = build_execution_progress(completed_steps=1, total_steps=4, label="halfway")
        assert result["percent"] == 25

    def test_capped_at_100(self) -> None:
        result = build_execution_progress(completed_steps=10, total_steps=5, label="over")
        assert result["percent"] == 100

    def test_zero_total_avoids_division(self) -> None:
        result = build_execution_progress(completed_steps=1, total_steps=0, label="edge")
        assert result["percent"] == 0

    def test_custom_source(self) -> None:
        result = build_execution_progress(completed_steps=1, total_steps=2, label="x", source="custom")
        assert result["source"] == "custom"
