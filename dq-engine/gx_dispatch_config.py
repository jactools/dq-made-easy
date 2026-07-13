"""GX worker configuration — loading GxWorkerConfig from environment variables.

Resolves all environment-based settings (Redis, queue keys, Spark master/port,
S3 endpoint/credentials, API URL, OIDC token provider) and bundles them into
a single ``GxWorkerConfig`` dataclass.

Public entry point: ``load_config()``
"""

from __future__ import annotations

import logging
import os
from typing import Any

try:
    import redis
except Exception:  # pragma: no cover
    redis = None

from dq_utils.auth_utils import AuthConfigError
from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import build_oidc_token_provider_from_env
from dq_utils.spark_runtime import resolve_spark_master
from dq_utils.spark_runtime import resolve_spark_ui_port

from dq_plan_execution_types import GxWorkerConfig
from dq_plan_execution_types import GxWorkerConfigError


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    from gx_dispatch_results import utc_now_iso

    return utc_now_iso()


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Queue keys
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Spark
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _resolve_api_url() -> str:
    # Must route through Kong. Default works for docker-compose.
    api_url = os.getenv("KONG_INTERNAL_URL") or "https://kong:8443"
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
        # Default to 12 retries with escalating backoff (~8 min total) so workers survive
        # transient keycloak startup races where healthcheck passes before HTTPS listener is ready.
        max_retries = int(os.getenv("DQ_ENGINE_MAX_RETRIES", "12"))
        backoff_ms = int(os.getenv("DQ_ENGINE_RETRY_BACKOFF_MS", "3000"))
        return build_oidc_token_provider_from_env(
            issuer_env_var="DQ_ENGINE_OIDC_ISSUER",
            token_url_env_var="DQ_ENGINE_OIDC_TOKEN_URL",
            client_id_env_var="DQ_ENGINE_OIDC_CLIENT_ID",
            client_secret_env_var="DQ_ENGINE_OIDC_CLIENT_SECRET",
            scope_env_var="DQ_ENGINE_OIDC_SCOPE",
            max_startup_retries=max_retries,
            retry_backoff_seconds=backoff_ms / 1000.0,
        )
    except AuthConfigError as exc:
        raise GxWorkerConfigError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def load_config() -> GxWorkerConfig:
    """Load and validate the full worker configuration from environment variables.

    Raises ``GxWorkerConfigError`` if any required setting is missing or invalid.
    """
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
