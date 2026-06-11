from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.infrastructure.repositories.postgres_exception_reason_analytics_projection_repository import (
    PostgresExceptionReasonAnalyticsProjectionRepository,
    _parse_iso_datetime,
)


class _FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self, existing: object | None = None, rows: list[object] | None = None) -> None:
        self.existing = existing
        self.rows = rows or []
        self.added: list[object] = []
        self.committed = False
        self.get_calls: list[tuple[object, str]] = []
        self.executed_queries: list[object] = []

    def get(self, model: object, row_id: str) -> object | None:
        self.get_calls.append((model, row_id))
        return self.existing

    def add(self, row: object) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.committed = True

    def execute(self, query: object) -> _FakeExecuteResult:
        self.executed_queries.append(query)
        return _FakeExecuteResult(self.rows)


def _install_session_scope(monkeypatch: pytest.MonkeyPatch, session: _FakeSession, seen: dict[str, str | None]) -> None:
    class _SessionScope:
        def __enter__(self) -> _FakeSession:
            return session

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def _session_scope(database_url: str) -> _SessionScope:
        seen["database_url"] = database_url
        return _SessionScope()

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_exception_reason_analytics_projection_repository.session_scope",
        _session_scope,
    )


def test_parse_iso_datetime_handles_missing_and_blank_values() -> None:
    none_value = _parse_iso_datetime(None)
    blank_value = _parse_iso_datetime("   ")

    assert none_value.tzinfo == UTC
    assert blank_value.tzinfo == UTC


def test_parse_iso_datetime_converts_timezone_aware_values_to_utc() -> None:
    parsed = _parse_iso_datetime("2024-05-01T10:11:12+02:00")

    assert parsed.tzinfo == UTC
    assert parsed.isoformat() == "2024-05-01T08:11:12+00:00"


@pytest.mark.anyio
async def test_persist_exception_records_returns_zero_for_empty_projection_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresExceptionReasonAnalyticsProjectionRepository("postgresql://example")

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_exception_reason_analytics_projection_repository.build_reason_analytics_projection_rows",
        lambda exception_records: [],
    )

    persisted = await repository.persist_exception_records([SimpleNamespace(id="record-1")])

    assert persisted == 0


@pytest.mark.anyio
async def test_persist_exception_records_inserts_new_rows_and_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresExceptionReasonAnalyticsProjectionRepository("postgresql://example")
    session = _FakeSession()
    seen: dict[str, str | None] = {"database_url": None}

    projection_rows = [
        {
            "id": "reason-1",
            "bucket_start": "2024-05-01T10:11:12",
            "engine_type": "gx",
            "delivery_id": "delivery-1",
            "execution_plan_id": "plan-1",
            "execution_plan_version_id": "plan-version-1",
            "suite_id": "suite-1",
            "data_object_version_id": "dov-1",
            "rule_id": "rule-1",
            "rule_version_id": "rule-version-1",
            "reason_code": "DQ1_EMPTY_EXPRESSION",
            "reason_text_snapshot": "Empty expression",
            "failed_record_count": 2,
            "distinct_record_identifier_count": 1,
            "distinct_execution_run_count": 1,
            "record_identifier_values": ["record-1", "record-2"],
            "execution_run_ids": ["run-1"],
        }
    ]

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_exception_reason_analytics_projection_repository.build_reason_analytics_projection_rows",
        lambda exception_records: projection_rows,
    )
    _install_session_scope(monkeypatch, session, seen)

    persisted = await repository.persist_exception_records([SimpleNamespace(id="record-1")])

    assert seen["database_url"] == "postgresql://example"
    assert persisted == 1
    assert session.committed is True
    assert len(session.added) == 1

    inserted = session.added[0]
    assert inserted.id == "reason-1"
    assert inserted.bucket_start.tzinfo == UTC
    assert inserted.bucket_start.isoformat() == "2024-05-01T10:11:12+00:00"
    assert inserted.failed_record_count == 2
    assert inserted.distinct_record_identifier_count == 1
    assert inserted.distinct_execution_run_count == 1
    assert inserted.record_identifier_values_json == ["record-1", "record-2"]
    assert inserted.execution_run_ids_json == ["run-1"]


