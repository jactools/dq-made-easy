from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

import trino_executor
from trino_config import load_trino_config
from trino_config import validate_trino_config
from trino_executor import TrinoQueryResult
from trino_executor import TrinoExecutionError
from trino_executor import TrinoExecutor


class _FakeCursor:
    def __init__(self, rows: list[tuple[int, ...]]) -> None:
        self._rows = rows
        self._offset = 0
        self.executed_queries: list[str] = []

    def execute(self, query: str) -> None:
        self.executed_queries.append(query)

    def fetchmany(self, size: int) -> list[tuple[int, ...]]:
        if self._offset >= len(self._rows):
            return []
        next_offset = min(self._offset + size, len(self._rows))
        batch = self._rows[self._offset:next_offset]
        self._offset = next_offset
        return batch


class _FakeConnection:
    def __init__(self, rows: list[tuple[int, ...]]) -> None:
        self._cursor = _FakeCursor(rows)

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FailingCursor:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def execute(self, query: str) -> None:
        raise self.exc


class _FailingConnection:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def cursor(self) -> _FailingCursor:
        return _FailingCursor(self.exc)


def _executor() -> TrinoExecutor:
    return TrinoExecutor(
        config={
            "host": "localhost",
            "http_port": 8080,
            "user": "user",
            "catalog": "hive",
            "schema": "default",
            "timeout_ms": 30000,
            "memory_per_task": "1GB",
            "max_row_fetch_size": 2,
            "max_result_sample_size": 3,
            "connection_attempts": 1,
            "connection_retry_backoff_ms": 0,
        }
    )


def test_trino_query_result_bool_iteration_and_empty_error_message() -> None:
    result = TrinoQueryResult(rows=[(1,), (2,)], row_count=2)

    assert bool(result) is True
    assert list(result) == [(1,), (2,)]
    assert str(TrinoExecutionError("plain failure")) == "plain failure"


def test_execute_query_streams_large_results_into_bounded_sample() -> None:
    rows = [(index,) for index in range(1, 6)]
    executor = TrinoExecutor(
        config={
            "host": "localhost",
            "http_port": 8080,
            "user": "user",
            "catalog": "hive",
            "schema": "default",
            "timeout_ms": 30000,
            "memory_per_task": "1GB",
            "max_row_fetch_size": 2,
            "max_result_sample_size": 3,
            "max_row_fetch_size_per_query": 10000,
        }
    )

    result = executor.execute_query(_FakeConnection(rows), "SELECT id FROM huge_error_set")

    assert len(result) == 5
    assert result.row_count == 5
    assert result.truncated is True
    assert result.sample_rows == [(1,), (2,), (3,)]
    assert result[0] == (1,)


@pytest.mark.parametrize(
    ("exception_name", "error_code", "message_fragment"),
    [
        ("TrinoUserError", "DQ_TRINO_QUERY_ERROR", "Trino query error"),
        ("TrinoQueryError", "DQ_TRINO_QUERY_ERROR", "Trino query exception"),
        ("OperationalError", "DQ_TRINO_CONNECTION_FAILED", "Trino connection error"),
        ("RuntimeError", "DQ_TRINO_EXECUTION_ERROR", "Query execution failed"),
    ],
)
def test_execute_query_maps_dbapi_errors_to_structured_trino_errors(
    monkeypatch: pytest.MonkeyPatch,
    exception_name: str,
    error_code: str,
    message_fragment: str,
) -> None:
    class FakeTrinoError(Exception):
        def __init__(self, message: str) -> None:
            self.message = message
            super().__init__(message)

    exception_type = RuntimeError if exception_name == "RuntimeError" else FakeTrinoError
    if exception_name != "RuntimeError":
        monkeypatch.setattr(trino_executor, exception_name, exception_type)

    executor = _executor()
    with pytest.raises(TrinoExecutionError) as exc_info:
        executor.execute_query(_FailingConnection(exception_type("broken query")), "SELECT broken")

    assert exc_info.value.error_code == error_code
    assert message_fragment in str(exc_info.value)


def test_close_connection_ignores_missing_close_and_logs_close_failures(caplog: pytest.LogCaptureFixture) -> None:
    class BadClose:
        def close(self) -> None:
            raise RuntimeError("close failed")

    executor = _executor()
    executor.close_connection(object())
    executor.close_connection(BadClose())

    assert "Failed to close Trino connection" in caplog.text


