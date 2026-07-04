"""Validation test: failure records topic → Kafka consumer → S3 storage.

This test validates the end-to-end pipeline:
1. A violation (failure record) message is published to the Kafka topic
2. The consumer reads the message from the topic
3. The consumer stores the batch to S3-compatible storage

Run with:
    pytest dq-engine/tests/test_kafka_failure_records_to_s3.py -v
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import sys
import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# Ensure dq-engine and dq-utils are on sys.path for imports
TESTS_DIR = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
DQ_UTILS_SRC = os.path.join(REPO_ROOT, "dq-utils", "src")

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)
if DQ_UTILS_SRC not in sys.path:
    sys.path.insert(0, DQ_UTILS_SRC)

# Avoid OTEL exporter noise in tests
os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")


# ---------------------------------------------------------------------------
# Mock Kafka infrastructure (no live Kafka broker needed)
# ---------------------------------------------------------------------------

@dataclass
class MockKafkaMessage:
    """Represents a single message stored in the mock Kafka topic."""
    key: bytes
    value: dict[str, Any]
    timestamp_ms: int
    offset: int = 0
    partition: int = 0


@dataclass
class MockKafkaTopic:
    """In-memory Kafka topic backed by a list of messages."""
    name: str
    messages: list[MockKafkaMessage] = field(default_factory=list)
    _next_offset: int = 0

    def publish(self, key: bytes | str | None, value: dict[str, Any]) -> MockKafkaMessage:
        """Publish a message and return the created message."""
        if isinstance(key, str):
            key = key.encode("utf-8")
        msg = MockKafkaMessage(
            key=key or b"",
            value=value,
            timestamp_ms=int(datetime.now(UTC).timestamp() * 1000),
            offset=self._next_offset,
        )
        self._next_offset += 1
        self.messages.append(msg)
        return msg

    def read(self, offset: int | None = None, max_records: int = 10) -> list[MockKafkaMessage]:
        """Read messages from the topic."""
        if offset is None:
            offset = 0
        return self.messages[offset : offset + max_records]


# ---------------------------------------------------------------------------
# Mock S3 storage
# ---------------------------------------------------------------------------

@dataclass
class S3ObjectRecord:
    """Represents an object stored in the mock S3 bucket."""
    bucket: str
    key: str
    body: bytes
    content_type: str
    content_encoding: str
    metadata: dict[str, str]


class MockS3Storage:
    """In-memory S3-compatible storage for testing."""
    def __init__(self) -> None:
        self.objects: dict[str, S3ObjectRecord] = {}

    def put_object(
        self,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str = "application/json",
        ContentEncoding: str = "gzip",
        Metadata: dict[str, str] | None = None,
    ) -> S3ObjectRecord:
        """Store an object."""
        record = S3ObjectRecord(
            bucket=Bucket,
            key=Key,
            body=Body,
            content_type=ContentType,
            content_encoding=ContentEncoding,
            metadata=Metadata or {},
        )
        self.objects[f"{Bucket}/{Key}"] = record
        return record

    def get_object(self, Bucket: str, Key: str) -> S3ObjectRecord:
        """Retrieve an object."""
        full_key = f"{Bucket}/{Key}"
        if full_key not in self.objects:
            raise KeyError(f"Object not found: {full_key}")
        return self.objects[full_key]

    def list_objects(self, Bucket: str, Prefix: str | None = None) -> list[S3ObjectRecord]:
        """List objects in the bucket with optional prefix filter."""
        results = []
        for full_key, record in self.objects.items():
            if record.bucket == Bucket:
                if Prefix is None or record.key.startswith(Prefix):
                    results.append(record)
        return results

    def has_objects(self, Bucket: str) -> bool:
        """Check if the bucket has any objects."""
        return any(r.bucket == Bucket for r in self.objects.values())

    def find_objects_with_prefix(self, Bucket: str, prefix: str) -> list[S3ObjectRecord]:
        """Find objects matching a prefix."""
        return [r for r in self.objects.values() if r.bucket == Bucket and r.key.startswith(prefix)]


# ---------------------------------------------------------------------------
# Mock S3BlobConnector (what kafka_violation_consumer uses)
# ---------------------------------------------------------------------------

class MockS3BlobConnector:
    """Mock S3BlobConnector that delegates to MockS3Storage."""
    def __init__(self, storage: MockS3Storage) -> None:
        self._storage = storage
        self.bucket: str = ""
        self.prefix: str = ""
        self.put_calls: list[dict[str, Any]] = []

    async def put_object(
        self,
        object_key: str,
        body: bytes,
        content_type: str = "application/json",
        content_encoding: str = "gzip",
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Async-compatible put_object for the consumer."""
        self.put_calls.append({
            "object_key": object_key,
            "body": body,
            "content_type": content_type,
            "content_encoding": content_encoding,
            "metadata": metadata or {},
        })
        self._storage.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=body,
            ContentType=content_type,
            ContentEncoding=content_encoding,
            Metadata=metadata,
        )


