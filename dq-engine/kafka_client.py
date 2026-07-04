from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dq_utils.logging_utils import log_event

logger = logging.getLogger(__name__)


@dataclass
class KafkaConfig:
    bootstrap_servers: str
    topic_prefix: str = "dq-made-easy"
    s3_bucket: str = "dq-gx-exceptions"
    s3_prefix: str = "gx-exceptions"
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"
    batch_size: int = 10000
    flush_interval_seconds: float = 30.0
    max_batch_bytes: int = 10_000_000  # 10MB


class KafkaExceptionPublisher:
    """Publishes exception violations to Kafka for downstream processing."""
    
    def __init__(self, config: KafkaConfig) -> None:
        self.config = config
        self._producer = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._batch: list[dict[str, Any]] = []
        self._batch_bytes = 0
        self._batch_task: asyncio.Task | None = None
        
        # Topic names
        self.violation_topic = f"{config.topic_prefix}.gx.violations"
        self.metrics_topic = f"{config.topic_prefix}.gx.metrics"
        
        logger.info("Kafka publisher initialized for topic: %s", self.violation_topic)
    
    async def start(self) -> None:
        """Start the Kafka publisher."""
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._batch_task = asyncio.create_task(self._flush_loop())
        
        # Import kafka-python here (optional dependency)
        try:
            from kafka import KafkaProducer
            from kafka.errors import KafkaTimeoutError, KafkaError
            
            self._producer = KafkaProducer(
                bootstrap_servers=self.config.bootstrap_servers.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
                request_timeout_ms=30000,
                linger_ms=50,  # Small delay for batching
                compression_type="gzip",
            )
            
            log_event(logger, "kafka.producer.started", component="dq-engine-kafka",
                     topic=self.violation_topic, servers=self.config.bootstrap_servers)
            
        except ImportError:
            logger.warning("kafka-python not installed, running in no-op mode")
            self._producer = None
        except Exception as exc:
            logger.error("Failed to create Kafka producer: %s", exc)
            self._producer = None
    
    async def stop(self) -> None:
        """Stop the Kafka publisher and flush remaining messages."""
        self._running = False
        
        # Flush remaining batch
        if self._batch:
            await self._flush_batch()
        
        # Wait for batch task
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
        
        # Close producer
        if self._producer:
            try:
                self._producer.flush()
                self._producer.close(timeout=10)
            except Exception as exc:
                logger.error("Error closing Kafka producer: %s", exc)
        
        log_event(logger, "kafka.producer.stopped", component="dq-engine-kafka",
                 topic=self.violation_topic)
    
    async def publish_violations(self, violations: Sequence[Mapping[str, Any]]) -> None:
        """Publish violations to Kafka for S3 storage."""
        if not self._producer:
            # No-op if Kafka not available
            return
        
        normalized_violations = [self._normalize_violation(v) for v in violations]
        
        for violation in normalized_violations:
            # Create a unique key for ordering (data_object_version_id + violation_id)
            key = f"{violation['data_object_version_id']}:{violation['violation_id']}"
            
            # Add batch metadata
            message = {
                **violation,
                "kafka": {
                    "publishedAt": datetime.now(UTC).isoformat(),
                    "batchSize": len(self._batch),
                    "batchBytes": self._batch_bytes,
                }
            }
            
            # Try to send asynchronously
            try:
                future = self._producer.send(
                    self.violation_topic,
                    key=key.encode("utf-8"),
                    value=message,
                )
                # Add to tracking batch
                self._batch.append(message)
                self._batch_bytes += len(json.dumps(message).encode("utf-8"))
                
                # Check if we should flush
                if len(self._batch) >= self.config.batch_size:
                    await self._flush_batch()
                elif self._batch_bytes >= self.config.max_batch_bytes:
                    await self._flush_batch()
                    
            except Exception as exc:
                logger.error("Failed to send violation to Kafka: %s", exc)
    
    async def _flush_loop(self) -> None:
        """Periodic flush of pending messages."""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval_seconds)
                if self._batch:
                    await self._flush_batch()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in Kafka flush loop: %s", exc)
    
    async def _flush_batch(self) -> None:
        """Flush the current batch to Kafka."""
        if not self._batch:
            return
        
        batch_count = len(self._batch)
        batch_bytes = self._batch_bytes
        
        # Trigger flush
        if self._producer:
            try:
                self._producer.flush()
            except Exception as exc:
                logger.error("Error flushing Kafka producer: %s", exc)
        
        # Clear batch
        self._batch.clear()
        self._batch_bytes = 0
        
        log_event(logger, "kafka.flush.completed", component="dq-engine-kafka",
                 topic=self.violation_topic, batchCount=batch_count, batchBytes=batch_bytes)
    
    def _normalize_violation(self, violation: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize violation record for Kafka."""
        # Extract key fields
        normalized = {
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
        return normalized


async def build_kafka_publisher() -> KafkaExceptionPublisher | None:
    """Build Kafka publisher from environment configuration."""
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS") or os.getenv("KAFKA_SERVERS")
    if not bootstrap_servers:
        logger.warning("KAFKA_BOOTSTRAP_SERVERS not set, skipping Kafka publisher")
        return None
    
    config = KafkaConfig(
        bootstrap_servers=bootstrap_servers,
        topic_prefix=os.getenv("KAFKA_TOPIC_PREFIX", "dq-made-easy"),
        s3_bucket=os.getenv("GX_EXCEPTION_STORAGE_BUCKET", "dq-gx-exceptions"),
        s3_prefix=os.getenv("GX_EXCEPTION_STORAGE_PREFIX", "gx-exceptions"),
        s3_endpoint=os.getenv("GX_EXCEPTION_STORAGE_ENDPOINT"),
        s3_access_key=os.getenv("GX_EXCEPTION_STORAGE_ACCESS_KEY"),
        s3_secret_key=os.getenv("GX_EXCEPTION_STORAGE_SECRET_KEY"),
        s3_region=os.getenv("GX_EXCEPTION_STORAGE_REGION", "us-east-1"),
        batch_size=int(os.getenv("KAFKA_BATCH_SIZE", "10000")),
        flush_interval_seconds=float(os.getenv("KAFKA_FLUSH_INTERVAL_SECONDS", "30.0")),
        max_batch_bytes=int(os.getenv("KAFKA_MAX_BATCH_BYTES", "10000000")),
    )
    
    return KafkaExceptionPublisher(config)
