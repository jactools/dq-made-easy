"""GX worker API client — Kong communication, run reporting, failure handling, exception helpers.

Provides the HTTP client layer for all API interactions (suite envelopes, data object
versions, run reporting, execution progress).  Also owns exception coercion and
transient-error detection logic.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

import requests

from dq_utils.logging_utils import log_event
from dq_utils.auth_utils import TokenProvider
from dq_plan_execution import report_run

from dq_plan_execution_types import GxWorkerConfig
from dq_plan_execution_types import GxWorkerExecutionError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception helpers
# ---------------------------------------------------------------------------


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        next_exc = current.__cause__ or current.__context__
        current = next_exc if isinstance(next_exc, BaseException) else None
    return chain


def _format_exception_message(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__


def _is_spark_runtime_exception(exc: BaseException) -> bool:
    module_name = str(exc.__class__.__module__ or "")
    return module_name.startswith("py4j") or module_name.startswith("pyspark")


def _is_transient_spark_gateway_error(exc: BaseException) -> bool:
    for candidate in _iter_exception_chain(exc):
        if isinstance(candidate, ConnectionRefusedError):
            return True
        if str(candidate.__class__.__module__ or "").startswith("py4j"):
            return True
    return False


def _coerce_reported_failure(exc: BaseException) -> GxWorkerExecutionError:
    for candidate in _iter_exception_chain(exc):
        if isinstance(candidate, GxWorkerExecutionError):
            return candidate

    for candidate in _iter_exception_chain(exc):
        if _is_spark_runtime_exception(candidate):
            return GxWorkerExecutionError(
                _format_exception_message(candidate),
                failure_code="GX_WORKER_EXECUTION_ERROR",
            )

    return GxWorkerExecutionError(
        _format_exception_message(exc),
        failure_code="GX_WORKER_EXECUTION_ERROR",
    )


def _should_fail_closed_worker(exc: BaseException) -> bool:
    return any(_is_spark_runtime_exception(candidate) for candidate in _iter_exception_chain(exc))


# ---------------------------------------------------------------------------
# Payload helpers (used by failure reporting)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Failure reporting
# ---------------------------------------------------------------------------


def _report_dispatch_failure(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    payload: dict[str, Any],
    exc: BaseException,
) -> bool:
    from gx_dispatch_config import _utc_now_iso

    run_id = coerce_str(payload, "run_id", "queue_message_id")
    if not run_id:
        return False

    correlation_id = coerce_str(payload, "correlation_id") or f"corr-{uuid4().hex[:12]}"
    requested_by = coerce_str(payload, "requested_by") or None
    failure = _coerce_reported_failure(exc)

    report_run(
        config,
        token_provider,
        run_id=run_id,
        correlation_id=correlation_id,
        new_status="failed",
        changed_by=requested_by,
        reason="GX worker execution failed",
        details={
            "source": "dq-engine-gx-worker",
            "exception_type": exc.__class__.__name__,
        },
        completed_at=_utc_now_iso(),
        result_summary=None,
        diagnostics=[],
        failure_code=getattr(failure, "failure_code", "GX_WORKER_EXECUTION_ERROR"),
        failure_message=str(failure),
    )
    return True


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


def _api_headers(config: GxWorkerConfig, token_provider: TokenProvider, *, correlation_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token_provider.get_token(correlation_id=correlation_id)}",
        "X-Correlation-ID": correlation_id,
        "Content-Type": "application/json",
    }


def _api_request(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    method: str,
    path: str,
    correlation_id: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: int = 15,
) -> Any:
    url = f"{config.api_url.rstrip('/')}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=_api_headers(config, token_provider, correlation_id=correlation_id),
            params=params,
            json=json_body,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        raise GxWorkerExecutionError(
            f"GX worker cannot reach API via Kong at '{config.api_url}'",
            failure_code="GX_API_UNAVAILABLE",
        ) from exc

    content_type = str(response.headers.get("content-type") or "")
    payload: Any = None
    if "application/json" in content_type:
        try:
            payload = response.json()
        except Exception:
            payload = None

    if response.status_code >= 400:
        raise GxWorkerExecutionError(
            f"API request failed: {method} {path} -> {response.status_code}",
            failure_code="GX_API_REQUEST_FAILED",
            status_code=response.status_code,
        )
    return payload


def _should_discard_failed_message(exc: BaseException) -> bool:
    if not isinstance(exc, GxWorkerExecutionError):
        return False
    return exc.failure_code == "GX_API_REQUEST_FAILED" and exc.status_code == 404


# ---------------------------------------------------------------------------
# Suite / data-object API helpers
# ---------------------------------------------------------------------------


def _api_get_suite_envelope(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    suite_id: str,
    suite_version: int,
    correlation_id: str,
) -> dict[str, Any]:
    payload = _api_request(
        config,
        token_provider,
        method="GET",
        path=f"/rulebuilder/v1/gx/suites/{suite_id}",
        params={"suiteVersion": suite_version, "status": "active"},
        correlation_id=correlation_id,
    )
    if not isinstance(payload, dict):
        raise GxWorkerExecutionError("API returned invalid GX suite envelope", failure_code="GX_SUITE_INVALID_ENVELOPE")
    return payload


def _api_get_data_object_version(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    version_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    payload = _api_request(
        config,
        token_provider,
        method="GET",
        path=f"/data-catalog/v1/data-object-versions/{version_id}",
        correlation_id=correlation_id,
    )
    if not isinstance(payload, dict):
        raise GxWorkerExecutionError(
            f"API returned invalid data object version payload for '{version_id}'",
            failure_code="GX_WORKER_MISSING_SOURCE_LOCATION",
        )
    return payload


# ---------------------------------------------------------------------------
# Run reporting
# ---------------------------------------------------------------------------




def _api_report_execution_progress(
    config: GxWorkerConfig,
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
