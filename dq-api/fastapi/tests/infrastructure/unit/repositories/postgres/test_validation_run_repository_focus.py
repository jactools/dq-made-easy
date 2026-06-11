from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import app.infrastructure.repositories.postgres_validation_run_repository as run_mod
from app.infrastructure.repositories.postgres_validation_run_repository import (
    PostgresValidationRunRepository,
)


class _FakeRunRow:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeItemRow:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._values, list):
            return self._values
        return [self._values]


class _Session:
    def __init__(self, scalar_values=None, gets=None):
        self.scalar_values = list(scalar_values or [])
        self.gets = dict(gets or {})
        self.added = []
        self.flushed = False
        self.committed = False

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True

    def execute(self, _stmt):
        if self.scalar_values:
            return _ScalarResult(self.scalar_values.pop(0))
        return _ScalarResult([])

    def get(self, _model, key):
        return self.gets.get(key)


@contextmanager
def _scope(session):
    yield session


def test_save_run_writes_parent_and_items_and_returns_serialized(monkeypatch) -> None:
    run_id = "run-1"
    now = datetime(2026, 3, 27, tzinfo=UTC)

    fake_run = SimpleNamespace(
        id=run_id,
        workspace="default",
        triggered_by="u1",
        run_at=now,
        total=2,
        valid_count=1,
        invalid_count=1,
        status="completed",
    )
    fake_item = SimpleNamespace(
        id="item-1",
        run_id=run_id,
        rule_id="rule-1",
        rule_name="Rule 1",
        version_number=2,
        valid=False,
        errors=1,
        warnings=0,
        diagnostics=[{"message": "failed"}],
        conflicts=[],
    )
    session = _Session(
        scalar_values=[[fake_item]],
        gets={run_id: fake_run},
    )

    monkeypatch.setattr(run_mod, "uuid4", lambda: "uuid-1")
    monkeypatch.setattr(run_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresValidationRunRepository("postgresql://example")
    payload = asyncio.run(
        repo.save_run(
            run_id=run_id,
            workspace="default",
            triggered_by="u1",
            run_at=now.isoformat(),
            total=2,
            valid_count=1,
            invalid_count=1,
            status="completed",
            items=[
                {
                    "ruleId": "rule-1",
                    "ruleName": "Rule 1",
                    "ruleVersionNumber": 2,
                    "valid": False,
                    "errors": 1,
                    "warnings": 0,
                    "diagnostics": [{"message": "failed"}],
                    "conflicts": [],
                }
            ],
        )
    )

    assert session.flushed is True
    assert session.committed is True
    assert len(session.added) == 2
    assert payload.id == run_id
    assert payload.validation_items[0].rule_id == "rule-1"


def test_list_runs_filters_and_paginates(monkeypatch) -> None:
    now = datetime(2026, 3, 27, tzinfo=UTC)
    rows = [
        SimpleNamespace(
            id="r1",
            workspace="w1",
            triggered_by="u1",
            run_at=now,
            total=1,
            valid_count=1,
            invalid_count=0,
            status="completed",
        ),
        SimpleNamespace(
            id="r2",
            workspace="w1",
            triggered_by="u2",
            run_at=now,
            total=2,
            valid_count=1,
            invalid_count=1,
            status="failed",
        ),
    ]
    session = _Session(scalar_values=[rows, rows[:1]])
    monkeypatch.setattr(run_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresValidationRunRepository("postgresql://example")
    payload = asyncio.run(repo.list_runs(workspace="w1", limit=1, offset=0))

    assert payload.total == 2
    assert len(payload.data) == 1
    assert payload.data[0].id == "r1"


def test_get_run_returns_none_when_missing(monkeypatch) -> None:
    session = _Session(gets={})
    monkeypatch.setattr(run_mod, "session_scope", lambda _dsn: _scope(session))

    repo = PostgresValidationRunRepository("postgresql://example")
    assert asyncio.run(repo.get_run("missing")) is None
