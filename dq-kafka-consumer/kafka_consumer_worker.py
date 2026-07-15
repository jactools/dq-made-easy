"""Kafka consumer worker (batch mode).

Lifecycle:
  1. Connect to Kafka, subscribe to the configured topic
  2. Poll messages until the batch timeout fires
  3. Flush the batch to S3 (compressed JSON) and optionally PostgreSQL
  4. Sleep for the configured loop delay
  5. Repeat from step 2
  6. On SIGTERM/SIGINT: flush remaining batch and exit cleanly

Environment variables:
  KAFKA_BOOTSTRAP_SERVERS  (required)  — comma-separated broker list
  KAFKA_TOPIC              (required)  — topic to consume from
  KAFKA_CONSUMER_GROUP_ID  (optional)  — consumer group id (default: dq-consumer-group)
  KAFKA_CONSUMER_POLL_TIMEOUT_SECONDS  (optional) — poll timeout before considering batch done (default: 5)
  KAFKA_CONSUMER_MAX_POLL_RECORDS  (optional) — max records per poll call (default: 500)
  KAFKA_CONSUMER_LOOP_DELAY_SECONDS  (optional) — sleep between batch cycles before exiting (default: 30)
  KAFKA_CONSUMER_BATCH_SIZE  (optional) — flush when batch reaches this size (default: 1000)
  KAFKA_AUTO_OFFSET_RESET  (optional) — earliest | latest (default: earliest)

  # S3 storage (optional — skip S3 writes if not configured)
  DQ_S3_ENDPOINT                       — S3-compatible endpoint
  DQ_S3_ACCESS_KEY                     — access key
  DQ_S3_SECRET_KEY                     — secret key
  DQ_S3_REGION                         — region (default: us-east-1)
  KAFKA_CONSUMER_S3_BUCKET             — target bucket (default: dq-kafka-consumer)
  KAFKA_CONSUMER_S3_PREFIX             — object key prefix (default: kafka-batches)
  KAFKA_CONSUMER_S3_PATH_STYLE_ACCESS  — path-style access (default: true)

  # PostgreSQL storage (optional — skip DB writes if not configured)
  KAFKA_CONSUMER_DB_URL                — full database URL (e.g. postgresql://user:pass@host/db)
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime
from typing import Any

# Kafka
from kafka import KafkaConsumer
from kafka.structs import TopicPartition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    return val.strip()


def _env_int(name: str, default: int) -> int:
    val = _env(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        logger.warning("Invalid integer for %s=%s, using default %d", name, val, default)
        return default


def _env_float(name: str, default: float) -> float:
    val = _env(name)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        logger.warning("Invalid float for %s=%s, using default %f", name, val, default)
        return default


class Config:
    def __init__(self) -> None:
        # Kafka
        self.bootstrap_servers: str = _env("KAFKA_BOOTSTRAP_SERVERS", "")
        if not self.bootstrap_servers:
            raise RuntimeError("KAFKA_BOOTSTRAP_SERVERS is required")

        self.topic: str = _env("KAFKA_TOPIC", "")
        if not self.topic:
            raise RuntimeError("KAFKA_TOPIC is required")

        self.group_id: str = _env("KAFKA_CONSUMER_GROUP_ID", "dq-consumer-group")
        self.poll_timeout_seconds: int = _env_int("KAFKA_CONSUMER_POLL_TIMEOUT_SECONDS", 5)
        self.max_poll_records: int = _env_int("KAFKA_CONSUMER_MAX_POLL_RECORDS", 500)
        self.loop_delay_seconds: int = _env_int("KAFKA_CONSUMER_LOOP_DELAY_SECONDS", 30)
        self.batch_size: int = _env_int("KAFKA_CONSUMER_BATCH_SIZE", 1000)
        self.auto_offset_reset: str = _env("KAFKA_AUTO_OFFSET_RESET", "earliest").lower()

        # S3 (optional)
        self.s3_endpoint: str | None = _env("DQ_S3_ENDPOINT")
        self.s3_access_key: str | None = _env("DQ_S3_ACCESS_KEY")
        self.s3_secret_key: str | None = _env("DQ_S3_SECRET_KEY")
        self.s3_region: str = _env("DQ_S3_REGION", "us-east-1")
        self.s3_bucket: str = _env("KAFKA_CONSUMER_S3_BUCKET", "dq-kafka-consumer")
        self.s3_prefix: str = _env("KAFKA_CONSUMER_S3_PREFIX", "kafka-batches")
        self.s3_path_style: bool = _env("KAFKA_CONSUMER_S3_PATH_STYLE_ACCESS", "true").lower() == "true"
        self.enable_s3: bool = bool(self.s3_endpoint and self.s3_access_key and self.s3_secret_key)

        # PostgreSQL (optional)
        self.db_url: str | None = _env("KAFKA_CONSUMER_DB_URL")
        self.enable_db: bool = bool(self.db_url)


# ---------------------------------------------------------------------------
# S3 writer
# ---------------------------------------------------------------------------

class S3Writer:
    """Writes batches to S3 as compressed JSON."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = _build_s3_client(config)

    def write_batch(self, batch: list[dict[str, Any]]) -> None:
        if not batch or not self.client:
            return

        now = datetime.now(UTC).isoformat()
        payload = {
            "storedAt": now,
            "schemaVersion": "v1",
            "recordCount": len(batch),
            "records": batch,
        }

        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        content_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        object_key = (
            f"{self.config.s3_prefix}/"
            f"batch-{now.replace(':', '').replace('+', '')}-{content_hash[:16]}.json.gz"
        )

        compressed = gzip.compress(canonical_json.encode("utf-8"))
        self.client.put_object(
            Bucket=self.config.s3_bucket,
            Key=object_key,
            Body=compressed,
            ContentType="application/json",
            ContentEncoding="gzip",
            Metadata={
                "content_sha256": content_hash,
                "storage_kind": "kafka_consumer_batch",
                "record_count": str(len(batch)),
            },
        )
        logger.info("Wrote %d records to S3: %s/%s", len(batch), self.config.s3_bucket, object_key)


