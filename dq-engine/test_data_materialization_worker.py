from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable

import redis
import requests

from dq_utils.auth_utils import AuthConfigError
from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import build_oidc_token_provider_from_env
from dq_utils.spark_runtime import build_spark_session_builder
from dq_utils.spark_runtime import resolve_spark_master
from dq_utils.spark_runtime import resolve_spark_ui_port


LOG = logging.getLogger("dq.engine.test_data_materialization")


@dataclass(frozen=True)
class WorkerConfig:
    redis_url: str
    queue_key: str
    processing_queue_key: str
    api_url: str
    spark_master: str
    spark_ui_port: int
    output_prefix: str
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str | None
    s3_path_style_access: bool
    s3_ssl_enabled: bool | None
    max_rows_per_request: int
    poll_timeout_seconds: int


def _truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _optional_bool(raw: str | None) -> bool | None:
    if raw is None or not str(raw).strip():
        return None
    return _truthy(raw)


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_env(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _resolve_spark_ui_port() -> int:
    try:
        return resolve_spark_ui_port()
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def _resolve_config() -> WorkerConfig:
    redis_url = (
        str(os.getenv("TEST_DATA_MATERIALIZATION_REDIS_URL") or "").strip()
        or str(os.getenv("REDIS_URL") or "").strip()
    )
    if not redis_url:
        raise RuntimeError("Missing TEST_DATA_MATERIALIZATION_REDIS_URL/REDIS_URL")

    queue_key = (
        str(os.getenv("TEST_DATA_MATERIALIZATION_QUEUE_KEY") or "").strip()
        or str(os.getenv("DQ_TEST_DATA_MATERIALIZATION_QUEUE_KEY") or "").strip()
        or "dq-test-data:materialize"
    )
    processing_queue_key = (
        str(os.getenv("TEST_DATA_MATERIALIZATION_PROCESSING_QUEUE_KEY") or "").strip()
        or f"{queue_key}:processing"
    )

    api_url = str(os.getenv("KONG_INTERNAL_URL") or "http://kong:8000").strip().rstrip("/")
    if not api_url:
        raise RuntimeError("Missing KONG_INTERNAL_URL")

    spark_master = resolve_spark_master()
    spark_ui_port = _resolve_spark_ui_port()

    output_prefix = str(os.getenv("DQ_TEST_DATA_OUTPUT_PREFIX") or "").strip().rstrip("/")
    if not output_prefix:
        raise RuntimeError("Missing DQ_TEST_DATA_OUTPUT_PREFIX (e.g. s3a://dq-test-data)")

    s3_endpoint = str(os.getenv("DQ_S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL") or "").strip()
    if not s3_endpoint:
        raise RuntimeError("Missing DQ_S3_ENDPOINT/AWS_ENDPOINT_URL")

    s3_access_key = str(os.getenv("DQ_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
    s3_secret_key = str(os.getenv("DQ_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
    if not (s3_access_key and s3_secret_key):
        raise RuntimeError("Missing DQ_S3_ACCESS_KEY/DQ_S3_SECRET_KEY (or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)")

    s3_region = str(os.getenv("DQ_S3_REGION") or "").strip() or None
    s3_path_style_access = _truthy(os.getenv("DQ_S3_PATH_STYLE_ACCESS") or "true")
    s3_ssl_enabled = _optional_bool(os.getenv("DQ_S3_SSL_ENABLED"))

    max_rows_per_request = int(os.getenv("TEST_DATA_MATERIALIZATION_MAX_ROWS", "5000"))
    poll_timeout_seconds = int(os.getenv("TEST_DATA_MATERIALIZATION_POLL_TIMEOUT_SECONDS", "5"))

    return WorkerConfig(
        redis_url=redis_url,
        queue_key=queue_key,
        processing_queue_key=processing_queue_key,
        api_url=api_url,
        spark_master=spark_master,
        spark_ui_port=spark_ui_port,
        output_prefix=output_prefix,
        s3_endpoint=s3_endpoint,
        s3_access_key=s3_access_key,
        s3_secret_key=s3_secret_key,
        s3_region=s3_region,
        s3_path_style_access=s3_path_style_access,
        s3_ssl_enabled=s3_ssl_enabled,
        max_rows_per_request=max_rows_per_request,
        poll_timeout_seconds=poll_timeout_seconds,
    )


def _normalize_s3_uri(uri: str) -> str:
    raw = str(uri or "").strip()
    if raw.startswith("s3://"):
        return "s3a://" + raw[len("s3://") :]
    return raw


def _parse_s3a_uri(uri: str) -> tuple[str, str]:
    uri = _normalize_s3_uri(uri)
    if not uri.startswith("s3a://"):
        raise RuntimeError(f"Unsupported output_uri scheme: {uri}")
    remainder = uri[len("s3a://") :]
    if "/" not in remainder:
        return remainder, ""
    bucket, key = remainder.split("/", 1)
    return bucket, key


def _derive_s3_ssl_enabled(cfg: WorkerConfig) -> bool:
    if cfg.s3_ssl_enabled is not None:
        return bool(cfg.s3_ssl_enabled)
    return cfg.s3_endpoint.lower().startswith("https://")


def _ensure_bucket_exists(cfg: WorkerConfig, *, bucket: str) -> None:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint,
        aws_access_key_id=cfg.s3_access_key,
        aws_secret_access_key=cfg.s3_secret_key,
        region_name=cfg.s3_region or "us-east-1",
        verify=_derive_s3_ssl_enabled(cfg),
    )

    try:
        client.head_bucket(Bucket=bucket)
        return
    except Exception:
        pass

    try:
        client.create_bucket(Bucket=bucket)
    except Exception as exc:
        # If a concurrent worker created the bucket, treat as success.
        try:
            client.head_bucket(Bucket=bucket)
            return
        except Exception:
            raise RuntimeError(f"Unable to create or access bucket '{bucket}': {exc}") from exc


def _upload_directory_to_s3(
    cfg: WorkerConfig,
    *,
    local_dir: str | Path,
    bucket: str,
    key_prefix: str,
) -> None:
    import boto3

    base = Path(local_dir)
    if not base.exists() or not base.is_dir():
        raise RuntimeError(f"Local output directory does not exist: {base}")

    client = boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint,
        aws_access_key_id=cfg.s3_access_key,
        aws_secret_access_key=cfg.s3_secret_key,
        region_name=cfg.s3_region or "us-east-1",
        verify=_derive_s3_ssl_enabled(cfg),
    )

    normalized_prefix = str(key_prefix or "").lstrip("/")
    continuation_token: str | None = None
    while True:
        list_kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": normalized_prefix}
        if continuation_token:
            list_kwargs["ContinuationToken"] = continuation_token
        response = client.list_objects_v2(**list_kwargs)
        contents = response.get("Contents") or []
        if contents:
            client.delete_objects(
                Bucket=bucket,
                Delete={
                    "Objects": [
                        {"Key": str(item.get("Key") or "")}
                        for item in contents
                        if str(item.get("Key") or "")
                    ]
                },
            )
        if not response.get("IsTruncated"):
            break
        continuation_token = str(response.get("NextContinuationToken") or "").strip() or None

    for path in base.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        if any(part.startswith(".") for part in Path(rel).parts):
            continue
        key = f"{normalized_prefix}/{rel}" if normalized_prefix else rel
        client.upload_file(str(path), bucket, key)


def _create_spark_session(cfg: WorkerConfig, *, enable_delta: bool) -> Any:
    from pyspark.sql import SparkSession
    from dq_utils.spark_jars import configure_spark_builder_with_local_jars

    builder = build_spark_session_builder(
        SparkSession=SparkSession,
        app_name="dq-made-easy-test-data-worker",
        master=cfg.spark_master,
        spark_ui_port=cfg.spark_ui_port,
    )
    builder = configure_spark_builder_with_local_jars(builder)

    if enable_delta:
        builder = builder.config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        builder = builder.config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")

    builder = builder.config("spark.hadoop.fs.s3a.endpoint", cfg.s3_endpoint)
    builder = builder.config(
        "spark.hadoop.fs.s3a.path.style.access",
        "true" if cfg.s3_path_style_access else "false",
    )
    builder = builder.config(
        "spark.hadoop.fs.s3a.connection.ssl.enabled",
        "true" if _derive_s3_ssl_enabled(cfg) else "false",
    )

    builder = builder.config("spark.hadoop.fs.s3a.access.key", cfg.s3_access_key)
    builder = builder.config("spark.hadoop.fs.s3a.secret.key", cfg.s3_secret_key)
    builder = builder.config(
        "spark.hadoop.fs.s3a.aws.credentials.provider",
        "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
    )

    if cfg.s3_region:
        builder = builder.config("spark.hadoop.fs.s3a.endpoint.region", cfg.s3_region)

    return builder.getOrCreate()


def _sample_value_for_attribute(attribute: dict[str, Any], index: int) -> object:
    field_name = str(attribute.get("name") or attribute.get("id") or "").lower()
    field_type = str(attribute.get("type") or "").lower()
    field_format = str(attribute.get("format") or "").lower()

    if "email" in field_name:
        return f"user{index + 1}@example.com"
    if "status" in field_name:
        return "active" if index % 2 == 0 else "inactive"
    if field_type in {"timestamp", "timestamptz", "datetime"} or field_format in {"timestamp", "date-time", "datetime"}:
        return (
            datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=index * 10)
        ).isoformat().replace("+00:00", "Z")
    if field_type == "date" or "date" in field_name or field_format == "date":
        return (date(2026, 1, 1) + timedelta(days=index)).isoformat()
    if field_type == "boolean":
        return index % 2 == 0
    if field_type in {"decimal", "numeric"}:
        return Decimal(index + 1)
    if field_type in {"integer", "int", "number", "float", "double", "bigint", "smallint"}:
        return index + 1
    return f"val_{index + 1}"


def _apply_contextual_row_values(row: dict[str, Any], *, attribute_names: set[str], index: int) -> None:
    if "status" in attribute_names and "order_id" in attribute_names:
        row["status"] = ("pending", "completed", "cancelled")[index % 3]

    if "warehouse_id" in attribute_names:
        row["warehouse_id"] = ("WH-001", "WH-002")[index % 2]

    if "preferred_contact" in attribute_names:
        row["preferred_contact"] = ("email", "phone")[index % 2]

    if "contact_type" in attribute_names:
        if "preferred_contact" in attribute_names:
            preferred_contact = str(row.get("preferred_contact") or "email").lower()
            allowed_contact_types = {
                "email": ("billing", "support"),
                "phone": ("sales", "service"),
            }.get(preferred_contact, ("billing", "support"))
            row["contact_type"] = allowed_contact_types[(index // 2) % len(allowed_contact_types)]
        else:
            row["contact_type"] = ("email", "phone", "sms")[index % 3]

    if "currency" in attribute_names:
        row["currency"] = ("USD", "EUR")[index % 2]

    if "payment_method" in attribute_names:
        if "currency" in attribute_names:
            currency = str(row.get("currency") or "USD").upper()
            allowed_payment_methods = {
                "USD": ("card", "ach"),
                "EUR": ("card", "sepa"),
            }.get(currency, ("card", "ach"))
            row["payment_method"] = allowed_payment_methods[(index // 2) % len(allowed_payment_methods)]
        else:
            row["payment_method"] = ("card", "ach", "sepa")[index % 3]


def _build_rows(attributes: list[dict[str, Any]], sample_count: int) -> list[dict[str, Any]]:
    attribute_names = {
        str(attribute.get("name") or attribute.get("id") or "").strip().lower()
        for attribute in attributes
        if str(attribute.get("name") or attribute.get("id") or "").strip()
    }
    rows: list[dict[str, Any]] = []
    for idx in range(sample_count):
        row: dict[str, Any] = {}
        for attribute in attributes:
            name = str(attribute.get("name") or attribute.get("id") or "").strip()
            if not name:
                continue
            row[name] = _sample_value_for_attribute(attribute, idx)
        _apply_contextual_row_values(row, attribute_names=attribute_names, index=idx)
        rows.append(row)
    return rows


def _safe_json_load(raw: str | bytes | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None


def _record_key(request_id: str) -> str:
    return f"test-data-materialization-request:{request_id}"


def _update_record(r: Any, *, request_id: str, patch: dict[str, Any], ttl_seconds: int) -> None:
    key = _record_key(request_id)
    current = _safe_json_load(r.get(key)) or {}
    current.update(patch)
    r.set(key, json.dumps(current), ex=ttl_seconds)


def _build_delivery_summary_from_results(target_results: list[dict[str, Any]]) -> dict[str, Any]:
    data_delivery_ids = [
        str(item.get("data_delivery_id") or "").strip()
        for item in target_results
        if str(item.get("data_delivery_id") or "").strip()
    ]
    object_storage_classifications = sorted(
        {
            str((item.get("delivery_note") or {}).get("object_storage_classification") or "").strip()
            for item in target_results
            if isinstance(item.get("delivery_note"), dict)
            and str((item.get("delivery_note") or {}).get("object_storage_classification") or "").strip()
        }
    )
    evidence_classifications = sorted(
        {
            str((item.get("delivery_note") or {}).get("evidence_classification") or "").strip()
            for item in target_results
            if isinstance(item.get("delivery_note"), dict)
            and str((item.get("delivery_note") or {}).get("evidence_classification") or "").strip()
        }
    )
    return {
        "target_count": len(target_results),
        "data_delivery_count": len(data_delivery_ids),
        "total_row_count": sum(int(item.get("row_count") or 0) for item in target_results),
        "reused_existing": any(bool(item.get("reused_existing")) for item in target_results),
        "data_delivery_ids": data_delivery_ids,
        "delivery_locations": [
            _normalize_s3_uri(str(item.get("output_uri") or "").strip())
            for item in target_results
            if str(item.get("output_uri") or "").strip()
        ],
        "output_formats": sorted(
            {
                str(item.get("output_format") or "").strip().lower()
                for item in target_results
                if str(item.get("output_format") or "").strip()
            }
        ),
        "object_storage_classifications": object_storage_classifications,
        "evidence_classifications": evidence_classifications,
    }


def _build_token_provider() -> TokenProvider:
    static_token = str(os.getenv("DQ_ENGINE_API_BEARER_TOKEN") or "").strip() or str(
        os.getenv("DQ_WORKER_API_BEARER_TOKEN") or ""
    ).strip()
    if static_token:
        raise RuntimeError(
            "Static bearer tokens are not supported for dq-engine materialization worker auth. "
            "Configure OIDC client credentials instead."
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
        raise RuntimeError(str(exc)) from exc


def _api_headers(cfg: WorkerConfig, token_provider: TokenProvider, *, correlation_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token_provider.get_token(correlation_id=correlation_id)}",
        "X-Correlation-ID": correlation_id,
        "Content-Type": "application/json",
    }


def _api_request(
    cfg: WorkerConfig,
    token_provider: TokenProvider,
    *,
    method: str,
    path: str,
    correlation_id: str,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: int = 15,
) -> Any:
    url = f"{cfg.api_url.rstrip('/')}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=_api_headers(cfg, token_provider, correlation_id=correlation_id),
            json=json_body,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        raise RuntimeError(f"Materialization worker cannot reach API via Kong at '{cfg.api_url}'") from exc

    payload: Any = None
    if "application/json" in str(response.headers.get("content-type") or ""):
        try:
            payload = response.json()
        except Exception:
            payload = None

    if response.status_code >= 400:
        raise RuntimeError(f"API request failed: {method} {path} -> {response.status_code}")
    return payload


def _api_report_materialization_completion(
    cfg: WorkerConfig,
    token_provider: TokenProvider,
    *,
    request_id: str,
    correlation_id: str,
    target_results: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = _api_request(
        cfg,
        token_provider,
        method="POST",
        path=f"/data-catalog/v1/materialization-requests/{request_id}/complete",
        correlation_id=correlation_id,
        json_body={
            "target_results": [
                {
                    "data_object_version_id": str(target.get("data_object_version_id") or "").strip(),
                    "row_count": int(target.get("row_count") or 0),
                    "output_uri": _normalize_s3_uri(str(target.get("output_uri") or "").strip()),
                    "output_format": str(target.get("output_format") or "").strip().lower(),
                }
                for target in target_results
            ],
        },
    )
    if not isinstance(payload, dict):
        raise RuntimeError("API returned invalid materialization completion payload")
    return payload


def _write_dataset(cfg: WorkerConfig, spark: Any, *, output_uri: str, output_format: str, rows: list[dict[str, Any]]) -> int:
    from pyspark.sql import Row

    df = spark.createDataFrame([Row(**row) for row in rows])

    output_uri = _normalize_s3_uri(output_uri)
    fmt = str(output_format or "").strip().lower()
    if fmt == "parquet":
        if output_uri.startswith("s3a://"):
            bucket, key_prefix = _parse_s3a_uri(output_uri)
            with tempfile.TemporaryDirectory(prefix="dq-test-data-parquet-") as tmpdir:
                df.write.mode("overwrite").parquet(tmpdir)
                _upload_directory_to_s3(cfg, local_dir=tmpdir, bucket=bucket, key_prefix=key_prefix)
        else:
            df.write.mode("overwrite").parquet(output_uri)
    elif fmt == "delta":
        df.write.format("delta").mode("overwrite").save(output_uri)
    else:
        raise RuntimeError(f"Unsupported output_format '{output_format}'")

    return int(df.count())


def _process_job(cfg: WorkerConfig, *, r: Any, raw_job: str, token_provider: TokenProvider) -> None:
    payload = _safe_json_load(raw_job)
    if payload is None:
        raise RuntimeError("Invalid JSON job payload")

    request_id = str(payload.get("materialization_request_id") or "").strip()
    correlation_id = str(payload.get("correlation_id") or f"corr-{request_id}").strip() or f"corr-{request_id}"
    if not request_id:
        raise RuntimeError("materialization_request_id is required")

    job_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    output_format = str(job_payload.get("output_format") or "").strip().lower()
    raw_targets = job_payload.get("targets") if isinstance(job_payload.get("targets"), list) else None
    targets = list(raw_targets or [])
    if not targets:
        targets = [
            {
                "data_object_version_id": str(job_payload.get("data_object_version_id") or "").strip(),
                "sample_count": int(job_payload.get("sample_count") or 0),
                "output_format": output_format,
                "output_uri": str(job_payload.get("output_uri") or "").strip(),
                "attributes": list(job_payload.get("attributes") or []),
            }
        ]

    normalized_targets: list[dict[str, Any]] = []
    for target in targets:
        version_id = str(target.get("data_object_version_id") or "").strip()
        target_output_format = str(target.get("output_format") or output_format or "").strip().lower()
        target_output_uri = str(target.get("output_uri") or "").strip()
        target_attributes = list(target.get("attributes") or [])
        target_sample_count = int(target.get("sample_count") or 0)

        if not version_id:
            raise RuntimeError("data_object_version_id is required")
        if not target_output_format:
            raise RuntimeError("output_format is required")
        if not target_output_uri:
            raise RuntimeError("output_uri is required")
        if target_sample_count <= 0:
            raise RuntimeError("sample_count must be > 0")
        if target_sample_count > cfg.max_rows_per_request:
            raise RuntimeError(f"sample_count exceeds max_rows_per_request ({cfg.max_rows_per_request})")

        bucket, _ = _parse_s3a_uri(target_output_uri)
        _ensure_bucket_exists(cfg, bucket=bucket)
        normalized_targets.append(
            {
                "data_object_version_id": version_id,
                "sample_count": target_sample_count,
                "output_format": target_output_format,
                "output_uri": target_output_uri,
                "attributes": target_attributes,
            }
        )

    ttl = int(os.getenv("TEST_DATA_MATERIALIZATION_REQUEST_TTL_SECONDS", "3600"))
    _update_record(
        r,
        request_id=request_id,
        patch={
            "status": "started",
            "started_at": _current_timestamp(),
            "error_message": None,
        },
        ttl_seconds=ttl,
    )

    spark = _create_spark_session(cfg, enable_delta=any(str(target.get("output_format") or "") == "delta" for target in normalized_targets))
    target_results: list[dict[str, Any]] = []
    for target in normalized_targets:
        rows = _build_rows(list(target.get("attributes") or []), int(target.get("sample_count") or 0))
        row_count = _write_dataset(
            cfg,
            spark,
            output_uri=str(target.get("output_uri") or ""),
            output_format=str(target.get("output_format") or ""),
            rows=rows,
        )
        target_results.append(
            {
                "data_object_version_id": str(target.get("data_object_version_id") or "").strip(),
                "row_count": row_count,
                "output_uri": str(target.get("output_uri") or "").strip(),
                "output_format": str(target.get("output_format") or "").strip().lower(),
            }
        )

    completion_payload = _api_report_materialization_completion(
        cfg,
        token_provider,
        request_id=request_id,
        correlation_id=correlation_id,
        target_results=target_results,
    )

    completion_deliveries = completion_payload.get("data_deliveries") if isinstance(completion_payload.get("data_deliveries"), list) else []
    deliveries_by_version = {
        str(item.get("data_object_version_id") or "").strip(): item
        for item in completion_deliveries
        if isinstance(item, dict) and str(item.get("data_object_version_id") or "").strip()
    }
    enriched_results: list[dict[str, Any]] = []
    for target_result in target_results:
        version_id = str(target_result.get("data_object_version_id") or "").strip()
        delivery = deliveries_by_version.get(version_id, {})
        enriched_results.append(
            {
                "data_object_version_id": version_id,
                "row_count": int(target_result.get("row_count") or 0),
                "output_uri": _normalize_s3_uri(str(target_result.get("output_uri") or "").strip()),
                "output_format": str(target_result.get("output_format") or "").strip().lower(),
                "data_delivery_id": str(delivery.get("data_delivery_id") or "").strip() or None,
                "delivery_note": delivery.get("delivery_note") if isinstance(delivery.get("delivery_note"), dict) else None,
            }
        )

    first_result = enriched_results[0] if len(enriched_results) == 1 else None

    _update_record(
        r,
        request_id=request_id,
        patch={
            "status": "completed",
            "completed_at": _current_timestamp(),
            "error_message": None,
            "result": {
                "row_count": sum(int(item.get("row_count") or 0) for item in enriched_results),
                "output_uri": _normalize_s3_uri(str(job_payload.get("output_uri") or "").strip() or str(normalized_targets[0].get("output_uri") or "").strip()),
                "output_format": output_format,
                "delivery_summary": _build_delivery_summary_from_results(enriched_results),
                "target_results": enriched_results,
                "data_delivery_ids": [item["data_delivery_id"] for item in enriched_results if item.get("data_delivery_id")],
                "data_delivery_id": first_result.get("data_delivery_id") if first_result is not None else None,
                "delivery_note": first_result.get("delivery_note") if first_result is not None else None,
            },
        },
        ttl_seconds=ttl,
    )


def run_worker_forever() -> None:
    logging.basicConfig(level=os.getenv("DQ_LOG_LEVEL", "INFO"))
    cfg = _resolve_config()
    token_provider = _build_token_provider()

    r = redis.from_url(cfg.redis_url, decode_responses=True)

    LOG.info(
        "test_data_materialization.worker.start",
        extra={
            "redis_url": cfg.redis_url,
            "queue_key": cfg.queue_key,
            "processing_queue_key": cfg.processing_queue_key,
            "spark_master": cfg.spark_master,
        },
    )

    ttl = int(os.getenv("TEST_DATA_MATERIALIZATION_REQUEST_TTL_SECONDS", "3600"))

    while True:
        raw_job = r.brpoplpush(cfg.queue_key, cfg.processing_queue_key, timeout=cfg.poll_timeout_seconds)
        if not raw_job:
            continue

        try:
            _process_job(cfg, r=r, raw_job=raw_job, token_provider=token_provider)
        except Exception as exc:
            payload = _safe_json_load(raw_job)
            request_id = str((payload or {}).get("materialization_request_id") or "").strip()
            if request_id:
                _update_record(
                    r,
                    request_id=request_id,
                    patch={
                        "status": "failed",
                        "completed_at": _current_timestamp(),
                        "error_message": str(exc),
                    },
                    ttl_seconds=ttl,
                )
            LOG.exception("test_data_materialization.job.failed")
        finally:
            # Ack by removing the exact payload from the processing list.
            try:
                r.lrem(cfg.processing_queue_key, 1, raw_job)
            except Exception:
                LOG.exception("failed to ack processing payload")


if __name__ == "__main__":
    run_worker_forever()
