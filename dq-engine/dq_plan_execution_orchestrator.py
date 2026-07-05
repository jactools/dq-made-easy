"""Engine dispatch orchestration and report envelope shaping (Layer 3).

This module owns the main execution dispatch loop
(`execute_engine_rule_payload` and `process_engine_dispatch_message`) and
the report envelope shaping helpers. It imports from lower layers only:
- Layer 0: dq_plan_execution_types
- Layer 2: runtime_lowerers (for build_failure_envelope)
- Layer 3: dq_plan_execution_api, dq_plan_execution_payload
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace
from typing import Any

from dq_utils.logging_utils import log_event

from dq_plan_execution_api import (
    ExecutePayloadFn,
    ReportProgressFn,
    ReportRunFn,
    TokenProviderFactory,
    build_execution_progress,
    build_token_provider,
)
from dq_plan_execution_report import (
    report_execution_progress,
    report_run,
)
from dq_plan_execution_payload import (
    normalize_execution_engine,
)
from dq_plan_execution_types import DqWorkerConfig, DqWorkerExecutionError

logger = logging.getLogger(__name__)

SUPPORTED_EXECUTION_ENGINES = {"gx", "soda", "sql", "pyspark", "spark", "spark_expectations", "trino"}


# ---------------------------------------------------------------------------
# Dispatch loop
# ---------------------------------------------------------------------------


def _request_from_rule_payload(rule_payload: dict[str, Any], *, engine_type: str, output_dir: str | None) -> Any:
    """Build a request namespace from a rule payload."""
    return SimpleNamespace(
        id=rule_payload.get("id"),
        table=str(rule_payload.get("table") or ""),
        column=rule_payload.get("column"),
        type=str(rule_payload.get("type") or ""),
        params=rule_payload.get("params") if isinstance(rule_payload.get("params"), dict) else None,
        output_dir=output_dir,
        engine_type=engine_type,
    )


def execute_engine_rule_payload(
    *,
    engine_type: str,
    rule_payload: dict[str, Any],
    output_dir: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a rule payload through the appropriate engine adapter."""
    from dq_plan_lowerers import build_failure_envelope

    normalized_engine = normalize_execution_engine(engine_type)
    if normalized_engine not in SUPPORTED_EXECUTION_ENGINES:
        return build_failure_envelope(
            rule_payload,
            engine_type=normalized_engine,
            failure_code="DQ_EXECUTION_UNSUPPORTED_ENGINE",
            failure_message=f"unsupported execution engine: {engine_type!r}",
            failure_stage="dispatch",
        )

    if normalized_engine in {"spark_expectations", "pyspark"}:
        from dq_plan_execution_persistence import persist_execution_payload
        from spark_expectations_execution_adapter import execute_spark_expectations_rule

        request = _request_from_rule_payload(rule_payload, engine_type="spark_expectations", output_dir=output_dir)
        result = execute_spark_expectations_rule(request)
        result.setdefault("engine_type", "spark_expectations")
        result.setdefault("rule_id", rule_payload.get("id"))
        if output_dir:
            persist_execution_payload(output_dir, result, artifact_prefix="spark_expectations")
        return result

    if normalized_engine == "trino":
        from trino_execution_adapter import create_trino_execution_plan
        from trino_execution_adapter import execute_trino_pipeline

        plan = create_trino_execution_plan(rule_payload, config=config or {})
        return execute_trino_pipeline(plan, output_dir=output_dir)

    return build_failure_envelope(
        rule_payload,
        engine_type=normalized_engine,
        failure_code="DQ_EXECUTION_NOT_IMPLEMENTED",
        failure_message=f"execution engine {normalized_engine!r} is not implemented in the rule dispatch executor",
        failure_stage="dispatch",
    )


# ---------------------------------------------------------------------------
# Report envelope shaping
# ---------------------------------------------------------------------------


def _result_status(payload: dict[str, Any]) -> str:
    """Derive a result status string from an execution payload."""
    observability = payload.get("observability_summary") if isinstance(payload.get("observability_summary"), dict) else {}
    explicit_status = payload.get("result_status") or observability.get("result")
    if isinstance(explicit_status, str) and explicit_status.strip():
        return explicit_status.strip().lower()
    result = payload.get("result")
    if isinstance(result, str) and result.strip():
        return result.strip().lower()
    if isinstance(result, dict) and isinstance(result.get("passed"), bool):
        return "passed" if result.get("passed") else "failed"
    return "passed" if payload.get("ok") else "failed"


def build_execution_report_summary(response_payload: dict[str, Any], *, output_dir: Any = None) -> dict[str, Any]:
    """Build an aggregated execution report summary."""
    metrics = response_payload.get("metrics")
    return {
        "engine_type": response_payload.get("engine_type"),
        "rule_id": response_payload.get("rule_id"),
        "result": _result_status(response_payload),
        "passed_count": response_payload.get("passed_count", 0),
        "failed_count": response_payload.get("failed_count", 0),
        "failure_code": response_payload.get("failure_code"),
        "failure_message": response_payload.get("failure_message"),
        "failed_check": response_payload.get("failed_check", {}),
        "failure_metrics": response_payload.get("failure_metrics", {}),
        "trace": response_payload.get("trace", {}),
        "summary": response_payload,
        "output_dir": output_dir,
        "execution_metadata": response_payload.get("execution_metadata", {}),
        "quarantine_artifact": response_payload.get("quarantine_artifact", {}),
        "error_management": response_payload.get("error_management", {}),
        "observability_summary": response_payload.get("observability_summary", {}),
        "metrics": metrics if isinstance(metrics, dict) else response_payload.get("observability_summary", {}),
    }