def _build_s3_client(config: Config):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=config.s3_endpoint,
        aws_access_key_id=config.s3_access_key,
        aws_secret_access_key=config.s3_secret_key,
        region_name=config.s3_region,
        config=boto3.session.Config(
            s3={"addressing_style": "path" if config.s3_path_style else "virtual"},
        ),
    )


# ---------------------------------------------------------------------------
# PostgreSQL writer
# ---------------------------------------------------------------------------

class DBWriter:
    """Writes batch records to a generic kafka_consumer_messages table."""

    def __init__(self, config: Config) -> None:
        self.db_url = config.db_url

    def write_batch(self, batch: list[dict[str, Any]]) -> None:
        if not batch or not self.db_url:
            return

        import psycopg2

        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            cur = conn.cursor()
            # Create table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kafka_consumer_messages (
                    id BIGSERIAL PRIMARY KEY,
                    topic TEXT NOT NULL,
                    partition INTEGER NOT NULL,
                    offset BIGINT NOT NULL,
                    key TEXT,
                    value JSONB NOT NULL,
                    headers JSONB,
                    consumed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            # Bulk insert
            consumed_at = datetime.now(UTC).isoformat()
            for record in batch:
                cur.execute(
                    """
                    INSERT INTO kafka_consumer_messages (topic, partition, offset, key, value, headers, consumed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.get("topic", ""),
                        record.get("partition", 0),
                        record.get("offset", 0),
                        record.get("key"),
                        json.dumps(record.get("value", {})),
                        json.dumps(record.get("headers") or {}),
                        consumed_at,
                    ),
                )
            conn.commit()
            logger.info("Wrote %d records to PostgreSQL", len(batch))
        except Exception as exc:
            logger.error("DB write failed: %s", exc)
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()


# ---------------------------------------------------------------------------
# Consumer worker
# ---------------------------------------------------------------------------

class KafkaConsumerWorker:
    """Batch-mode Kafka consumer worker."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._shutdown = False
        self._consumer: KafkaConsumer | None = None
        self._s3_writer = S3Writer(config) if config.enable_s3 else None
        self._db_writer = DBWriter(config) if config.enable_db else None

        # Signal handling
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle_signal)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        logger.info("Received signal %d, shutting down...", signum)
        self._shutdown = True

    def run(self) -> None:
        logger.info(
            "Starting Kafka consumer: topic=%s group=%s poll_timeout=%ds loop_delay=%ds",
            self.config.topic,
            self.config.group_id,
            self.config.poll_timeout_seconds,
            self.config.loop_delay_seconds,
        )

        self._consumer = KafkaConsumer(
            self.config.topic,
            bootstrap_servers=self.config.bootstrap_servers,
            group_id=self.config.group_id,
            auto_offset_reset=self.config.auto_offset_reset,
            enable_auto_commit=True,
            max_poll_records=self.config.max_poll_records,
            consumer_timeout_ms=1000,
            value_deserializer=lambda v: v,
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
        )

        try:
            self._run_loop()
        finally:
            logger.info("Closing Kafka consumer...")
            self._consumer.close()
            logger.info("Kafka consumer stopped.")

    def _run_loop(self) -> None:
        while not self._shutdown:
            batch = self._poll_batch()
            if batch:
                self._flush_batch(batch)
            # Sleep for loop delay before next cycle
            self._sleep_interruptible(self.config.loop_delay_seconds)

    def _poll_batch(self) -> list[dict[str, Any]]:
        """Poll messages until the timeout fires."""
        batch: list[dict[str, Any]] = []
        deadline = time.monotonic() + self.config.poll_timeout_seconds

        while not self._shutdown:
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if remaining <= 0:
                break

            # Poll with remaining timeout (in ms)
            records = self._consumer.poll(timeout_ms=remaining)
            for _tp, messages in records.items():
                for msg in messages:
                    record = {
                        "topic": msg.topic,
                        "partition": msg.partition,
                        "offset": msg.offset,
                        "key": msg.key,
                        "headers": dict(msg.headers) if msg.headers else {},
                    }
                    # Deserialize value
                    try:
                        if isinstance(msg.value, bytes):
                            record["value"] = json.loads(msg.value.decode("utf-8"))
                        else:
                            record["value"] = msg.value
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        logger.warning("Failed to deserialize message at offset %d: %s", msg.offset, exc)
                        record["value"] = {"raw": msg.value.decode("utf-8", errors="replace")} if isinstance(msg.value, bytes) else msg.value
                    batch.append(record)

            if len(batch) >= self.config.batch_size:
                break

            # Small sleep to avoid busy-waiting when no messages arrive
            time.sleep(0.1)

        return batch

    def _flush_batch(self, batch: list[dict[str, Any]]) -> None:
        """Flush batch to S3 and/or DB."""
        logger.info("Flushing batch of %d records", len(batch))

        if self._s3_writer:
            try:
                self._s3_writer.write_batch(batch)
            except Exception as exc:
                logger.error("S3 write failed: %s", exc)

        if self._db_writer:
            try:
                self._db_writer.write_batch(batch)
            except Exception as exc:
                logger.error("DB write failed: %s", exc)

    def _sleep_interruptible(self, seconds: int) -> None:
        """Sleep that can be interrupted by signals."""
        deadline = time.monotonic() + seconds
        while not self._shutdown and time.monotonic() < deadline:
            time.sleep(min(0.5, deadline - time.monotonic()))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    config = Config()
    logger.info("S3 enabled: %s, DB enabled: %s", config.enable_s3, config.enable_db)

    worker = KafkaConsumerWorker(config)
    worker.run()


if __name__ == "__main__":
    main()
