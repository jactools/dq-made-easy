"""Run reporting (Layer 3.5).

Reports run status and progress to the API, optionally publishing
violations to Kafka.
"""

from __future__ import annotations

from typing import Any

from dq_plan_execution_api import api_request
from dq_plan_execution_types import (
    DqWorkerConfig,
)

# Optional Kafka client
try:
    from kafka_client import KafkaExceptionPublisher
except ImportError:
    KafkaExceptionPublisher = None  # type: ignore[assignment-missing]

REPORT_RUN_PATH_TEMPLATE = "/rulebuilder/v1/gx/runs/{run_id}/report"


async def report_run(
    config: DqWorkerConfig,
    token_provider: Any,
    *,
    run_id: str,
    correlation_id: str,
    new_status: str,
    changed_by: str | None,
    reason: str | None,
    details: dict[str, Any] | None = None,
    execution_progress: dict[str, Any] | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    result_summary: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
    kafka_publisher: Any = None,
) -> None:
    """Report run status to the API and optionally publish violations to Kafka."""
    from dq_plan_execution_streaming import publish_violations_to_kafka

    # Separate diagnostics (violations) from metadata
    violation_diagnostics = diagnostics if diagnostics else []

    # Publish violations to Kafka if available
    if kafka_publisher and violation_diagnostics:
        await publish_violations_to_kafka(
            kafka_publisher,
            violation_diagnostics,
            run_id,
        )

    # Only send summary metadata via API (not full violation details)
    api_payload = {
        "new_status": new_status,
        "changed_by": changed_by,
        "reason": reason,
        "details": details,
        "execution_progress": execution_progress,
        "started_at": started_at,
        "completed_at": completed_at,
        "result_summary": result_summary,
        "metrics": metrics,
        "violation_count": len(violation_diagnostics),
        "diagnostics_count": min(len(violation_diagnostics), 100),
        "failure_code": failure_code,
        "failure_message": failure_message,
    }

    _ = api_request(
        config,
        token_provider,
        method="POST",
        path=REPORT_RUN_PATH_TEMPLATE.format(run_id=run_id),
        correlation_id=correlation_id,
        json_body=api_payload,
    )


def report_execution_progress(
    config: DqWorkerConfig,
    token_provider: Any,
    *,
    run_id: str,
    correlation_id: str,
    changed_by: str | None,
    reason: str,
    details: dict[str, Any] | None,
    completed_steps: int,
    total_steps: int,
    label: str,
) -> None:
    """Report execution progress via the report_run API."""
    report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="running",
        changed_by=changed_by,
        reason=reason,
        details=details,
        execution_progress=_build_execution_progress(
            completed_steps=completed_steps,
            total_steps=total_steps,
            label=label,
        ),
    )


def _build_execution_progress(
    *,
    completed_steps: int,
    total_steps: int,
    label: str,
) -> dict[str, Any]:
    """Build a progress envelope for run reporting."""
    import time

    percent = 0 if total_steps <= 0 else int(round((completed_steps / total_steps) * 100))
    return {
        "percent": max(0, min(percent, 100)),
        "label": label,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "source": "dq-engine-execution-worker",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
