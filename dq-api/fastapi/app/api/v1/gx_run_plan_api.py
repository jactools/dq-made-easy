from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi import Request

from app.api.presenters.gx import to_gx_run_plan_view
from app.api.v1.schemas import GxRunPlanView
from app.api.v1.schemas import GxRunPlanCreateRequestView
from app.api.v1.schemas import GxRunPlanGovernanceTransitionRequestView
from app.api.v1.schemas import GxRunPlanVersionCreateRequestView
from app.application.services.grouped_execution_planner import GroupedExecutionPlanner
from app.application.services.gx_run_plan_dispatcher import ActivateGroupedScopeRunRequest
from app.application.services.gx_run_plan_dispatcher import ActivateScheduledSuiteRunRequest
from app.application.services.gx_run_plan_seed_resolver import GxRunPlanSeedResolver
from app.application.services.gx_run_plan_seed_resolver import GxRunPlanSeedResolutionService
from app.application.use_cases.gx_run_plans import activate_gx_run_plan_version as activate_gx_run_plan_version_use_case
from app.application.use_cases.gx_run_plans import ActivateGxRunPlanVersionCommand
from app.application.use_cases.gx_run_plans import create_gx_run_plan as create_gx_run_plan_use_case
from app.application.use_cases.gx_run_plans import CreateGxRunPlanCommand
from app.application.use_cases.gx_run_plans import create_gx_run_plan_version as create_gx_run_plan_version_use_case
from app.application.use_cases.gx_run_plans import CreateGxRunPlanVersionCommand
from app.application.use_cases.gx_run_plans import transition_gx_run_plan_version_governance_state as transition_gx_run_plan_version_governance_state_use_case
from app.application.use_cases.gx_run_plans import TransitionGxRunPlanVersionGovernanceStateCommand
from app.application.use_cases.gx_run_plans import validate_gx_run_plan_version as validate_gx_run_plan_version_use_case
from app.application.use_cases.gx_run_plans import ValidateGxRunPlanVersionCommand
from app.domain.entities import GxRunPlanVersionEntity
from app.domain.entities import build_gx_run_plan_entity_from_validation_run_plan
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import RulesRepository
from app.domain.interfaces import ValidationArtifactRepository
from app.domain.interfaces import ValidationRunPlanRepository


GroupedScopeRunEnqueuer = Callable[..., Awaitable[Any]]
ScheduledSuiteRunEnqueuer = Callable[..., Awaitable[Any]]


@dataclass(slots=True)
class RunPlanActivationDispatcherImpl:
    request: Request
    execution_run_repository: GxExecutionRunRepository
    enqueue_grouped_scope_run_impl: GroupedScopeRunEnqueuer
    enqueue_scheduled_suite_run_impl: ScheduledSuiteRunEnqueuer

    async def enqueue_grouped_scope_run(
        self,
        request: ActivateGroupedScopeRunRequest,
    ) -> Any:
        return await self.enqueue_grouped_scope_run_impl(
            request=self.request,
            grouped_execution_plan=request.grouped_execution_plan,
            scope_selector=request.scope_selector,
            suite_refs=request.suite_refs,
            scheduled_at=request.scheduled_at,
            execution_run_repository=self.execution_run_repository,
            requested_by=request.requested_by,
            run_plan_id=request.run_plan_id,
            run_plan_version_id=request.run_plan_version_id,
        )

    async def enqueue_scheduled_suite_run(
        self,
        request: ActivateScheduledSuiteRunRequest,
    ) -> Any:
        return await self.enqueue_scheduled_suite_run_impl(
            request=self.request,
            suite=request.suite,
            scheduled_at=request.scheduled_at,
            execution_run_repository=self.execution_run_repository,
            requested_by=request.requested_by,
            status_source=request.status_source,
            status_reason=request.status_reason,
            run_plan_id=request.run_plan_id,
            run_plan_version_id=request.run_plan_version_id,
        )


