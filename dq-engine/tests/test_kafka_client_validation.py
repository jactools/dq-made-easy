from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

TESTS_DIR = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
DQ_UTILS_SRC = os.path.join(REPO_ROOT, "dq-utils", "src")

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)
if DQ_UTILS_SRC not in sys.path:
    sys.path.insert(0, DQ_UTILS_SRC)

if "dq_utils.logging_utils" not in sys.modules:
    logging_utils_stub = types.ModuleType("dq_utils.logging_utils")
    logging_utils_stub.log_event = lambda *args, **kwargs: None
    dq_utils_stub = types.ModuleType("dq_utils")
    dq_utils_stub.logging_utils = logging_utils_stub
    sys.modules["dq_utils"] = dq_utils_stub
    sys.modules["dq_utils.logging_utils"] = logging_utils_stub

from kafka_client import KafkaConfig
from kafka_client import KafkaExceptionPublisher
from kafka_client import KafkaViolationValidationError
from kafka_client import VIOLATION_SCHEMA_VERSION
from kafka_client import VIOLATIONS_TOPIC_NAME
from kafka_client import build_kafka_publisher


class KafkaClientValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.publisher = KafkaExceptionPublisher(KafkaConfig(bootstrap_servers="kafka.jac.dot:9092"))
        producer = MagicMock()
        producer.send = MagicMock()
        producer.flush = MagicMock()
        self.publisher._producer = producer

    def test_publish_violations_uses_fixed_topic_and_schema(self) -> None:
        asyncio.run(
            self.publisher.publish_violations(
                [
                    {
                        "violation_id": "viol-1",
                        "data_object_version_id": "dov-1",
                        "execution_run_id": "run-1",
                        "rule_id": "rule-1",
                        "record_identifier_type": "primary_key",
                        "record_identifier_value": "id=1",
                        "reason_code": "not_null",
                        "reason_text": "value cannot be null",
                        "detected_at": "2026-07-05T00:00:00Z",
                        "ops_metadata": {"suite_id": "suite-1"},
                    }
                ]
            )
        )
        self.publisher._producer.send.assert_called_once()
        args = self.publisher._producer.send.call_args.args
        kwargs = self.publisher._producer.send.call_args.kwargs
        self.assertEqual(args[0], VIOLATIONS_TOPIC_NAME)
        self.assertEqual(kwargs["key"], "dov-1:viol-1")
        self.assertEqual(kwargs["value"]["schemaVersion"], VIOLATION_SCHEMA_VERSION)

    def test_publish_violations_rejects_invalid_payload(self) -> None:
        with self.assertRaises(KafkaViolationValidationError):
            asyncio.run(
                self.publisher.publish_violations(
                    [
                        {
                            "data_object_version_id": "dov-1",
                            "execution_run_id": "run-1",
                            "rule_id": "rule-1",
                            "record_identifier_type": "primary_key",
                            "record_identifier_value": "id=1",
                            "reason_code": "not_null",
                            "reason_text": "value cannot be null",
                            "detected_at": "2026-07-05T00:00:00Z",
                            "ops_metadata": {"suite_id": "suite-1"},
                        }
                    ]
                )
            )
        self.publisher._producer.send.assert_not_called()

    def test_build_kafka_publisher_rejects_topic_override(self) -> None:
        previous_bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
        previous_topic = os.environ.get("KAFKA_VIOLATIONS_TOPIC")
        try:
            os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "kafka.jac.dot:9092"
            os.environ["KAFKA_VIOLATIONS_TOPIC"] = "custom.topic"
            with self.assertRaises(ValueError):
                asyncio.run(build_kafka_publisher())
        finally:
            if previous_bootstrap is None:
                os.environ.pop("KAFKA_BOOTSTRAP_SERVERS", None)
            else:
                os.environ["KAFKA_BOOTSTRAP_SERVERS"] = previous_bootstrap
            if previous_topic is None:
                os.environ.pop("KAFKA_VIOLATIONS_TOPIC", None)
            else:
                os.environ["KAFKA_VIOLATIONS_TOPIC"] = previous_topic


if __name__ == "__main__":
    unittest.main()
