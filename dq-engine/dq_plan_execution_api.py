"""API request helpers and run reporting (Layer 3).

These functions build API tokens, make authenticated requests, report
run status/progress, and optionally publish violations to Kafka.
They are engine-agnostic and imported by shared and engine-specific
dispatch modules.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import build_oidc_token_provider_from_env

from dq_plan_execution_types import DqWorkerConfig, DqWorkerConfigError, DqWorkerExecutionError

logger = logging.getLogger(__name__)

REPORT_RUN_PATH_TEMPLATE = "/rulebuilder/v1/gx/runs/{run_id}/report"

# Optional Kafka client
try:
    from kafka_client import KafkaExceptionPublisher
except ImportError:
    KafkaExceptionPublisher = None  # type: ignore[assignment-missing]


# ---------------------------------------------------------------------------
# Token and request helpers
# ---------------------------------------------------------------------------


def build_token_provider() -> TokenProvider:
    """Build an OIDC token provider from environment variables."""
    try:
        return build_oidc_token_provider_from_env()
    except Exception:
        raise DqWorkerConfigError("Failed to initialize API token provider") from None


def _build_api_request_headers(config: DqWorkerConfig, token_provider: TokenProvider, *, correlation_id: str) -> dict[str, str]:
    token = token_provider.get_token(correlation_id=correlation_id)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Correlation-ID": correlation_id,
        "X-Request-Source": "dq-engine-execution-worker",
        "X-Api-Url": config.api_url,
    }


def api_request(
    config: DqWorkerConfig,
    token_provider: TokenProvider,
    *,
    method: str,
    path: str,
    correlation_id: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    """Make an authenticated API request and return the JSON response."""
    url = f"{config.api_url.rstrip('/')}{path}"
    headers = _build_api_request_headers(config, token_provider, correlation_id=correlation_id)
    try:
        response = requests.request(method=method.upper(), url=url, headers=headers, params=params, json=json_body, timeout=30)
    except requests.RequestException as exc:
        raise DqWorkerExecutionError(f"API request failed: {exc}", failure_code="DQ_API_REQUEST_FAILED") from exc

    if response.status_code >= 400:
        raise DqWorkerExecutionError(
            f"API request failed with {response.status_code}: {response.text}",
            failure_code="DQ_API_REQUEST_FAILED",
            status_code=response.status_code,
        )

    try:
        return response.json() if response.content else None
    except ValueError:
        return response.text


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------


def build_execution_progress(*, completed_steps: int, total_steps: int, label: str, source: str = "dq-engine-execution-worker") -> dict[str, Any]:
    """Build a progress envelope for run reporting."""
    percent = 0 if total_steps <= 0 else int(round((completed_steps / total_steps) * 100))
    return {
        "percent": max(0, min(percent, 100)),
        "label": label,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "source": source,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ---------------------------------------------------------------------------
# Run reporting
# ---------------------------------------------------------------------------


async def report_run(
    config: DqWorkerConfig,
    token_provider: TokenProvider,
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
    kafka_publisher: "KafkaExceptionPublisher | None" = None,
) -> None:
    """Report run status to the API and optionally publish violations to Kafka."""
    # Separate diagnostics (violations) from metadata
    violation_diagnostics = diagnostics if diagnostics else []

    # Publish violations to Kafka if available
    if kafka_publisher and violation_diagnostics:
        await kafka_publisher.publish_violations(violation_diagnostics)
        logger.info("Published %d violations to Kafka for run %s", len(violation_diagnostics), run_id)

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
    token_provider: TokenProvider,
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
        execution_progress=build_execution_progress(
            completed_steps=completed_steps,
            total_steps=total_steps,
            label=label,
        ),
    )


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ReportRunFn = Callable[..., None]
ReportProgressFn = Callable[..., None]
TokenProviderFactory = Callable[[], TokenProvider]
ExecutePayloadFn = Callable[..., dict[str, Any]]
