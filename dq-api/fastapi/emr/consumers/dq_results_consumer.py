"""DQ Results Kafka consumer for EMR.

Consumes DQ execution results from Kafka and stores them in the EMR repository,
linking each result to the correct delivery via delivery_id and delivery_time_event.

Environment variables:
    KAFKA_BOOTSTRAP_SERVERS — comma-separated broker list
    KAFKA_DQ_RESULTS_TOPIC  — topic to consume from (default: dq-made-easy.dq.results)
    KAFKA_CONSUMER_GROUP_ID — consumer group id (default: emr-dq-results-group)
    EMR_DQ_RESULTS_ENABLED  — enable DQ results consumer (default: false)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import UTC, datetime
from typing import Any

from emr.domain.dq_result import EmrDqResultEntity
from emr.repository import InMemoryEmrRepository

logger = logging.getLogger(__name__)

# Default Kafka topic for DQ results
DEFAULT_DQ_RESULTS_TOPIC = "dq-made-easy.dq.results"
DEFAULT_CONSUMER_GROUP = "emr-dq-results-group"


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    return val.strip()


def _env_bool(name: str, default: bool) -> bool:
    val = _env(name)
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes")


class DqResultsConsumer:
    """Consumes DQ results from Kafka and stores them in EMR.

    This consumer reads DQ execution results from a Kafka topic, parses each
    message, extracts the delivery_id and delivery_time_event, and stores the
    result in the EMR repository linked to the correct delivery.

    The consumer can be started as a background task in the EMR app or run
    as a standalone process.
    """

    def __init__(
        self,
        repository: InMemoryEmrRepository,
        bootstrap_servers: str | None = None,
        topic: str | None = None,
        group_id: str | None = None,
    ) -> None:
        self.repository = repository
        self.bootstrap_servers = bootstrap_servers or _env("KAFKA_BOOTSTRAP_SERVERS")
        self.topic = topic or _env("KAFKA_DQ_RESULTS_TOPIC", DEFAULT_DQ_RESULTS_TOPIC)
        self.group_id = group_id or _env("KAFKA_CONSUMER_GROUP_ID", DEFAULT_CONSUMER_GROUP)
        self._running = False
        self._consumer = None
        self._shutdown = False

        if self.bootstrap_servers:
            self._try_init_consumer()

    def _try_init_consumer(self) -> None:
        """Initialize Kafka consumer if kafka-python is available."""
        try:
            from kafka import KafkaConsumer

            self._consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers.split(","),
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                max_poll_records=500,
                value_deserializer=lambda v: v,
                key_deserializer=lambda k: k.decode("utf-8") if k else None,
            )
            logger.info(
                "DQ results consumer initialized: topic=%s group=%s",
                self.topic,
                self.group_id,
            )
        except ImportError:
            logger.warning("kafka-python not installed; DQ results consumer disabled")
            self._consumer = None
        except Exception as exc:
            logger.error("Failed to initialize Kafka consumer: %s", exc)
            self._consumer = None

    @property
    def is_available(self) -> bool:
        """Check if the consumer is available and connected."""
        return self._consumer is not None and bool(self.bootstrap_servers)

    def start(self) -> None:
        """Start the consumer in a background loop."""
        if not self.is_available:
            logger.warning("DQ results consumer not available; skipping start")
            return

        self._running = True
        self._shutdown = False

        # Signal handling for graceful shutdown
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle_signal)

        self._run_loop()

    def stop(self) -> None:
        """Stop the consumer gracefully."""
        self._running = False
        self._shutdown = True
        if self._consumer:
            self._consumer.close()
            logger.info("DQ results consumer stopped")

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        logger.info("Received signal %d, shutting down DQ results consumer...", signum)
        self._shutdown = True
        self.stop()

    def _run_loop(self) -> None:
        """Main consumption loop."""
        while self._running and not self._shutdown:
            try:
                records = self._consumer.poll(timeout_ms=1000)
                for _tp, messages in records.items():
                    for msg in messages:
                        self._process_message(msg)
            except Exception as exc:
                logger.error("Error in DQ results consumer loop: %s", exc)
                time.sleep(1)

    def _process_message(self, msg: Any) -> None:
        """Process a single Kafka message containing a DQ result."""
        try:
            # Deserialize value
            if isinstance(msg.value, bytes):
                payload = json.loads(msg.value.decode("utf-8"))
            else:
                payload = msg.value

            result = self._parse_result(payload)
            if result:
                self.repository.store_dq_result(result)
                logger.debug(
                    "Stored DQ result: delivery_id=%s execution_run_id=%s status=%s",
                    result.delivery_id,
                    result.execution_run_id,
                    result.status,
                )
        except Exception as exc:
            logger.error("Failed to process DQ result message at offset %d: %s", msg.offset, exc)

    def _parse_result(self, payload: dict[str, Any]) -> EmrDqResultEntity | None:
        """Parse a Kafka message into a DQ result entity.

        The message must contain a delivery_id to link to a delivery.
        If delivery_time_event is present, it links to a specific occurrence.
        """
        delivery_id = payload.get("deliveryId") or payload.get("delivery_id")
        if not delivery_id:
            logger.warning("DQ result message missing delivery_id, skipping")
            return None

        return EmrDqResultEntity(
            delivery_id=delivery_id,
            delivery_time_event=payload.get("deliveryTimeEvent") or payload.get("delivery_time_event"),
            execution_run_id=payload.get("executionRunId") or payload.get("execution_run_id", ""),
            rule_id=payload.get("ruleId") or payload.get("rule_id", ""),
            rule_name=payload.get("ruleName") or payload.get("rule_name"),
            status=payload.get("status", "unknown"),
            result=payload.get("result"),
            passed=payload.get("passed"),
            score=payload.get("score"),
            score_label=payload.get("scoreLabel") or payload.get("score_label"),
            total_count=payload.get("totalCount") or payload.get("total_count"),
            valid_count=payload.get("validCount") or payload.get("valid_count"),
            invalid_count=payload.get("invalidCount") or payload.get("invalid_count"),
            warning_count=payload.get("warningCount") or payload.get("warning_count"),
            error_count=payload.get("errorCount") or payload.get("error_count"),
            observed_at=payload.get("observedAt") or payload.get("observed_at"),
            duration_ms=payload.get("durationMs") or payload.get("duration_ms"),
            message=payload.get("message"),
            data_product_id=payload.get("dataProductId") or payload.get("data_product_id"),
            data_set_id=payload.get("dataSetId") or payload.get("data_set_id"),
            workspace_id=payload.get("workspaceId") or payload.get("workspace_id"),
            created_at=datetime.now(UTC).isoformat(),
        )

    def process_batch(self, results: list[dict[str, Any]]) -> int:
        """Process a batch of DQ results directly (for testing or non-Kafka sources).

        Args:
            results: List of DQ result payloads

        Returns:
            Number of results stored
        """
        count = 0
        for payload in results:
            result = self._parse_result(payload)
            if result:
                self.repository.store_dq_result(result)
                count += 1
        return count
