from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any
from uuid import uuid4

from gx_dispatch_worker import GxWorkerConfig
from gx_dispatch_worker import GxWorkerConfigError
from gx_dispatch_worker import GxWorkerExecutionError
from gx_dispatch_worker import SourceLocation
from gx_dispatch_worker import _api_get_data_object_version
from gx_dispatch_worker import _api_report_execution_progress
from gx_dispatch_worker import _api_report_run
from gx_dispatch_worker import _assert_supported_uri
from gx_dispatch_worker import _build_token_provider
from gx_dispatch_worker import _coerce_source_location
from gx_dispatch_worker import _create_spark_session
from gx_dispatch_worker import _infer_materialized_source_location
from gx_dispatch_worker import _normalize_s3_uri
from gx_dispatch_worker import _parse_dispatch_payload
from gx_dispatch_worker import _parse_s3a_uri
from gx_dispatch_worker import _require_redis
from gx_dispatch_worker import _require_s3_config_for_location
from gx_dispatch_worker import _resolve_api_url
from gx_dispatch_worker import _resolve_bool_env
from gx_dispatch_worker import _resolve_optional_bool_env
from gx_dispatch_worker import _resolve_redis_url
from gx_dispatch_worker import _resolve_s3_access_key
from gx_dispatch_worker import _resolve_s3_endpoint
from gx_dispatch_worker import _resolve_s3_region
from gx_dispatch_worker import _resolve_s3_secret_key
from gx_dispatch_worker import _resolve_spark_master
from gx_dispatch_worker import _resolve_spark_ui_port
from gx_dispatch_worker import _resolve_worker_heartbeat_interval_seconds
from gx_dispatch_worker import _spark_read_dataset
from gx_dispatch_worker import _start_worker_heartbeat_loop
from gx_dispatch_worker import _utc_now_iso
from gx_dispatch_worker import _write_worker_heartbeat
from test_data_materialization_worker import _ensure_bucket_exists
from test_data_materialization_worker import _upload_directory_to_s3


LOG = logging.getLogger("dq.engine.join_pair_materialization")


def _resolve_queue_key() -> str:
    return (
        os.environ.get("GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY")
        or os.environ.get("DQ_GX_JOIN_PAIR_MATERIALIZATION_QUEUE_KEY")
        or "dq-gx:join-pair-materialize"
    )


def _resolve_processing_queue_key(queue_key: str) -> str:
    configured = os.environ.get("GX_JOIN_PAIR_MATERIALIZATION_PROCESSING_QUEUE_KEY")
    if configured and configured.strip():
        return configured.strip()
    return f"{queue_key}:processing"


def _resolve_worker_heartbeat_key(queue_key: str) -> str:
    configured = os.environ.get("GX_JOIN_PAIR_MATERIALIZATION_WORKER_HEARTBEAT_KEY")
    if configured and configured.strip():
        return configured.strip()
    return f"{queue_key}:worker-heartbeat"


def _resolve_worker_heartbeat_ttl_seconds() -> int:
    raw_value = (
        os.environ.get("GX_JOIN_PAIR_MATERIALIZATION_WORKER_HEARTBEAT_TTL_SECONDS")
        or os.environ.get("DQ_GX_JOIN_PAIR_MATERIALIZATION_WORKER_HEARTBEAT_TTL_SECONDS")
        or "30"
    )
    try:
        parsed = int(raw_value)
    except Exception:
        parsed = 30
    return max(parsed, 5)


def load_config() -> GxWorkerConfig:
    redis_url = _resolve_redis_url()
    queue_key = _resolve_queue_key()
    processing_queue_key = _resolve_processing_queue_key(queue_key)
    heartbeat_ttl_seconds = _resolve_worker_heartbeat_ttl_seconds()
    return GxWorkerConfig(
        redis_url=redis_url,
        queue_key=queue_key,
        processing_queue_key=processing_queue_key,
        heartbeat_key=_resolve_worker_heartbeat_key(queue_key),
        heartbeat_ttl_seconds=heartbeat_ttl_seconds,
        heartbeat_interval_seconds=_resolve_worker_heartbeat_interval_seconds(heartbeat_ttl_seconds),
        max_rows=int(os.getenv("DQ_ENGINE_MAX_ROWS", "100000")),
        poll_timeout_seconds=int(os.getenv("GX_JOIN_PAIR_MATERIALIZATION_POLL_TIMEOUT_SECONDS", "5")),
        api_url=_resolve_api_url(),
        spark_master=_resolve_spark_master(),
        spark_ui_port=_resolve_spark_ui_port(),
        s3_endpoint=_resolve_s3_endpoint(),
        s3_access_key=_resolve_s3_access_key(),
        s3_secret_key=_resolve_s3_secret_key(),
        s3_region=_resolve_s3_region(),
        s3_path_style_access=_resolve_bool_env("DQ_S3_PATH_STYLE_ACCESS", True),
        s3_ssl_enabled=_resolve_optional_bool_env("DQ_S3_SSL_ENABLED"),
    )


