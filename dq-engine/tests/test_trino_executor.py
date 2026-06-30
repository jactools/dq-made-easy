from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from trino_config import load_trino_config
from trino_config import validate_trino_config
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
            "session_properties": {
                "query_max_runtime_ms": "60000",
                "memory_per_task": "2GB",
                "max_row_fetch_size": "500",
            },
            "extra_credential_headers": {"x-trino-token": "token"},
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
