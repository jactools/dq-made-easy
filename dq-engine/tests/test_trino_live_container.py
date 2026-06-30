from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trino_config import load_trino_config
from trino_executor import TrinoExecutionError
from trino_executor import TrinoExecutor
from trino_execution_pipeline import create_trino_execution_plan
from trino_execution_pipeline import execute_trino_pipeline


TRINO_CONTAINER_HINT = (
    "Start the live Trino service with `./scripts/stack_ctl.sh start --profile trino` "
    "and stop it with `./scripts/stack_ctl.sh stop --profile trino`."
)


def _env_is_set(name: str) -> bool:
    return name in os.environ and os.environ[name].strip() != ""


def _live_trino_config() -> dict[str, Any]:
    config = load_trino_config()

    if not _env_is_set("DQ_TRINO_HOST"):
        config["host"] = "127.0.0.1"
    if not _env_is_set("DQ_TRINO_PORT"):
        config["http_port"] = int(os.environ.get("TRINO_HOST_PORT", "8084"))
    if not _env_is_set("DQ_TRINO_USER"):
        config["user"] = "dq-live-test"
    if not _env_is_set("DQ_TRINO_CATALOG"):
        config["catalog"] = "system"
    if not _env_is_set("DQ_TRINO_SCHEMA"):
        config["schema"] = "runtime"
    if not _env_is_set("DQ_TRINO_TIMEOUT"):
        config["timeout_ms"] = 10000
    if not _env_is_set("DQ_TRINO_MAX_ROW_FETCH_SIZE"):
        config["max_row_fetch_size"] = 50
    if not _env_is_set("DQ_TRINO_MAX_RESULT_SAMPLE_SIZE"):
        config["max_result_sample_size"] = 10
    if not _env_is_set("DQ_TRINO_CONNECTION_ATTEMPTS"):
        config["connection_attempts"] = 1
    if not _env_is_set("DQ_TRINO_CONNECTION_RETRY_BACKOFF_MS"):
        config["connection_retry_backoff_ms"] = 0
    if not _env_is_set("DQ_TRINO_SOURCE"):
        config["source"] = "dq-engine-live-tests"

    return config


def _skip_when_trino_is_unavailable(config: dict[str, Any]) -> None:
    try:
        with socket.create_connection((str(config["host"]), int(config["http_port"])), timeout=1.0):
            return
    except OSError as exc:
        pytest.skip(f"Live Trino container is not reachable: {exc}. {TRINO_CONTAINER_HINT}")


@pytest.fixture(scope="module")
def live_trino_executor() -> TrinoExecutor:
    config = _live_trino_config()
    _skip_when_trino_is_unavailable(config)
    executor = TrinoExecutor(config=config)

    client = None
    try:
        client = executor.create_connection()
        executor.execute_query(client, "SELECT 1")
    except TrinoExecutionError as exc:
        pytest.skip(f"Live Trino container did not accept a smoke query: {exc}. {TRINO_CONTAINER_HINT}")
    finally:
        if client is not None:
            executor.close_connection(client)

    return executor


def test_live_trino_container_smoke_query(live_trino_executor: TrinoExecutor) -> None:
    client = live_trino_executor.create_connection()
    try:
        result = live_trino_executor.execute_query(client, "SELECT 1 AS dq_smoke")
    finally:
        live_trino_executor.close_connection(client)

    assert result.row_count == 1
    assert result.sample_rows[0][0] == 1
    assert result.truncated is False


def test_live_trino_container_query_rule_pipeline_persists_result(
    live_trino_executor: TrinoExecutor,
    tmp_path: Path,
) -> None:
    rule = {
        "id": "trino-live-query-rule",
        "table": "system.runtime.nodes",
        "type": "query",
        "params": {
            "query": "SELECT count(*) AS dq_count FROM (VALUES 1) AS dq_live(id)",
            "expected_count": 1,
        },
    }

    plan = create_trino_execution_plan(
        rule,
        config=live_trino_executor.config,
        executor=live_trino_executor,
    )
    result = execute_trino_pipeline(plan, output_dir=str(tmp_path))

    assert result["ok"] is True
    assert result["engine_type"] == "trino"
    assert result["result_status"] == "passed"
    assert result["result"]["passed"] is True
    assert result["result"]["actual_count"] == 1
    assert result["metrics"]["rows_returned"] == 1
    assert result["execution_metadata"]["engine_type"] == "trino"
    assert result["observability_summary"]["engine_type"] == "trino"
    assert (tmp_path / "trino_execution.json").exists()
    assert (tmp_path / "trino_results.json").exists()
    assert (tmp_path / "trino_query.sql").exists()