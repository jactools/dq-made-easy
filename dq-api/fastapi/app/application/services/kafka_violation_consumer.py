from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aiokafka
from aiokafka import ConsumerRecord

from app.application.services.s3_blob_connector import S3BlobConnector
from app.core.config import Settings
from app.domain.entities import GxExecutionViolationCreateEntity
from app.domain.interfaces import ExceptionFactRepository
from app.domain.interfaces import ExceptionReasonAnalyticsProjectionRepository
from app.infrastructure.orm.session import session_scope
from app.infrastructure.orm.models import GxExecutionViolationRow

logger = logging.getLogger(__name__)


@dataclass
class KafkaConsumerConfig:
    bootstrap_servers: str
    topic: str = "dq-made-easy.gx.violations"
    group_id: str = "dq-made-easy-violation-consumer"
    max_batch_size: int = 10000
    flush_interval_seconds: float = 60.0
    s3_bucket: str = "dq-gx-exceptions"
    s3_prefix: str = "gx-exceptions"
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"
    enable_db_storage: bool = True


class KafkaViolationConsumer:
    """Consumer that reads violations from Kafka and stores to S3 (and optionally DB)."""
    
    def __init__(self, config: KafkaConsumerConfig, settings_provider: Callable[[], Settings]):
        self.config = config
        self.settings_provider = settings_provider
        self._consumer: aiokafka.AIOKafkaConsumer | None = None
        self._running = False
        self._batch: list[dict[str, Any]] = []
        self._batch_bytes = 0
        self._task: asyncio.Task | None = None
        self._s3_connector: S3BlobConnector | None = None
    
    async def start(self) -> None:
        """Start the Kafka consumer."""
        self._running = True
        
        # Initialize S3 connector
        self._s3_connector = S3BlobConnector(
            bucket=self.config.s3_bucket,
            prefix=self.config.s3_prefix,
            endpoint=self.config.s3_endpoint,
            access_key=self.config.s3_access_key,
            secret_key=self.config.s3_secret_key,
            region=self.config.s3_region,
        )
        
        # Create Kafka consumer
        self._consumer = aiokafka.AIOKafkaConsumer(
            self.config.topic,
            bootstrap_servers=self.config.bootstrap_servers,
            group_id=self.config.group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            max_poll_records=1000,
            consumer_timeout_ms=1000,
        )
        
        await self._consumer.start()
        logger.info("Started Kafka violation consumer for topic: %s", self.config.topic)
        
        # Start background flush task
        self._task = asyncio.create_task(self._flush_loop())
    
    async def stop(self) -> None:
        """Stop the consumer and flush remaining batch."""
        self._running = False
        
        # Flush remaining batch
        if self._batch:
            await self._flush_batch()
        
        # Wait for flush task
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # Stop consumer
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        
        logger.info("Stopped Kafka violation consumer for topic: %s", self.config.topic)
    
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
        """Flush the current batch to S3."""
        if not self._batch or not self._s3_connector:
            return
        
        batch_count = len(self._batch)
        batch_bytes = self._batch_bytes
        
        # Group by data_object_version_id and execution_run_id
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for violation in self._batch:
            key = (
                violation.get("dataObjectVersionId", ""),
                violation.get("executionRunId", ""),
            )
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(violation)
        
        # Write each group to S3
        for (data_object_version_id, execution_run_id), violations in grouped.items():
            await self._write_to_s3(data_object_version_id, execution_run_id, violations)
        
        # Clear batch
        self._batch.clear()
        self._batch_bytes = 0
        
        logger.info("Flushed %d violations to S3 in %d batches", batch_count, len(grouped))
    
    async def _write_to_s3(self, data_object_version_id: str, execution_run_id: str, violations: list[dict[str, Any]]) -> None:
        """Write violations to S3 in compressed JSON format."""
        if not self._s3_connector:
            return
        
        # Build payload
        payload = {
            "storedAt": datetime.now(UTC).isoformat(),
            "schemaVersion": "v4",
            "violationCount": len(violations),
            "dataObjectVersionId": data_object_version_id,
            "executionRunId": execution_run_id,
            "violations": violations,
        }
        
        # Canonical JSON for hash
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        content_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        
        # Generate object key
        key_parts = [
            self.config.s3_prefix or "gx-exceptions",
            f"data_object_version_id={data_object_version_id}",
            f"execution_run_id={execution_run_id}",
            f"violation-batch-{content_hash[:16]}.json.gz",
        ]
        object_key = "/".join(part for part in key_parts if part)
        
        # Compress and upload
        compressed_body = gzip.compress(canonical_json.encode("utf-8"))
        
        await self._s3_connector.put_object(
            object_key=object_key,
            body=compressed_body,
            content_type="application/json",
            content_encoding="gzip",
            metadata={
                "content_sha256": content_hash,
                "storage_kind": "kafka_violation_batch",
                "violation_count": str(len(violations)),
            },
        )
        
        logger.debug("Wrote %d violations to S3: %s", len(violations), object_key)
    
    async def _process_message(self, record: ConsumerRecord) -> None:
        """Process a single Kafka message."""
        try:
            # Parse message
            message = json.loads(record.value.decode("utf-8"))
            
            # Extract violation data
            violation = {
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
            
            # Add to batch
            self._batch.append(violation)
            self._batch_bytes += len(json.dumps(violation).encode("utf-8"))
            
            # Check if batch is full
            if len(self._batch) >= self.config.max_batch_size:
                await self._flush_batch()
            
        except Exception as exc:
            logger.error("Error processing Kafka message: %s", exc)
    
    async def __aenter__(self) -> KafkaViolationConsumer:
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()


async def build_kafka_violation_consumer(
    settings: Settings,
    settings_provider: Callable[[], Settings],
) -> KafkaViolationConsumer | None:
    """Build Kafka consumer from environment configuration."""
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS") or os.getenv("KAFKA_SERVERS")
    if not bootstrap_servers:
        logger.warning("KAFKA_BOOTSTRAP_SERVERS not set, skipping Kafka consumer")
        return None
    
    config = KafkaConsumerConfig(
        bootstrap_servers=bootstrap_servers,
        topic=os.getenv("KAFKA_VIOLATIONS_TOPIC", "dq-made-easy.gx.violations"),
        group_id=os.getenv("KAFKA_CONSUMER_GROUP_ID", "dq-made-easy-violation-consumer"),
        max_batch_size=int(os.getenv("KAFKA_CONSUMER_BATCH_SIZE", "10000")),
        flush_interval_seconds=float(os.getenv("KAFKA_CONSUMER_FLUSH_INTERVAL_SECONDS", "60.0")),
        s3_bucket=getattr(settings, "gx_exception_storage_bucket", "dq-gx-exceptions"),
        s3_prefix=getattr(settings, "gx_exception_storage_prefix", "gx-exceptions"),
        s3_endpoint=getattr(settings, "gx_exception_storage_endpoint", None),
        s3_access_key=getattr(settings, "gx_exception_storage_access_key", None),
        s3_secret_key=getattr(settings, "gx_exception_storage_secret_key", None),
        s3_region=getattr(settings, "gx_exception_storage_region", "us-east-1"),
        enable_db_storage=os.getenv("KAFKA_CONSUMER_ENABLE_DB_STORAGE", "true").lower() == "true",
    )
    
    return KafkaViolationConsumer(config, settings_provider)
