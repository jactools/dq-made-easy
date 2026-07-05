"""API request helpers (Layer 3).

These functions build API tokens, make authenticated requests, and build
progress envelopes.  Run reporting lives in `dq_plan_execution_report.py`.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import requests

from dq_utils.auth_utils import TokenProvider
from dq_utils.auth_utils import build_oidc_token_provider_from_env

from dq_plan_execution_types import DqWorkerConfig, DqWorkerConfigError, DqWorkerExecutionError

# ---------------------------------------------------------------------------
# Token and request helpers
# ---------------------------------------------------------------------------


def build_token_provider() -> TokenProvider:
    """Build an OIDC token provider from environment variables."""
    try:
        return build_oidc_token_provider_from_env()
    except Exception:
        raise DqWorkerConfigError("Failed to initialize API token provider") from None


def _build_api_request_headers(
    config: DqWorkerConfig,
    token_provider: TokenProvider,
    *,
    correlation_id: str,
) -> dict[str, str]:
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
    headers = _build_api_request_headers(
        config,
        token_provider,
        correlation_id=correlation_id,
    )
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise DqWorkerExecutionError(
            f"API request failed: {exc}",
            failure_code="DQ_API_REQUEST_FAILED",
        ) from exc

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


def build_execution_progress(
    *,
    completed_steps: int,
    total_steps: int,
    label: str,
    source: str = "dq-engine-execution-worker",
) -> dict[str, Any]:
    """Build a progress envelope for run reporting."""
    percent = 0 if total_steps <= 0 else int(
        round((completed_steps / total_steps) * 100)
    )
    return {
        "percent": max(0, min(percent, 100)),
        "label": label,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "source": source,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ReportRunFn = Callable[..., None]
ReportProgressFn = Callable[..., None]
TokenProviderFactory = Callable[[], TokenProvider]
ExecutePayloadFn = Callable[..., dict[str, Any]]
