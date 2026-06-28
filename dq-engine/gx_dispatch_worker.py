from __future__ import annotations

import importlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import requests

try:
    import redis
except Exception:  # pragma: no cover
    redis = None

from dq_utils.logging_utils import configure_logging
from dq_utils.logging_utils import log_event

from dq_utils.auth_utils import AuthConfigError
from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import build_oidc_token_provider_from_env
from dq_utils.spark_runtime import build_spark_session_builder
from dq_utils.spark_runtime import resolve_spark_master
from dq_utils.spark_runtime import resolve_spark_ui_port
from gx_dispatch_dispatch import build_execution_progress
from gx_dispatch_dispatch import build_token_provider
from gx_dispatch_dispatch import coerce_int
from gx_dispatch_dispatch import coerce_str
from gx_dispatch_dispatch import log_dispatch_received
from gx_dispatch_dispatch import parse_dispatch_payload
from gx_dispatch_dispatch import report_execution_progress
from gx_dispatch_dispatch import report_run
from gx_dispatch_expectations import evaluate_expectations_spark
from gx_dispatch_runtime import assert_supported_uri
from gx_dispatch_runtime import coerce_source_location
from gx_dispatch_runtime import create_spark_session
from gx_dispatch_runtime import download_s3a_prefix_to_tempdir
from gx_dispatch_runtime import normalize_s3_uri
from gx_dispatch_runtime import parse_s3a_uri
from gx_dispatch_runtime import require_s3_config_for_location
from gx_dispatch_runtime import safe_stop_spark_session
from gx_dispatch_runtime import spark_read_dataset
from gx_dispatch_results import utc_now_iso
from gx_dispatch_telemetry import configure_worker_telemetry
from gx_dispatch_telemetry import record_spark_expectations_observability
from gx_dispatch_telemetry import record_worker_duration
from gx_dispatch_telemetry import record_worker_expectation_results
from gx_dispatch_telemetry import record_worker_failure
from gx_dispatch_telemetry import record_worker_heartbeat
from gx_dispatch_telemetry import traced_worker_span
from gx_dispatch_types import GxWorkerConfig
from gx_dispatch_types import GxWorkerConfigError
from gx_dispatch_types import GxWorkerExecutionError
from gx_dispatch_types import SourceLocation
from main import ExecuteRequest
from main import execute_rule


_S3_URI_RE = re.compile(r"^s3a?://")
_MATERIALIZED_FORMAT_RE = re.compile(r"(?:^|/)format=(parquet|delta)(?:/|$)", re.IGNORECASE)


def _utc_now_iso() -> str:
    return utc_now_iso()


def _require_redis() -> Any:
    if redis is None:
        raise GxWorkerConfigError("Python 'redis' package is not installed in dq-engine; required for GX worker")
    return redis


def _resolve_redis_url() -> str:
    explicit = os.getenv("GX_EXECUTION_REDIS_URL") or os.getenv("REDIS_URL")
    if explicit and explicit.strip():
        return explicit.strip()

    host = str(os.getenv("REDIS_HOST") or "").strip()
    if not host:
        raise GxWorkerConfigError(
            "Redis is not configured for dq-engine GX worker (set GX_EXECUTION_REDIS_URL/REDIS_URL or REDIS_HOST)"
        )
    port = int(os.getenv("REDIS_PORT") or 6379)
    db = int(os.getenv("REDIS_DB") or 0)
    password = os.getenv("REDIS_PASSWORD")
    if password:
        from urllib.parse import quote

        return f"redis://:{quote(password, safe='')}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


def _resolve_queue_key() -> str:
    return (
        os.environ.get("GX_EXECUTION_QUEUE_KEY")
        or os.environ.get("DQ_GX_EXECUTION_QUEUE_KEY")
        or "dq-gx:execution-dispatch"
    )


def _resolve_processing_queue_key(queue_key: str) -> str:
    configured = os.environ.get("GX_EXECUTION_PROCESSING_QUEUE_KEY")
    if configured and configured.strip():
        return configured.strip()
    return f"{queue_key}:processing"


def _resolve_worker_heartbeat_key(queue_key: str) -> str:
    configured = os.environ.get("GX_EXECUTION_WORKER_HEARTBEAT_KEY")
    if configured and configured.strip():
        return configured.strip()
    return f"{queue_key}:worker-heartbeat"


def _resolve_worker_heartbeat_ttl_seconds() -> int:
    raw_value = os.environ.get("GX_EXECUTION_WORKER_HEARTBEAT_TTL_SECONDS") or "30"
    try:
        parsed = int(raw_value)
    except Exception:
        parsed = 30
    return max(parsed, 5)


