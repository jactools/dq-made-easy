"""Kafka violation streaming (Layer 3.5).

Publishes violation diagnostics to Kafka after run reporting.
"""

from __future__ import annotations

import logging
from typing import Any

# Optional Kafka client
try:
    from kafka_client import KafkaExceptionPublisher
except ImportError:
    KafkaExceptionPublisher = None  # type: ignore[assignment-missing]

logger = logging.getLogger(__name__)


async def publish_violations_to_kafka(
    publisher: Any,
    violations: list[dict[str, Any]],
    run_id: str,
) -> None:
    """Publish violation diagnostics to Kafka."""
    if publisher and violations:
        await publisher.publish_violations(violations)
        logger.info(
            "Published %d violations to Kafka for run %s",
            len(violations),
            run_id,
        )
