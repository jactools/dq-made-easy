from __future__ import annotations

import logging
import re

from prometheus_client import CollectorRegistry, Counter, start_http_server

LOG = logging.getLogger("dq.profiling.metrics")

REGISTRY = CollectorRegistry()

REQUEST_COUNT = Counter(
    "dq_profiling_request_count",
    "Total profiling worker requests by type and status.",
    labelnames=("request_type", "status"),
    registry=REGISTRY,
)

FAILURE_COUNT = Counter(
    "dq_profiling_failure_count",
    "Total profiling worker failures by type and failure reason.",
    labelnames=("request_type", "failure_type"),
    registry=REGISTRY,
)

REDIS_REQUEST_COUNT = Counter(
    "dq_profiling_redis_request_count",
    "Total Redis operations from the profiling worker by operation type and status.",
    labelnames=("operation_type", "status"),
    registry=REGISTRY,
)

REDIS_FAILURE_COUNT = Counter(
    "dq_profiling_redis_failure_count",
    "Total Redis operation failures from the profiling worker by operation type and failure reason.",
    labelnames=("operation_type", "failure_type"),
    registry=REGISTRY,
)


def _snake_case(value: object, default: str = "unknown") -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return default

    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized)
    normalized = normalized.replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.lower().strip("_") or default


def _normalize_status(status: object) -> str:
    normalized = _snake_case(status)
    return normalized if normalized in {"success", "failure"} else "unknown"


def start_metrics_server(port: int) -> None:
    start_http_server(port, addr="0.0.0.0", registry=REGISTRY)
    LOG.info("Profiling metrics server listening on 0.0.0.0:%s", port)


def record_request(request_type: object, status: object) -> None:
    REQUEST_COUNT.labels(
        request_type=_snake_case(request_type),
        status=_normalize_status(status),
    ).inc()


def record_failure(request_type: object, failure_type: object) -> None:
    FAILURE_COUNT.labels(
        request_type=_snake_case(request_type),
        failure_type=_snake_case(failure_type),
    ).inc()


def record_redis_request(operation_type: object, status: object) -> None:
    REDIS_REQUEST_COUNT.labels(
        operation_type=_snake_case(operation_type),
        status=_normalize_status(status),
    ).inc()


def record_redis_failure(operation_type: object, failure_type: object) -> None:
    REDIS_FAILURE_COUNT.labels(
        operation_type=_snake_case(operation_type),
        failure_type=_snake_case(failure_type),
    ).inc()
