from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import app.infrastructure.repositories.postgres_gx_execution_run_repository as gx_run_mod
from app.domain.entities.gx_execution_run import build_gx_execution_run_create_entity
from app.domain.entities.gx_execution_run import build_gx_execution_run_status_transition_entity
from app.infrastructure.repositories.postgres_gx_execution_run_repository import PostgresGxExecutionRunRepository


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _Session:
    def __init__(self, get_map=None, scalar_values=None):
        self.get_map = dict(get_map or {})
        self.scalar_values = list(scalar_values or [])
        self.added = []
        self.flushed = False
        self.committed = False

    def get(self, model, key):
        model_key = (getattr(model, "__name__", str(model)), str(key))
        if model_key in self.get_map:
            return self.get_map[model_key]
        if str(key) in self.get_map:
            return self.get_map[str(key)]
        for row in self.added:
            if getattr(row, "id", None) == key and row.__class__.__name__ == getattr(model, "__name__", ""):
                return row
        return None

    def execute(self, stmt):
        values = self.scalar_values.pop(0) if self.scalar_values else [row for row in self.added if row.__class__.__name__ == "GxExecutionRunStatusHistoryRow"]
        return _ScalarResult(values)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_create_run_persists_pending_record(monkeypatch):
    session = _Session()
    monkeypatch.setattr(gx_run_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresGxExecutionRunRepository("postgresql://example")
    out = asyncio.run(
        repo.create_run(
            build_gx_execution_run_create_entity(
                {
                    "run_id": "run-1",
                    "suite_id": "gx_suite_1",
                    "suite_version": 1,
                    "rule_id": "rule_1",
                    "rule_version_id": "rule_version_1",
                    "correlation_id": "corr-1",
                    "requested_by": "user-1",
                    "engine_type": "gx",
                    "engine_target": "pyspark",
                    "execution_shape": "single_object",
                    "status": "pending",
                    "submitted_at": "2026-04-06T12:00:00+00:00",
                    "execution_contract": {"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule_1", "ruleVersionId": "rule_version_1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 1}},
                    "handoff_payload": {"runId": "run-1", "engineType": "gx"},
                    "execution_progress": {"percent": 0, "label": "Queued for execution"},
                    "status_reason": "accepted",
                    "status_details": {"source": "gx.suite.run.start"},
                }
            )
        )
    )
    payload = out.model_dump()

    assert payload["id"] == "run-1"
    assert payload["status"] == "pending"
    assert payload["executionProgress"]["percent"] == 0
    assert payload["statusHistory"][0]["toStatus"] == "pending"
    assert len(session.added) == 2
    assert session.flushed is True
    assert session.committed is True


def test_get_run_maps_history_rows(monkeypatch):
    run_row = SimpleNamespace(
        id="run-2",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-2",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="running",
        submitted_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 4, 6, 12, 1, tzinfo=UTC),
        completed_at=None,
        execution_progress_json={"percent": 50, "label": "Halfway there"},
        execution_contract_json={"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule_1", "ruleVersionId": "rule_version_1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 1}},
        handoff_payload_json={"runId": "run-2", "engineType": "gx"},
        result_summary_json={"total": 1},
        diagnostics_json=[{"message": "ok"}],
        failure_code=None,
        failure_message=None,
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 6, 12, 1, tzinfo=UTC),
    )
    history1 = SimpleNamespace(
        id="hist-1",
        run_id="run-2",
        from_status=None,
        to_status="pending",
        changed_by="user-1",
        changed_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        reason="accepted",
        details={"source": "gx.suite.run.start"},
    )
    history2 = SimpleNamespace(
        id="hist-2",
        run_id="run-2",
        from_status="pending",
        to_status="running",
        changed_by="worker-1",
        changed_at=datetime(2026, 4, 6, 12, 1, tzinfo=UTC),
        reason="picked up",
        details={},
    )
    session = _Session(get_map={("GxExecutionRunRow", "run-2"): run_row}, scalar_values=[[history1, history2]])
    monkeypatch.setattr(gx_run_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresGxExecutionRunRepository("postgresql://example")
    out = asyncio.run(repo.get_run("run-2"))

    assert out is not None
    payload = out.model_dump()
    assert payload["status"] == "running"
    assert payload["executionProgress"]["percent"] == 50
    assert payload["statusHistory"][0]["toStatus"] == "pending"
    assert payload["statusHistory"][1]["toStatus"] == "running"


def test_record_run_status_transition_updates_progress_without_history(monkeypatch):
    run_row = SimpleNamespace(
        id="run-3",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-3",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="running",
        submitted_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 4, 6, 12, 1, tzinfo=UTC),
        completed_at=None,
        execution_progress_json=None,
        execution_contract_json={"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule_1", "ruleVersionId": "rule_version_1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 1}},
        handoff_payload_json={"runId": "run-3", "engineType": "gx"},
        result_summary_json={},
        diagnostics_json=[],
        failure_code=None,
        failure_message=None,
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 6, 12, 1, tzinfo=UTC),
    )
    session = _Session(get_map={("GxExecutionRunRow", "run-3"): run_row}, scalar_values=[])
    monkeypatch.setattr(gx_run_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresGxExecutionRunRepository("postgresql://example")
    out = asyncio.run(
        repo.record_run_status_transition(
            build_gx_execution_run_status_transition_entity(
                {
                    "run_id": "run-3",
                    "new_status": "running",
                    "changed_by": "worker-1",
                    "reason": "updated progress",
                    "execution_progress": {"percent": 75, "label": "Nearly done"},
                }
            )
        )
    )
    payload = out.model_dump()

    assert payload["status"] == "running"
    assert payload["executionProgress"]["percent"] == 75
    assert len(session.added) == 0


def test_record_run_status_transition_persists_metrics_json(monkeypatch):
    run_row = SimpleNamespace(
        id="run-3b",
        suite_id="gx_suite_1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-3b",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="running",
        submitted_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 4, 6, 12, 1, tzinfo=UTC),
        completed_at=None,
        execution_progress_json=None,
        execution_contract_json={"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule_1", "ruleVersionId": "rule_version_1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 1}},
        handoff_payload_json={"runId": "run-3b", "engineType": "gx"},
        result_summary_json={},
        metrics_json=None,
        diagnostics_json=[],
        failure_code=None,
        failure_message=None,
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 6, 12, 1, tzinfo=UTC),
    )
    session = _Session(get_map={("GxExecutionRunRow", "run-3b"): run_row}, scalar_values=[])
    monkeypatch.setattr(gx_run_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresGxExecutionRunRepository("postgresql://example")
    out = asyncio.run(
        repo.record_run_status_transition(
            build_gx_execution_run_status_transition_entity(
                {
                    "run_id": "run-3b",
                    "new_status": "succeeded",
                    "changed_by": "worker-1",
                    "reason": "completed",
                    "metrics": {"engine_type": "spark_expectations", "duration_ms": 42.5},
                }
            )
        )
    )

    assert out.metrics is not None
    assert out.metrics["engine_type"] == "spark_expectations"
    assert out.metrics["duration_ms"] == 42.5


def test_list_runs_normalizes_artifact_alias_queries_at_repository_boundary(monkeypatch):
    run_row = SimpleNamespace(
        id="run-4",
        suite_id="artifact-suite-1",
        suite_version=1,
        rule_id="rule_1",
        rule_version_id="rule_version_1",
        correlation_id="corr-4",
        requested_by="user-1",
        engine_type="gx",
        engine_target="pyspark",
        execution_shape="single_object",
        status="running",
        submitted_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        started_at=None,
        completed_at=None,
        execution_progress_json=None,
        execution_contract_json={"engineType": "gx", "engineTarget": "pyspark", "executionShape": "single_object", "traceability": {"ruleId": "rule_1", "ruleVersionId": "rule_version_1", "gxSuiteId": "artifact-suite-1", "gxSuiteVersion": 1}},
        handoff_payload_json=None,
        result_summary_json={},
        diagnostics_json=[],
        failure_code=None,
        failure_message=None,
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
    )
    session = _Session(scalar_values=[[run_row]])
    monkeypatch.setattr(gx_run_mod, "session_scope", lambda db_url: _Ctx(session))

    captured = {}
    original_builder = gx_run_mod.build_gx_execution_run_list_query_entity

    def _capture_builder(payload):
        captured["payload"] = payload
        return original_builder(payload)

    monkeypatch.setattr(gx_run_mod, "build_gx_execution_run_list_query_entity", _capture_builder)

    repo = PostgresGxExecutionRunRepository("postgresql://example")
    rows = asyncio.run(repo.list_runs({"artifact_id": "artifact-suite-1", "status": "running"}))

    assert captured["payload"] == {"artifact_id": "artifact-suite-1", "status": "running"}
    assert [item.id for item in rows] == ["run-4"]