def _normalize_location(location: SourceLocation) -> SourceLocation:
    return SourceLocation(
        uri=_normalize_s3_uri(str(location.uri or "").strip()),
        format=str(location.format or "").strip().lower(),
        options=dict(location.options or {}),
    )


def _require_mapping(source_materialization: dict[str, Any]) -> list[dict[str, str]]:
    raw_pairs = source_materialization.get("join_key_pairs")
    pairs: list[dict[str, str]] = []
    if isinstance(raw_pairs, list):
        for item in raw_pairs:
            if not isinstance(item, dict):
                continue
            left_attribute = str(item.get("left_attribute") or "").strip()
            right_attribute = str(item.get("right_attribute") or "").strip()
            if left_attribute and right_attribute:
                pairs.append({"left_attribute": left_attribute, "right_attribute": right_attribute})
    if pairs:
        return pairs

    raw_join_keys = source_materialization.get("join_keys")
    if isinstance(raw_join_keys, list):
        for item in raw_join_keys:
            attribute = str(item or "").strip()
            if attribute:
                pairs.append({"left_attribute": attribute, "right_attribute": attribute})
    if not pairs:
        raise GxWorkerExecutionError(
            "GX join-pair materialization requires non-empty join keys",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_CONTRACT",
        )
    return pairs


def _resolve_join_type(join_type: str) -> str:
    normalized = str(join_type or "inner").strip().lower()
    mapping = {
        "inner": "inner",
        "left": "left",
        "right": "right",
        "full": "outer",
        "outer": "outer",
    }
    if normalized not in mapping:
        raise GxWorkerExecutionError(
            f"Unsupported join_type '{join_type}' for join-pair materialization",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_CONTRACT",
        )
    return mapping[normalized]


def _build_joined_dataframe(
    config: GxWorkerConfig,
    *,
    spark_session: Any,
    left_location: SourceLocation,
    right_location: SourceLocation,
    source_materialization: dict[str, Any],
) -> Any:
    from pyspark.sql import functions as F

    join_key_pairs = _require_mapping(source_materialization)
    join_type = _resolve_join_type(str(source_materialization.get("join_type") or "inner"))

    left_df = _spark_read_dataset(spark_session, location=left_location, max_rows=config.max_rows).alias("lhs")
    right_df = _spark_read_dataset(spark_session, location=right_location, max_rows=config.max_rows).alias("rhs_raw")

    left_columns = list(getattr(left_df, "columns", []) or [])
    right_columns = list(getattr(right_df, "columns", []) or [])
    missing_left = [item["left_attribute"] for item in join_key_pairs if item["left_attribute"] not in left_columns]
    missing_right = [item["right_attribute"] for item in join_key_pairs if item["right_attribute"] not in right_columns]
    if missing_left or missing_right:
        raise GxWorkerExecutionError(
            "GX join-pair materialization join keys do not exist on the source datasets",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_CONTRACT",
        )

    join_condition = None
    for pair in join_key_pairs:
        candidate = F.col(f"lhs.{pair['left_attribute']}") == F.col(f"rhs_raw.{pair['right_attribute']}")
        join_condition = candidate if join_condition is None else (join_condition & candidate)
    if join_condition is None:
        raise GxWorkerExecutionError(
            "GX join-pair materialization could not build a join condition",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_CONTRACT",
        )

    rhs_struct = F.struct(*[F.col(f"rhs_raw.{column}").alias(column) for column in right_columns]).alias("rhs")
    return left_df.join(right_df, on=join_condition, how=join_type).select(
        *[F.col(f"lhs.{column}").alias(column) for column in left_columns],
        rhs_struct,
    )


