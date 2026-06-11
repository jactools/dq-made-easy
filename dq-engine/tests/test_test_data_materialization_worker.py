from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
DQ_UTILS_SRC = os.path.join(REPO_ROOT, "dq-utils", "src")

sys.path.insert(0, DQ_UTILS_SRC)
sys.path.insert(0, ENGINE_DIR)

from test_data_materialization_worker import WorkerConfig
from test_data_materialization_worker import _build_rows
from test_data_materialization_worker import _process_job
from test_data_materialization_worker import _resolve_spark_ui_port
from test_data_materialization_worker import _sample_value_for_attribute
from test_data_materialization_worker import _upload_directory_to_s3


class _StubTokenProvider:
    def get_token(self, correlation_id: str | None = None) -> str:
        return "token"


class _StubRedisClient:
    def __init__(self, initial_record: dict[str, object]) -> None:
        self._store = {
            "test-data-materialization-request:tdm-1": json.dumps(initial_record)
        }

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    def record(self) -> dict[str, object]:
        raw = self._store["test-data-materialization-request:tdm-1"]
        return json.loads(raw)


class TestDataMaterializationWorkerSamplingTests(unittest.TestCase):
    def test_resolve_spark_ui_port_defaults_to_4044(self) -> None:
        previous = os.environ.get("DQ_SPARK_UI_PORT")
        try:
            os.environ.pop("DQ_SPARK_UI_PORT", None)
            self.assertEqual(_resolve_spark_ui_port(), 4044)
        finally:
            if previous is None:
                os.environ.pop("DQ_SPARK_UI_PORT", None)
            else:
                os.environ["DQ_SPARK_UI_PORT"] = previous

    def test_sample_value_for_decimal_attribute_returns_decimal(self) -> None:
        value = _sample_value_for_attribute({"name": "total_amount", "type": "decimal"}, 100)

        self.assertEqual(value, Decimal("101"))

    def test_sample_value_for_numeric_attribute_returns_decimal(self) -> None:
        value = _sample_value_for_attribute({"name": "credit_limit", "type": "numeric"}, 4)

        self.assertEqual(value, Decimal("5"))

    def test_sample_value_for_timestamp_attribute_returns_recent_iso_timestamp(self) -> None:
        before = datetime.now(UTC)

        value = _sample_value_for_attribute({"name": "created_at", "type": "timestamp"}, 3)

        after = datetime.now(UTC)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        self.assertGreaterEqual(parsed, before - timedelta(minutes=1))
        self.assertLessEqual(parsed, after)

    def test_build_rows_uses_operational_order_status_values(self) -> None:
        rows = _build_rows(
            [
                {"name": "order_id", "type": "string", "format": "uuid"},
                {"name": "status", "type": "string"},
            ],
            4,
        )

        self.assertEqual([row["status"] for row in rows], ["pending", "completed", "cancelled", "pending"])

    def test_build_rows_uses_contextual_contact_values(self) -> None:
        rows = _build_rows(
            [
                {"name": "contact_id", "type": "string", "format": "uuid"},
                {"name": "preferred_contact", "type": "string"},
                {"name": "contact_type", "type": "string"},
            ],
            4,
        )

        self.assertEqual([row["preferred_contact"] for row in rows], ["email", "phone", "email", "phone"])
        self.assertEqual([row["contact_type"] for row in rows], ["billing", "sales", "support", "service"])

    def test_build_rows_uses_contextual_payment_method_values(self) -> None:
        rows = _build_rows(
            [
                {"name": "transaction_id", "type": "string", "format": "uuid"},
                {"name": "currency", "type": "string"},
                {"name": "payment_method", "type": "string"},
            ],
            4,
        )

        self.assertEqual([row["currency"] for row in rows], ["USD", "EUR", "USD", "EUR"])
        self.assertEqual([row["payment_method"] for row in rows], ["card", "card", "ach", "sepa"])

    def test_build_rows_uses_supported_warehouse_ids(self) -> None:
        rows = _build_rows(
            [
                {"name": "inventory_id", "type": "string", "format": "uuid"},
                {"name": "warehouse_id", "type": "string"},
            ],
            4,
        )

        self.assertEqual([row["warehouse_id"] for row in rows], ["WH-001", "WH-002", "WH-001", "WH-002"])


class _FakeS3Client:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []
        self.upload_calls: list[tuple[str, str, str]] = []

    def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
        self.list_calls.append(dict(kwargs))
        return {
            "Contents": [
                {"Key": "generated/dov-7/old-part-00000.snappy.parquet"},
                {"Key": "generated/dov-7/.old-part-00000.snappy.parquet.crc"},
            ],
            "IsTruncated": False,
        }

    def delete_objects(self, **kwargs: object) -> None:
        self.delete_calls.append(dict(kwargs))

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.upload_calls.append((filename, bucket, key))


