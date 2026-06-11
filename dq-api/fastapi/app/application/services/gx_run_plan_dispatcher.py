from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.domain.entities.gx_execution_run import GxDispatchPayloadEntity
from app.domain.entities.gx_suite import GxArtifactEnvelopeEntity


@dataclass(slots=True)
class ActivateGroupedScopeRunRequest:
    grouped_execution_plan: dict[str, Any]
    scope_selector: dict[str, Any]
    suite_refs: list[dict[str, Any]]
    scheduled_at: datetime
    requested_by: str | None
    run_plan_id: str | None = None
    run_plan_version_id: str | None = None


@dataclass(slots=True)
class ActivateScheduledSuiteRunRequest:
    suite: GxArtifactEnvelopeEntity
    scheduled_at: datetime
    requested_by: str | None
    status_source: str
    status_reason: str
    run_plan_id: str | None = None
    run_plan_version_id: str | None = None


class GxRunPlanActivationDispatcher(Protocol):
    async def enqueue_grouped_scope_run(
        self,
        request: ActivateGroupedScopeRunRequest,
    ) -> GxDispatchPayloadEntity:
        ...

    async def enqueue_scheduled_suite_run(
        self,
        request: ActivateScheduledSuiteRunRequest,
    ) -> GxDispatchPayloadEntity:
        ...