def request_correlation_id(request: Request | None) -> str:
    return (request.headers.get("X-Correlation-ID") if request is not None else None) or f"corr-{uuid4().hex[:12]}"


def build_run_plan_view(row: Any) -> GxRunPlanView:
    return to_gx_run_plan_view(row)


def build_create_command(
    *,
    request_body: GxRunPlanCreateRequestView,
    request: Request | None,
    created_by: str | None,
) -> CreateGxRunPlanCommand:
    return CreateGxRunPlanCommand(
        workspace_id=request_body.workspaceId,
        planning_mode=request_body.planningMode,
        suite_id=request_body.suiteId,
        suite_version=request_body.suiteVersion,
        scheduled_at=request_body.scheduledAt,
        data_object_id=request_body.dataObjectId,
        data_object_version_id=request_body.dataObjectVersionId,
        dataset_id=request_body.datasetId,
        data_product_id=request_body.dataProductId,
        tag_ids=list(request_body.tagIds or []),
        created_by=created_by,
        correlation_id=request_correlation_id(request),
    )


def build_create_version_command(
    *,
    run_plan_id: str,
    request_body: GxRunPlanVersionCreateRequestView,
    request: Request | None,
    created_by: str | None,
) -> CreateGxRunPlanVersionCommand:
    return CreateGxRunPlanVersionCommand(
        run_plan_id=run_plan_id,
        planning_mode=request_body.planningMode,
        suite_id=request_body.suiteId,
        suite_version=request_body.suiteVersion,
        scheduled_at=request_body.scheduledAt,
        data_object_id=request_body.dataObjectId,
        data_object_version_id=request_body.dataObjectVersionId,
        dataset_id=request_body.datasetId,
        data_product_id=request_body.dataProductId,
        tag_ids=list(request_body.tagIds or []),
        created_by=created_by,
        correlation_id=request_correlation_id(request),
    )


def build_transition_command(
    *,
    run_plan_id: str,
    run_plan_version_id: str,
    request_body: GxRunPlanGovernanceTransitionRequestView,
    request: Request | None,
    updated_by: str | None,
) -> TransitionGxRunPlanVersionGovernanceStateCommand:
    return TransitionGxRunPlanVersionGovernanceStateCommand(
        run_plan_id=run_plan_id,
        run_plan_version_id=run_plan_version_id,
        target_state=request_body.targetState,
        updated_by=updated_by,
        effective_from=request_body.effectiveFrom,
        correlation_id=request_correlation_id(request),
    )


def build_validate_command(
    *,
    request: Request,
    run_plan_id: str,
    run_plan_version_id: str,
    updated_by: str | None,
) -> ValidateGxRunPlanVersionCommand:
    return ValidateGxRunPlanVersionCommand(
        run_plan_id=run_plan_id,
        run_plan_version_id=run_plan_version_id,
        updated_by=updated_by,
        correlation_id=request_correlation_id(request),
    )


def build_activate_command(
    *,
    request: Request,
    run_plan_id: str,
    run_plan_version_id: str,
    activated_by: str | None,
) -> ActivateGxRunPlanVersionCommand:
    return ActivateGxRunPlanVersionCommand(
        run_plan_id=run_plan_id,
        run_plan_version_id=run_plan_version_id,
        activated_by=activated_by,
        correlation_id=request_correlation_id(request),
    )


async def get_run_plan(
    *,
    run_plan_id: str,
    repository: ValidationRunPlanRepository,
) -> GxRunPlanView:
    row = await repository.get_plan(run_plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"GX run plan '{run_plan_id}' not found")

    return build_run_plan_view(build_gx_run_plan_entity_from_validation_run_plan(row))


async def list_run_plans(
    *,
    workspace_id: str | None,
    business_key: str | None,
    suite_id: str | None,
    status: str | None,
    repository: ValidationRunPlanRepository,
) -> list[GxRunPlanView]:
    rows = await repository.list_plans(
        workspace_id=workspace_id,
        business_key=business_key,
        status=status,
        artifact_id=suite_id,
    )
    return [build_run_plan_view(build_gx_run_plan_entity_from_validation_run_plan(row)) for row in rows]