class TestDataMaterializationWorkerS3UploadTests(unittest.TestCase):
    def _build_config(self) -> WorkerConfig:
        return WorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-test-data:materialize",
            processing_queue_key="dq-test-data:materialize:processing",
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            output_prefix="s3a://dq-test-data",
            s3_endpoint="http://aistor:9000",
            s3_access_key="aistor",
            s3_secret_key="aistorpass",
            s3_region="eu-west-1",
            s3_path_style_access=True,
            s3_ssl_enabled=False,
            max_rows_per_request=5000,
            poll_timeout_seconds=5,
        )

    def test_upload_directory_to_s3_replaces_existing_prefix_and_skips_hidden_files(self) -> None:
        fake_client = _FakeS3Client()

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "part-00000.snappy.parquet").write_text("parquet-data")
            (base / ".part-00000.snappy.parquet.crc").write_text("crc-data")

            with patch("boto3.client", return_value=fake_client):
                _upload_directory_to_s3(
                    self._build_config(),
                    local_dir=tmpdir,
                    bucket="dq-test-data",
                    key_prefix="generated/dov-7",
                )

        self.assertEqual(fake_client.list_calls, [{"Bucket": "dq-test-data", "Prefix": "generated/dov-7"}])
        self.assertEqual(len(fake_client.delete_calls), 1)
        self.assertEqual(
            fake_client.delete_calls[0],
            {
                "Bucket": "dq-test-data",
                "Delete": {
                    "Objects": [
                        {"Key": "generated/dov-7/old-part-00000.snappy.parquet"},
                        {"Key": "generated/dov-7/.old-part-00000.snappy.parquet.crc"},
                    ]
                },
            },
        )
        self.assertEqual(len(fake_client.upload_calls), 1)
        self.assertEqual(fake_client.upload_calls[0][1:], ("dq-test-data", "generated/dov-7/part-00000.snappy.parquet"))


