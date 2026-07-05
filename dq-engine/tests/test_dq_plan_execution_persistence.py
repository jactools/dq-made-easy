"""Tests for dq_plan_execution_persistence (Layer 3.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dq_plan_execution_persistence import persist_execution_payload


class TestPersistExecutionPayload:
    def test_creates_execution_and_errors_files(self, tmp_path: Path) -> None:
        payload = {
            "engine_type": "spark_expectations",
            "rule_id": "r1",
            "failed_count": 2,
            "result": "failed",
            "failure_code": "TEST_FAIL",
            "failure_message": "test error",
            "failed_check": {"col": "x"},
            "failure_metrics": {"x": 1},
            "trace": {},
            "execution_metadata": {},
            "observability_summary": {},
            "error_management": {},
            "quarantine_artifact": {},
        }
        paths = persist_execution_payload(tmp_path, payload, artifact_prefix="test")
        assert len(paths) == 2
        execution_file = tmp_path / "test_execution.json"
        errors_file = tmp_path / "test_errors.json"
        assert execution_file.exists()
        assert errors_file.exists()

        exec_data = json.loads(execution_file.read_text())
        assert exec_data["rule_id"] == "r1"

        err_data = json.loads(errors_file.read_text())
        assert err_data["error_count"] == 2
        assert err_data["failure_code"] == "TEST_FAIL"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        payload = {"rule_id": "r1", "engine_type": "trino"}
        paths = persist_execution_payload(nested, payload, artifact_prefix="x")
        assert len(paths) == 2
        assert (nested / "x_execution.json").exists()
        assert (nested / "x_errors.json").exists()

    def test_default_error_fields(self) -> None:
        payload = {"rule_id": "r1", "engine_type": "gx"}
        paths = persist_execution_payload("/tmp", payload, artifact_prefix="t")
        # Just verify it runs without error with minimal payload
        assert len(paths) == 2
