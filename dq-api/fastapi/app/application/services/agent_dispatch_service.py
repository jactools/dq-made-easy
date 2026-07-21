"""Outbound webhook dispatch service for external agent platforms.

Handles the actual HTTP delivery of DQ events to allowlisted platforms
(Mistral AI, Microsoft Copilot, etc.) via webhook or job dispatch modes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any
from uuid import uuid4

import httpx

from app.api.v1.schemas.agent_dispatch_view import WebhookDeliveryResult

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_RETRY_DELAY_SECONDS = 1.0


class AgentDispatchError(RuntimeError):
    """Raised when an outbound dispatch fails after all retries."""


@dataclass(slots=True)
class WebhookDispatchConfig:
    """Configuration for outbound webhook delivery."""

    webhook_url: str
    webhook_headers: dict[str, str] | None = None
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    max_retries: int = _DEFAULT_MAX_RETRIES
    retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS


def _generated_dispatch_id(prefix: str = "agent-dispatch") -> str:
    return f"{prefix}-{uuid4().hex}"


async def _send_webhook_request(
    config: WebhookDispatchConfig,
    payload: dict[str, Any],
) -> WebhookDeliveryResult:
    """Send a single HTTP POST to the webhook URL.

    Returns a delivery result with status, HTTP code, and response body.
    """
    dispatch_id = _generated_dispatch_id()
    headers = dict(config.webhook_headers or {})
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")

    try:
        async with httpx.AsyncClient(
            timeout=config.timeout_seconds,
        ) as client:
            response = await client.post(
                config.webhook_url,
                json=payload,
                headers=headers,
            )

        return WebhookDeliveryResult(
            dispatch_id=dispatch_id,
            status="delivered" if response.status_code < 400 else "failed",
            http_status_code=response.status_code,
            error_message=(
                None if response.status_code < 400
                else f"Webhook returned HTTP {response.status_code}"
            ),
            retry_count=0,
            response_body=response.text[:2048] if response.text else None,
        )

    except httpx.TimeoutException as exc:
        logger.warning(
            "Webhook timeout for %s after %.1fs",
            config.webhook_url,
            config.timeout_seconds,
        )
        return WebhookDeliveryResult(
            dispatch_id=dispatch_id,
            status="failed",
            error_message=f"Request timed out after {config.timeout_seconds}s: {exc}",
            retry_count=0,
        )

    except httpx.ConnectError as exc:
        logger.warning(
            "Webhook connection failed for %s: %s",
            config.webhook_url,
            exc,
        )
        return WebhookDeliveryResult(
            dispatch_id=dispatch_id,
            status="failed",
            error_message=f"Connection error: {exc}",
            retry_count=0,
        )

    except httpx.RequestError as exc:
        logger.warning(
            "Webhook request error for %s: %s",
            config.webhook_url,
            exc,
        )
        return WebhookDeliveryResult(
            dispatch_id=dispatch_id,
            status="failed",
            error_message=f"Request error: {exc}",
            retry_count=0,
        )


async def dispatch_webhook(
    *,
    webhook_url: str,
    payload: dict[str, Any],
    webhook_headers: dict[str, str] | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> WebhookDeliveryResult:
    """Dispatch a webhook with retry logic.

    Sends the payload to the target webhook URL. On transient failures
    (5xx, timeouts, connection errors), retries up to *max_retries* times
    with exponential back-off starting at *retry_delay_seconds*.

    Returns a ``WebhookDeliveryResult`` describing the final outcome.
    Raises ``AgentDispatchError`` only if retries are exhausted on
    non-retryable errors (e.g. 4xx client errors).
    """
    config = WebhookDispatchConfig(
        webhook_url=webhook_url,
        webhook_headers=webhook_headers,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
    )

    # First attempt
    result = await _send_webhook_request(config, payload)
    if result.status == "delivered":
        logger.info(
            "Webhook dispatched to %s (HTTP %s, dispatch_id=%s)",
            webhook_url,
            result.http_status_code,
            result.dispatch_id,
        )
        return result

    # Determine if we should retry
    if _is_retryable(result):
        delay = retry_delay_seconds
        for attempt in range(1, max_retries + 1):
            logger.info(
                "Retrying webhook to %s (attempt %d/%d, delay=%.1fs)",
                webhook_url,
                attempt,
                max_retries,
                delay,
            )
            result = await _send_webhook_request(config, payload)
            result.retry_count = attempt

            if result.status == "delivered":
                logger.info(
                    "Webhook dispatched to %s on retry %d (HTTP %s, dispatch_id=%s)",
                    webhook_url,
                    attempt,
                    result.http_status_code,
                    result.dispatch_id,
                )
                return result

            # Increase delay for next attempt (exponential back-off)
            delay *= 2

        # All retries exhausted
        logger.error(
            "Webhook to %s failed after %d retries (dispatch_id=%s): %s",
            webhook_url,
            max_retries + 1,
            result.dispatch_id,
            result.error_message,
        )
        raise AgentDispatchError(
            f"Dispatch failed after {max_retries + 1} attempts: {result.error_message}"
        )

    # Non-retryable error (e.g. 4xx)
    logger.error(
        "Webhook to %s failed with non-retryable error (HTTP %s): %s",
        webhook_url,
        result.http_status_code,
        result.error_message,
    )
    raise AgentDispatchError(
        f"Dispatch failed: {result.error_message}"
    )


def _is_retryable(result: WebhookDeliveryResult) -> bool:
    """Return True if the delivery failure is worth retrying.

    Retry on:
    - 5xx server errors
    - Timeout / connection errors (http_status_code is None)
    - 429 rate-limit responses
    """
    if result.http_status_code is None:
        return True
    if result.http_status_code in (429,):
        return True
    if result.http_status_code >= 500:
        return True
    return False


def build_webhook_payload(
    *,
    platform: str,
    event_type: str,
    payload: dict[str, Any],
    dispatch_id: str,
) -> dict[str, Any]:
    """Build the outbound webhook payload envelope.

    Wraps the caller's payload in a standard envelope that includes
    platform metadata, event type, and delivery tracing fields.
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "metadata": {
            "dispatch_id": dispatch_id,
            "platform": platform,
            "source": "dq-made-easy",
            "contract_version": "1.0",
            "sent_at": now,
        },
        "event": {
            "type": event_type,
            "timestamp": now,
        },
        "data": payload,
    }