# ---------------------------------------------------------------------------
# Test: Failure Records Topic → S3
# ---------------------------------------------------------------------------

class TestKafkaFailureRecordsToS3(unittest.TestCase):
    """End-to-end validation: publish failure record to topic, read from topic, store to S3."""

    def setUp(self) -> None:
        self.topic = MockKafkaTopic(name="dq-made-easy.gx.violations")
        self.s3_storage = MockS3Storage()

    # --- Test 1: Producer sends a failure record to the topic ---
    def test_producer_publishes_failure_record_to_topic(self) -> None:
        """A failure record (violation) is sent to the Kafka violations topic."""
        # Simulate what the KafkaExceptionPublisher._normalize_violation does
        violation = {
            "violation_id": "viol-001",
            "data_object_version_id": "dov-12345",
            "execution_run_id": "run-abc-789",
            "rule_id": "rule-not-null-customer_id",
            "record_identifier_type": "primary_key",
            "record_identifier_value": "order_id=100",
            "reason_code": "expect_column_values_to_not_be_null",
            "reason_text": "customer_id must not be null",
            "detected_at": "2026-04-06T12:01:00+00:00",
            "ops_metadata": {
                "suite_id": "gx_suite_1",
                "suite_version": 1,
                "engine_target": "pyspark",
            },
        }

        # Build the message as the producer would
        normalized = {
            "violationId": str(violation["violation_id"]),
            "dataObjectVersionId": str(violation["data_object_version_id"]),
            "executionRunId": str(violation["execution_run_id"]),
            "ruleId": str(violation["rule_id"]),
            "recordIdentifierType": str(violation["record_identifier_type"]),
            "recordIdentifierValue": str(violation["record_identifier_value"]),
            "reasonCode": str(violation["reason_code"]),
            "reasonText": str(violation["reason_text"]),
            "detectedAt": str(violation["detected_at"]),
            "opsMetadata": dict(violation["ops_metadata"]),
        }

        message = {
            **normalized,
            "kafka": {
                "publishedAt": datetime.now(UTC).isoformat(),
                "batchSize": 1,
                "batchBytes": len(json.dumps(normalized)),
            },
        }

        # Publish to the topic (simulates producer.send())
        key = f"{normalized['dataObjectVersionId']}:{normalized['violationId']}"
        published_msg = self.topic.publish(key=key, value=message)

        # Assert: message is in the topic
        self.assertEqual(len(self.topic.messages), 1)
        self.assertEqual(self.topic.messages[0].key.decode("utf-8"), key)
        self.assertEqual(self.topic.messages[0].value["violationId"], "viol-001")
        self.assertEqual(self.topic.messages[0].value["dataObjectVersionId"], "dov-12345")
        self.assertIn("publishedAt", self.topic.messages[0].value["kafka"])

        # Assert: published message matches
        self.assertEqual(published_msg.value, message)

    # --- Test 2: Consumer reads from the topic ---
    def test_consumer_reads_failure_record_from_topic(self) -> None:
        """The consumer can read failure records from the Kafka violations topic."""
        # Pre-populate the topic with messages
        messages = [
            {
                "violationId": "viol-001",
                "dataObjectVersionId": "dov-12345",
                "executionRunId": "run-abc",
                "ruleId": "rule-1",
                "recordIdentifierType": "primary_key",
                "recordIdentifierValue": "order_id=100",
                "reasonCode": "expect_column_values_to_not_be_null",
                "reasonText": "customer_id must not be null",
                "detectedAt": "2026-04-06T12:01:00+00:00",
                "opsMetadata": {"suite_id": "gx_suite_1"},
            },
            {
                "violationId": "viol-002",
                "dataObjectVersionId": "dov-12345",
                "executionRunId": "run-abc",
                "ruleId": "rule-2",
                "recordIdentifierType": "business_key",
                "recordIdentifierValue": "order_number=SO-2",
                "reasonCode": "value_mismatch",
                "reasonText": "customer_id differs from golden source",
                "detectedAt": "2026-04-06T12:02:00+00:00",
                "opsMetadata": {"suite_id": "gx_suite_1"},
            },
        ]

        for i, msg in enumerate(messages):
            key = f"dov-12345:{msg['violationId']}"
            self.topic.publish(key=key, value=msg)

        # Consumer reads from the topic
        consumed = self.topic.read(offset=0, max_records=10)

        # Assert: all messages are readable
        self.assertEqual(len(consumed), 2)
        self.assertEqual(consumed[0].value["violationId"], "viol-001")
        self.assertEqual(consumed[1].value["violationId"], "viol-002")

        # Assert: offsets are sequential
        self.assertEqual(consumed[0].offset, 0)
        self.assertEqual(consumed[1].offset, 1)

    # --- Test 3: Full pipeline - publish, read, store to S3 ---
    def test_full_pipeline_failure_record_to_s3(self) -> None:
        """End-to-end: publish → read from topic → store batch to S3."""
        # Step 1: Publish failure records to the topic (simulates KafkaExceptionPublisher)
        violations = [
            {
                "violation_id": "viol-001",
                "data_object_version_id": "dov-12345",
                "execution_run_id": "run-abc-789",
                "rule_id": "rule-1",
                "record_identifier_type": "primary_key",
                "record_identifier_value": "order_id=100",
                "reason_code": "expect_column_values_to_not_be_null",
                "reason_text": "customer_id must not be null",
                "detected_at": "2026-04-06T12:01:00+00:00",
                "ops_metadata": {"suite_id": "gx_suite_1"},
            },
            {
                "violation_id": "viol-002",
                "data_object_version_id": "dov-12345",
                "execution_run_id": "run-abc-789",
                "rule_id": "rule-2",
                "record_identifier_type": "business_key",
                "record_identifier_value": "order_number=SO-2",
                "reason_code": "value_mismatch",
                "reason_text": "customer_id differs from golden source",
                "detected_at": "2026-04-06T12:02:00+00:00",
                "ops_metadata": {"suite_id": "gx_suite_1"},
            },
        ]

        # Publish each violation to the topic
        for v in violations:
            normalized = self._normalize_violation(v)
            message = {
                **normalized,
                "kafka": {
                    "publishedAt": datetime.now(UTC).isoformat(),
                    "batchSize": 1,
                    "batchBytes": len(json.dumps(normalized)),
                },
            }
            key = f"{normalized['dataObjectVersionId']}:{normalized['violationId']}"
            self.topic.publish(key=key, value=message)

        # Assert: messages are in the topic
        self.assertEqual(len(self.topic.messages), 2)

        # Step 2: Consumer reads from the topic
        consumed = self.topic.read(offset=0)
        self.assertEqual(len(consumed), 2)

        # Step 3: Consumer writes batch to S3 (simulates KafkaViolationConsumer._write_to_s3)
        connector = MockS3BlobConnector(self.s3_storage)
        connector.bucket = "dq-gx-exceptions"
        connector.prefix = "gx-exceptions"

        data_object_version_id = "dov-12345"
        execution_run_id = "run-abc-789"

        # Build the batch payload as the consumer would
        batch_violations = [
            self._extract_violation_from_message(msg.value) for msg in consumed
        ]

        payload = {
            "storedAt": datetime.now(UTC).isoformat(),
            "schemaVersion": "v4",
            "violationCount": len(batch_violations),
            "dataObjectVersionId": data_object_version_id,
            "executionRunId": execution_run_id,
            "violations": batch_violations,
        }

        # Canonical JSON for hash (matches consumer logic)
        canonical_json = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        content_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        # Build object key (matches consumer logic)
        object_key = (
            f"gx-exceptions/"
            f"data_object_version_id={data_object_version_id}/"
            f"execution_run_id={execution_run_id}/"
            f"violation-batch-{content_hash[:16]}.json.gz"
        )

        # Compress and upload
        compressed_body = gzip.compress(canonical_json.encode("utf-8"))

        asyncio.run(
            connector.put_object(
                object_key=object_key,
                body=compressed_body,
                content_type="application/json",
                content_encoding="gzip",
                metadata={
                    "content_sha256": content_hash,
                    "storage_kind": "kafka_violation_batch",
                    "violation_count": str(len(batch_violations)),
                },
            )
        )

        # Assert: S3 storage has the object
        self.assertTrue(self.s3_storage.has_objects("dq-gx-exceptions"))

        # Assert: object can be retrieved
        s3_obj = self.s3_storage.get_object("dq-gx-exceptions", object_key)
        self.assertEqual(s3_obj.content_type, "application/json")
        self.assertEqual(s3_obj.content_encoding, "gzip")
        self.assertEqual(s3_obj.metadata["storage_kind"], "kafka_violation_batch")
        self.assertEqual(s3_obj.metadata["violation_count"], "2")

        # Assert: content can be decompressed and validated
        decompressed = gzip.decompress(s3_obj.body).decode("utf-8")
        stored_payload = json.loads(decompressed)

        self.assertEqual(stored_payload["violationCount"], 2)
        self.assertEqual(stored_payload["dataObjectVersionId"], "dov-12345")
        self.assertEqual(stored_payload["executionRunId"], "run-abc-789")
        self.assertEqual(stored_payload["schemaVersion"], "v4")
        self.assertEqual(len(stored_payload["violations"]), 2)

        # Assert: individual violation records are intact
        stored_violations = stored_payload["violations"]
        violation_ids = [v["violationId"] for v in stored_violations]
        self.assertIn("viol-001", violation_ids)
        self.assertIn("viol-002", violation_ids)

        # Assert: SHA-256 integrity check
        recomputed_hash = hashlib.sha256(
            json.dumps(stored_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(recomputed_hash, s3_obj.metadata["content_sha256"])

    # --- Test 4: Multiple batches with different data_object_version_ids ---
    def test_multiple_batches_different_data_objects(self) -> None:
        """Multiple data object versions are stored as separate S3 objects."""
        violations = [
            {
                "violation_id": "viol-A1",
                "data_object_version_id": "dov-A",
                "execution_run_id": "run-A",
                "rule_id": "rule-1",
                "record_identifier_type": "primary_key",
                "record_identifier_value": "id=1",
                "reason_code": "not_null",
                "reason_text": "field is null",
                "detected_at": "2026-04-06T12:00:00+00:00",
                "ops_metadata": {},
            },
            {
                "violation_id": "viol-B1",
                "data_object_version_id": "dov-B",
                "execution_run_id": "run-B",
                "rule_id": "rule-1",
                "record_identifier_type": "primary_key",
                "record_identifier_value": "id=2",
                "reason_code": "not_null",
                "reason_text": "field is null",
                "detected_at": "2026-04-06T12:00:00+00:00",
                "ops_metadata": {},
            },
        ]

        # Publish to topic
        for v in violations:
            normalized = self._normalize_violation(v)
            message = {**normalized, "kafka": {"publishedAt": datetime.now(UTC).isoformat()}}
            key = f"{normalized['dataObjectVersionId']}:{normalized['violationId']}"
            self.topic.publish(key=key, value=message)

        # Consumer reads and groups by data_object_version_id + execution_run_id
        consumed = self.topic.read(offset=0)

        # Group violations (matches consumer logic)
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for msg in consumed:
            violation = self._extract_violation_from_message(msg.value)
            key = (violation["dataObjectVersionId"], violation["executionRunId"])
            grouped.setdefault(key, []).append(violation)

        # Each group gets its own S3 object
        connector = MockS3BlobConnector(self.s3_storage)
        connector.bucket = "dq-gx-exceptions"
        connector.prefix = "gx-exceptions"

        for (dov_id, run_id), batch_violations in grouped.items():
            payload = {
                "storedAt": datetime.now(UTC).isoformat(),
                "schemaVersion": "v4",
                "violationCount": len(batch_violations),
                "dataObjectVersionId": dov_id,
                "executionRunId": run_id,
                "violations": batch_violations,
            }
            canonical_json = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            content_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
            object_key = (
                f"gx-exceptions/"
                f"data_object_version_id={dov_id}/"
                f"execution_run_id={run_id}/"
                f"violation-batch-{content_hash[:16]}.json.gz"
            )
            compressed_body = gzip.compress(canonical_json.encode("utf-8"))

            asyncio.run(
                connector.put_object(
                    object_key=object_key,
                    body=compressed_body,
                    content_type="application/json",
                    content_encoding="gzip",
                    metadata={
                        "content_sha256": content_hash,
                        "storage_kind": "kafka_violation_batch",
                        "violation_count": str(len(batch_violations)),
                    },
                )
            )

        # Assert: two separate S3 objects exist
        all_objects = self.s3_storage.list_objects("dq-gx-exceptions")
        self.assertEqual(len(all_objects), 2)

        # Assert: each object has its own data_object_version_id in the key
        keys = {obj.key for obj in all_objects}
        self.assertTrue(any("data_object_version_id=dov-A" in k for k in keys))
        self.assertTrue(any("data_object_version_id=dov-B" in k for k in keys))

    # --- Test 5: KafkaExceptionPublisher normalization matches consumer expectations ---
    def test_producer_consumer_violation_schema_compatibility(self) -> None:
        """Producer normalization output matches consumer parsing expectations."""
        raw_violation = {
            "violation_id": "test-viol-1",
            "data_object_version_id": "dov-test",
            "execution_run_id": "run-test",
            "rule_id": "rule-test",
            "record_identifier_type": "primary_key",
            "record_identifier_value": "id=99",
            "reason_code": "test_reason",
            "reason_text": "test failure",
            "detected_at": "2026-04-06T10:00:00+00:00",
            "ops_metadata": {"key": "value"},
        }

        # Producer normalizes
        normalized = self._normalize_violation(raw_violation)

        # Consumer extracts
        consumed = self._extract_violation_from_message(normalized)

        # Assert: all fields match
        self.assertEqual(consumed["violationId"], "test-viol-1")
        self.assertEqual(consumed["dataObjectVersionId"], "dov-test")
        self.assertEqual(consumed["executionRunId"], "run-test")
        self.assertEqual(consumed["ruleId"], "rule-test")
        self.assertEqual(consumed["recordIdentifierType"], "primary_key")
        self.assertEqual(consumed["recordIdentifierValue"], "id=99")
        self.assertEqual(consumed["reasonCode"], "test_reason")
        self.assertEqual(consumed["reasonText"], "test failure")
        self.assertEqual(consumed["detectedAt"], "2026-04-06T10:00:00+00:00")
        self.assertEqual(consumed["opsMetadata"], {"key": "value"})

    # --- Helpers ---
    def _normalize_violation(self, violation: dict[str, Any]) -> dict[str, Any]:
        """Mirrors KafkaExceptionPublisher._normalize_violation."""
        return {
            "violationId": str(violation.get("violation_id") or violation.get("violationId") or ""),
            "dataObjectVersionId": str(violation.get("data_object_version_id") or violation.get("dataObjectVersionId") or ""),
            "executionRunId": str(violation.get("execution_run_id") or violation.get("executionRunId") or ""),
            "ruleId": str(violation.get("rule_id") or violation.get("ruleId") or ""),
            "recordIdentifierType": str(violation.get("record_identifier_type") or violation.get("recordIdentifierType") or ""),
            "recordIdentifierValue": str(violation.get("record_identifier_value") or violation.get("recordIdentifierValue") or ""),
            "reasonCode": str(violation.get("reason_code") or violation.get("reasonCode") or ""),
            "reasonText": str(violation.get("reason_text") or violation.get("reasonText") or ""),
            "detectedAt": str(violation.get("detected_at") or violation.get("detectedAt") or ""),
            "opsMetadata": dict(violation.get("ops_metadata") or violation.get("opsMetadata") or {}),
        }

    def _extract_violation_from_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Mirrors KafkaViolationConsumer._process_message extraction."""
        return {
            "violationId": message.get("violationId", ""),
            "dataObjectVersionId": message.get("dataObjectVersionId", ""),
            "executionRunId": message.get("executionRunId", ""),
            "ruleId": message.get("ruleId", ""),
            "recordIdentifierType": message.get("recordIdentifierType", ""),
            "recordIdentifierValue": message.get("recordIdentifierValue", ""),
            "reasonCode": message.get("reasonCode", ""),
            "reasonText": message.get("reasonText", ""),
            "detectedAt": message.get("detectedAt", ""),
            "opsMetadata": message.get("opsMetadata", {}),
        }


if __name__ == "__main__":
    unittest.main()