def test_validate_query_result_handles_scalar_variants_and_count_mismatch() -> None:
    executor = _executor()

    assert executor.validate_query_result([{"dq_count": 4}], {"expected_count": 4, "treat_first_cell_as_count": True})["passed"] is True
    assert executor.validate_query_result([[4]], {"expected_count": 5, "treat_first_cell_as_count": True})["details"] == {
        "count_mismatch": True,
        "actual_count": 4,
        "expected_count": 5,
    }
    assert executor.validate_query_result([1, 2], {"expected_count": 1})["details"] == {
        "count_mismatch": True,
        "actual_count": 2,
        "expected_count": 1,
    }


def test_collect_query_metrics_reports_duration_and_rows() -> None:
    executor = _executor()
    metrics = executor.collect_query_metrics("SELECT 1", time.time() - 1, 7)

    assert metrics["duration_ms"] >= 0
    assert metrics["rows_returned"] == 7
    assert metrics["warnings"] == []


def test_load_trino_config_coerces_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DQ_TRINO_PORT", "8443")
    monkeypatch.setenv("DQ_TRINO_TIMEOUT", "45000")
    monkeypatch.setenv("DQ_TRINO_HTTP_SCHEME", "https")
    monkeypatch.setenv("DQ_TRINO_VERIFY", "false")
    monkeypatch.setenv("DQ_TRINO_CONNECTION_ATTEMPTS", "2")
    monkeypatch.setenv("DQ_TRINO_CONNECTION_RETRY_BACKOFF_MS", "0")

    config = load_trino_config()

    assert config["http_port"] == 8443
    assert config["timeout_ms"] == 45000
    assert config["http_scheme"] == "https"
    assert config["verify"] is False
    assert config["connection_attempts"] == 2
    assert config["connection_retry_backoff_ms"] == 0


def test_validate_trino_config_rejects_invalid_connection_settings() -> None:
    errors = validate_trino_config(
        {
            "host": "",
            "http_port": "70000",
            "user": "",
            "catalog": "hive",
            "schema": "default",
            "http_scheme": "ftp",
            "timeout_ms": 0,
            "max_row_fetch_size": 0,
            "max_result_sample_size": 1,
            "connection_attempts": 0,
            "connection_retry_backoff_ms": -1,
            "extra_credential_headers": [],
        }
    )

    assert "host cannot be empty" in errors
    assert "user cannot be empty" in errors
    assert any("http_port must be a valid port number" in item for item in errors)
    assert any("http_scheme must be 'http' or 'https'" in item for item in errors)
    assert any("connection_attempts must be a positive integer" in item for item in errors)
    assert "extra_credential_headers must be a dictionary" in errors


def test_create_connection_uses_validated_dbapi_settings() -> None:
    calls: list[dict[str, Any]] = []

    def fake_connect(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    executor = TrinoExecutor(
        config={
            "host": "trino.example.test",
            "http_port": "8443",
            "user": "dq-user",
            "catalog": "lakehouse",
            "schema": "quality",
            "http_scheme": "https",
            "verify": "false",
            "timeout_ms": "60000",
            "memory_per_task": "2GB",
            "max_row_fetch_size": "500",
            "max_result_sample_size": "50",
            "connection_attempts": "1",
            "connection_retry_backoff_ms": "0",
            "source": "dq-tests",
            "extra_credential_headers": {"x-trino-token": "token"},
        },
        connect_factory=fake_connect,
    )

    client = executor.create_connection()

    assert client is not None
    assert calls == [
        {
            "host": "trino.example.test",
            "port": 8443,
            "user": "dq-user",
            "catalog": "lakehouse",
            "schema": "quality",
            "http_scheme": "https",
            "verify": False,
            "source": "dq-tests",
            "request_timeout": 60.0,
            "session_properties": {},
            "http_headers": {"x-trino-token": "token"},
        }
    ]


def test_create_connection_retries_then_reports_connection_failure() -> None:
    calls = 0

    def failing_connect(**kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        raise RuntimeError("temporary unavailable")

    executor = TrinoExecutor(
        config={
            "host": "localhost",
            "http_port": 8080,
            "user": "user",
            "catalog": "hive",
            "schema": "default",
            "timeout_ms": 30000,
            "memory_per_task": "1GB",
            "max_row_fetch_size": 100,
            "max_result_sample_size": 10,
            "connection_attempts": 2,
            "connection_retry_backoff_ms": 0,
        },
        connect_factory=failing_connect,
    )

    with pytest.raises(TrinoExecutionError) as exc_info:
        executor.create_connection()

    assert calls == 2
    assert exc_info.value.error_code == "DQ_TRINO_CONNECTION_FAILED"
    assert "after 2 attempt" in str(exc_info.value)