def _write_joined_dataframe(config: GxWorkerConfig, *, df: Any, output_location: str) -> tuple[str, str, int]:
    location = _infer_materialized_source_location(output_location=output_location)
    normalized_uri = _normalize_s3_uri(str(location.uri or "").strip())
    _assert_supported_uri(normalized_uri)
    _require_s3_config_for_location(config, uri=normalized_uri)

    bucket, key_prefix = _parse_s3a_uri(normalized_uri)
    _ensure_bucket_exists(config, bucket=bucket)

    if location.format == "parquet":
        with tempfile.TemporaryDirectory(prefix="dq-join-pair-parquet-") as tmpdir:
            df.write.mode("overwrite").parquet(tmpdir)
            _upload_directory_to_s3(config, local_dir=tmpdir, bucket=bucket, key_prefix=key_prefix)
    elif location.format == "delta":
        df.write.format("delta").mode("overwrite").save(normalized_uri)
    else:
        raise GxWorkerExecutionError(
            f"Unsupported join-pair materialization format '{location.format}'",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_CONTRACT",
        )

    return normalized_uri, location.format, int(df.count())


def _report_failure(
    config: GxWorkerConfig,
    token_provider: Any,
    *,
    run_id: str,
    correlation_id: str,
    requested_by: str | None,
    exc: Exception,
) -> None:
    _api_report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="failed",
        changed_by=requested_by,
        reason="Join-pair materialization failed",
        details={
            "source": "dq-engine-join-pair-etl-worker",
            "failure_stage": "join_pair_materialization",
            "exception": exc.__class__.__name__,
        },
        completed_at=_utc_now_iso(),
        diagnostics=[],
        failure_code=getattr(exc, "failure_code", "GX_JOIN_PAIR_MATERIALIZATION_FAILED"),
        failure_message=str(exc),
    )


def _process_job(config: GxWorkerConfig, *, redis_client: Any, raw_job: str, token_provider: Any) -> None:
    payload = _parse_dispatch_payload(raw_job)
    run_id = str(payload.get("run_id") or payload.get("queue_message_id") or "").strip()
    correlation_id = str(payload.get("correlation_id") or f"corr-{run_id}").strip() or f"corr-{run_id}"
    requested_by = str(payload.get("requested_by") or "").strip() or None
    if not run_id:
        raise GxWorkerExecutionError(
            "Join-pair materialization payload is missing run_id",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_PAYLOAD",
        )

    execution_contract = payload.get("execution_contract") if isinstance(payload.get("execution_contract"), dict) else {}
    if str(execution_contract.get("execution_shape") or "").strip() != "join_pair":
        raise GxWorkerExecutionError(
            "Join-pair materialization worker received a non-join_pair execution payload",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_PAYLOAD",
        )
    source_materialization = execution_contract.get("source_materialization") if isinstance(execution_contract.get("source_materialization"), dict) else None
    if source_materialization is None:
        raise GxWorkerExecutionError(
            "Join-pair materialization payload is missing source_materialization",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_CONTRACT",
        )

    next_dispatch_payload = payload.get("next_dispatch_payload") if isinstance(payload.get("next_dispatch_payload"), dict) else None
    if next_dispatch_payload is None:
        raise GxWorkerExecutionError(
            "Join-pair materialization payload is missing next_dispatch_payload",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_PAYLOAD",
        )
    next_queue_key = str(next_dispatch_payload.get("queue_key") or "").strip()
    if not next_queue_key:
        raise GxWorkerExecutionError(
            "Join-pair materialization payload is missing next_dispatch_payload.queue_key",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_PAYLOAD",
        )

    left_source = source_materialization.get("left_source") if isinstance(source_materialization.get("left_source"), dict) else None
    right_source = source_materialization.get("right_source") if isinstance(source_materialization.get("right_source"), dict) else None
    if left_source is None or right_source is None:
        raise GxWorkerExecutionError(
            "Join-pair materialization requires left_source and right_source",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_CONTRACT",
        )
    left_version_id = str(left_source.get("data_object_version_id") or "").strip()
    right_version_id = str(right_source.get("data_object_version_id") or "").strip()
    if not left_version_id or not right_version_id:
        raise GxWorkerExecutionError(
            "Join-pair materialization requires left and right data_object_version_id values",
            failure_code="GX_JOIN_PAIR_ETL_INVALID_CONTRACT",
        )

    _api_report_execution_progress(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        changed_by=requested_by,
        reason="Join-pair materialization started",
        details={"source": "dq-engine-join-pair-etl-worker", "stage": "resolve_sources"},
        completed_steps=1,
        total_steps=3,
        label="Resolving join-pair sources",
    )

    left_location = _normalize_location(
        _coerce_source_location(
            _api_get_data_object_version(config, token_provider, version_id=left_version_id, correlation_id=correlation_id),
            data_object_version_id=left_version_id,
        )
    )
    right_location = _normalize_location(
        _coerce_source_location(
            _api_get_data_object_version(config, token_provider, version_id=right_version_id, correlation_id=correlation_id),
            data_object_version_id=right_version_id,
        )
    )
    output_location = str(source_materialization.get("output_location") or "").strip()
    target_location = _infer_materialized_source_location(output_location=output_location)

    spark = _create_spark_session(
        config,
        enable_delta=any(
            item == "delta"
            for item in (
                left_location.format,
                right_location.format,
                target_location.format,
            )
        ),
    )
    try:
        _api_report_execution_progress(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            changed_by=requested_by,
            reason="Join-pair materialization in progress",
            details={"source": "dq-engine-join-pair-etl-worker", "stage": "materialize_join"},
            completed_steps=2,
            total_steps=3,
            label="Materializing join-pair landing-zone dataset",
        )
        joined_df = _build_joined_dataframe(
            config,
            spark_session=spark,
            left_location=left_location,
            right_location=right_location,
            source_materialization=source_materialization,
        )
        normalized_output_uri, output_format, row_count = _write_joined_dataframe(
            config,
            df=joined_df,
            output_location=output_location,
        )
    finally:
        if hasattr(spark, "stop"):
            spark.stop()

    redis_client.lpush(next_queue_key, json.dumps(next_dispatch_payload))
    _api_report_execution_progress(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        changed_by=requested_by,
        reason="Join-pair materialization completed and GX dispatch enqueued",
        details={
            "source": "dq-engine-join-pair-etl-worker",
            "stage": "dispatch_enqueued",
            "output_uri": normalized_output_uri,
            "output_format": output_format,
            "row_count": row_count,
            "next_queue_key": next_queue_key,
        },
        completed_steps=3,
        total_steps=3,
        label="Queued GX validation after join-pair materialization",
    )


