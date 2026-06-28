from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from uuid import uuid4

import requests

from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import build_oidc_token_provider_from_env
from dq_utils.logging_utils import log_event

from gx_dispatch_types import GxWorkerConfig
from gx_dispatch_types import GxWorkerExecutionError
from gx_dispatch_types import GxWorkerConfigError


logger = logging.getLogger(__name__)


def parse_dispatch_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise GxWorkerExecutionError("GX dispatch message is not valid JSON", failure_code="GX_DISPATCH_INVALID_JSON") from exc
    if not isinstance(payload, dict):
        raise GxWorkerExecutionError("GX dispatch message must be a JSON object", failure_code="GX_DISPATCH_INVALID_JSON")
    return payload


def coerce_str(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value:
            return text_value
    return ""


def coerce_int(payload: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
            if parsed >= 1:
                return parsed
        except Exception:
            continue
    return 0


def build_token_provider() -> TokenProvider:
    try:
        return build_oidc_token_provider_from_env()
    except Exception:
        raise GxWorkerConfigError("Failed to initialize API token provider") from None


def _build_api_request_headers(config: GxWorkerConfig, token_provider: TokenProvider, *, correlation_id: str) -> dict[str, str]:
    token = token_provider.get_token(correlation_id=correlation_id)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Correlation-ID": correlation_id,
        "X-Request-Source": "dq-engine-gx-worker",
        "X-Api-Url": config.api_url,
    }


def api_request(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    method: str,
    path: str,
    correlation_id: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    url = f"{config.api_url.rstrip('/')}{path}"
    headers = _build_api_request_headers(config, token_provider, correlation_id=correlation_id)
    try:
        response = requests.request(method=method.upper(), url=url, headers=headers, params=params, json=json_body, timeout=30)
    except requests.RequestException as exc:  # pragma: no cover
        raise GxWorkerExecutionError(f"API request failed: {exc}", failure_code="GX_API_REQUEST_FAILED") from exc

    if response.status_code >= 400:
        raise GxWorkerExecutionError(
            f"API request failed with {response.status_code}: {response.text}",
            failure_code="GX_API_REQUEST_FAILED",
            status_code=response.status_code,
        )

    try:
        return response.json() if response.content else None
    except ValueError:
        return response.text


def report_run(
    config: GxWorkerConfig,
    token_provider: TokenProvider,
    *,
    run_id: str,
    correlation_id: str,
    new_status: str,
    changed_by: str | None,
    reason: str | None,
    details: dict[str, Any] | None,
    execution_progress: dict[str, Any] | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    result_summary: dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> None:
    _ = api_request(
        config,
        token_provider,
        method="POST",
        path=f"/rulebuilder/v1/gx/runs/{run_id}/report",
        correlation_id=correlation_id,
        json_body={
            "new_status": new_status,
            "changed_by": changed_by,
            "reason": reason,
            "details": details,
            "execution_progress": execution_progress,
            "started_at": started_at,
            "completed_at": completed_at,
            "result_summary": result_summary,
            "diagnostics": diagnostics,
            "failure_code": failure_code,
            "failure_message": failure_message,
        },
    )


def report_execution_progress(
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


def build_execution_progress(*, completed_steps: int, total_steps: int, label: str) -> dict[str, Any]:
    percent = 0 if total_steps <= 0 else int(round((completed_steps / total_steps) * 100))
    return {
        "percent": max(0, min(percent, 100)),
        "label": label,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "source": "dq-engine-gx-worker",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def log_dispatch_received(*, correlation_id: str, run_id: str, suite_id: str | None = None, suite_version: int | None = None, execution_shape: str | None = None, **extra: Any) -> None:
    log_event(
        logger,
        "gx.worker.dispatch.received",
        component="dq-engine-gx-worker",
        correlation_id=correlation_id,
        run_id=run_id,
        suite_id=suite_id,
        suite_version=suite_version,
        execution_shape=execution_shape,
        **extra,
    )