def build_execution_report_details(response_payload: dict[str, Any], *, output_dir: Any = None) -> dict[str, Any]:
    """Build a detailed execution report."""
    details = {
        "source": "dq-engine-execution-worker",
        "engine_type": response_payload.get("engine_type"),
        "rule_id": response_payload.get("rule_id"),
        "result": _result_status(response_payload),
        "passed_count": response_payload.get("passed_count", 0),
        "failed_count": response_payload.get("failed_count", 0),
        "execution_metadata": response_payload.get("execution_metadata", {}),
        "quarantine_artifact": response_payload.get("quarantine_artifact", {}),
        "error_management": response_payload.get("error_management", {}),
        "observability_summary": response_payload.get("observability_summary", {}),
        "output_dir": output_dir,
    }
    if not response_payload.get("ok"):
        details.update(
            {
                "failure_code": response_payload.get("failure_code"),
                "failure_message": response_payload.get("failure_message") or response_payload.get("error"),
                "failed_check": response_payload.get("failed_check", {}),
                "failure_metrics": response_payload.get("failure_metrics", {}),
                "trace": response_payload.get("trace", {}),
            }
        )
    return details


# ---------------------------------------------------------------------------
# Full dispatch message processing
# ---------------------------------------------------------------------------


async def process_engine_dispatch_message(
    config: DqWorkerConfig,
    *,
    payload: dict[str, Any],
    run_id: str,
    correlation_id: str,
    requested_by: str | None,
    report_run_fn: ReportRunFn = report_run,
    report_progress_fn: ReportProgressFn | None = None,
    token_provider_factory: TokenProviderFactory = build_token_provider,
    execute_payload_fn: ExecutePayloadFn = execute_engine_rule_payload,
) -> dict[str, Any]:
    """Process a full engine dispatch message through the execution pipeline."""
    from dq_plan_execution_api import build_token_provider
    from kafka_client import build_kafka_publisher

    rule_payload = payload.get("rule_payload")
    if not isinstance(rule_payload, dict):
        raise DqWorkerExecutionError(
            "Execution dispatch payload is missing rule_payload",
            failure_code="DQ_DISPATCH_INVALID_PAYLOAD",
        )

    engine_type = normalize_execution_engine(payload.get("engine_type", ""))
    if engine_type not in SUPPORTED_EXECUTION_ENGINES:
        raise DqWorkerExecutionError(
            f"Unsupported execution dispatch engine type: {engine_type!r}",
            failure_code="DQ_DISPATCH_INVALID_PAYLOAD",
        )

    token_provider = token_provider_factory()
    execution_started = time.perf_counter()
    output_dir = str(payload.get("output_dir")) if payload.get("output_dir") is not None else None

    # Initialize Kafka publisher for streaming violations
    kafka_publisher = None
    try:
        kafka_publisher = await build_kafka_publisher()
        if kafka_publisher:
            await kafka_publisher.start()
    except Exception as exc:
        logger.warning("Failed to initialize Kafka publisher: %s", exc)

    try:
        await report_run_fn(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status="running",
            changed_by=requested_by,
            reason=f"Execution worker routed {engine_type} execution",
            details={"source": "dq-engine-execution-worker", "engine_type": engine_type, "rule_payload": rule_payload},
            execution_progress=build_execution_progress(
                completed_steps=1,
                total_steps=2,
                label=f"Invoking {engine_type} execution",
            ),
            metrics={"engine_type": engine_type, "stage": "started"},
            kafka_publisher=kafka_publisher,
        )

        response_payload = execute_payload_fn(
            engine_type=engine_type,
            rule_payload=rule_payload,
            output_dir=output_dir,
            config=payload.get("config") if isinstance(payload.get("config"), dict) else None,
        )
        if not isinstance(response_payload, dict):
            raise DqWorkerExecutionError(
                f"{engine_type} execution failed",
                failure_code="DQ_WORKER_EXECUTION_ERROR",
            )

        report_summary = build_execution_report_summary(response_payload, output_dir=payload.get("output_dir"))
        report_details = build_execution_report_details(response_payload, output_dir=payload.get("output_dir"))
        metrics = response_payload.get("metrics") if isinstance(response_payload.get("metrics"), dict) else response_payload.get("observability_summary", {})

        diagnostics = response_payload.get("diagnostics") or []

        status = "succeeded" if response_payload.get("ok") else "failed"
        label = f"{engine_type} execution completed" if status == "succeeded" else f"{engine_type} execution completed with failures"
        failure_code = None if status == "succeeded" else response_payload.get("failure_code") or "DQ_WORKER_EXECUTION_ERROR"
        failure_message = None if status == "succeeded" else response_payload.get("failure_message") or response_payload.get("error") or f"{engine_type} execution failed"

        if report_progress_fn is not None:
            await report_progress_fn(
                config,
                token_provider,
                run_id=run_id,
                correlation_id=correlation_id,
                changed_by=requested_by,
                reason=label,
                details=report_details,
                completed_steps=2,
                total_steps=2,
                label=label,
            )

        await report_run_fn(
            config,
            token_provider,
            run_id=run_id,
            correlation_id=correlation_id,
            new_status=status,
            changed_by=requested_by,
            reason=label,
            details=report_details,
            execution_progress=build_execution_progress(
                completed_steps=2,
                total_steps=2,
                label=label,
            ),
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            result_summary=report_summary,
            metrics=metrics,
            diagnostics=diagnostics,
            failure_code=failure_code,
            failure_message=failure_message,
            kafka_publisher=kafka_publisher,
        )

        record_duration = payload.get("record_duration")
        if callable(record_duration):
            record_duration(engine_type=engine_type, status=status, duration_ms=(time.perf_counter() - execution_started) * 1000.0)

        return response_payload
    finally:
        if kafka_publisher:
            await kafka_publisher.stop()