def _resolve_worker_heartbeat_interval_seconds(ttl_seconds: int) -> int:
    raw_value = os.environ.get("GX_EXECUTION_WORKER_HEARTBEAT_INTERVAL_SECONDS")
    if raw_value and raw_value.strip():
        try:
            parsed = int(raw_value)
            return max(parsed, 1)
        except Exception:
            pass
    return max(min(ttl_seconds // 3, 10), 1)


def _resolve_spark_master() -> str:
    try:
        return resolve_spark_master()
    except Exception as exc:
        raise GxWorkerConfigError(str(exc)) from exc


def _resolve_spark_ui_port() -> int:
    try:
        return resolve_spark_ui_port()
    except ValueError as exc:
        raise GxWorkerConfigError(str(exc)) from exc


def _resolve_s3_endpoint() -> str | None:
    endpoint = os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL")
    if endpoint and endpoint.strip():
        return endpoint.strip()
    return None


def _resolve_s3_access_key() -> str | None:
    value = os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID")
    return value.strip() if value and value.strip() else None


def _resolve_s3_secret_key() -> str | None:
    value = os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
    return value.strip() if value and value.strip() else None


def _resolve_s3_region() -> str | None:
    value = os.getenv("DQ_S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    return value.strip() if value and value.strip() else None


def _resolve_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_optional_bool_env(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_api_url() -> str:
    # Must route through Kong. Default works for docker-compose.
    api_url = os.getenv("KONG_INTERNAL_URL") or "http://kong:8000"
    api_url = str(api_url).strip().rstrip("/")
    if not api_url:
        raise GxWorkerConfigError("KONG_INTERNAL_URL is required for dq-engine GX worker")
    return api_url

def _build_token_provider() -> TokenProvider:
    static_token = str(os.getenv("DQ_ENGINE_API_BEARER_TOKEN") or "").strip() or str(
        os.getenv("DQ_WORKER_API_BEARER_TOKEN") or ""
    ).strip()
    if static_token:
        raise GxWorkerConfigError(
            "Static bearer tokens are not supported for dq-engine GX worker auth. "
            "Remove DQ_ENGINE_API_BEARER_TOKEN/DQ_WORKER_API_BEARER_TOKEN and configure OIDC client credentials "
            "(DQ_ENGINE_OIDC_ISSUER or DQ_ENGINE_OIDC_TOKEN_URL) plus DQ_ENGINE_OIDC_CLIENT_ID and "
            "DQ_ENGINE_OIDC_CLIENT_SECRET."
        )

    try:
        return build_oidc_token_provider_from_env(
            issuer_env_var="DQ_ENGINE_OIDC_ISSUER",
            token_url_env_var="DQ_ENGINE_OIDC_TOKEN_URL",
            client_id_env_var="DQ_ENGINE_OIDC_CLIENT_ID",
            client_secret_env_var="DQ_ENGINE_OIDC_CLIENT_SECRET",
            scope_env_var="DQ_ENGINE_OIDC_SCOPE",
        )
    except AuthConfigError as exc:
        raise GxWorkerConfigError(str(exc)) from exc


def load_config() -> GxWorkerConfig:
    redis_url = _resolve_redis_url()
    queue_key = _resolve_queue_key()
    processing_key = _resolve_processing_queue_key(queue_key)
    heartbeat_key = _resolve_worker_heartbeat_key(queue_key)
    heartbeat_ttl_seconds = _resolve_worker_heartbeat_ttl_seconds()
    heartbeat_interval_seconds = _resolve_worker_heartbeat_interval_seconds(heartbeat_ttl_seconds)
    max_rows = int(os.getenv("DQ_ENGINE_MAX_ROWS", "100000"))
    poll_timeout_seconds = int(os.getenv("GX_EXECUTION_POLL_TIMEOUT_SECONDS", "5"))

    api_url = _resolve_api_url()

    spark_master = _resolve_spark_master()
    spark_ui_port = _resolve_spark_ui_port()
    s3_endpoint = _resolve_s3_endpoint()
    s3_access_key = _resolve_s3_access_key()
    s3_secret_key = _resolve_s3_secret_key()
    s3_region = _resolve_s3_region()
    s3_path_style_access = _resolve_bool_env("DQ_S3_PATH_STYLE_ACCESS", True)
    s3_ssl_enabled = _resolve_optional_bool_env("DQ_S3_SSL_ENABLED")

    return GxWorkerConfig(
        redis_url=redis_url,
        queue_key=queue_key,
        processing_queue_key=processing_key,
        heartbeat_key=heartbeat_key,
        heartbeat_ttl_seconds=heartbeat_ttl_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        max_rows=max_rows,
        poll_timeout_seconds=poll_timeout_seconds,
        api_url=api_url,
        spark_master=spark_master,
        spark_ui_port=spark_ui_port,
        s3_endpoint=s3_endpoint,
        s3_access_key=s3_access_key,
        s3_secret_key=s3_secret_key,
        s3_region=s3_region,
        s3_path_style_access=s3_path_style_access,
        s3_ssl_enabled=s3_ssl_enabled,
    )


def _write_worker_heartbeat(client: Any, *, config: GxWorkerConfig, worker_id: str) -> None:
    heartbeat_payload = {
        "workerId": worker_id,
        "queueKey": config.queue_key,
        "processingQueueKey": config.processing_queue_key,
        "updatedAt": _utc_now_iso(),
    }
    client.set(config.heartbeat_key, json.dumps(heartbeat_payload), ex=config.heartbeat_ttl_seconds)
    record_worker_heartbeat(queue_key=config.queue_key, heartbeat_ttl_seconds=config.heartbeat_ttl_seconds)


def _start_worker_heartbeat_loop(
    client: Any,
    *,
    config: GxWorkerConfig,
    worker_id: str,
    logger: logging.Logger,
) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()

    def _heartbeat_loop() -> None:
        while not stop_event.wait(config.heartbeat_interval_seconds):
            try:
                _write_worker_heartbeat(client, config=config, worker_id=worker_id)
            except Exception as exc:
                log_event(
                    logger,
                    "gx.worker.heartbeat.failed",
                    level="error",
                    component="dq-engine-gx-worker",
                    heartbeatKey=config.heartbeat_key,
                    exceptionType=exc.__class__.__name__,
                    errorMessage=str(exc),
                )

    thread = threading.Thread(target=_heartbeat_loop, name="gx-worker-heartbeat", daemon=True)
    thread.start()
    return stop_event, thread


def _parse_dispatch_payload(raw: str) -> dict[str, Any]:
    return parse_dispatch_payload(raw)


def _coerce_str(payload: dict[str, Any], *keys: str) -> str:
    return coerce_str(payload, *keys)


def _coerce_int(payload: dict[str, Any], *keys: str) -> int:
    return coerce_int(payload, *keys)


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        next_exc = current.__cause__ or current.__context__
        current = next_exc if isinstance(next_exc, BaseException) else None
    return chain


def _format_exception_message(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__


def _is_spark_runtime_exception(exc: BaseException) -> bool:
    module_name = str(exc.__class__.__module__ or "")
    return module_name.startswith("py4j") or module_name.startswith("pyspark")


def _is_transient_spark_gateway_error(exc: BaseException) -> bool:
    for candidate in _iter_exception_chain(exc):
        if isinstance(candidate, ConnectionRefusedError):
            return True
        if str(candidate.__class__.__module__ or "").startswith("py4j"):
            return True
    return False


def _coerce_reported_failure(exc: BaseException) -> GxWorkerExecutionError:
    for candidate in _iter_exception_chain(exc):
        if isinstance(candidate, GxWorkerExecutionError):
            return candidate

    for candidate in _iter_exception_chain(exc):
        if _is_spark_runtime_exception(candidate):
            return GxWorkerExecutionError(
                _format_exception_message(candidate),
                failure_code="GX_WORKER_EXECUTION_ERROR",
            )

    return GxWorkerExecutionError(
        _format_exception_message(exc),
        failure_code="GX_WORKER_EXECUTION_ERROR",
    )


def _should_fail_closed_worker(exc: BaseException) -> bool:
    return any(_is_spark_runtime_exception(candidate) for candidate in _iter_exception_chain(exc))


def _safe_stop_spark_session(spark_session: Any) -> None:
    if not hasattr(spark_session, "stop"):
        return
    try:
        spark_session.stop()
    except Exception:
        # Preserve the original execution failure; Spark JVM teardown can fail after
        # the worker has already encountered the real error.
        pass


def _report_dispatch_failure(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    payload: dict[str, Any],
    exc: BaseException,
) -> bool:
    run_id = _coerce_str(payload, "run_id", "queue_message_id")
    if not run_id:
        return False

    correlation_id = _coerce_str(payload, "correlation_id") or f"corr-{uuid4().hex[:12]}"
    requested_by = _coerce_str(payload, "requested_by") or None
    failure = _coerce_reported_failure(exc)

    _api_report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="failed",
        changed_by=requested_by,
        reason="GX worker execution failed",
        details={
            "source": "dq-engine-gx-worker",
            "exception_type": exc.__class__.__name__,
        },
        completed_at=_utc_now_iso(),
        result_summary=None,
        diagnostics=[],
        failure_code=getattr(failure, "failure_code", "GX_WORKER_EXECUTION_ERROR"),
        failure_message=str(failure),
    )
    return True


def _api_headers(config: GxWorkerConfig, token_provider: TokenProvider, *, correlation_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token_provider.get_token(correlation_id=correlation_id)}",
        "X-Correlation-ID": correlation_id,
        "Content-Type": "application/json",
    }


def _api_request(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    method: str,
    path: str,
    correlation_id: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: int = 15,
) -> Any:
    url = f"{config.api_url.rstrip('/')}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=_api_headers(config, token_provider, correlation_id=correlation_id),
            params=params,
            json=json_body,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        raise GxWorkerExecutionError(
            f"GX worker cannot reach API via Kong at '{config.api_url}'",
            failure_code="GX_API_UNAVAILABLE",
        ) from exc

    content_type = str(response.headers.get("content-type") or "")
    payload: Any = None
    if "application/json" in content_type:
        try:
            payload = response.json()
        except Exception:
            payload = None

    if response.status_code >= 400:
        raise GxWorkerExecutionError(
            f"API request failed: {method} {path} -> {response.status_code}",
            failure_code="GX_API_REQUEST_FAILED",
            status_code=response.status_code,
        )
    return payload


def _should_discard_failed_message(exc: BaseException) -> bool:
    if not isinstance(exc, GxWorkerExecutionError):
        return False
    return exc.failure_code == "GX_API_REQUEST_FAILED" and exc.status_code == 404


def _api_get_suite_envelope(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    suite_id: str,
    suite_version: int,
    correlation_id: str,
) -> dict[str, Any]:
    payload = _api_request(
        config,
        token_provider,
        method="GET",
        path=f"/rulebuilder/v1/gx/suites/{suite_id}",
        params={"suiteVersion": suite_version, "status": "active"},
        correlation_id=correlation_id,
    )
    if not isinstance(payload, dict):
        raise GxWorkerExecutionError("API returned invalid GX suite envelope", failure_code="GX_SUITE_INVALID_ENVELOPE")
    return payload


def _api_get_data_object_version(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    version_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    payload = _api_request(
        config,
        token_provider,
        method="GET",
        path=f"/data-catalog/v1/data-object-versions/{version_id}",
        correlation_id=correlation_id,
    )
    if not isinstance(payload, dict):
        raise GxWorkerExecutionError(
            f"API returned invalid data object version payload for '{version_id}'",
            failure_code="GX_WORKER_MISSING_SOURCE_LOCATION",
        )
    return payload


def _api_report_run(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    run_id: str,
    correlation_id: str,
    new_status: str,
    changed_by: str | None,
    reason: str | None,
    details: dict[str, Any] | None,
    execution_progress: dict[str, Any] | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    result_summary: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> None:
    # Keep the downstream GX run report endpoint explicit for propagation contract checks:
    # path=f"/rulebuilder/v1/gx/runs/{run_id}/report"
    report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status=new_status,
        changed_by=changed_by,
        reason=reason,
        details=details,
        execution_progress=execution_progress,
        started_at=started_at,
        completed_at=completed_at,
        result_summary=result_summary,
        metrics=metrics,
        diagnostics=diagnostics,
        failure_code=failure_code,
        failure_message=failure_message,
    )


def _build_execution_progress(
    *,
    completed_steps: int,
    total_steps: int,
    label: str,
) -> dict[str, Any]:
    percent = 0 if total_steps <= 0 else int(round((completed_steps / total_steps) * 100))
    return {
        "percent": max(0, min(percent, 100)),
        "label": label,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "source": "dq-engine-gx-worker",
        "updated_at": _utc_now_iso(),
    }


def _api_report_execution_progress(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    run_id: str,
    correlation_id: str,
    changed_by: str | None,
    reason: str,
    details: dict[str, Any] | None,
    completed_steps: int,
    total_steps: int,
    label: str,
) -> None:
    _api_report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="running",
        changed_by=changed_by,
        reason=reason,
        details=details,
        execution_progress=_build_execution_progress(
            completed_steps=completed_steps,
            total_steps=total_steps,
            label=label,
        ),
    )


def _extract_primary_key_fields(envelope: dict[str, Any]) -> list[str]:
    execution_hints = envelope.get("executionHints") if isinstance(envelope.get("executionHints"), dict) else None
    if execution_hints is None and isinstance(envelope.get("execution_hints"), dict):
        execution_hints = envelope.get("execution_hints")
    if not isinstance(execution_hints, dict):
        return []

    raw_fields = execution_hints.get("primaryKeyFields")
    if raw_fields is None:
        raw_fields = execution_hints.get("primary_key_fields")
    if not isinstance(raw_fields, list):
        return []
    return [str(value).strip() for value in raw_fields if str(value).strip()]


def _assert_runnable_suite(envelope: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    gx_suite = envelope.get("gx_suite") if isinstance(envelope.get("gx_suite"), dict) else None
    if not isinstance(gx_suite, dict):
        raise GxWorkerExecutionError("GX suite envelope is missing gx_suite", failure_code="GX_SUITE_NOT_RUNNABLE")

    expectations = gx_suite.get("expectations")
    if not isinstance(expectations, list) or not expectations:
        raise GxWorkerExecutionError("GX suite has no executable expectations", failure_code="GX_SUITE_NOT_RUNNABLE")
    for idx, exp in enumerate(expectations):
        if not isinstance(exp, dict):
            raise GxWorkerExecutionError(
                f"GX suite expectation at index {idx} is invalid",
                failure_code="GX_SUITE_NOT_RUNNABLE",
            )
        if not str(exp.get("expectation_type") or "").strip():
            raise GxWorkerExecutionError(
                f"GX suite expectation at index {idx} missing expectation_type",
                failure_code="GX_SUITE_NOT_RUNNABLE",
            )
        kwargs = exp.get("kwargs")
        if not isinstance(kwargs, dict) or not kwargs:
            raise GxWorkerExecutionError(
                f"GX suite expectation at index {idx} missing kwargs",
                failure_code="GX_SUITE_NOT_RUNNABLE",
            )

    resolved_scope = envelope.get("resolved_execution_scope") if isinstance(envelope.get("resolved_execution_scope"), dict) else None
    target_ids: list[str] = []
    if isinstance(resolved_scope, dict):
        raw_ids = resolved_scope.get("data_object_version_ids") or []
        target_ids = [str(v).strip() for v in raw_ids if str(v).strip()]
    if not target_ids:
        raise GxWorkerExecutionError("GX suite has no resolved execution targets", failure_code="GX_SUITE_NOT_RUNNABLE")

    return expectations, target_ids, _extract_primary_key_fields(envelope)


def _resolve_spark_session_class() -> Any:
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:  # pragma: no cover
        raise GxWorkerConfigError("pyspark is not installed; cannot run dq-engine GX worker") from exc
    return SparkSession


def _resolve_spark_functions_module() -> Any:
    try:
        from pyspark.sql import functions as F
    except ImportError as exc:  # pragma: no cover
        raise GxWorkerExecutionError(
            "pyspark is not installed; cannot evaluate GX expectations",
            failure_code="GX_WORKER_EXECUTION_ERROR",
        ) from exc
    return F


def _derive_s3_ssl_enabled(config: GxWorkerConfig) -> bool:
    if config.s3_ssl_enabled is not None:
        return bool(config.s3_ssl_enabled)
    if config.s3_endpoint and config.s3_endpoint.strip().lower().startswith("https://"):
        return True
    return False


def _resolve_worker_spark_setting(env_name: str, default: str) -> str:
    raw_value = str(os.getenv(env_name) or "").strip()
    return raw_value or default


def _configure_worker_spark_builder(builder: Any, config: GxWorkerConfig, *, enable_delta: bool) -> Any:
    from dq_utils.spark_jars import configure_spark_builder_with_local_jars

    configured = configure_spark_builder_with_local_jars(builder)
    configured = configured.config(
        "spark.driver.memory",
        _resolve_worker_spark_setting("DQ_SPARK_DRIVER_MEMORY", "2g"),
    )
    configured = configured.config(
        "spark.executor.memory",
        _resolve_worker_spark_setting("DQ_SPARK_EXECUTOR_MEMORY", "2g"),
    )
    configured = configured.config(
        "spark.driver.maxResultSize",
        _resolve_worker_spark_setting("DQ_SPARK_DRIVER_MAX_RESULT_SIZE", "512m"),
    )

    if enable_delta:
        configured = configured.config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        configured = configured.config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")

    if config.s3_endpoint:
        configured = configured.config("spark.hadoop.fs.s3a.endpoint", config.s3_endpoint)
        configured = configured.config(
            "spark.hadoop.fs.s3a.path.style.access",
            "true" if config.s3_path_style_access else "false",
        )
        configured = configured.config(
            "spark.hadoop.fs.s3a.connection.ssl.enabled",
            "true" if _derive_s3_ssl_enabled(config) else "false",
        )

    if config.s3_access_key and config.s3_secret_key:
        configured = configured.config("spark.hadoop.fs.s3a.access.key", config.s3_access_key)
        configured = configured.config("spark.hadoop.fs.s3a.secret.key", config.s3_secret_key)
        configured = configured.config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
        )

    if config.s3_region:
        configured = configured.config("spark.hadoop.fs.s3a.endpoint.region", config.s3_region)

    return configured


def _create_spark_session(config: GxWorkerConfig, *, enable_delta: bool) -> Any:
    spark_session_class = _resolve_spark_session_class()
    builder = build_spark_session_builder(
        SparkSession=spark_session_class,
        app_name="dq-made-easy-gx-worker",
        master=config.spark_master,
        spark_ui_port=config.spark_ui_port,
    )
    builder = _configure_worker_spark_builder(builder, config, enable_delta=enable_delta)

    logger = logging.getLogger(__name__)
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            return builder.getOrCreate()
        except Exception as exc:
            if attempt >= max_attempts or not _is_transient_spark_gateway_error(exc):
                raise

            log_event(
                logger,
                "gx.worker.spark_session.retry",
                level="warning",
                component="dq-engine-gx-worker",
                attempt=attempt,
                maxAttempts=max_attempts,
                exceptionType=exc.__class__.__name__,
                errorMessage=str(exc),
            )
            time.sleep(float(attempt))


def _normalize_s3_uri(uri: str) -> str:
    raw = uri.strip()
    if raw.startswith("s3://"):
        return "s3a://" + raw[len("s3://") :]
    return raw


def _parse_s3a_uri(uri: str) -> tuple[str, str]:
    raw = uri.strip()
    if not raw.startswith("s3a://"):
        raise GxWorkerExecutionError(
            f"Expected an s3a:// URI, got '{uri}'",
            failure_code="GX_WORKER_UNSUPPORTED_STORAGE_URI",
        )
    remainder = raw[len("s3a://") :]
    bucket, sep, key_prefix = remainder.partition("/")
    bucket = bucket.strip()
    if not bucket:
        raise GxWorkerExecutionError(
            f"Invalid s3a:// URI '{uri}' (missing bucket)",
            failure_code="GX_WORKER_UNSUPPORTED_STORAGE_URI",
        )
    return bucket, key_prefix if sep else ""


def _download_s3a_prefix_to_tempdir(config: GxWorkerConfig, *, uri: str) -> tuple[tempfile.TemporaryDirectory[str], str]:
    import boto3

    bucket, key_prefix = _parse_s3a_uri(uri)
    normalized_prefix = str(key_prefix or "").lstrip("/")
    if not normalized_prefix:
        raise GxWorkerExecutionError(
            f"Refusing to download entire bucket for URI '{uri}' (empty key prefix)",
            failure_code="GX_WORKER_INVALID_SOURCE_LOCATION",
        )

    client = boto3.client(
        "s3",
        endpoint_url=config.s3_endpoint,
        aws_access_key_id=config.s3_access_key,
        aws_secret_access_key=config.s3_secret_key,
        region_name=config.s3_region or "us-east-1",
        verify=_derive_s3_ssl_enabled(config),
    )

    tmpdir = tempfile.TemporaryDirectory(prefix="dq-gx-source-")
    base = Path(tmpdir.name)

    keys: list[str] = []
    continuation: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": normalized_prefix}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        resp = client.list_objects_v2(**kwargs)
        for obj in (resp.get("Contents") or []):
            key = str(obj.get("Key") or "").strip()
            if not key or key.endswith("/"):
                continue
            keys.append(key)
        if resp.get("IsTruncated"):
            continuation = str(resp.get("NextContinuationToken") or "") or None
            continue
        break

    if not keys:
        tmpdir.cleanup()
        raise GxWorkerExecutionError(
            f"No objects found for s3a://{bucket}/{normalized_prefix}",
            failure_code="GX_WORKER_MISSING_SOURCE_LOCATION",
        )

    for key in keys:
        rel = key[len(normalized_prefix) :].lstrip("/") if key.startswith(normalized_prefix) else ""
        if not rel:
            rel = Path(key).name
        local_path = base / rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, key, str(local_path))

    if len(keys) == 1 and keys[0] == normalized_prefix:
        return tmpdir, str(base / Path(normalized_prefix).name)

    return tmpdir, str(base)


def _assert_supported_uri(uri: str) -> None:
    if not _S3_URI_RE.match(uri):
        raise GxWorkerExecutionError(
            f"Unsupported storage URI scheme for '{uri}'. Only s3:// and s3a:// are supported initially.",
            failure_code="GX_WORKER_UNSUPPORTED_STORAGE_URI",
        )


def _require_s3_config_for_location(config: GxWorkerConfig, *, uri: str) -> None:
    if not _S3_URI_RE.match(uri):
        return
    if not config.s3_endpoint:
        raise GxWorkerConfigError("Missing DQ_S3_ENDPOINT/AWS_ENDPOINT_URL (required for s3:// sources)")
    if not (config.s3_access_key and config.s3_secret_key):
        raise GxWorkerConfigError(
            "Missing S3 credentials for s3:// sources (set DQ_S3_ACCESS_KEY/DQ_S3_SECRET_KEY or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)"
        )


def _coerce_source_location(version_payload: dict[str, Any], *, data_object_version_id: str) -> SourceLocation:
    storage_uri = str(version_payload.get("storage_uri") or "").strip()
    storage_format = str(version_payload.get("storage_format") or "").strip().lower()
    storage_options = version_payload.get("storage_options_json")

    if not storage_uri:
        raise GxWorkerExecutionError(
            f"Missing storage_uri for data_object_version_id '{data_object_version_id}'",
            failure_code="GX_WORKER_MISSING_SOURCE_LOCATION",
        )
    if not storage_format:
        raise GxWorkerExecutionError(
            f"Missing storage_format for data_object_version_id '{data_object_version_id}'",
            failure_code="GX_WORKER_MISSING_SOURCE_LOCATION",
        )
    if storage_format not in {"parquet", "delta"}:
        raise GxWorkerExecutionError(
            f"Unsupported storage_format '{storage_format}' for data_object_version_id '{data_object_version_id}'",
            failure_code="GX_WORKER_UNSUPPORTED_STORAGE_FORMAT",
        )

    options: dict[str, Any] = {}
    if isinstance(storage_options, dict):
        options = dict(storage_options)

    return SourceLocation(uri=storage_uri, format=storage_format, options=options)


def _extract_source_overrides(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_overrides = payload.get("source_overrides_by_data_object_version_id") or payload.get("source_overrides")
    overrides_by_target: dict[str, dict[str, Any]] = {}
    if isinstance(raw_overrides, dict):
        for key, value in raw_overrides.items():
            target_id = str(key).strip()
            if not target_id or not isinstance(value, dict):
                continue
            overrides_by_target[target_id] = dict(value)
    return overrides_by_target


def _column_is_available(df_columns: set[str], column_name: str) -> bool:
    normalized = str(column_name or "").strip()
    if not normalized:
        return False
    if normalized in df_columns:
        return True
    if "." in normalized:
        return normalized.split(".", 1)[0] in df_columns
    return False


def _build_spark_row_condition_expression(
    *,
    row_condition: Any,
    functions_module: Any,
    df_columns: set[str],
) -> Any:
    if isinstance(row_condition, str):
        return functions_module.expr(row_condition)

    if not isinstance(row_condition, dict):
        raise GxWorkerExecutionError(
            "Expectation row_condition must be a string or object",
            failure_code="GX_WORKER_INVALID_EXPECTATION",
        )

    condition_type = str(row_condition.get("type") or "").strip().lower()
    if not condition_type:
        raise GxWorkerExecutionError(
            "Expectation row_condition is missing type",
            failure_code="GX_WORKER_INVALID_EXPECTATION",
        )

    if condition_type == "pass_through":
        pass_through_filter = str(row_condition.get("pass_through_filter") or "").strip()
        if not pass_through_filter:
            raise GxWorkerExecutionError(
                "Expectation pass-through row_condition is missing pass_through_filter",
                failure_code="GX_WORKER_INVALID_EXPECTATION",
            )
        return functions_module.expr(pass_through_filter)

    if condition_type in {"and", "or"}:
        raw_conditions = row_condition.get("conditions")
        if not isinstance(raw_conditions, list) or not raw_conditions:
            raise GxWorkerExecutionError(
                f"Expectation row_condition '{condition_type}' requires a non-empty conditions list",
                failure_code="GX_WORKER_INVALID_EXPECTATION",
            )
        expressions = [
            _build_spark_row_condition_expression(
                row_condition=item,
                functions_module=functions_module,
                df_columns=df_columns,
            )
            for item in raw_conditions
        ]
        combined = expressions[0]
        for expression in expressions[1:]:
            combined = combined & expression if condition_type == "and" else combined | expression
        return combined

    raw_column = row_condition.get("column")
    column_name = str(raw_column.get("name") or "").strip() if isinstance(raw_column, dict) else ""
    if not column_name:
        raise GxWorkerExecutionError(
            "Expectation row_condition is missing column.name",
            failure_code="GX_WORKER_INVALID_EXPECTATION",
        )
    if not _column_is_available(df_columns, column_name):
        raise GxWorkerExecutionError(
            f"Expectation row_condition references unknown column '{column_name}'",
            failure_code="GX_WORKER_INVALID_EXPECTATION",
        )

    column_expr = functions_module.col(column_name)

    if condition_type == "nullity":
        is_null = row_condition.get("is_null")
        if not isinstance(is_null, bool):
            raise GxWorkerExecutionError(
                "Expectation nullity row_condition requires boolean is_null",
                failure_code="GX_WORKER_INVALID_EXPECTATION",
            )
        return column_expr.isNull() if is_null else column_expr.isNotNull()

    if condition_type != "comparison":
        raise GxWorkerExecutionError(
            f"Unsupported row_condition type '{condition_type}'",
            failure_code="GX_WORKER_INVALID_EXPECTATION",
        )

    operator = str(row_condition.get("operator") or "").strip().upper()
    parameter = row_condition.get("parameter")
    if operator == "==":
        return column_expr == functions_module.lit(parameter)
    if operator == "!=":
        return column_expr != functions_module.lit(parameter)
    if operator == ">":
        return column_expr > functions_module.lit(parameter)
    if operator == ">=":
        return column_expr >= functions_module.lit(parameter)
    if operator == "<":
        return column_expr < functions_module.lit(parameter)
    if operator == "<=":
        return column_expr <= functions_module.lit(parameter)
    if operator == "IN":
        if not isinstance(parameter, list):
            raise GxWorkerExecutionError(
                "Expectation row_condition operator IN requires list parameter",
                failure_code="GX_WORKER_INVALID_EXPECTATION",
            )
        return column_expr.isin(parameter)
    if operator == "NOT_IN":
        if not isinstance(parameter, list):
            raise GxWorkerExecutionError(
                "Expectation row_condition operator NOT_IN requires list parameter",
                failure_code="GX_WORKER_INVALID_EXPECTATION",
            )
        return ~column_expr.isin(parameter)

    raise GxWorkerExecutionError(
        f"Unsupported row_condition comparison operator '{operator}'",
        failure_code="GX_WORKER_INVALID_EXPECTATION",
    )


def _infer_materialized_source_location(*, output_location: str) -> SourceLocation:
    normalized_uri = _normalize_s3_uri(str(output_location or "").strip())
    if not normalized_uri:
        raise GxWorkerExecutionError(
            "GX join_pair execution requires source_materialization.output_location",
            failure_code="GX_WORKER_MISSING_SOURCE_LOCATION",
        )

    format_match = _MATERIALIZED_FORMAT_RE.search(normalized_uri)
    if format_match is None:
        raise GxWorkerExecutionError(
            "GX join_pair source_materialization.output_location must include '/format=parquet' or '/format=delta'",
            failure_code="GX_WORKER_INVALID_SOURCE_LOCATION",
        )

    return SourceLocation(uri=normalized_uri, format=str(format_match.group(1)).lower(), options={})


def _resolve_join_pair_location(
    *,
    payload: dict[str, Any],
    envelope: dict[str, Any],
    target_ids: list[str],
) -> SourceLocation:
    overrides_by_target = _extract_source_overrides(payload)
    override_candidates: list[SourceLocation] = []
    for target_id in target_ids:
        override = overrides_by_target.get(target_id)
        if override is None:
            continue
        uri = str(override.get("uri") or "").strip()
        fmt = str(override.get("format") or "").strip().lower()
        options_raw = override.get("options")
        if not uri or not fmt:
            raise GxWorkerExecutionError(
                "GX dispatch join_pair source override is missing required fields (uri/format)",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        if fmt not in {"parquet", "delta"}:
            raise GxWorkerExecutionError(
                f"GX dispatch join_pair source override has unsupported format '{fmt}'",
                failure_code="GX_WORKER_UNSUPPORTED_STORAGE_FORMAT",
            )
        if options_raw is not None and not isinstance(options_raw, dict):
            raise GxWorkerExecutionError(
                "GX dispatch join_pair source override options must be an object",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        override_candidates.append(SourceLocation(uri=uri, format=fmt, options=dict(options_raw or {})))

    if override_candidates:
        first = override_candidates[0]
        distinct = {(item.uri, item.format, json.dumps(item.options, sort_keys=True)) for item in override_candidates}
        if len(distinct) > 1:
            raise GxWorkerExecutionError(
                "GX join_pair execution received conflicting source overrides across targets",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        return first

    execution_contract = envelope.get("execution_contract") if isinstance(envelope.get("execution_contract"), dict) else None
    source_materialization = execution_contract.get("source_materialization") if isinstance(execution_contract, dict) else None
    if not isinstance(source_materialization, dict):
        raise GxWorkerExecutionError(
            "GX join_pair execution requires source_materialization in the suite execution contract",
            failure_code="GX_WORKER_MISSING_SOURCE_LOCATION",
        )

    return _infer_materialized_source_location(output_location=str(source_materialization.get("output_location") or ""))


def _resolve_join_pair_report_storage_uri(
    *,
    payload: dict[str, Any],
    envelope: dict[str, Any],
    target_ids: list[str],
    join_pair_location: SourceLocation,
) -> str:
    overrides_by_target = _extract_source_overrides(payload)
    for target_id in target_ids:
        override = overrides_by_target.get(target_id)
        if not isinstance(override, dict):
            continue
        override_uri = str(override.get("uri") or "").strip()
        if override_uri:
            return override_uri

    execution_contract = envelope.get("execution_contract") if isinstance(envelope.get("execution_contract"), dict) else None
    source_materialization = execution_contract.get("source_materialization") if isinstance(execution_contract, dict) else None
    if isinstance(source_materialization, dict):
        output_location = str(source_materialization.get("output_location") or "").strip()
        if output_location:
            return output_location

    return join_pair_location.uri


def _build_execution_progress(
    *,
    completed_steps: int,
    total_steps: int,
    label: str,
) -> dict[str, Any]:
    percent = 0 if total_steps <= 0 else int(round((completed_steps / total_steps) * 100))
    return {
        "percent": max(0, min(percent, 100)),
        "label": label,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "source": "dq-engine-gx-worker",
        "updated_at": _utc_now_iso(),
    }


def _api_report_execution_progress(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    run_id: str,
    correlation_id: str,
    changed_by: str | None,
    reason: str,
    details: dict[str, Any] | None,
    completed_steps: int,
    total_steps: int,
    label: str,
) -> None:
    _api_report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="running",
        changed_by=changed_by,
        reason=reason,
        details=details,
        execution_progress=_build_execution_progress(
            completed_steps=completed_steps,
            total_steps=total_steps,
            label=label,
        ),
    )


def _resolve_locations_for_targets(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    correlation_id: str,
    target_ids: list[str],
    payload: dict[str, Any],
) -> dict[str, SourceLocation]:
    locations_by_target: dict[str, SourceLocation] = {}
    overrides_by_target = _extract_source_overrides(payload)

    for target_id in target_ids:
        override = overrides_by_target.get(target_id)
        if override is None:
            continue
        uri = str(override.get("uri") or "").strip()
        fmt = str(override.get("format") or "").strip().lower()
        options_raw = override.get("options")
        if not uri or not fmt:
            raise GxWorkerExecutionError(
                "GX dispatch source override is missing required fields (uri/format)",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        if fmt not in {"parquet", "delta"}:
            raise GxWorkerExecutionError(
                f"GX dispatch source override has unsupported format '{fmt}'",
                failure_code="GX_WORKER_UNSUPPORTED_STORAGE_FORMAT",
            )
        if options_raw is not None and not isinstance(options_raw, dict):
            raise GxWorkerExecutionError(
                "GX dispatch source override options must be an object",
                failure_code="GX_WORKER_INVALID_SOURCE_OVERRIDE",
            )
        locations_by_target[target_id] = SourceLocation(uri=uri, format=fmt, options=dict(options_raw or {}))

    for target_id in target_ids:
        if target_id in locations_by_target:
            continue
        version_payload = _api_get_data_object_version(
            config,
            token_provider,
            version_id=target_id,
            correlation_id=correlation_id,
        )
        locations_by_target[target_id] = _coerce_source_location(version_payload, data_object_version_id=target_id)

    return locations_by_target


def _spark_read_dataset(spark_session: Any, *, location: SourceLocation, max_rows: int) -> Any:
    uri = str(location.uri or "").strip()

    reader = spark_session.read
    for key, value in (location.options or {}).items():
        if value is None:
            continue
        reader = reader.option(str(key), str(value))

    if location.format == "parquet":
        df = reader.parquet(uri)
    elif location.format == "delta":
        df = reader.format("delta").load(uri)
    else:
        raise GxWorkerExecutionError(
            f"Unsupported storage_format '{location.format}'",
            failure_code="GX_WORKER_UNSUPPORTED_STORAGE_FORMAT",
        )

    if max_rows and max_rows > 0:
        df = df.limit(int(max_rows))
    return df


_NATIVE_GX_EXPECTATION_TYPES = {
    "expect_table_row_count_to_be_between",
    "expect_compound_columns_to_be_unique",
    "expect_column_values_to_not_be_null",
    "expect_column_values_to_be_null",
    "expect_column_values_to_be_in_set",
    "expect_column_values_to_not_be_in_set",
    "expect_column_values_to_be_between",
    "expect_column_values_to_not_be_between",
    "expect_column_values_to_match_regex",
    "expect_column_values_to_not_match_regex",
    "expect_column_values_to_be_unique",
    "expect_column_pair_values_to_be_equal",
    "expect_column_proportion_of_non_null_values_to_be_between",
}


def _is_real_spark_dataframe(df: Any) -> bool:
    return str(getattr(df.__class__, "__module__", "")).startswith("pyspark.")


def _supports_native_gx_execution(expectation_type: str) -> bool:
    return expectation_type in _NATIVE_GX_EXPECTATION_TYPES


def _collect_row_condition_columns(row_condition: Any) -> list[str]:
    if isinstance(row_condition, str) or row_condition is None:
        return []
    if not isinstance(row_condition, dict):
        return []

    condition_type = str(row_condition.get("type") or "").strip().lower()
    if condition_type in {"and", "or"}:
        raw_conditions = row_condition.get("conditions")
        if not isinstance(raw_conditions, list):
            return []
        columns: list[str] = []
        for item in raw_conditions:
            columns.extend(_collect_row_condition_columns(item))
        return columns

    raw_column = row_condition.get("column")
    if isinstance(raw_column, dict):
        column_name = str(raw_column.get("name") or "").strip()
        return [column_name] if column_name else []
    return []


def _required_columns_for_expectation(expectation_type: str, kwargs: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    if expectation_type == "expect_compound_columns_to_be_unique":
        raw_columns = kwargs.get("columns")
        if isinstance(raw_columns, list):
            columns.extend(str(value).strip() for value in raw_columns if str(value).strip())
    elif expectation_type == "expect_column_pair_values_to_be_equal":
        for key in ("column_A", "column_B"):
            value = str(kwargs.get(key) or "").strip()
            if value:
                columns.append(value)
    else:
        column = str(kwargs.get("column") or "").strip()
        if column:
            columns.append(column)
    columns.extend(_collect_row_condition_columns(kwargs.get("row_condition")))
    deduplicated: list[str] = []
    for column_name in columns:
        if column_name and column_name not in deduplicated:
            deduplicated.append(column_name)
    return deduplicated


def _native_gx_requires_column_projection(expectation_type: str, kwargs: dict[str, Any]) -> bool:
    return any("." in column_name for column_name in _required_columns_for_expectation(expectation_type, kwargs))


def _build_native_gx_alias_map(columns: list[str]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    used_aliases: set[str] = set()
    for idx, column_name in enumerate(columns):
        normalized = re.sub(r"[^0-9A-Za-z_]+", "_", str(column_name or "")).strip("_") or "column"
        candidate = f"dq_native_{normalized}"
        while candidate in used_aliases:
            candidate = f"dq_native_{normalized}_{idx}"
            idx += 1
        alias_map[column_name] = candidate
        used_aliases.add(candidate)
    return alias_map


def _rewrite_native_gx_row_condition_for_aliases(
    row_condition: Any,
    alias_map: Mapping[str, str],
) -> Any:
    if row_condition is None or isinstance(row_condition, str):
        return row_condition
    if not isinstance(row_condition, dict):
        return row_condition

    rewritten = dict(row_condition)
    condition_type = str(row_condition.get("type") or "").strip().lower()
    if condition_type in {"and", "or"}:
        raw_conditions = row_condition.get("conditions")
        if isinstance(raw_conditions, list):
            rewritten["conditions"] = [
                _rewrite_native_gx_row_condition_for_aliases(item, alias_map)
                for item in raw_conditions
            ]
        return rewritten

    raw_column = row_condition.get("column")
    if isinstance(raw_column, dict):
        column_name = str(raw_column.get("name") or "").strip()
        rewritten_name = alias_map.get(column_name)
        if rewritten_name:
            rewritten["column"] = {
                **raw_column,
                "name": rewritten_name,
            }
    return rewritten


def _rewrite_native_gx_expectation_for_aliases(
    expectation: dict[str, Any],
    alias_map: Mapping[str, str],
) -> dict[str, Any]:
    kwargs = dict(expectation.get("kwargs") or {})
    rewritten_kwargs: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key in {"column", "column_A", "column_B"}:
            text_value = str(value or "").strip()
            rewritten_kwargs[key] = alias_map.get(text_value, text_value)
            continue
        if key == "columns" and isinstance(value, list):
            rewritten_kwargs[key] = [alias_map.get(str(item or "").strip(), str(item or "").strip()) for item in value]
            continue
        if key == "row_condition":
            rewritten_kwargs[key] = _rewrite_native_gx_row_condition_for_aliases(value, alias_map)
            continue
        rewritten_kwargs[key] = value

    return {
        **expectation,
        "kwargs": rewritten_kwargs,
    }


def _lower_native_gx_row_condition(row_condition: Any) -> Any:
    if row_condition is None or isinstance(row_condition, str):
        return row_condition
    if not isinstance(row_condition, dict):
        raise GxWorkerExecutionError(
            "Expectation row_condition must be a string or object",
            failure_code="GX_WORKER_INVALID_EXPECTATION",
        )

    try:
        row_conditions_module = importlib.import_module("great_expectations.expectations.row_conditions")
    except ModuleNotFoundError as exc:
        raise GxWorkerExecutionError(
            "Great Expectations row_conditions module is unavailable in dq-engine",
            failure_code="GX_WORKER_EXECUTION_ERROR",
        ) from exc

    deserialize_row_condition = getattr(row_conditions_module, "deserialize_row_condition", None)
    if not callable(deserialize_row_condition):
        raise GxWorkerExecutionError(
            "Great Expectations row_condition deserializer is unavailable in dq-engine",
            failure_code="GX_WORKER_EXECUTION_ERROR",
        )
    try:
        return deserialize_row_condition(dict(row_condition))
    except Exception as exc:
        raise GxWorkerExecutionError(
            f"Failed to lower GX row_condition: {exc}",
            failure_code="GX_WORKER_INVALID_EXPECTATION",
        ) from exc


class _NativeGxBatchRunner:
    def __init__(self, df: Any) -> None:
        self._df = df
        self._context: Any | None = None
        self._batches: dict[tuple[str, ...], Any] = {}

    def _get_context(self) -> Any:
        if self._context is not None:
            return self._context
        try:
            import great_expectations as gx
        except ModuleNotFoundError as exc:
            raise GxWorkerExecutionError(
                "great_expectations is not installed in dq-engine",
                failure_code="GX_WORKER_EXECUTION_ERROR",
            ) from exc

        self._context = gx.get_context(mode="ephemeral")
        return self._context

    def _get_batch(self, *, batch_key: tuple[str, ...], df: Any) -> Any:
        cached = self._batches.get(batch_key)
        if cached is not None:
            return cached

        try:
            context = self._get_context()
            datasource = context.data_sources.add_or_update_spark("dq_worker_runtime")
            asset = datasource.add_dataframe_asset(f"execution_data_{len(self._batches)}")
            batch_definition = asset.add_batch_definition_whole_dataframe("batch")
            batch = batch_definition.get_batch(batch_parameters={"dataframe": df})
        except Exception as exc:
            raise GxWorkerExecutionError(
                f"Failed to initialize native GX Spark batch: {exc}",
                failure_code="GX_WORKER_EXECUTION_ERROR",
            ) from exc
        self._batches[batch_key] = batch
        return batch

    def validate(self, expectation: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
        from great_expectations.expectations import registry
        from pyspark.sql import functions as F

        expectation_type = str(expectation.get("expectation_type") or "").strip()
        expectation_class = registry.get_expectation_impl(expectation_type)
        if expectation_class is None:
            raise GxWorkerExecutionError(
                f"Native GX expectation '{expectation_type}' is not registered",
                failure_code="GX_WORKER_UNSUPPORTED_EXPECTATION",
            )

        prepared_expectation = expectation
        batch_key: tuple[str, ...] = tuple()
        batch_df = self._df
        kwargs = dict(prepared_expectation.get("kwargs") or {})
        row_condition = kwargs.get("row_condition")
        if _native_gx_requires_column_projection(expectation_type, kwargs) and not isinstance(row_condition, str):
            required_columns = _required_columns_for_expectation(expectation_type, kwargs)
            alias_map = _build_native_gx_alias_map(required_columns)
            batch_key = tuple(required_columns)
            batch_df = self._df.select(*[F.col(column_name).alias(alias_map[column_name]) for column_name in required_columns])
            prepared_expectation = _rewrite_native_gx_expectation_for_aliases(expectation, alias_map)
            kwargs = dict(prepared_expectation.get("kwargs") or {})

        if "row_condition" in kwargs:
            kwargs["row_condition"] = _lower_native_gx_row_condition(kwargs.get("row_condition"))
        meta = prepared_expectation.get("meta") if isinstance(prepared_expectation.get("meta"), dict) else None

        try:
            gx_expectation = expectation_class(meta=dict(meta) if meta else None, **kwargs)
            result = self._get_batch(batch_key=batch_key, df=batch_df).validate(gx_expectation)
        except Exception as exc:
            raise GxWorkerExecutionError(
                f"Native GX validation failed for '{expectation_type}': {exc}",
                failure_code="GX_WORKER_EXECUTION_ERROR",
            ) from exc

        if bool(result.success):
            return True, None

        payload = result.result if isinstance(result.result, dict) else None
        return False, {
            "reason": "expectation_failed",
            "expectation_type": expectation_type,
            "message": "Expectation failed",
            "gx_result": payload,
        }


def _row_to_mapping(row: Any) -> dict[str, Any] | None:
    if isinstance(row, dict):
        return row

    as_dict = getattr(row, "asDict", None)
    if callable(as_dict):
        try:
            mapped = as_dict(recursive=True)
        except TypeError:
            mapped = as_dict()
        if isinstance(mapped, dict):
            return mapped

    as_dict = getattr(row, "_asdict", None)
    if callable(as_dict):
        mapped = as_dict()
        if isinstance(mapped, dict):
            return mapped

    return None


def _resolve_row_value(row: Any, field_name: str) -> Any:
    current: Any = row
    for part in str(field_name).split("."):
        current_mapping = _row_to_mapping(current)
        if current_mapping is None:
            return None
        current = current_mapping.get(part)
    return current


def _build_row_identifier(row: Any, primary_key_fields: list[str]) -> str | None:
    if _row_to_mapping(row) is None or not primary_key_fields:
        return None

    parts: list[str] = []
    for field_name in primary_key_fields:
        value = _resolve_row_value(row, field_name)
        if value is None:
            return None
        parts.append(f"{field_name}={value}")
    return "|".join(parts) if parts else None


def _first_row_identifier(df: Any, failure_condition: Any, primary_key_fields: list[str]) -> str | None:
    if not primary_key_fields or failure_condition is None:
        return None

    failing_rows = df.where(failure_condition).limit(1).take(1)
    if not failing_rows:
        return None
    return _build_row_identifier(failing_rows[0], primary_key_fields)


def _build_row_failure_diagnostics(
    df: Any,
    failure_condition: Any,
    *,
    primary_key_fields: list[str],
    expectation_index: int,
    expectation_type: str,
    column: str,
    message: str,
) -> list[dict[str, Any]]:
    failing_rows = df.where(failure_condition).collect()
    diagnostics: list[dict[str, Any]] = []
    for row in failing_rows:
        row_identifier = _build_row_identifier(row, primary_key_fields)
        if not row_identifier:
            continue
        diagnostics.append(
            {
                "reason": "expectation_failed",
                "expectation_index": expectation_index,
                "expectation_type": expectation_type,
                "column": column,
                "message": message,
                "row_identifier": row_identifier,
                "data_primary_key": row_identifier,
            }
        )
    return diagnostics


def _evaluate_expectations_spark(
    df: Any, expectations: list[dict[str, Any]], *, primary_key_fields: list[str] | None = None
) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
    functions_module: Any | None = None

    def _get_functions_module() -> Any:
        nonlocal functions_module
        if functions_module is None:
            functions_module = _resolve_spark_functions_module()
        return functions_module

    diagnostics: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    started_at = _utc_now_iso()

    computed_row_counts: dict[int, int] = {}
    normalized_primary_key_fields = [str(value).strip() for value in (primary_key_fields or []) if str(value).strip()]

    def _get_row_count(frame: Any) -> int:
        frame_key = id(frame)
        if frame_key not in computed_row_counts:
            computed_row_counts[frame_key] = int(frame.count())
        return computed_row_counts[frame_key]

    df_columns = set(getattr(df, "columns", []) or [])
    native_gx_runner = _NativeGxBatchRunner(df) if _is_real_spark_dataframe(df) and not normalized_primary_key_fields else None

    for idx, exp in enumerate(expectations):
        expectation_type = str(exp.get("expectation_type") or "").strip()
        kwargs = exp.get("kwargs") if isinstance(exp.get("kwargs"), dict) else {}

        if native_gx_runner is not None and _supports_native_gx_execution(expectation_type):
            missing_columns = [
                column_name
                for column_name in _required_columns_for_expectation(expectation_type, kwargs)
                if not _column_is_available(df_columns, column_name)
            ]
            if missing_columns:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "columns": missing_columns,
                        "message": f"Column(s) missing: {', '.join(missing_columns)}",
                    }
                )
                continue

            ok, native_failure = native_gx_runner.validate(exp)
            if ok:
                passed += 1
            else:
                failed += 1
                diagnostics.append(
                    {
                        "expectation_index": idx,
                        **(native_failure or {
                            "reason": "expectation_failed",
                            "expectation_type": expectation_type,
                            "message": "Expectation failed",
                        }),
                    }
                )
            continue

        row_condition = kwargs.get("row_condition")
        scoped_df = df
        if row_condition is not None:
            functions_module = _get_functions_module()
            scoped_df = df.where(
                _build_spark_row_condition_expression(
                    row_condition=row_condition,
                    functions_module=functions_module,
                    df_columns=df_columns,
                )
            )

        if expectation_type == "expect_table_row_count_to_be_between":
            min_value = kwargs.get("min_value")
            max_value = kwargs.get("max_value")
            if min_value is None or max_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires min_value and max_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            row_count = _get_row_count(scoped_df)
            ok = int(min_value) <= row_count <= int(max_value)
            if ok:
                passed += 1
            else:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "expectation_failed",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "row_count": row_count,
                        "min_value": min_value,
                        "max_value": max_value,
                        "message": "Row count expectation failed",
                    }
                )
            continue

        if expectation_type == "expect_compound_columns_to_be_unique":
            F = _get_functions_module()
            columns = kwargs.get("columns")
            if not isinstance(columns, list) or not columns:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires columns list",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            missing_columns = [str(value).strip() for value in columns if str(value).strip() and str(value).strip() not in df_columns]
            if missing_columns:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "columns": missing_columns,
                        "message": f"Column(s) missing: {', '.join(missing_columns)}",
                    }
                )
                continue
            has_failure = bool(scoped_df.groupBy(*columns).count().where(F.col("count") > 1).limit(1).take(1))
            if not has_failure:
                passed += 1
            else:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "expectation_failed",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "columns": list(columns),
                        "message": "Expectation failed",
                    }
                )
            continue

        if expectation_type == "expect_query_results_to_match_comparison":
            try:
                ok, native_failure = _NativeGxBatchRunner(df).validate(exp)
            except GxWorkerExecutionError:
                raise
            except Exception as exc:
                raise GxWorkerExecutionError(
                    f"Native GX validation failed for '{expectation_type}': {exc}",
                    failure_code="GX_WORKER_EXECUTION_ERROR",
                ) from exc
            if ok:
                passed += 1
            else:
                failed += 1
                diagnostics.append(
                    {
                        "expectation_index": idx,
                        **(native_failure or {
                            "reason": "expectation_failed",
                            "expectation_type": expectation_type,
                            "message": "Expectation failed",
                        }),
                    }
                )
            continue

        F = _get_functions_module()
        column = str(kwargs.get("column") or kwargs.get("column_A") or "").strip()
        if not column:
            raise GxWorkerExecutionError(
                f"Expectation '{expectation_type}' missing column",
                failure_code="GX_WORKER_INVALID_EXPECTATION",
            )

        if not _column_is_available(df_columns, column):
            failed += 1
            row_identifier = _first_row_identifier(scoped_df, F.lit(True), normalized_primary_key_fields)
            diagnostics.append(
                {
                    "reason": "missing_column",
                    "expectation_index": idx,
                    "expectation_type": expectation_type,
                    "column": column,
                    "message": f"Column '{column}' not found",
                    **(
                        {
                            "row_identifier": row_identifier,
                            "data_primary_key": row_identifier,
                        }
                        if row_identifier
                        else {}
                    ),
                }
            )
            continue

        col = F.col(column)
        has_failure = False
        failure_condition = None

        if expectation_type == "expect_column_values_to_not_be_null":
            failure_condition = col.isNull()
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_unique":
            has_failure = bool(scoped_df.groupBy(column).count().where(F.col("count") > 1).limit(1).take(1))
        elif expectation_type == "expect_column_pair_values_to_be_equal":
            other_column = str(kwargs.get("column_B") or "").strip()
            left_column = str(kwargs.get("column_A") or column).strip()
            ignore_row_if = str(kwargs.get("ignore_row_if") or "both_values_are_missing").strip().lower()
            if not left_column or not other_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires column_A and column_B",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not _column_is_available(df_columns, left_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": left_column,
                        "message": f"Column '{left_column}' not found",
                    }
                )
                continue
            if not _column_is_available(df_columns, other_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": other_column,
                        "message": f"Column '{other_column}' not found",
                    }
                )
                continue

            left_col = F.col(left_column)
            right_col = F.col(other_column)
            if ignore_row_if == "both_values_are_missing":
                evaluated_rows = ~(left_col.isNull() & right_col.isNull())
            elif ignore_row_if == "either_value_is_missing":
                evaluated_rows = left_col.isNotNull() & right_col.isNotNull()
            elif ignore_row_if == "neither":
                evaluated_rows = F.lit(True)
            else:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' has unsupported ignore_row_if '{ignore_row_if}'",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            failure_condition = evaluated_rows & (left_col.isNull() | right_col.isNull() | (left_col != right_col))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_between_for_other_column_value":
            other_column = str(kwargs.get("other_column") or "").strip()
            other_value = kwargs.get("other_value")
            min_value = kwargs.get("min_value")
            max_value = kwargs.get("max_value")
            strict_min = bool(kwargs.get("strict_min"))
            strict_max = bool(kwargs.get("strict_max"))
            if not other_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_column",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if other_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if min_value is None and max_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires at least one of min_value or max_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not _column_is_available(df_columns, other_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": other_column,
                        "message": f"Column '{other_column}' not found",
                    }
                )
                continue

            other_col = F.col(other_column)
            context_matches = other_col == F.lit(other_value)
            in_range = F.lit(True)
            if min_value is not None:
                min_lit = F.lit(min_value)
                in_range = in_range & ((col > min_lit) if strict_min else (col >= min_lit))
            if max_value is not None:
                max_lit = F.lit(max_value)
                in_range = in_range & ((col < max_lit) if strict_max else (col <= max_lit))

            failure_condition = context_matches & (col.isNull() | (~in_range))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_in_set_for_other_column_value":
            other_column = str(kwargs.get("other_column") or "").strip()
            other_value = kwargs.get("other_value")
            value_set = kwargs.get("value_set")
            case_sensitive = bool(kwargs.get("case_sensitive", True))
            if not other_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_column",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if other_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not isinstance(value_set, list):
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires value_set list",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not _column_is_available(df_columns, other_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": other_column,
                        "message": f"Column '{other_column}' not found",
                    }
                )
                continue

            other_col = F.col(other_column)
            context_matches = other_col == F.lit(other_value)
            if case_sensitive:
                allowed = col.isin(value_set)
            else:
                normalized_values = [str(item).lower() for item in value_set]
                allowed = F.lower(col.cast("string")).isin(normalized_values)
            failure_condition = context_matches & (col.isNull() | (~allowed))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type in {
            "expect_column_values_to_equal_other_column",
            "expect_column_values_to_equal_other_column_case_insensitive",
            "expect_column_values_to_be_within_numeric_tolerance_of_other_column",
            "expect_column_timestamps_to_be_within_tolerance_of_other_column",
        }:
            other_column = str(kwargs.get("other_column") or "").strip()
            if not other_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires other_column",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if not _column_is_available(df_columns, other_column):
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": other_column,
                        "message": f"Column '{other_column}' not found",
                    }
                )
                continue

            other_col = F.col(other_column)
            if expectation_type == "expect_column_values_to_equal_other_column":
                failure_condition = col.isNull() | other_col.isNull() | (col != other_col)
            elif expectation_type == "expect_column_values_to_equal_other_column_case_insensitive":
                failure_condition = col.isNull() | other_col.isNull() | (F.lower(col.cast("string")) != F.lower(other_col.cast("string")))
            elif expectation_type == "expect_column_values_to_be_within_numeric_tolerance_of_other_column":
                tolerance = kwargs.get("tolerance")
                if tolerance is None:
                    raise GxWorkerExecutionError(
                        f"Expectation '{expectation_type}' requires tolerance",
                        failure_code="GX_WORKER_INVALID_EXPECTATION",
                    )
                failure_condition = col.isNull() | other_col.isNull() | (F.abs(col - other_col) > F.lit(float(tolerance)))
            else:
                max_difference = kwargs.get("max_difference")
                difference_unit = str(kwargs.get("difference_unit") or "").strip().lower()
                if max_difference is None:
                    raise GxWorkerExecutionError(
                        f"Expectation '{expectation_type}' requires max_difference",
                        failure_code="GX_WORKER_INVALID_EXPECTATION",
                    )
                if difference_unit not in {"minute", "minutes", "hour", "hours", "day", "days"}:
                    raise GxWorkerExecutionError(
                        f"Expectation '{expectation_type}' has unsupported difference_unit '{difference_unit}'",
                        failure_code="GX_WORKER_INVALID_EXPECTATION",
                    )
                divisor = 60.0 if difference_unit.startswith("minute") else 3600.0 if difference_unit.startswith("hour") else 86400.0
                left_ts = F.to_timestamp(col)
                right_ts = F.to_timestamp(other_col)
                difference = F.abs(F.unix_timestamp(left_ts) - F.unix_timestamp(right_ts)) / F.lit(divisor)
                failure_condition = left_ts.isNull() | right_ts.isNull() | (difference > F.lit(float(max_difference)))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_null":
            failure_condition = col.isNotNull()
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_proportion_of_non_null_values_to_be_between":
            min_value = kwargs.get("min_value")
            max_value = kwargs.get("max_value")
            strict_min = bool(kwargs.get("strict_min"))
            strict_max = bool(kwargs.get("strict_max"))
            row_count = int(scoped_df.count())
            if row_count <= 0:
                proportion = 0.0
            else:
                non_null_count = int(scoped_df.where(col.isNotNull()).count())
                proportion = float(non_null_count) / float(row_count)
            lower_ok = True if min_value is None else proportion > float(min_value) if strict_min else proportion >= float(min_value)
            upper_ok = True if max_value is None else proportion < float(max_value) if strict_max else proportion <= float(max_value)
            has_failure = not (lower_ok and upper_ok)
        elif expectation_type == "expect_column_values_to_be_in_set":
            value_set = kwargs.get("value_set")
            if not isinstance(value_set, list):
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires value_set list",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            failure_condition = col.isNotNull() & (~col.isin(value_set))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_not_be_in_set":
            value_set = kwargs.get("value_set")
            if not isinstance(value_set, list):
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires value_set list",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            failure_condition = col.isNotNull() & (col.isin(value_set))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type in {"expect_column_values_to_be_between", "expect_column_values_to_not_be_between"}:
            min_value = kwargs.get("min_value")
            max_value = kwargs.get("max_value")
            strict_min = bool(kwargs.get("strict_min"))
            strict_max = bool(kwargs.get("strict_max"))
            if min_value is None and max_value is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires at least one of min_value or max_value",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            in_range = F.lit(True)
            if min_value is not None:
                min_lit = F.lit(min_value)
                in_range = in_range & ((col > min_lit) if strict_min else (col >= min_lit))
            if max_value is not None:
                max_lit = F.lit(max_value)
                in_range = in_range & ((col < max_lit) if strict_max else (col <= max_lit))

            if expectation_type == "expect_column_values_to_be_between":
                failure_condition = col.isNotNull() & (~in_range)
            else:
                failure_condition = col.isNotNull() & (in_range)
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type in {"expect_column_values_to_match_regex", "expect_column_values_to_not_match_regex"}:
            regex = str(kwargs.get("regex") or "")
            if not regex:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires regex",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            matches = col.cast("string").rlike(regex)
            if expectation_type == "expect_column_values_to_match_regex":
                failure_condition = col.isNull() | (~matches)
            else:
                failure_condition = col.isNotNull() & matches
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_be_within_past_days":
            max_days_old = kwargs.get("max_days_old")
            anchor = str(kwargs.get("anchor") or "now").strip().lower()
            if max_days_old is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires max_days_old",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if anchor != "now":
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' supports only anchor='now'",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            column_ts = F.to_timestamp(col)
            age_days = (F.unix_timestamp(F.current_timestamp()) - F.unix_timestamp(column_ts)) / F.lit(86400.0)
            failure_condition = column_ts.isNull() | (age_days > F.lit(float(max_days_old)))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_pair_values_to_have_max_lag_hours":
            start_column = str(kwargs.get("start_column") or "").strip()
            max_hours = kwargs.get("max_hours")
            if not start_column:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires start_column",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if max_hours is None:
                raise GxWorkerExecutionError(
                    f"Expectation '{expectation_type}' requires max_hours",
                    failure_code="GX_WORKER_INVALID_EXPECTATION",
                )
            if start_column not in df_columns:
                failed += 1
                diagnostics.append(
                    {
                        "reason": "missing_column",
                        "expectation_index": idx,
                        "expectation_type": expectation_type,
                        "column": start_column,
                        "message": f"Column '{start_column}' not found",
                    }
                )
                continue
            start_ts = F.to_timestamp(F.col(start_column))
            end_ts = F.to_timestamp(col)
            lag_hours = (F.unix_timestamp(end_ts) - F.unix_timestamp(start_ts)) / F.lit(3600.0)
            failure_condition = start_ts.isNull() | end_ts.isNull() | (lag_hours > F.lit(float(max_hours)))
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        elif expectation_type == "expect_column_values_to_not_be_in_future":
            reference_time = kwargs.get("reference_time")
            column_ts = F.to_timestamp(col)
            reference_ts = F.to_timestamp(F.lit(reference_time)) if reference_time is not None else F.current_timestamp()
            failure_condition = column_ts.isNull() | (column_ts > reference_ts)
            has_failure = bool(scoped_df.where(failure_condition).limit(1).take(1))
        else:
            raise GxWorkerExecutionError(
                f"Unsupported expectation_type '{expectation_type}'",
                failure_code="GX_WORKER_UNSUPPORTED_EXPECTATION",
            )

        ok = not has_failure
        if ok:
            passed += 1
        else:
            failed += 1
            if normalized_primary_key_fields and failure_condition is not None:
                row_diagnostics = _build_row_failure_diagnostics(
                    scoped_df,
                    failure_condition,
                    primary_key_fields=normalized_primary_key_fields,
                    expectation_index=idx,
                    expectation_type=expectation_type,
                    column=column,
                    message="Expectation failed",
                )
                if row_diagnostics:
                    diagnostics.extend(row_diagnostics)
                    continue

            row_identifier = _first_row_identifier(scoped_df, failure_condition, normalized_primary_key_fields)
            diagnostic = {
                "reason": "expectation_failed",
                "expectation_index": idx,
                "expectation_type": expectation_type,
                "column": column,
                "message": "Expectation failed",
            }
            if row_identifier:
                diagnostic["row_identifier"] = row_identifier
                diagnostic["data_primary_key"] = row_identifier
            diagnostics.append(diagnostic)

    completed_at = _utc_now_iso()
    summary = {
        "started_at": started_at,
        "completed_at": completed_at,
        "row_count": computed_row_counts.get(id(df)),
        "expectation_count": int(len(expectations)),
        "passed_expectation_count": int(passed),
        "failed_expectation_count": int(failed),
    }
    return failed == 0, summary, diagnostics


