from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.domain.entities import GxExecutionViolationCreateEntity
import app.infrastructure.repositories.postgres_gx_execution_violation_repository as gx_violation_mod
from app.infrastructure.repositories.postgres_gx_execution_violation_repository import PostgresGxExecutionViolationRepository


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
        self.committed = False

    def get(self, model, key):
        model_key = (getattr(model, "__name__", str(model)), tuple(key) if isinstance(key, (list, tuple)) else key)
        if model_key in self.get_map:
            return self.get_map[model_key]
        for row in self.added:
            row_key = getattr(row, "data_object_version_id", None), getattr(row, "id", None)
            if row.__class__.__name__ == getattr(model, "__name__", "") and row_key == model_key[1]:
                return row
        return None

    def execute(self, stmt):
        values = self.scalar_values.pop(0) if self.scalar_values else list(self.added)
        return _ScalarResult(values)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_save_violation_persists_scoped_row(monkeypatch):
    session = _Session()
    monkeypatch.setattr(gx_violation_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresGxExecutionViolationRepository("postgresql://example")
    out = asyncio.run(
        repo.save_violation(
            data_object_version_id="dov-1",
            execution_run_id="run-1",
            rule_id="rule_1",
            data_primary_key="row-1",
            violation_reason="value mismatch",
            ops_metadata={
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "rule_version_id": "rule_version_1",
                "correlation_id": "corr-1",
                "failure_class": "value_mismatch",
            },
            detected_at="2026-04-06T12:00:00+00:00",
        )
    )
    payload = out.model_dump()

    assert payload["dataObjectVersionId"] == "dov-1"
    assert payload["violationReason"] == "value mismatch"
    assert payload["dataPrimaryKey"] == "row-1"
    assert payload["opsMetadata"]["suite_id"] == "gx_suite_1"
    assert session.committed is True



def test_get_violation_rejects_wrong_scope(monkeypatch):
    row = SimpleNamespace(
        data_object_version_id="dov-1",
        id="vio-1",
        execution_run_id="run-1",
        rule_id="rule_1",
        data_primary_key="row-1",
        violation_reason="value mismatch",
        ops_metadata_json={
            "suite_id": "gx_suite_1",
            "suite_version": 1,
            "rule_version_id": "rule_version_1",
            "correlation_id": "corr-1",
            "failure_class": "value_mismatch",
        },
        detected_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 6, 12, 0, tzinfo=UTC),
    )
    session = _Session(get_map={("GxExecutionViolationRow", ("dov-1", "vio-1")): row})
    monkeypatch.setattr(gx_violation_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresGxExecutionViolationRepository("postgresql://example")

    assert asyncio.run(repo.get_violation("dov-1", "vio-1")) is not None
    assert asyncio.run(repo.get_violation("dov-2", "vio-1")) is None


def test_save_violations_persists_batch(monkeypatch):
    session = _Session()
    monkeypatch.setattr(gx_violation_mod, "session_scope", lambda db_url: _Ctx(session))

    repo = PostgresGxExecutionViolationRepository("postgresql://example")
    out = asyncio.run(
        repo.save_violations(
            [
                GxExecutionViolationCreateEntity(
                    id="gx-violation-fixed-1",
                    dataObjectVersionId="dov-1",
                    executionRunId="run-1",
                    ruleId="rule_1",
                    dataPrimaryKey="row-1",
                    violationReason="value mismatch",
                    opsMetadata={
                        "suite_id": "gx_suite_1",
                        "suite_version": 1,
                        "rule_version_id": "rule_version_1",
                        "correlation_id": "corr-1",
                        "failure_class": "value_mismatch",
                    },
                    detectedAt="2026-04-06T12:00:00+00:00",
                ),
                GxExecutionViolationCreateEntity(
                    id="gx-violation-fixed-2",
                    dataObjectVersionId="dov-1",
                    executionRunId="run-1",
                    ruleId="rule_1",
                    dataPrimaryKey="row-2",
                    violationReason="missing value",
                    opsMetadata={
                        "suite_id": "gx_suite_1",
                        "suite_version": 1,
                        "rule_version_id": "rule_version_1",
                        "correlation_id": "corr-1",
                    },
                    detectedAt="2026-04-06T12:01:00+00:00",
                ),
            ]
        )
    )
    payload = [row.model_dump() for row in out]

    assert [row["id"] for row in payload] == ["gx-violation-fixed-1", "gx-violation-fixed-2"]
    assert payload[0]["dataPrimaryKey"] == "row-1"
    assert payload[0]["opsMetadata"]["suite_id"] == "gx_suite_1"
    assert session.committed is True
