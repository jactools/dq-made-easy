from __future__ import annotations

import os
import re
import tempfile
from typing import Any

from dq_utils.spark_runtime import build_spark_session_builder
from dq_utils.spark_runtime import resolve_spark_master
from dq_utils.spark_runtime import resolve_spark_ui_port

from gx_dispatch_types import GxWorkerConfig
from gx_dispatch_types import GxWorkerConfigError
from gx_dispatch_types import SourceLocation


_S3_URI_RE = re.compile(r"^s3a?://")
_MATERIALIZED_FORMAT_RE = re.compile(r"(?:^|/)format=(parquet|delta)(?:/|$)", re.IGNORECASE)


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

    configured = configured.config("spark.master", config.spark_master)
    configured = configured.config("spark.ui.port", str(config.spark_ui_port))
    return configured


def _require_pyspark() -> None:
    try:
        from pyspark.sql import SparkSession  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise GxWorkerConfigError("pyspark is not installed; cannot run dq-engine GX worker") from exc


def create_spark_session(config: GxWorkerConfig, *, enable_delta: bool) -> Any:
    _require_pyspark()

    builder = build_spark_session_builder()
    configured_builder = _configure_worker_spark_builder(builder, config, enable_delta=enable_delta)
    return configured_builder.getOrCreate()


def normalize_s3_uri(uri: str) -> str:
    return uri.strip()


def parse_s3a_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3a://"):
        raise ValueError(f"Unsupported S3A URI: {uri}")
    suffix = uri[len("s3a://") :]
    bucket, _, key = suffix.partition("/")
    if not bucket:
        raise ValueError(f"Unsupported S3A URI: {uri}")
    return bucket, key


def download_s3a_prefix_to_tempdir(config: GxWorkerConfig, *, uri: str) -> tuple[tempfile.TemporaryDirectory[str], str]:
    from dq_utils.cloud import download_prefix_to_local_dir

    tmpdir = tempfile.TemporaryDirectory(prefix="dq-s3a-", dir="/tmp")
    local_dir = download_prefix_to_local_dir(uri, tmpdir.name, config=config)
    return tmpdir, local_dir


def assert_supported_uri(uri: str) -> None:
    if not uri or not _S3_URI_RE.match(uri) and not uri.startswith("file://") and not uri.startswith("/tmp/"):
        raise GxWorkerConfigError(f"Unsupported source URI {uri!r}; only s3://, s3a://, file:// and local paths are supported")


def require_s3_config_for_location(config: GxWorkerConfig, *, uri: str) -> None:
    if not uri.startswith("s3://") and not uri.startswith("s3a://"):
        return
    if not config.s3_endpoint or not config.s3_access_key or not config.s3_secret_key:
        raise GxWorkerConfigError("S3 configuration is incomplete for source location")


def parse_materialized_format(uri: str) -> str | None:
    match = _MATERIALIZED_FORMAT_RE.search(uri)
    if match:
        return match.group(1).lower()
    return None


def coerce_source_location(version_payload: dict[str, Any], *, data_object_version_id: str) -> SourceLocation:
    storage_uri = version_payload.get("storage_uri")
    if not isinstance(storage_uri, str) or not storage_uri.strip():
        raise GxWorkerConfigError(f"Data object version '{data_object_version_id}' is missing storage_uri")

    storage_format = version_payload.get("storage_format")
    if not isinstance(storage_format, str) or not storage_format.strip():
        storage_format = "parquet"

    options = version_payload.get("storage_options") if isinstance(version_payload.get("storage_options"), dict) else {}
    return SourceLocation(uri=storage_uri, format=storage_format, options=dict(options))


def spark_read_dataset(spark_session: Any, *, location: SourceLocation, max_rows: int) -> Any:
    from pyspark.sql import DataFrameReader

    reader: DataFrameReader = spark_session.read
    if location.format.lower() == "delta":
        reader = reader.format("delta")
    else:
        reader = reader.format(location.format.lower())

    for key, value in (location.options or {}).items():
        reader = reader.option(key, value)

    df = reader.load(location.uri)
    if max_rows and max_rows > 0:
        return df.limit(max_rows)
    return df


def safe_stop_spark_session(spark_session: Any) -> None:
    if spark_session is None:
        return
    try:
        spark_session.stop()
    except Exception:
        pass