def _process_grouped_dispatch_message(
    config: GxWorkerConfig,
    *,
    payload: dict[str, Any],
    run_id: str,
    correlation_id: str,
    requested_by: str | None,
) -> None:
    logger = logging.getLogger(__name__)
    grouped_plan = payload.get("grouped_execution_plan") if isinstance(payload.get("grouped_execution_plan"), dict) else None
    if grouped_plan is None:
        raise GxWorkerExecutionError(
            "Grouped GX dispatch payload is missing grouped_execution_plan",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    batches = grouped_plan.get("batches")
    if not isinstance(batches, list) or not batches:
        raise GxWorkerExecutionError(
            "Grouped GX dispatch payload is missing execution batches",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    log_event(
        logger,
        "gx.worker.dispatch.received",
        component="dq-engine-gx-worker",
        correlation_id=correlation_id,
        run_id=run_id,
        execution_shape="grouped_scope",
        batch_count=grouped_plan.get("batch_count"),
        suite_count=grouped_plan.get("suite_count"),
    )

    token_provider = _build_token_provider()
    grouped_execution_started = time.perf_counter()
    total_steps = len(batches) + 1
    _api_report_execution_progress(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        changed_by=requested_by,
        reason="GX worker started grouped execution",
        details={"source": "dq-engine-gx-worker", "dispatch": payload},
        completed_steps=0,
        total_steps=total_steps,
        label="Queued for grouped execution",
    )

    target_ids = [
        str(batch.get("data_object_version_id") or "").strip()
        for batch in batches
        if isinstance(batch, dict)
    ]
    target_ids = [target_id for target_id in target_ids if target_id]
    if not target_ids:
        raise GxWorkerExecutionError(
            "Grouped GX dispatch payload does not define any data_object_version_id targets",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    locations_by_target = _resolve_locations_for_targets(
        config,
        token_provider,
        correlation_id=correlation_id,
        target_ids=target_ids,
        payload=payload,
    )

    _api_report_execution_progress(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        changed_by=requested_by,
        reason="GX worker resolved grouped execution inputs",
        details={"source": "dq-engine-gx-worker"},
        completed_steps=1,
        total_steps=total_steps,
        label=f"Resolved {len(batches)} grouped batches",
    )

    needs_delta = any(loc.format == "delta" for loc in locations_by_target.values())
    spark_session = _create_spark_session(config, enable_delta=needs_delta)
    tmpdirs: list[tempfile.TemporaryDirectory[str]] = []
    all_ok = True
    all_diagnostics: list[dict[str, Any]] = []
    batch_results: list[dict[str, Any]] = []
    total_suite_count = 0

    try:
        for batch_index, batch in enumerate(batches, start=1):
            if not isinstance(batch, dict):
                raise GxWorkerExecutionError(
                    "Grouped GX dispatch batch is invalid",
                    failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                )
            target_id = str(batch.get("data_object_version_id") or "").strip()
            if not target_id:
                raise GxWorkerExecutionError(
                    "Grouped GX dispatch batch is missing data_object_version_id",
                    failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                )
            suites = batch.get("suites")
            if not isinstance(suites, list) or not suites:
                raise GxWorkerExecutionError(
                    f"Grouped GX dispatch batch '{target_id}' does not include any suite envelopes",
                    failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                )

            batch_started_at = time.perf_counter()
            batch_ok = True
            location = locations_by_target[target_id]
            normalized_uri = _normalize_s3_uri(location.uri)
            _assert_supported_uri(normalized_uri)
            _require_s3_config_for_location(config, uri=normalized_uri)
            read_uri = normalized_uri
            if normalized_uri.startswith("s3a://"):
                tmpdir, localized_path = _download_s3a_prefix_to_tempdir(config, uri=normalized_uri)
                tmpdirs.append(tmpdir)
                read_uri = localized_path

            with traced_worker_span(
                "gx.worker.batch",
                component="dq-engine-gx-worker",
                correlation_id=correlation_id,
                run_id=run_id,
                execution_shape="grouped_scope",
                batch_index=batch_index,
                data_object_version_id=target_id,
                suite_count=len(suites),
            ):
                source_read_started_at = time.perf_counter()
                df = _spark_read_dataset(
                    spark_session,
                    location=SourceLocation(uri=read_uri, format=location.format, options=location.options),
                    max_rows=config.max_rows,
                )
                record_worker_duration(
                    stage="source_read",
                    execution_shape="grouped_scope",
                    duration_ms=(time.perf_counter() - source_read_started_at) * 1000.0,
                    result="success",
                    source_format=location.format,
                    batch_count=len(batches),
                    suite_count=len(suites),
                    target_count=1,
                )

                suite_results: list[dict[str, Any]] = []
                for suite_payload in suites:
                    if not isinstance(suite_payload, dict):
                        raise GxWorkerExecutionError(
                            f"Grouped GX dispatch batch '{target_id}' contains an invalid suite envelope",
                            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                        )
                    expectations, suite_targets, primary_key_fields = _assert_runnable_suite(suite_payload)
                    if target_id not in suite_targets:
                        raise GxWorkerExecutionError(
                            f"Grouped GX dispatch suite is not attached to target '{target_id}'",
                            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
                        )
                    ok, summary, diagnostics = _evaluate_expectations_spark(
                        df,
                        expectations,
                        primary_key_fields=primary_key_fields,
                    )
                    record_worker_expectation_results(
                        execution_shape="grouped_scope",
                        passed_count=int(summary.get("passed_expectation_count") or 0),
                        failed_count=int(summary.get("failed_expectation_count") or 0),
                    )
                    suite_id = str(suite_payload.get("suite_id") or "")
                    suite_version = int(suite_payload.get("suite_version") or 0)
                    compiled_from = suite_payload.get("compiled_from") if isinstance(suite_payload.get("compiled_from"), dict) else None
                    rule_ids = []
                    if isinstance(compiled_from, dict):
                        raw_rule_ids = compiled_from.get("rule_ids") or []
                        if isinstance(raw_rule_ids, list):
                            rule_ids = [str(item).strip() for item in raw_rule_ids if str(item).strip()]
                    suite_results.append(
                        {
                            "suite_id": suite_id,
                            "suite_version": suite_version,
                            "rule_ids": rule_ids,
                            "ok": ok,
                            "summary": summary,
                        }
                    )
                    total_suite_count += 1
                    if not ok:
                        batch_ok = False
                        all_ok = False
                    for diag in diagnostics:
                        diag["data_object_version_id"] = target_id
                        diag["storage_uri"] = normalized_uri
                        diag["storage_format"] = location.format
                        diag["suite_id"] = suite_id
                        diag["suite_version"] = suite_version
                        all_diagnostics.append(diag)

                batch_results.append(
                    {
                        "data_object_version_id": target_id,
                        "storage_uri": normalized_uri,
                        "storage_format": location.format,
                        "suite_count": len(suite_results),
                        "suite_results": suite_results,
                        "ok": batch_ok,
                    }
                )

                _api_report_execution_progress(
                    config,
                    token_provider,
                    run_id=run_id,
                    correlation_id=correlation_id,
                    changed_by=requested_by,
                    reason="GX worker evaluated a grouped batch",
                    details={"source": "dq-engine-gx-worker", "batch_index": batch_index},
                    completed_steps=batch_index + 1,
                    total_steps=total_steps,
                    label=f"Evaluated grouped batch {batch_index} of {len(batches)}",
                )

            record_worker_duration(
                stage="batch_execution",
                execution_shape="grouped_scope",
                duration_ms=(time.perf_counter() - batch_started_at) * 1000.0,
                result="success" if batch_ok else "failure",
                batch_count=len(batches),
                suite_count=len(suite_results),
                target_count=1,
            )
    finally:
        _safe_stop_spark_session(spark_session)
        for tmpdir in tmpdirs:
            tmpdir.cleanup()

    result_summary = {
        "selection_mode": "grouped_scope",
        "batch_count": len(batch_results),
        "suite_count": total_suite_count,
        "results": batch_results,
    }

    if all_ok:
        _api_report_run(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="succeeded",
            changed_by=requested_by,
            reason="GX worker completed grouped execution",
            details={"source": "dq-engine-gx-worker", "selection_mode": "grouped_scope"},
            execution_progress=_build_execution_progress(
                completed_steps=total_steps,
                total_steps=total_steps,
                label="Grouped execution completed",
            ),
            completed_at=_utc_now_iso(),
            result_summary=result_summary,
            diagnostics=[],
            failure_code=None,
            failure_message=None,
        )
        record_worker_duration(
            stage="dispatch",
            execution_shape="grouped_scope",
            duration_ms=(time.perf_counter() - grouped_execution_started) * 1000.0,
            result="success",
            batch_count=len(batch_results),
            suite_count=total_suite_count,
            target_count=len(target_ids),
        )
    else:
        _api_report_run(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="failed",
            changed_by=requested_by,
            reason="GX worker completed grouped execution with failures",
            details={"source": "dq-engine-gx-worker", "selection_mode": "grouped_scope", "failure_count": len(all_diagnostics)},
            execution_progress=_build_execution_progress(
                completed_steps=total_steps,
                total_steps=total_steps,
                label="Grouped execution completed with failures",
            ),
            completed_at=_utc_now_iso(),
            result_summary=result_summary,
            diagnostics=all_diagnostics,
            failure_code="GX_VALIDATION_FAILED",
            failure_message="One or more grouped-scope expectations failed",
        )
        record_worker_duration(
            stage="dispatch",
            execution_shape="grouped_scope",
            duration_ms=(time.perf_counter() - grouped_execution_started) * 1000.0,
            result="failure",
            batch_count=len(batch_results),
            suite_count=total_suite_count,
            target_count=len(target_ids),
        )


def _build_spark_expectations_report_summary(response_payload: dict[str, Any], *, output_dir: Any) -> dict[str, Any]:
    metrics = response_payload.get("metrics")
    return {
        "engine_type": "spark_expectations",
        "rule_id": response_payload.get("rule_id"),
        "result": response_payload.get("result", "passed"),
        "passed_count": response_payload.get("passed_count", 0),
        "failed_count": response_payload.get("failed_count", 0),
        "failure_code": response_payload.get("failure_code"),
        "failure_message": response_payload.get("failure_message"),
        "failed_check": response_payload.get("failed_check", {}),
        "failure_metrics": response_payload.get("failure_metrics", {}),
        "trace": response_payload.get("trace", {}),
        "summary": response_payload,
        "output_dir": output_dir,
        "execution_metadata": response_payload.get("execution_metadata", {}),
        "quarantine_artifact": response_payload.get("quarantine_artifact", {}),
        "error_management": response_payload.get("error_management", {}),
        "observability_summary": response_payload.get("observability_summary", {}),
        "metrics": metrics if isinstance(metrics, dict) else response_payload.get("observability_summary", {}),
    }


def _process_spark_expectations_dispatch_message(
    config: GxWorkerConfig,
    *,
    payload: dict[str, Any],
    run_id: str,
    correlation_id: str,
    requested_by: str | None,
) -> None:
    rule_payload = payload.get("rule_payload")
    if not isinstance(rule_payload, dict):
        raise GxWorkerExecutionError(
            "Spark Expectations dispatch payload is missing rule_payload",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    engine_type = _coerce_str(payload, "engine_type") or _coerce_str(rule_payload, "engine_type")
    if str(engine_type).strip().lower() != "spark_expectations":
        raise GxWorkerExecutionError(
            f"Unsupported Spark Expectations dispatch engine type: {engine_type!r}",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    raw_rule_id = rule_payload.get("id")
    try:
        rule_id = int(raw_rule_id) if raw_rule_id is not None else 0
    except Exception:
        rule_id = 0

    token_provider = _build_token_provider()
    spark_expectations_started = time.perf_counter()
    _api_report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="running",
        changed_by=requested_by,
        reason="GX worker routed Spark Expectations execution",
        details={"source": "dq-engine-gx-worker", "engine_type": "spark_expectations"},
        execution_progress=_build_execution_progress(
            completed_steps=1,
            total_steps=2,
            label="Invoking Spark Expectations execution endpoint",
        ),
        metrics={"engine_type": "spark_expectations", "stage": "started"},
    )

    execution_request = ExecuteRequest(
        id=rule_id,
        table=str(rule_payload.get("table") or ""),
        column=rule_payload.get("column"),
        type=str(rule_payload.get("type") or ""),
        params=rule_payload.get("params") if isinstance(rule_payload.get("params"), dict) else None,
        output_dir=str(payload.get("output_dir")) if payload.get("output_dir") is not None else None,
        engine_type="spark_expectations",
    )
    response_payload = execute_rule(execution_request)
    if not isinstance(response_payload, dict):
        raise GxWorkerExecutionError(
            "Spark Expectations execution failed",
            failure_code="GX_WORKER_EXECUTION_ERROR",
        )

    report_summary = _build_spark_expectations_report_summary(response_payload, output_dir=payload.get("output_dir"))
    report_details = {
        "source": "dq-engine-gx-worker",
        "engine_type": "spark_expectations",
        "rule_id": rule_id,
        "result": response_payload.get("result", "passed"),
        "passed_count": response_payload.get("passed_count", 0),
        "failed_count": response_payload.get("failed_count", 0),
        "execution_metadata": response_payload.get("execution_metadata", {}),
        "quarantine_artifact": response_payload.get("quarantine_artifact", {}),
        "error_management": response_payload.get("error_management", {}),
        "observability_summary": response_payload.get("observability_summary", {}),
        "output_dir": payload.get("output_dir"),
    }
    if not response_payload.get("ok"):
        failure_code = response_payload.get("failure_code") or "GX_WORKER_EXECUTION_ERROR"
        failure_message = response_payload.get("failure_message") or response_payload.get("error") or "Spark Expectations execution failed"
        report_details.update(
            {
                "failure_code": failure_code,
                "failure_message": failure_message,
                "failed_check": response_payload.get("failed_check", {}),
                "failure_metrics": response_payload.get("failure_metrics", {}),
                "trace": response_payload.get("trace", {}),
            }
        )
        record_spark_expectations_observability(
            observability_summary=response_payload.get("observability_summary"),
            result=response_payload.get("result", "failed"),
        )
        _api_report_execution_progress(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            changed_by=requested_by,
            reason="GX worker completed Spark Expectations execution with failures",
            details=report_details,
            completed_steps=2,
            total_steps=2,
            label="Spark Expectations execution completed with failures",
        )
        _api_report_run(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="failed",
            changed_by=requested_by,
            reason="GX worker completed Spark Expectations execution with failures",
            details=report_details,
            execution_progress=_build_execution_progress(
                completed_steps=2,
                total_steps=2,
                label="Spark Expectations execution completed with failures",
            ),
            completed_at=_utc_now_iso(),
            result_summary=report_summary,
            metrics=response_payload.get("metrics") if isinstance(response_payload.get("metrics"), dict) else response_payload.get("observability_summary", {}),
            diagnostics=[],
            failure_code=failure_code,
            failure_message=failure_message,
        )
        record_worker_duration(
            stage="dispatch",
            execution_shape="spark_expectations",
            duration_ms=(time.perf_counter() - spark_expectations_started) * 1000.0,
            result="failure",
            batch_count=1,
            suite_count=1,
            target_count=1,
        )
        return

    record_spark_expectations_observability(
        observability_summary=response_payload.get("observability_summary"),
        result=response_payload.get("result"),
    )

    _api_report_execution_progress(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        changed_by=requested_by,
        reason="GX worker completed Spark Expectations execution",
        details=report_details,
        completed_steps=2,
        total_steps=2,
        label="Spark Expectations execution completed",
    )

    _api_report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="succeeded",
        changed_by=requested_by,
        reason="GX worker completed Spark Expectations execution",
        details=report_details,
        execution_progress=_build_execution_progress(
            completed_steps=2,
            total_steps=2,
            label="Spark Expectations execution completed",
        ),
        completed_at=_utc_now_iso(),
        result_summary=report_summary,
        metrics=response_payload.get("metrics") if isinstance(response_payload.get("metrics"), dict) else response_payload.get("observability_summary", {}),
        diagnostics=[],
        failure_code=None,
        failure_message=None,
    )


def process_dispatch_message(config: GxWorkerConfig, *, raw_message: str) -> None:
    payload = _parse_dispatch_payload(raw_message)

    run_id = _coerce_str(payload, "run_id", "queue_message_id")
    execution_shape = _coerce_str(payload, "execution_shape") or "single_object"
    suite_id = _coerce_str(payload, "suite_id")
    suite_version = _coerce_int(payload, "suite_version")
    correlation_id = _coerce_str(payload, "correlation_id") or f"corr-{uuid4().hex[:12]}"
    requested_by = _coerce_str(payload, "requested_by") or None

    if execution_shape == "grouped_scope":
        if not run_id:
            raise GxWorkerExecutionError(
                "GX dispatch payload is missing required run_id for grouped execution",
                failure_code="GX_DISPATCH_INVALID_PAYLOAD",
            )
        _process_grouped_dispatch_message(
            config,
            payload=payload,
            run_id=run_id,
            correlation_id=correlation_id,
            requested_by=requested_by,
        )
        return

    if str(_coerce_str(payload, "engine_type") or "").strip().lower() == "spark_expectations":
        _process_spark_expectations_dispatch_message(
            config,
            payload=payload,
            run_id=run_id,
            correlation_id=correlation_id,
            requested_by=requested_by,
        )
        return

    if not run_id or not suite_id or suite_version <= 0:
        raise GxWorkerExecutionError(
            "GX dispatch payload is missing required identifiers (run_id/suite_id/suite_version)",
            failure_code="GX_DISPATCH_INVALID_PAYLOAD",
        )

    logger = logging.getLogger(__name__)
    log_event(
        logger,
        "gx.worker.dispatch.received",
        component="dq-engine-gx-worker",
        correlation_id=correlation_id,
        run_id=run_id,
        suite_id=suite_id,
        suite_version=suite_version,
    )

    # Mark the run as running via API (Kong -> FastAPI -> DB).
    token_provider = _build_token_provider()
    single_execution_started = time.perf_counter()

    _api_report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="running",
        changed_by=requested_by,
        reason="GX worker started execution",
        details={"source": "dq-engine-gx-worker", "dispatch": payload},
        execution_progress=_build_execution_progress(
            completed_steps=0,
            total_steps=1,
            label="Queued for execution",
        ),
        started_at=_utc_now_iso(),
    )

    envelope = _api_get_suite_envelope(
        config,
        token_provider,
        suite_id=suite_id,
        suite_version=suite_version,
        correlation_id=correlation_id,
    )
    expectations, target_ids, primary_key_fields = _assert_runnable_suite(envelope)

    # Optional scope override (adhoc runs may choose a subset of the resolved targets).
    raw_scope_override = payload.get("executionScopeOverride") or payload.get("execution_scope_override")
    if isinstance(raw_scope_override, list):
        normalized_override = [str(v).strip() for v in raw_scope_override if str(v).strip()]
        if normalized_override:
            missing = [v for v in normalized_override if v not in target_ids]
            if missing:
                raise GxWorkerExecutionError(
                    "GX dispatch executionScopeOverride contains target(s) not attached to the suite",
                    failure_code="GX_WORKER_INVALID_SCOPE_OVERRIDE",
                )
            target_ids = normalized_override

    if execution_shape == "join_pair":
        join_pair_location = _resolve_join_pair_location(
            payload=payload,
            envelope=envelope,
            target_ids=target_ids,
        )
        total_steps = 2
        _api_report_execution_progress(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            changed_by=requested_by,
            reason="GX worker resolved join-pair source",
            details={"source": "dq-engine-gx-worker", "execution_shape": "join_pair"},
            completed_steps=1,
            total_steps=total_steps,
            label="Resolved joined source materialization",
        )

        needs_delta = join_pair_location.format == "delta"
        spark_session = _create_spark_session(config, enable_delta=needs_delta)
        normalized_uri = _normalize_s3_uri(join_pair_location.uri)
        _assert_supported_uri(normalized_uri)
        _require_s3_config_for_location(config, uri=normalized_uri)

        tmpdirs: list[tempfile.TemporaryDirectory[str]] = []
        try:
            read_uri = normalized_uri
            if normalized_uri.startswith("s3a://"):
                tmpdir, localized_path = _download_s3a_prefix_to_tempdir(config, uri=normalized_uri)
                tmpdirs.append(tmpdir)
                read_uri = localized_path

            with traced_worker_span(
                "gx.worker.join_pair",
                component="dq-engine-gx-worker",
                correlation_id=correlation_id,
                run_id=run_id,
                suite_id=suite_id,
                suite_version=suite_version,
                execution_shape="join_pair",
            ):
                source_read_started_at = time.perf_counter()
                df = _spark_read_dataset(
                    spark_session,
                    location=SourceLocation(uri=read_uri, format=join_pair_location.format, options=join_pair_location.options),
                    max_rows=config.max_rows,
                )
                record_worker_duration(
                    stage="source_read",
                    execution_shape="join_pair",
                    duration_ms=(time.perf_counter() - source_read_started_at) * 1000.0,
                    result="success",
                    source_format=join_pair_location.format,
                    target_count=len(target_ids),
                )

                ok, summary, diagnostics = _evaluate_expectations_spark(
                    df,
                    expectations,
                    primary_key_fields=primary_key_fields,
                )
                record_worker_expectation_results(
                    execution_shape="join_pair",
                    passed_count=int(summary.get("passed_expectation_count") or 0),
                    failed_count=int(summary.get("failed_expectation_count") or 0),
                )

            _api_report_execution_progress(
                config,
                token_provider,
                run_id=run_id,
                correlation_id=correlation_id,
                changed_by=requested_by,
                reason="GX worker evaluated join-pair source",
                details={"source": "dq-engine-gx-worker", "execution_shape": "join_pair"},
                completed_steps=2,
                total_steps=total_steps,
                label="Evaluated joined source materialization",
            )
        finally:
            _safe_stop_spark_session(spark_session)
            for tmpdir in tmpdirs:
                tmpdir.cleanup()

        result_summary = {
            "suite_id": suite_id,
            "suite_version": suite_version,
            "target_count": len(target_ids),
            "results": [
                {
                    "data_object_version_id": target_ids[0] if target_ids else None,
                    "storage_uri": _resolve_join_pair_report_storage_uri(
                        payload=payload,
                        envelope=envelope,
                        target_ids=target_ids,
                        join_pair_location=join_pair_location,
                    ),
                    "storage_format": join_pair_location.format,
                    "ok": ok,
                    "summary": summary,
                }
            ],
        }
        if ok:
            _api_report_run(
                config,
                token_provider,
                run_id=run_id,
                correlation_id=correlation_id,
                new_status="succeeded",
                changed_by=requested_by,
                reason="GX worker completed join-pair execution",
                details={"source": "dq-engine-gx-worker", "execution_shape": "join_pair"},
                execution_progress=_build_execution_progress(
                    completed_steps=total_steps,
                    total_steps=total_steps,
                    label="Execution completed",
                ),
                completed_at=_utc_now_iso(),
                result_summary=result_summary,
                diagnostics=[],
                failure_code=None,
                failure_message=None,
            )
            record_worker_duration(
                stage="dispatch",
                execution_shape="join_pair",
                duration_ms=(time.perf_counter() - single_execution_started) * 1000.0,
                result="success",
                target_count=len(target_ids),
            )
        else:
            _api_report_run(
                config,
                token_provider,
                run_id=run_id,
                correlation_id=correlation_id,
                new_status="failed",
                changed_by=requested_by,
                reason="GX worker completed join-pair execution with failures",
                details={"source": "dq-engine-gx-worker", "execution_shape": "join_pair", "failure_count": len(diagnostics)},
                execution_progress=_build_execution_progress(
                    completed_steps=total_steps,
                    total_steps=total_steps,
                    label="Execution completed with failures",
                ),
                completed_at=_utc_now_iso(),
                result_summary=result_summary,
                diagnostics=diagnostics,
                failure_code="GX_VALIDATION_FAILED",
                failure_message="One or more expectations failed",
            )
            record_worker_duration(
                stage="dispatch",
                execution_shape="join_pair",
                duration_ms=(time.perf_counter() - single_execution_started) * 1000.0,
                result="failure",
                target_count=len(target_ids),
            )
        return

    locations_by_target = _resolve_locations_for_targets(
        config,
        token_provider,
        correlation_id=correlation_id,
        target_ids=target_ids,
        payload=payload,
    )

    total_steps = len(target_ids) + 1
    _api_report_execution_progress(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        changed_by=requested_by,
        reason="GX worker resolved execution inputs",
        details={"source": "dq-engine-gx-worker"},
        completed_steps=1,
        total_steps=total_steps,
        label=f"Resolved {len(target_ids)} source targets",
    )

    needs_delta = any(loc.format == "delta" for loc in locations_by_target.values())
    spark_session = _create_spark_session(config, enable_delta=needs_delta)

    all_ok = True
    per_target_results: list[dict[str, Any]] = []
    all_diagnostics: list[dict[str, Any]] = []

    tmpdirs: list[tempfile.TemporaryDirectory[str]] = []

    try:
        for target_index, target_id in enumerate(target_ids, start=1):
            target_started_at = time.perf_counter()
            location = locations_by_target[target_id]
            normalized_uri = _normalize_s3_uri(location.uri)
            _assert_supported_uri(normalized_uri)
            _require_s3_config_for_location(config, uri=normalized_uri)

            read_uri = normalized_uri
            if normalized_uri.startswith("s3a://"):
                tmpdir, localized_path = _download_s3a_prefix_to_tempdir(config, uri=normalized_uri)
                tmpdirs.append(tmpdir)
                read_uri = localized_path

            with traced_worker_span(
                "gx.worker.target",
                component="dq-engine-gx-worker",
                correlation_id=correlation_id,
                run_id=run_id,
                suite_id=suite_id,
                suite_version=suite_version,
                execution_shape="single_object",
                target_index=target_index,
                data_object_version_id=target_id,
            ):
                source_read_started_at = time.perf_counter()
                df = _spark_read_dataset(
                    spark_session,
                    location=SourceLocation(uri=read_uri, format=location.format, options=location.options),
                    max_rows=config.max_rows,
                )
                record_worker_duration(
                    stage="source_read",
                    execution_shape="single_object",
                    duration_ms=(time.perf_counter() - source_read_started_at) * 1000.0,
                    result="success",
                    source_format=location.format,
                    target_count=len(target_ids),
                )

                ok, summary, diagnostics = _evaluate_expectations_spark(
                    df,
                    expectations,
                    primary_key_fields=primary_key_fields,
                )
                record_worker_expectation_results(
                    execution_shape="single_object",
                    passed_count=int(summary.get("passed_expectation_count") or 0),
                    failed_count=int(summary.get("failed_expectation_count") or 0),
                )
                per_target_results.append(
                    {
                        "data_object_version_id": target_id,
                        "storage_uri": normalized_uri,
                        "storage_format": location.format,
                        "ok": ok,
                        "summary": summary,
                    }
                )
                if not ok:
                    all_ok = False
                for diag in diagnostics:
                    diag["data_object_version_id"] = target_id
                    diag["storage_uri"] = normalized_uri
                    diag["storage_format"] = location.format
                    all_diagnostics.append(diag)

                _api_report_execution_progress(
                    config,
                    token_provider,
                    run_id=run_id,
                    correlation_id=correlation_id,
                    changed_by=requested_by,
                    reason="GX worker evaluated a source target",
                    details={"source": "dq-engine-gx-worker", "target_index": target_index},
                    completed_steps=target_index + 1,
                    total_steps=total_steps,
                    label=f"Evaluated source target {target_index} of {len(target_ids)}",
                )

            record_worker_duration(
                stage="target_execution",
                execution_shape="single_object",
                duration_ms=(time.perf_counter() - target_started_at) * 1000.0,
                result="success" if ok else "failure",
                source_format=location.format,
                target_count=len(target_ids),
            )
    finally:
        _safe_stop_spark_session(spark_session)
        for tmpdir in tmpdirs:
            tmpdir.cleanup()

    result_summary = {
        "suite_id": suite_id,
        "suite_version": suite_version,
        "target_count": len(target_ids),
        "results": per_target_results,
    }

    if all_ok:
        _api_report_run(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="succeeded",
            changed_by=requested_by,
            reason="GX worker completed execution",
            details={"source": "dq-engine-gx-worker"},
            execution_progress=_build_execution_progress(
                completed_steps=total_steps,
                total_steps=total_steps,
                label="Execution completed",
            ),
            completed_at=_utc_now_iso(),
            result_summary=result_summary,
            diagnostics=[],
            failure_code=None,
            failure_message=None,
        )
        record_worker_duration(
            stage="dispatch",
            execution_shape="single_object",
            duration_ms=(time.perf_counter() - single_execution_started) * 1000.0,
            result="success",
            target_count=len(target_ids),
        )
    else:
        _api_report_run(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="failed",
            changed_by=requested_by,
            reason="GX worker completed execution with failures",
            details={"source": "dq-engine-gx-worker", "failure_count": len(all_diagnostics)},
            execution_progress=_build_execution_progress(
                completed_steps=total_steps,
                total_steps=total_steps,
                label="Execution completed with failures",
            ),
            completed_at=_utc_now_iso(),
            result_summary=result_summary,
            diagnostics=all_diagnostics,
            failure_code="GX_VALIDATION_FAILED",
            failure_message="One or more expectations failed",
        )
        record_worker_duration(
            stage="dispatch",
            execution_shape="single_object",
            duration_ms=(time.perf_counter() - single_execution_started) * 1000.0,
            result="failure",
            target_count=len(target_ids),
        )


def run_worker_forever() -> None:
    log_level = os.getenv("DQ_LOG_LEVEL", "INFO")
    configure_logging(log_level)
    configure_worker_telemetry()
    logger = logging.getLogger(__name__)

    config = load_config()
    redis_mod = _require_redis()

    # Fail-fast: validate we can mint or read an API token at startup.
    token_provider = _build_token_provider()
    _ = token_provider.get_token(correlation_id=f"corr-{uuid4().hex[:12]}")

    log_event(
        logger,
        "gx.worker.start",
        component="dq-engine-gx-worker",
        redisUrl=config.redis_url,
        queueKey=config.queue_key,
        processingQueueKey=config.processing_queue_key,
        maxRows=config.max_rows,
        sparkMaster=config.spark_master,
        apiUrl=config.api_url,
    )

    client = redis_mod.from_url(config.redis_url, decode_responses=True)
    worker_id = f"dq-engine-gx-worker-{uuid4().hex[:12]}"

    _write_worker_heartbeat(client, config=config, worker_id=worker_id)
    heartbeat_stop_event, heartbeat_thread = _start_worker_heartbeat_loop(
        client,
        config=config,
        worker_id=worker_id,
        logger=logger,
    )
    try:
        # Crash recovery: messages can remain stuck in the processing queue when the
        # worker process dies mid-execution (e.g. JVM crash, OOM, bug). Requeue them
        # on startup so they are retried and the corresponding runs can be resolved.
        recovered = 0
        try:
            while True:
                msg = client.rpoplpush(config.processing_queue_key, config.queue_key)
                if msg is None:
                    break
                recovered += 1
        except Exception as exc:
            log_event(
                logger,
                "gx.worker.recovery.failed",
                level="error",
                component="dq-engine-gx-worker",
                exceptionType=exc.__class__.__name__,
                errorMessage=str(exc),
            )

        if recovered:
            log_event(
                logger,
                "gx.worker.recovery.requeued",
                level="warning",
                component="dq-engine-gx-worker",
                recoveredCount=recovered,
                processingQueueKey=config.processing_queue_key,
                queueKey=config.queue_key,
            )

        while True:
            raw_message = None
            try:
                raw_message = client.brpoplpush(
                    config.queue_key,
                    config.processing_queue_key,
                    timeout=config.poll_timeout_seconds,
                )
                if raw_message is None:
                    continue

                process_dispatch_message(config, raw_message=raw_message)
                client.lrem(config.processing_queue_key, 1, raw_message)
            except KeyboardInterrupt:
                raise
            except BaseException as exc:
                # Fail fast but do not silently drop messages.
                execution_shape = "unknown"
                payload: dict[str, Any] = {}
                if raw_message is not None:
                    try:
                        payload = _parse_dispatch_payload(raw_message)
                        execution_shape = _coerce_str(payload, "execution_shape") or "unknown"
                    except Exception:
                        execution_shape = "unknown"
                log_event(
                    logger,
                    "gx.worker.process.failed",
                    level="error",
                    component="dq-engine-gx-worker",
                    exceptionType=exc.__class__.__name__,
                    errorMessage=str(exc),
                )
                record_worker_failure(
                    stage="dispatch",
                    execution_shape=execution_shape,
                    reason=getattr(exc, "failure_code", exc.__class__.__name__),
                )
                failure_reported = False
                failure_report_must_discard = False
                if raw_message is not None:
                    try:
                        failure_reported = _report_dispatch_failure(
                            config,
                            token_provider,
                            payload=payload,
                            exc=exc,
                        )
                    except Exception as report_exc:
                        failure_report_must_discard = _should_discard_failed_message(report_exc)
                        log_event(
                            logger,
                            "gx.worker.failure.report.failed",
                            level="error",
                            component="dq-engine-gx-worker",
                            runId=_coerce_str(payload, "run_id", "queue_message_id") or None,
                            exceptionType=report_exc.__class__.__name__,
                            errorMessage=str(report_exc),
                        )

                if raw_message is not None and (failure_reported or failure_report_must_discard):
                    try:
                        client.lrem(config.processing_queue_key, 1, raw_message)
                    except Exception as cleanup_exc:
                        log_event(
                            logger,
                            "gx.worker.processing.cleanup.failed",
                            level="error",
                            component="dq-engine-gx-worker",
                            processingQueueKey=config.processing_queue_key,
                            exceptionType=cleanup_exc.__class__.__name__,
                            errorMessage=str(cleanup_exc),
                        )

                if _should_fail_closed_worker(exc):
                    log_event(
                        logger,
                        "gx.worker.process.fail_closed",
                        level="critical",
                        component="dq-engine-gx-worker",
                        exceptionType=exc.__class__.__name__,
                        errorMessage=str(exc),
                        failureReported=failure_reported,
                    )
                    raise

                time.sleep(1.0)
    finally:
        heartbeat_stop_event.set()
        heartbeat_thread.join(timeout=1.0)
        try:
            client.delete(config.heartbeat_key)
        except Exception:
            pass


if __name__ == "__main__":
    run_worker_forever()