async def create_run_plan(
    *,
    request_body: GxRunPlanCreateRequestView,
    request: Request | None,
    created_by: str | None,
    artifact_repository: ValidationArtifactRepository,
    rules_repository: RulesRepository,
    run_plan_repository: ValidationRunPlanRepository,
    grouped_execution_planner: GroupedExecutionPlanner,
    seed_resolver: GxRunPlanSeedResolver | None = None,
) -> Any:
    return await create_gx_run_plan_use_case(
        command=build_create_command(
            request_body=request_body,
            request=request,
            created_by=created_by,
        ),
        run_plan_repository=run_plan_repository,
        seed_resolver=seed_resolver
        or GxRunPlanSeedResolutionService(
            artifact_repository=artifact_repository,
            grouped_execution_planner=grouped_execution_planner,
            rules_repository=rules_repository,
        ),
    )


async def create_run_plan_version(
    *,
    run_plan_id: str,
    request_body: GxRunPlanVersionCreateRequestView,
    request: Request | None,
    created_by: str | None,
    artifact_repository: ValidationArtifactRepository,
    rules_repository: RulesRepository,
    run_plan_repository: ValidationRunPlanRepository,
    grouped_execution_planner: GroupedExecutionPlanner,
    seed_resolver: GxRunPlanSeedResolver | None = None,
) -> Any:
    return await create_gx_run_plan_version_use_case(
        command=build_create_version_command(
            run_plan_id=run_plan_id,
            request_body=request_body,
            request=request,
            created_by=created_by,
        ),
        run_plan_repository=run_plan_repository,
        seed_resolver=seed_resolver
        or GxRunPlanSeedResolutionService(
            artifact_repository=artifact_repository,
            grouped_execution_planner=grouped_execution_planner,
            rules_repository=rules_repository,
        ),
    )


async def transition_run_plan_version(
    *,
    run_plan_id: str,
    run_plan_version_id: str,
    request_body: GxRunPlanGovernanceTransitionRequestView,
    request: Request | None,
    updated_by: str | None,
    approvals_repository: ApprovalsRepository,
    run_plan_repository: ValidationRunPlanRepository,
) -> Any:
    return await transition_gx_run_plan_version_governance_state_use_case(
        command=build_transition_command(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            request_body=request_body,
            request=request,
            updated_by=updated_by,
        ),
        approvals_repository=approvals_repository,
        run_plan_repository=run_plan_repository,
    )


async def validate_run_plan_version(
    *,
    request: Request,
    run_plan_id: str,
    run_plan_version_id: str,
    updated_by: str | None,
    run_plan_repository: ValidationRunPlanRepository,
) -> Any:
    return await validate_gx_run_plan_version_use_case(
        command=build_validate_command(
            request=request,
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            updated_by=updated_by,
        ),
        run_plan_repository=run_plan_repository,
    )


async def activate_run_plan_version(
    *,
    request: Request,
    run_plan_id: str,
    run_plan_version_id: str,
    activated_by: str | None,
    run_plan_repository: ValidationRunPlanRepository,
    execution_run_repository: GxExecutionRunRepository,
    enqueue_grouped_scope_run: GroupedScopeRunEnqueuer,
    enqueue_scheduled_suite_run: ScheduledSuiteRunEnqueuer,
) -> Any:
    return await activate_gx_run_plan_version_use_case(
        command=build_activate_command(
            request=request,
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            activated_by=activated_by,
        ),
        run_plan_repository=run_plan_repository,
        dispatcher=RunPlanActivationDispatcherImpl(
            request=request,
            execution_run_repository=execution_run_repository,
            enqueue_grouped_scope_run_impl=enqueue_grouped_scope_run,
            enqueue_scheduled_suite_run_impl=enqueue_scheduled_suite_run,
        ),
    )