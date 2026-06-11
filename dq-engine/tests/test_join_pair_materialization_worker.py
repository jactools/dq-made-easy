from __future__ import annotations

import json
import os
import sys

TESTS_DIR = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
DQ_UTILS_SRC = os.path.join(REPO_ROOT, "dq-utils", "src")

os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")

sys.path.insert(0, DQ_UTILS_SRC)
sys.path.insert(0, ENGINE_DIR)

import join_pair_materialization_worker as worker
from gx_dispatch_worker import GxWorkerConfig


class _RedisCapture:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def lpush(self, queue_key: str, payload: str) -> None:
        self.calls.append((queue_key, json.loads(payload)))


class _SparkStub:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _config() -> GxWorkerConfig:
    return GxWorkerConfig(
        redis_url="redis://example",
        queue_key="dq-gx:join-pair-materialize",
        processing_queue_key="dq-gx:join-pair-materialize:processing",
        heartbeat_key="dq-gx:join-pair-materialize:worker-heartbeat",
        heartbeat_ttl_seconds=30,
        heartbeat_interval_seconds=10,
        max_rows=1000,
        poll_timeout_seconds=5,
        api_url="http://kong:8000",
        spark_master="local[*]",
        spark_ui_port=4044,
        s3_endpoint="http://aistor:9000",
        s3_access_key="aistoradmin",
        s3_secret_key="aistoradmin",
        s3_region="us-east-1",
        s3_path_style_access=True,
        s3_ssl_enabled=False,
    )


def test_process_job_materializes_join_pair_and_enqueues_next_dispatch(monkeypatch) -> None:
    config = _config()
    redis_client = _RedisCapture()
    spark = _SparkStub()
    progress_calls: list[dict] = []

    monkeypatch.setattr(
        worker,
        "_api_get_data_object_version",
        lambda config, token_provider, version_id, correlation_id: {
            "storage_uri": f"s3://source/{version_id}",
            "storage_format": "parquet",
            "storage_options_json": {},
        },
    )
    monkeypatch.setattr(worker, "_create_spark_session", lambda config, enable_delta: spark)
    monkeypatch.setattr(worker, "_build_joined_dataframe", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        worker,
        "_write_joined_dataframe",
        lambda config, df, output_location: (
            "s3a://dq-landing-zone-retail-banking/gx/join-pairs/suite_id=gx_suite_join/suite_version=3/format=parquet",
            "parquet",
            12,
        ),
    )
    monkeypatch.setattr(
        worker,
        "_api_report_execution_progress",
        lambda config, token_provider, **kwargs: progress_calls.append(kwargs),
    )

    payload = {
        "run_id": "run-join-1",
        "queue_message_id": "run-join-1",
        "suite_id": "gx_suite_join",
        "suite_version": 3,
        "correlation_id": "corr-join-1",
        "requested_by": "user-1",
        "engine_target": "pyspark",
        "execution_shape": "join_pair",
        "dispatch_mode": "queued",
        "executor_target": "dq-engine",
        "queue_key": "dq-gx:join-pair-materialize",
        "handoff_status": "accepted",
        "handoff_ready": True,
        "submitted_at": "2026-04-19T10:00:00Z",
        "scheduled_at": "2026-04-19T10:00:00Z",
        "execution_contract": {
            "engine_target": "pyspark",
            "execution_shape": "join_pair",
            "traceability": {
                "rule_id": "rule-1",
                "rule_version_id": "rv-1",
                "gx_suite_id": "gx_suite_join",
                "gx_suite_version": 3,
                "data_object_version_id": "dov-left",
            },
            "source_materialization": {
                "landing_zone_artifact_id": "lz_gx_suite_join",
                "landing_zone_version_id": "lzv_3",
                "output_location": "s3://dq-landing-zone-retail-banking/gx/join-pairs/suite_id=gx_suite_join/suite_version=3/format=parquet",
                "join_type": "inner",
                "join_keys": ["order_id"],
                "join_key_pairs": [{"left_attribute": "order_id", "right_attribute": "order_id"}],
                "left_source": {"data_object_id": "do-left", "data_object_version_id": "dov-left", "dataset_id": "ds-left"},
                "right_source": {"data_object_id": "do-right", "data_object_version_id": "dov-right", "dataset_id": "ds-right"},
            },
        },
        "next_dispatch_payload": {
            "run_id": "run-join-1",
            "queue_message_id": "run-join-1",
            "suite_id": "gx_suite_join",
            "suite_version": 3,
            "queue_key": "dq-gx:execution-dispatch",
            "execution_contract": {
                "engine_target": "pyspark",
                "execution_shape": "join_pair",
                "traceability": {
                    "rule_id": "rule-1",
                    "rule_version_id": "rv-1",
                    "gx_suite_id": "gx_suite_join",
                    "gx_suite_version": 3,
                    "data_object_version_id": "dov-left",
                },
                "source_materialization": {
                    "output_location": "s3://dq-landing-zone-retail-banking/gx/join-pairs/suite_id=gx_suite_join/suite_version=3/format=parquet"
                },
            },
        },
    }

    worker._process_job(config, redis_client=redis_client, raw_job=json.dumps(payload), token_provider=object())

    assert spark.stopped is True
    assert len(progress_calls) == 3
    assert redis_client.calls == [("dq-gx:execution-dispatch", payload["next_dispatch_payload"])]