@pytest.mark.anyio
async def test_persist_exception_records_updates_existing_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresExceptionReasonAnalyticsProjectionRepository("postgresql://example")
    existing = SimpleNamespace(
        record_identifier_values_json=["record-1", "record-1", "record-2"],
        execution_run_ids_json=["run-1"],
        failed_record_count=4,
        distinct_record_identifier_count=2,
        distinct_execution_run_count=1,
        updated_at=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    )
    session = _FakeSession(existing=existing)
    seen: dict[str, str | None] = {"database_url": None}

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_exception_reason_analytics_projection_repository.build_reason_analytics_projection_rows",
        lambda exception_records: [
            {
                "id": "reason-1",
                "bucket_start": "2024-05-01T10:11:12+00:00",
                "engine_type": "gx",
                "delivery_id": None,
                "execution_plan_id": None,
                "execution_plan_version_id": None,
                "suite_id": None,
                "data_object_version_id": "dov-1",
                "rule_id": "rule-1",
                "rule_version_id": None,
                "reason_code": "DQ1_EMPTY_EXPRESSION",
                "reason_text_snapshot": "Empty expression",
                "failed_record_count": 3,
                "distinct_record_identifier_count": 1,
                "distinct_execution_run_count": 1,
                "record_identifier_values": ["record-2", "record-3", "record-3"],
                "execution_run_ids": ["run-1", "run-2"],
            }
        ],
    )
    _install_session_scope(monkeypatch, session, seen)

    persisted = await repository.persist_exception_records([SimpleNamespace(id="record-1")])

    assert persisted == 1
    assert session.added == []
    assert session.committed is True
    assert existing.failed_record_count == 7
    assert existing.record_identifier_values_json == ["record-1", "record-2", "record-3"]
    assert existing.execution_run_ids_json == ["run-1", "run-2"]
    assert existing.distinct_record_identifier_count == 3
    assert existing.distinct_execution_run_count == 2
    assert existing.updated_at > datetime(2024, 1, 1, 0, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_summarize_reason_analytics_reads_rows_and_forwards_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = PostgresExceptionReasonAnalyticsProjectionRepository("postgresql://example")
    session = _FakeSession(
        rows=[
            SimpleNamespace(
                id="reason-1",
                bucket_start=datetime(2024, 5, 1, 10, 0),
                engine_type="gx",
                delivery_id="delivery-1",
                execution_plan_id="plan-1",
                execution_plan_version_id="plan-version-1",
                suite_id="suite-1",
                data_object_version_id="dov-1",
                rule_id="rule-1",
                rule_version_id=None,
                reason_code="DQ1_EMPTY_EXPRESSION",
                reason_text_snapshot="Empty expression",
                failed_record_count=2,
                distinct_record_identifier_count=1,
                distinct_execution_run_count=1,
                record_identifier_values_json=["record-1"],
                execution_run_ids_json=["run-1"],
                created_at=datetime(2024, 5, 1, 10, 0),
                updated_at=datetime(2024, 5, 1, 10, 0),
            )
        ]
    )
    seen: dict[str, str | None] = {"database_url": None}
    captured: dict[str, object] = {}

    def _summarize_reason_analytics_projection_rows(rows: list[dict[str, object]], **kwargs: object) -> SimpleNamespace:
        captured["rows"] = rows
        captured["kwargs"] = kwargs
        return SimpleNamespace(summary="ok")

    monkeypatch.setattr(
        "app.infrastructure.repositories.postgres_exception_reason_analytics_projection_repository.summarize_reason_analytics_projection_rows",
        _summarize_reason_analytics_projection_rows,
    )
    _install_session_scope(monkeypatch, session, seen)

    summary = await repository.summarize_reason_analytics(
        data_object_version_ids=["dov-1"],
        execution_run_ids=["run-1"],
        reason_codes=["DQ1_EMPTY_EXPRESSION"],
        detected_after="2024-05-01T00:00:00Z",
        detected_before="2024-05-02T00:00:00Z",
        bucket_origin="start_of_hour",
        bucket_size_seconds=3600,
        bucket_count=24,
    )

    assert seen["database_url"] == "postgresql://example"
    assert summary.summary == "ok"
    assert captured["kwargs"] == {
        "data_object_version_ids": ["dov-1"],
        "execution_run_ids": ["run-1"],
        "reason_codes": ["DQ1_EMPTY_EXPRESSION"],
        "detected_after": "2024-05-01T00:00:00Z",
        "detected_before": "2024-05-02T00:00:00Z",
        "bucket_origin": "start_of_hour",
        "bucket_size_seconds": 3600,
        "bucket_count": 24,
    }

    row = captured["rows"][0]
    assert row["bucket_start"] == "2024-05-01T10:00:00+00:00"
    assert row["created_at"] == "2024-05-01T10:00:00+00:00"
    assert row["updated_at"] == "2024-05-01T10:00:00+00:00"
    assert row["record_identifier_values"] == ["record-1"]
    assert row["execution_run_ids"] == ["run-1"]
