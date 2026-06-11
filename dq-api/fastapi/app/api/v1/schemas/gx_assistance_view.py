from __future__ import annotations

from typing import Any

from pydantic import ConfigDict

from app.schemas.pydantic_base import SnakeModel
from app.schemas.pydantic_base import to_snake_alias
from dq_domain_validation import GxAssistanceDeliveryMode


class GxAssistanceRequestView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    runPlanId: str | None = None
    runPlanVersionId: str | None = None
    workspaceId: str | None = None
    errorMessage: str
    diagnostics: list[dict[str, Any]] | None = None


class GxAssistanceRequestResponseView(SnakeModel):
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)

    deliveryMode: GxAssistanceDeliveryMode
    message: str
    correlationId: str
    mailtoUrl: str | None = None
    recipientEmail: str | None = None
    ticketNumber: str | None = None
    ticketSystem: str | None = None
    ticketUrl: str | None = None