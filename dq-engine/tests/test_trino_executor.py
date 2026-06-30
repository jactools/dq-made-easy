from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
