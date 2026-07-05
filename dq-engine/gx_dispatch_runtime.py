"""GX dispatch runtime — Spark session management, S3/URI handling, source resolution.

This module owns the infrastructure for:
  • Spark session creation, configuration, and teardown
  • S3 URI parsing, normalization, and S3A prefix downloading
  • Source location resolution and data-reading abstractions
  • Exception-chain helpers used for transient-error detection

The worker (gx_dispatch_worker) imports the private ``_`` versions from here.
Public (non-underscore) names are kept for backward compatibility.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from dq_utils.spark_runtime import build_spark_session_builder
from dq_utils.spark_runtime import resolve_spark_master
from dq_utils.spark_runtime import resolve_spark_ui_port

from dq_plan_execution_types import GxWorkerConfig
from dq_plan_execution_types import GxWorkerConfigError
from dq_plan_execution_types import GxWorkerExecutionError
from dq_plan_execution_types import SourceLocation


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_S3_URI_RE = re.compile(r"^s3a?://")
_MATERIALIZED_FORMAT_RE = re.compile(r"(?:^|/)format=(parquet|delta)(?:/|$)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Exception-chain helpers (used by Spark session retry logic)
# ---------------------------------------------------------------------------


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    """Walk the full cause/context chain of an exception."""
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
    """Return True if *exc* looks like a transient Spark gateway error."""
    for candidate in _iter_exception_chain(exc):
        if isinstance(candidate, ConnectionRefusedError):
            return True
        if str(candidate.__class__.__module__ or "").startswith("py4j"):
            return True
    return False


# ---------------------------------------------------------------------------
# Spark session — creation, configuration, teardown
# ---------------------------------------------------------------------------


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


def _is_real_spark_dataframe(df: Any) -> bool:
    return str(getattr(df.__class__, "__module__", "")).startswith("pyspark.")


def _resolve_worker_spark_setting(env_name: str, default: str) -> str:
    raw_value = str(os.getenv(env_name) or "").strip()
    return raw_value or default


def _derive_s3_ssl_enabled(config: GxWorkerConfig) -> bool:
    if config.s3_ssl_enabled is not None:
        return bool(config.s3_ssl_enabled)
    if config.s3_endpoint and config.s3_endpoint.strip().lower().startswith("https://"):
        return True
    return False


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
    """Create (or reuse) a Spark session with retry on transient gateway errors."""
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

            from dq_utils.logging_utils import log_event

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


def _safe_stop_spark_session(spark_session: Any) -> None:
    """Stop the Spark session, swallowing teardown errors (preserves original failure)."""
    if not hasattr(spark_session, "stop"):
        return
    try:
        spark_session.stop()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# S3 URI helpers
# ---------------------------------------------------------------------------


def _normalize_s3_uri(uri: str) -> str:
    """Normalize ``s3://`` → ``s3a://``; pass through everything else."""
    raw = uri.strip()
    if raw.startswith("s3://"):
        return "s3a://" + raw[len("s3://") :]
    return raw


def _parse_s3a_uri(uri: str) -> tuple[str, str]:
    """Parse ``s3a://bucket/prefix`` → ``(bucket, prefix)``."""
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
        raise GxWorkerConfigError(
            "Missing DQ_S3_ENDPOINT/AWS_ENDPOINT_URL (required for s3:// sources)"
        )
    if not (config.s3_access_key and config.s3_secret_key):
        raise GxWorkerConfigError(
            "Missing S3 credentials for s3:// sources "
            "(set DQ_S3_ACCESS_KEY/DQ_S3_SECRET_KEY or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)"
        )


def _download_s3a_prefix_to_tempdir(
    config: GxWorkerConfig, *, uri: str
) -> tuple[tempfile.TemporaryDirectory[str], str]:
    """Download all S3A objects under *uri* to a local temp dir.

    Returns ``(tmpdir_context, local_path)``.
    """
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


# ---------------------------------------------------------------------------
# Source location resolution
# ---------------------------------------------------------------------------


def _coerce_source_location(
    version_payload: dict[str, Any], *, data_object_version_id: str
) -> SourceLocation:
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


# ---------------------------------------------------------------------------
# Spark dataset reader
# ---------------------------------------------------------------------------


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

