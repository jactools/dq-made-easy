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

DEFAULT_PARQUET_URI = (
    "s3a://retail-banking/"
    "standardized/analytics/"
    "Currency/v1/"
    "LOAD_DTS=20260220T071500000Z"
)
DEFAULT_EXPECTED_ROW_COUNT = 180
TRINO_CONTAINER_HINT = (
    "Start Trino and AIStor with the existing stack scripts, for example "
    "`./scripts/stack_ctl.sh start --profile trino --profile aistor`, and seed the delivery parquet with "
    "`./scripts/seed_trino_aistor_catalogs.sh`."
)


def _env_is_set(name: str) -> bool:
    return name in os.environ and os.environ[name].strip() != ""


def _trino_s3_uri(uri: str) -> str:
    if uri.startswith("s3a://"):
        return "s3://" + uri[len("s3a://") :]
    return uri


def _live_trino_config() -> dict[str, Any]:
    config = load_trino_config()

    if not _env_is_set("DQ_TRINO_HOST"):
        config["host"] = "127.0.0.1"
    if not _env_is_set("DQ_TRINO_PORT"):
        config["http_port"] = int(os.environ.get("TRINO_HOST_PORT", "8084"))
    if not _env_is_set("DQ_TRINO_USER"):
        config["user"] = "dq-trino-aistor-validation"
    config["catalog"] = os.getenv("TRINO_AISTOR_VALIDATION_CATALOG", "aistor")
    config["schema"] = os.getenv("TRINO_AISTOR_VALIDATION_SCHEMA", "dq_validation")
    if not _env_is_set("DQ_TRINO_TIMEOUT"):
        config["timeout_ms"] = 30000
    if not _env_is_set("DQ_TRINO_MAX_ROW_FETCH_SIZE"):
        config["max_row_fetch_size"] = 100
    if not _env_is_set("DQ_TRINO_MAX_RESULT_SAMPLE_SIZE"):
        config["max_result_sample_size"] = 10
    if not _env_is_set("DQ_TRINO_CONNECTION_ATTEMPTS"):
        config["connection_attempts"] = 1
    if not _env_is_set("DQ_TRINO_CONNECTION_RETRY_BACKOFF_MS"):
        config["connection_retry_backoff_ms"] = 0
    if not _env_is_set("DQ_TRINO_SOURCE"):
        config["source"] = "dq-engine-trino-aistor-validation"

    return config


def _skip_when_trino_is_unavailable(config: dict[str, Any]) -> None:
    try:
        with socket.create_connection((str(config["host"]), int(config["http_port"])), timeout=1.0):
            return
    except OSError as exc:
        pytest.skip(f"Live Trino container is not reachable: {exc}. {TRINO_CONTAINER_HINT}")


def _execute_statement(executor: TrinoExecutor, client: Any, sql: str) -> None:
    executor.execute_query(client, sql)


def _skip_when_aistor_catalog_is_unavailable(exc: TrinoExecutionError, catalog: str) -> None:
    if "CATALOG_NOT_FOUND" in str(exc) or f"Catalog '{catalog}' not found" in str(exc):
        pytest.skip(
            f"Trino catalog {catalog!r} is not available. Rebuild/start the Trino image with the repo dq-trino catalog config. "
            f"{TRINO_CONTAINER_HINT}"
        )
    raise exc


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


def test_trino_query_rule_executes_against_existing_aistor_parquet(
    live_trino_executor: TrinoExecutor,
    tmp_path: Path,
) -> None:
    catalog = os.getenv("TRINO_AISTOR_VALIDATION_CATALOG", "aistor")
    schema = os.getenv("TRINO_AISTOR_VALIDATION_SCHEMA", "dq_validation")
    table = os.getenv("TRINO_AISTOR_VALIDATION_TABLE", "currency_real_aistor_validation")
    parquet_uri = _trino_s3_uri(os.getenv("TRINO_AISTOR_VALIDATION_INPUT_URI", DEFAULT_PARQUET_URI))
    expected_count = int(os.getenv("TRINO_AISTOR_VALIDATION_EXPECTED_COUNT", str(DEFAULT_EXPECTED_ROW_COUNT)))
    schema_location = _trino_s3_uri(os.getenv("TRINO_AISTOR_VALIDATION_SCHEMA_LOCATION", "s3a://retail-banking/trino-validation"))
    qualified_table = f'"{catalog}"."{schema}"."{table}"'

    client = live_trino_executor.create_connection()
    try:
        try:
            _execute_statement(live_trino_executor, client, f'CREATE SCHEMA IF NOT EXISTS "{catalog}"."{schema}" WITH (location = \'{schema_location}\')')
            _execute_statement(live_trino_executor, client, f"DROP TABLE IF EXISTS {qualified_table}")
            _execute_statement(
                live_trino_executor,
                client,
                f"""
                CREATE TABLE {qualified_table} (
                    currency_code varchar,
                    currency_name varchar,
                    symbol varchar,
                    decimal_places bigint,
                    is_active boolean
                )
                WITH (
                    external_location = '{parquet_uri}',
                    format = 'PARQUET'
                )
                """,
            )
        except TrinoExecutionError as exc:
            _skip_when_aistor_catalog_is_unavailable(exc, catalog)

        count_result = live_trino_executor.execute_query(
            client,
            f"""
            SELECT COUNT(*) AS dq_count
            FROM {qualified_table}
            """,
        )
    finally:
        live_trino_executor.close_connection(client)

    assert count_result.row_count == 1
    assert count_result.sample_rows[0][0] == expected_count

    rule = {
        "id": "trino-real-aistor-parquet-count",
        "table": f'{catalog}.{schema}.{table}',
        "type": "query",
        "params": {
            "query": f"""
                SELECT COUNT(*) AS dq_count
                FROM {qualified_table}
            """,
            "expected_count": expected_count,
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
    assert result["result"]["actual_count"] == expected_count
    assert result["result"]["expected_count"] == expected_count
    assert result["metrics"]["rows_returned"] == 1
    assert (tmp_path / "trino_execution.json").exists()
    assert (tmp_path / "trino_results.json").exists()
    assert (tmp_path / "trino_query.sql").exists()
