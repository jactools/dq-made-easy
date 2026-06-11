from __future__ import annotations
from datetime import datetime
import pytest

from app.domain.entities.profiling_request import ProfilingRequest
from app.infrastructure.repositories.postgres_profiling_repository import (
    PostgresProfilingRepository,
)


class _DummyRow:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _DummySession:
    def __init__(self, pre_get=None):
        self._pre_get = pre_get
        self.add_called_with = None
        self.committed = False

    def add(self, row):
        self.add_called_with = row

    def commit(self):
        self.committed = True

    def get(self, model, key):
        # return a copy of the pre_get row if provided, otherwise None
        return self._pre_get


class _DummyCM:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_create_request_uses_supplied_id(monkeypatch):
    sess = _DummySession()

    # patch the session_scope context manager to yield our dummy session
    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_profiling_repository.session_scope",
        lambda db: _DummyCM(sess),
    )

    # patch the ORM row class so we can inspect constructor args
    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_profiling_repository.DataSourceProfilingRequestRow",
        _DummyRow,
    )

    repo = PostgresProfilingRepository("sqlite://test")

    req = ProfilingRequest(
        id=None,
        profiling_request_id="given-id",
        data_source_id="ds1",
        requested_by_user_id="user1",
        requested_at=datetime(2020, 1, 1),
        started_at=None,
        completed_at=None,
        status="pending",
        error_message=None,
        job_id=None,
    )

    out = repo.create_request(req)

    assert out.profiling_request_id == "given-id"
    assert isinstance(sess.add_called_with, _DummyRow)
    assert sess.add_called_with.id == "given-id"
    assert sess.add_called_with.data_source_id == "ds1"
    assert sess.committed is True


def test_create_request_generates_id_when_empty(monkeypatch):
    sess = _DummySession()

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_profiling_repository.session_scope",
        lambda db: _DummyCM(sess),
    )
    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_profiling_repository.DataSourceProfilingRequestRow",
        _DummyRow,
    )

    repo = PostgresProfilingRepository("sqlite://test")

    req = ProfilingRequest(
        id=None,
        profiling_request_id="",
        data_source_id="ds2",
        requested_by_user_id="user2",
        requested_at=datetime(2020, 1, 2),
        started_at=None,
        completed_at=None,
        status="pending",
        error_message=None,
        job_id=None,
    )

    out = repo.create_request(req)

    assert out.profiling_request_id != ""
    assert sess.add_called_with.id == out.profiling_request_id


def test_set_started_updates_row(monkeypatch):
    row = _DummyRow(id="r1", status="pending", started_at=None, job_id=None)
    sess = _DummySession(pre_get=row)

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_profiling_repository.session_scope",
        lambda db: _DummyCM(sess),
    )

    repo = PostgresProfilingRepository("sqlite://test")
    repo.set_started("r1", "job-123")

    assert row.status == "started"
    assert row.job_id == "job-123"
    assert row.started_at is not None
    assert sess.committed is True


def test_set_started_missing_raises(monkeypatch):
    sess = _DummySession(pre_get=None)
    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_profiling_repository.session_scope",
        lambda db: _DummyCM(sess),
    )

    repo = PostgresProfilingRepository("sqlite://test")

    with pytest.raises(KeyError):
        repo.set_started("missing", "job-1")


def test_set_completed_success_and_failure(monkeypatch):
    # success path
    row_success = _DummyRow(id="s1", status="started", completed_at=None, error_message=None)
    sess_success = _DummySession(pre_get=row_success)
    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_profiling_repository.session_scope",
        lambda db: _DummyCM(sess_success),
    )
    repo = PostgresProfilingRepository("sqlite://test")
    repo.set_completed("s1", True)
    assert row_success.status == "completed"
    assert row_success.completed_at is not None

    # failure path with error message
    row_fail = _DummyRow(id="f1", status="started", completed_at=None, error_message=None)
    sess_fail = _DummySession(pre_get=row_fail)
    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_profiling_repository.session_scope",
        lambda db: _DummyCM(sess_fail),
    )
    repo.set_completed("f1", False, error_message="boom")
    assert row_fail.status == "failed"
    assert row_fail.error_message == "boom"