def run_worker_forever() -> None:
    logging.basicConfig(level=os.getenv("DQ_LOG_LEVEL", "INFO"))
    config = load_config()
    redis_module = _require_redis()
    redis_client = redis_module.from_url(config.redis_url, decode_responses=True)
    token_provider = _build_token_provider()

    worker_id = f"gx-join-pair-etl-{uuid4().hex[:8]}"
    _write_worker_heartbeat(redis_client, config=config, worker_id=worker_id)
    stop_event, _ = _start_worker_heartbeat_loop(redis_client, config=config, worker_id=worker_id, logger=LOG)

    LOG.info(
        "join_pair_materialization.worker.start",
        extra={
            "queue_key": config.queue_key,
            "processing_queue_key": config.processing_queue_key,
            "heartbeat_key": config.heartbeat_key,
            "api_url": config.api_url,
        },
    )

    try:
        while True:
            raw_job = redis_client.brpoplpush(config.queue_key, config.processing_queue_key, timeout=config.poll_timeout_seconds)
            if not raw_job:
                continue
            try:
                _process_job(config, redis_client=redis_client, raw_job=raw_job, token_provider=token_provider)
            except Exception as exc:
                try:
                    payload = _parse_dispatch_payload(raw_job)
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    run_id = str(payload.get("run_id") or payload.get("queue_message_id") or "").strip()
                    correlation_id = str(payload.get("correlation_id") or f"corr-{run_id}").strip() or f"corr-{run_id}"
                    requested_by = str(payload.get("requested_by") or "").strip() or None
                    if run_id:
                        try:
                            _report_failure(
                                config,
                                token_provider,
                                run_id=run_id,
                                correlation_id=correlation_id,
                                requested_by=requested_by,
                                exc=exc,
                            )
                        except Exception:
                            LOG.exception("join_pair_materialization.report_failure.failed")
                LOG.exception("join_pair_materialization.job.failed")
            finally:
                try:
                    redis_client.lrem(config.processing_queue_key, 1, raw_job)
                except Exception:
                    LOG.exception("join_pair_materialization.ack.failed")
    finally:
        stop_event.set()


if __name__ == "__main__":
    run_worker_forever()