class TestDataMaterializationWorkerApiCallbackTests(unittest.TestCase):
    def _build_config(self) -> WorkerConfig:
        return WorkerConfig(
            redis_url="redis://redis:6379/0",
            queue_key="dq-test-data:materialize",
            processing_queue_key="dq-test-data:materialize:processing",
            api_url="http://kong:8000",
            spark_master="local[*]",
            spark_ui_port=4044,
            output_prefix="s3a://dq-test-data",
            s3_endpoint="http://aistor:9000",
            s3_access_key="aistor",
            s3_secret_key="aistorpass",
            s3_region="eu-west-1",
            s3_path_style_access=True,
            s3_ssl_enabled=False,
            max_rows_per_request=5000,
            poll_timeout_seconds=5,
        )

    def test_process_job_reports_completion_via_api_and_marks_record_completed(self) -> None:
        redis_client = _StubRedisClient(
            {
                "request_id": "tdm-1",
                "job_id": "tdmj-1",
                "status": "pending",
                "data_object_version_id": "dov-1",
                "sample_count": 3,
                "output_format": "parquet",
                "output_uri": "s3a://dq-test-data/generated/dov-1",
                "correlation_id": "corr-tdm-1",
            }
        )
        raw_job = json.dumps(
            {
                "type": "test_data_materialization",
                "job_id": "tdmj-1",
                "materialization_request_id": "tdm-1",
                "correlation_id": "corr-tdm-1",
                "payload": {
                    "data_object_version_id": "dov-1",
                    "sample_count": 3,
                    "output_format": "parquet",
                    "output_uri": "s3a://dq-test-data/generated/dov-1",
                    "attributes": [{"name": "id", "type": "integer"}],
                },
            }
        )

        with patch("test_data_materialization_worker._ensure_bucket_exists", return_value=None), patch(
            "test_data_materialization_worker._create_spark_session",
            return_value=object(),
        ), patch(
            "test_data_materialization_worker._build_rows",
            return_value=[{"id": 1}, {"id": 2}, {"id": 3}],
        ), patch(
            "test_data_materialization_worker._write_dataset",
            return_value=3,
        ), patch(
            "test_data_materialization_worker._api_report_materialization_completion",
            return_value={
                "data_deliveries": [
                    {
                        "data_object_version_id": "dov-1",
                        "data_delivery_id": "del-tdm-1",
                        "delivery_note": {
                            "id": "note-del-tdm-1",
                            "data_delivery_id": "del-tdm-1",
                            "delivery_format": "parquet",
                        },
                    }
                ],
            },
        ) as report_completion:
            _process_job(
                self._build_config(),
                r=redis_client,
                raw_job=raw_job,
                token_provider=_StubTokenProvider(),
            )

        report_completion.assert_called_once()
        record = redis_client.record()
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["result"]["data_delivery_id"], "del-tdm-1")
        self.assertEqual(record["result"]["delivery_note"]["data_delivery_id"], "del-tdm-1")
        self.assertEqual(record["result"]["row_count"], 3)
        self.assertEqual(record["result"]["delivery_summary"]["target_count"], 1)
        self.assertEqual(record["result"]["delivery_summary"]["data_delivery_ids"], ["del-tdm-1"])
        self.assertEqual(record["result"]["target_results"][0]["data_delivery_id"], "del-tdm-1")

    def test_process_job_handles_multi_target_materialization_batches(self) -> None:
        redis_client = _StubRedisClient(
            {
                "request_id": "tdm-1",
                "job_id": "tdmj-1",
                "status": "pending",
                "data_object_version_id": "dov-3",
                "sample_count": 3,
                "output_format": "parquet",
                "output_uri": "s3a://dq-test-data/generated",
                "correlation_id": "corr-tdm-1",
            }
        )
        raw_job = json.dumps(
            {
                "type": "test_data_materialization",
                "job_id": "tdmj-1",
                "materialization_request_id": "tdm-1",
                "correlation_id": "corr-tdm-1",
                "payload": {
                    "data_object_version_id": "dov-3",
                    "sample_count": 3,
                    "output_format": "parquet",
                    "output_uri": "s3a://dq-test-data/generated",
                    "targets": [
                        {
                            "data_object_version_id": "dov-3",
                            "sample_count": 3,
                            "output_format": "parquet",
                            "output_uri": "s3a://dq-test-data/generated/data_object_version_id=dov-3",
                            "attributes": [{"name": "id", "type": "integer"}],
                        },
                        {
                            "data_object_version_id": "dov-23",
                            "sample_count": 3,
                            "output_format": "parquet",
                            "output_uri": "s3a://dq-test-data/generated/data_object_version_id=dov-23",
                            "attributes": [{"name": "id", "type": "integer"}],
                        },
                    ],
                },
            }
        )

        with patch("test_data_materialization_worker._ensure_bucket_exists", return_value=None), patch(
            "test_data_materialization_worker._create_spark_session",
            return_value=object(),
        ), patch(
            "test_data_materialization_worker._build_rows",
            return_value=[{"id": 1}, {"id": 2}, {"id": 3}],
        ), patch(
            "test_data_materialization_worker._write_dataset",
            side_effect=[3, 3],
        ), patch(
            "test_data_materialization_worker._api_report_materialization_completion",
            return_value={
                "data_deliveries": [
                    {
                        "data_object_version_id": "dov-3",
                        "data_delivery_id": "del-tdm-3",
                        "delivery_note": {"data_delivery_id": "del-tdm-3"},
                    },
                    {
                        "data_object_version_id": "dov-23",
                        "data_delivery_id": "del-tdm-23",
                        "delivery_note": {"data_delivery_id": "del-tdm-23"},
                    },
                ],
            },
        ):
            _process_job(
                self._build_config(),
                r=redis_client,
                raw_job=raw_job,
                token_provider=_StubTokenProvider(),
            )

        record = redis_client.record()
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["result"]["row_count"], 6)
        self.assertEqual(record["result"]["delivery_summary"]["target_count"], 2)
        self.assertEqual(record["result"]["delivery_summary"]["data_delivery_count"], 2)
        self.assertEqual(len(record["result"]["target_results"]), 2)
        self.assertEqual(record["result"]["target_results"][1]["data_delivery_id"], "del-tdm-23")

    def test_process_generic_batch_job_marks_request_record_completed(self) -> None:
        redis_client = _StubRedisClient(
            {
                "request_id": "tdm-1",
                "job_id": "tdmj-1",
                "request_contract": "catalog_materialization_v1",
                "status": "pending",
                "data_object_version_id": "dov-3",
                "target_data_object_version_ids": ["dov-3", "dov-23"],
                "sample_count": 12,
                "output_format": "parquet",
                "output_uri": "s3a://dq-test-data/generated/catalog-integration-batch",
                "correlation_id": "corr-tdm-1",
                "selection": {
                    "selector_type": "data_set_id",
                    "requested": {"data_set_id": "ds-1"},
                    "resolved": {
                        "target_count": 2,
                        "data_object_version_ids": ["dov-3", "dov-23"],
                        "targets": [
                            {
                                "data_object_version_id": "dov-3",
                                "output_uri": "s3a://dq-test-data/generated/catalog-integration-batch/data_object_version_id=dov-3/attr_hash=all/sample_count=12/format=parquet",
                                "output_format": "parquet",
                            },
                            {
                                "data_object_version_id": "dov-23",
                                "output_uri": "s3a://dq-test-data/generated/catalog-integration-batch/data_object_version_id=dov-23/attr_hash=all/sample_count=12/format=parquet",
                                "output_format": "parquet",
                            },
                        ],
                    },
                },
            }
        )
        raw_job = json.dumps(
            {
                "type": "test_data_materialization",
                "job_id": "tdmj-1",
                "materialization_request_id": "tdm-1",
                "correlation_id": "corr-tdm-1",
                "payload": {
                    "data_object_version_id": "dov-3",
                    "sample_count": 12,
                    "output_format": "parquet",
                    "output_uri": "s3a://dq-test-data/generated/catalog-integration-batch",
                    "targets": [
                        {
                            "data_object_version_id": "dov-3",
                            "sample_count": 12,
                            "output_format": "parquet",
                            "output_uri": "s3a://dq-test-data/generated/catalog-integration-batch/data_object_version_id=dov-3/attr_hash=all/sample_count=12/format=parquet",
                            "attributes": [{"name": "id", "type": "integer"}],
                        },
                        {
                            "data_object_version_id": "dov-23",
                            "sample_count": 12,
                            "output_format": "parquet",
                            "output_uri": "s3a://dq-test-data/generated/catalog-integration-batch/data_object_version_id=dov-23/attr_hash=all/sample_count=12/format=parquet",
                            "attributes": [{"name": "contact_id", "type": "string"}],
                        },
                    ],
                },
            }
        )

        with patch("test_data_materialization_worker._ensure_bucket_exists", return_value=None), patch(
            "test_data_materialization_worker._create_spark_session",
            return_value=object(),
        ), patch(
            "test_data_materialization_worker._build_rows",
            side_effect=[
                [{"id": 1}] * 12,
                [{"contact_id": "c-1"}] * 12,
            ],
        ), patch(
            "test_data_materialization_worker._write_dataset",
            side_effect=[12, 9],
        ), patch(
            "test_data_materialization_worker._api_report_materialization_completion",
            return_value={
                "data_deliveries": [
                    {
                        "data_object_version_id": "dov-3",
                        "data_delivery_id": "del-tdm-3",
                        "delivery_note": {"data_delivery_id": "del-tdm-3", "delivery_format": "parquet"},
                    },
                    {
                        "data_object_version_id": "dov-23",
                        "data_delivery_id": "del-tdm-23",
                        "delivery_note": {"data_delivery_id": "del-tdm-23", "delivery_format": "parquet"},
                    },
                ],
            },
        ) as report_completion:
            _process_job(
                self._build_config(),
                r=redis_client,
                raw_job=raw_job,
                token_provider=_StubTokenProvider(),
            )

        report_completion.assert_called_once()
        callback_kwargs = report_completion.call_args.kwargs
        self.assertEqual(callback_kwargs["request_id"], "tdm-1")
        self.assertEqual(callback_kwargs["correlation_id"], "corr-tdm-1")
        self.assertEqual(
            callback_kwargs["target_results"],
            [
                {
                    "data_object_version_id": "dov-3",
                    "row_count": 12,
                    "output_uri": "s3a://dq-test-data/generated/catalog-integration-batch/data_object_version_id=dov-3/attr_hash=all/sample_count=12/format=parquet",
                    "output_format": "parquet",
                },
                {
                    "data_object_version_id": "dov-23",
                    "row_count": 9,
                    "output_uri": "s3a://dq-test-data/generated/catalog-integration-batch/data_object_version_id=dov-23/attr_hash=all/sample_count=12/format=parquet",
                    "output_format": "parquet",
                },
            ],
        )

        record = redis_client.record()
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["request_contract"], "catalog_materialization_v1")
        self.assertEqual(record["target_data_object_version_ids"], ["dov-3", "dov-23"])
        self.assertEqual(record["selection"]["selector_type"], "data_set_id")
        self.assertEqual(record["selection"]["resolved"]["target_count"], 2)
        self.assertEqual(record["result"]["row_count"], 21)
        self.assertEqual(record["result"]["output_uri"], "s3a://dq-test-data/generated/catalog-integration-batch")
        self.assertEqual(record["result"]["data_delivery_ids"], ["del-tdm-3", "del-tdm-23"])
        self.assertEqual(record["result"]["delivery_summary"]["target_count"], 2)
        self.assertEqual(record["result"]["delivery_summary"]["data_delivery_count"], 2)
        self.assertEqual(record["result"]["delivery_summary"]["total_row_count"], 21)
        self.assertIsNone(record["result"]["data_delivery_id"])
        self.assertIsNone(record["result"]["delivery_note"])
        self.assertEqual(
            [item["data_object_version_id"] for item in record["result"]["target_results"]],
            ["dov-3", "dov-23"],
        )
        self.assertEqual(record["result"]["target_results"][0]["data_delivery_id"], "del-tdm-3")
        self.assertEqual(record["result"]["target_results"][1]["data_delivery_id"], "del-tdm-23")


if __name__ == "__main__":
    unittest.main()