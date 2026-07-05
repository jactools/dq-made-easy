"""GX dispatch worker — main entry point, Redis heartbeat, crash recovery, worker loop.

This module owns ONLY the worker lifecycle:
- Configuration loading (via ``gx_dispatch_config``)
- Redis heartbeat management
- Crash recovery (requeuing stuck messages)
- Main ``run_worker_forever()`` loop

All dispatch routing logic lives in ``gx_dispatch_dispatch``, expectation
evaluation in ``gx_dispatch_expectations``, config resolution in
``gx_dispatch_config``, and API communication in ``gx_dispatch_api``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any
from uuid import uuid4

from dq_utils.logging_utils import configure_logging
from dq_utils.logging_utils import log_event
from dq_utils.auth_utils import TokenProvider

from gx_dispatch_api import _coerce_reported_failure
from gx_dispatch_api import _report_dispatch_failure
from gx_dispatch_api import _should_discard_failed_message
from gx_dispatch_api import _should_fail_closed_worker
from gx_dispatch_config import _build_token_provider
from gx_dispatch_config import _require_redis
from gx_dispatch_config import _resolve_processing_queue_key
from gx_dispatch_config import _resolve_queue_key
from gx_dispatch_config import _resolve_worker_heartbeat_interval_seconds
from gx_dispatch_config import _resolve_worker_heartbeat_key
from gx_dispatch_config import _resolve_worker_heartbeat_ttl_seconds
from gx_dispatch_config import load_config
from gx_dispatch_dispatch import process_dispatch_message
from dq_plan_execution import parse_dispatch_payload
from gx_dispatch_telemetry import configure_worker_telemetry
from gx_dispatch_telemetry import record_worker_failure
from dq_plan_execution_types import GxWorkerConfig
from dq_plan_execution_types import GxWorkerExecutionError


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


def _write_worker_heartbeat(
    client: Any,
    *,
    config: GxWorkerConfig,
    worker_id: str,
) -> None:
    payload = json.dumps(
        {
            "worker_id": worker_id,
            "timestamp_ms": int(time.time() * 1000),
            "spark_master": config.spark_master,
            "max_rows": config.max_rows,
        }
    )
    client.set(config.heartbeat_key, payload, ex=config.heartbeat_ttl_seconds)


def _start_worker_heartbeat_loop(
    client: Any,
    *,
    config: GxWorkerConfig,
    worker_id: str,
    logger: logging.Logger,
) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()

    def _heartbeat_worker() -> None:
        try:
            while not stop_event.is_set():
                try:
                    _write_worker_heartbeat(client, config=config, worker_id=worker_id)
                except Exception as exc:
                    log_event(
                        logger,
                        "gx.worker.heartbeat.failed",
                        level="warning",
                        component="dq-engine-gx-worker",
                        exceptionType=exc.__class__.__name__,
                        errorMessage=str(exc),
                    )
                stop_event.wait(timeout=config.heartbeat_interval_seconds)
        except Exception as exc:
            log_event(
                logger,
                "gx.worker.heartbeat.critical",
                level="critical",
                component="dq-engine-gx-worker",
                exceptionType=exc.__class__.__name__,
                errorMessage=str(exc),
            )

    thread = threading.Thread(target=_heartbeat_worker, name="gx-worker-heartbeat", daemon=True)
    thread.start()
    return stop_event, thread


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_worker_forever() -> None:
    """Start the GX dispatch worker main loop.

    Loads configuration, establishes a Redis connection, starts the heartbeat
    thread, and processes dispatch messages from the queue until interrupted.
    """
    log_level = os.getenv("DQ_LOG_LEVEL", "INFO")
    configure_logging(log_level)
    configure_worker_telemetry()
    logger = logging.getLogger(__name__)

    config = load_config()
    redis_mod = _require_redis()

    # Fail-fast: validate we can mint or read an API token at startup.
    token_provider = _build_token_provider()
    _ = token_provider.get_token(correlation_id=f"corr-{uuid4().hex[:12]}")

    log_event(
        logger,
        "gx.worker.start",
        component="dq-engine-gx-worker",
        redisUrl=config.redis_url,
        queueKey=config.queue_key,
        processingQueueKey=config.processing_queue_key,
        maxRows=config.max_rows,
        sparkMaster=config.spark_master,
        apiUrl=config.api_url,
    )

    client = redis_mod.from_url(config.redis_url, decode_responses=True)
    worker_id = f"dq-engine-gx-worker-{uuid4().hex[:12]}"

    _write_worker_heartbeat(client, config=config, worker_id=worker_id)
    heartbeat_stop_event, heartbeat_thread = _start_worker_heartbeat_loop(
        client,
        config=config,
        worker_id=worker_id,
        logger=logger,
    )
    try:
        # Crash recovery: messages can remain stuck in the processing queue when the
        # worker process dies mid-execution (e.g. JVM crash, OOM, bug). Requeue them
        # on startup so they are retried and the corresponding runs can be resolved.
        recovered = 0
        try:
            while True:
                msg = client.rpoplpush(config.processing_queue_key, config.queue_key)
                if msg is None:
                    break
                recovered += 1
        except Exception as exc:
            log_event(
                logger,
                "gx.worker.recovery.failed",
                level="error",
                component="dq-engine-gx-worker",
                exceptionType=exc.__class__.__name__,
                errorMessage=str(exc),
            )

        if recovered:
            log_event(
                logger,
                "gx.worker.recovery.requeued",
                level="warning",
                component="dq-engine-gx-worker",
                recoveredCount=recovered,
                processingQueueKey=config.processing_queue_key,
                queueKey=config.queue_key,
            )

        while True:
            raw_message = None
            try:
                raw_message = client.brpoplpush(
                    config.queue_key,
                    config.processing_queue_key,
                    timeout=config.poll_timeout_seconds,
                )
                if raw_message is None:
                    continue

                process_dispatch_message(config, raw_message=raw_message)
                client.lrem(config.processing_queue_key, 1, raw_message)
            except KeyboardInterrupt:
                raise
            except BaseException as exc:
                # Fail fast but do not silently drop messages.
                execution_shape = "unknown"
                payload: dict[str, Any] = {}
                if raw_message is not None:
                    try:
                        payload = parse_dispatch_payload(raw_message)
                        execution_shape = (
                            str(payload.get("execution_shape") or "").strip()
                            if isinstance(payload, dict)
                            else "unknown"
                        )
                    except Exception:
                        execution_shape = "unknown"
                log_event(
                    logger,
                    "gx.worker.process.failed",
                    level="error",
                    component="dq-engine-gx-worker",
                    exceptionType=exc.__class__.__name__,
                    errorMessage=str(exc),
                )
                record_worker_failure(
                    stage="dispatch",
                    execution_shape=execution_shape,
                    reason=getattr(exc, "failure_code", exc.__class__.__name__),
                )
                failure_reported = False
                failure_report_must_discard = False
                if raw_message is not None:
                    try:
                        failure_reported = _report_dispatch_failure(
                            config,
                            token_provider,
                            payload=payload,
                            exc=exc,
                        )
                    except Exception as report_exc:
                        failure_report_must_discard = _should_discard_failed_message(report_exc)
                        log_event(
                            logger,
                            "gx.worker.failure.report.failed",
                            level="error",
                            component="dq-engine-gx-worker",
                            runId=(
                                str(payload.get("run_id") or payload.get("queue_message_id") or "")
                                if isinstance(payload, dict)
                                else None
                            ),
                            exceptionType=report_exc.__class__.__name__,
                            errorMessage=str(report_exc),
                        )

                if raw_message is not None and (failure_reported or failure_report_must_discard):
                    try:
                        client.lrem(config.processing_queue_key, 1, raw_message)
                    except Exception as cleanup_exc:
                        log_event(
                            logger,
                            "gx.worker.processing.cleanup.failed",
                            level="error",
                            component="dq-engine-gx-worker",
                            processingQueueKey=config.processing_queue_key,
                            exceptionType=cleanup_exc.__class__.__name__,
                            errorMessage=str(cleanup_exc),
                        )

                if _should_fail_closed_worker(exc):
                    log_event(
                        logger,
                        "gx.worker.process.fail_closed",
                        level="critical",
                        component="dq-engine-gx-worker",
                        exceptionType=exc.__class__.__name__,
                        errorMessage=str(exc),
                        failureReported=failure_reported,
                    )
                    raise

                time.sleep(1.0)
    finally:
        heartbeat_stop_event.set()
        heartbeat_thread.join(timeout=1.0)
        try:
            client.delete(config.heartbeat_key)
        except Exception:
            pass


if __name__ == "__main__":
    run_worker_forever()
