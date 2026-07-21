"""Schema models for agent platform dispatch and webhook delivery tracking.

These models support the outbound webhook dispatch layer that delivers DQ
events to external agent platforms (Mistral AI, Microsoft Copilot, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field

from app.schemas.pydantic_base import SnakeModel


# -- Request models (used by the dispatch endpoint) --


class AgentPlatformDispatchRequestView(SnakeModel):
    """Request to queue a dispatch to an external agent platform."""

    platform: str
    dispatch_mode: str
    event_type: str
    webhook_url: str | None = None
    webhook_headers: dict[str, str] = Field(default_factory=dict)
    job_name: str | None = None
    job_arguments: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


# -- Response models --


class AgentPlatformDispatchResponseView(SnakeModel):
    """Response from the dispatch endpoint with delivery outcome."""

    dispatch_id: str
    status: str  # accepted, delivered, failed
    platform: str
    dispatch_mode: str
    event_type: str
    target: dict[str, Any] = Field(default_factory=dict)
    queued_at: str
    delivered_at: str | None = None
    delivery_result: dict[str, Any] | None = None
    contract_version: str = "1.0"


# -- Delivery result (internal, stored in audit trail) --


@dataclass(slots=True)
class WebhookDeliveryResult:
    """Structured result from an outbound webhook delivery attempt."""

    dispatch_id: str
    status: str  # delivered, failed
    http_status_code: int | None = None
    error_message: str | None = None
    retry_count: int = 0
    response_body: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dispatch_id": self.dispatch_id,
            "status": self.status,
            "http_status_code": self.http_status_code,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "response_body": self.response_body,
        }
