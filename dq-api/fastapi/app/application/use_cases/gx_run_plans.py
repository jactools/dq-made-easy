from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import HTTPException

from app.application.services.gx_run_plan_dispatcher import ActivateGroupedScopeRunRequest
from app.application.services.gx_run_plan_dispatcher import ActivateScheduledSuiteRunRequest
from app.application.services.gx_run_plan_dispatcher import GxRunPlanActivationDispatcher
from app.application.services.gx_run_plan_seed_resolver import GxRunPlanSeedResolver
from app.application.services.gx_run_plan_seed_resolver import ResolveGxRunPlanSeedCommand
from app.application.services.gx_run_plan_validation import GxRunPlanActivationSnapshotError
from app.application.services.gx_run_plan_validation import resolve_single_suite_activation_snapshot
from app.application.services.gx_run_plan_validation import validate_gx_run_plan_version_snapshot
from app.domain.entities.approvals import build_approval_entity
from app.domain.entities.gx_execution_run import build_gx_dispatch_payload_entity
from app.domain.entities.gx_execution_run import GxDispatchPayloadEntity
from app.domain.entities.gx_run_plan import GxRunPlanEntity
from app.domain.entities.gx_run_plan import GxRunPlanValidationDiagnosticEntity
from app.domain.entities.gx_run_plan import GxRunPlanScheduleDefinitionEntity
from app.domain.entities.gx_run_plan import GxRunPlanSeedEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_schedule_definition_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_suite_selection_entity
from app.domain.entities.gx_run_plan import GxRunPlanVersionEntity
from app.domain.entities.gx_run_plan_governance import is_valid_run_plan_version_transition
from app.domain.entities.validation_run_plan import build_gx_run_plan_entity_from_validation_run_plan
from app.domain.entities.validation_run_plan import build_validation_artifact_selection_payload_from_gx_suite_selection
from app.domain.entities.validation_run_plan import build_validation_artifact_snapshot_payload_from_gx_snapshot
from app.domain.entities.validation_run_plan import build_validation_run_plan_artifact_selection_entity
from app.domain.entities.validation_run_plan import build_validation_run_plan_schedule_definition_entity
from app.domain.entities.validation_run_plan import build_validation_run_plan_scope_selector_entity
from app.domain.interfaces import ApprovalsRepository
from app.domain.interfaces import ValidationRunPlanRepository
from app.domain.interfaces import RulesRepository


@dataclass(slots=True)
class CreateGxRunPlanCommand:
    workspace_id: str
    scheduled_at: datetime
    planning_mode: str = "single_suite"
    suite_id: str | None = None
    suite_version: int | None = None
    data_object_id: str | None = None
    data_object_version_id: str | None = None
    dataset_id: str | None = None
    data_product_id: str | None = None
    tag_ids: list[str] | None = None
    created_by: str | None = None
    correlation_id: str | None = None

    def seed_command(self) -> ResolveGxRunPlanSeedCommand:
        return ResolveGxRunPlanSeedCommand(
            planning_mode=self.planning_mode,
            suite_id=self.suite_id,
            suite_version=self.suite_version,
            data_object_id=self.data_object_id,
            data_object_version_id=self.data_object_version_id,
            dataset_id=self.dataset_id,
            data_product_id=self.data_product_id,
            tag_ids=self.tag_ids,
        )


@dataclass(slots=True)
class CreateGxRunPlanVersionCommand:
    run_plan_id: str
    scheduled_at: datetime
    planning_mode: str = "single_suite"
    suite_id: str | None = None
    suite_version: int | None = None
    data_object_id: str | None = None
    data_object_version_id: str | None = None
    dataset_id: str | None = None
    data_product_id: str | None = None
    tag_ids: list[str] | None = None
    created_by: str | None = None
    correlation_id: str | None = None

    def seed_command(self) -> ResolveGxRunPlanSeedCommand:
        return ResolveGxRunPlanSeedCommand(
            planning_mode=self.planning_mode,
            suite_id=self.suite_id,
            suite_version=self.suite_version,
            data_object_id=self.data_object_id,
            data_object_version_id=self.data_object_version_id,
            dataset_id=self.dataset_id,
            data_product_id=self.data_product_id,
            tag_ids=self.tag_ids,
        )


@dataclass(slots=True)
class TransitionGxRunPlanVersionGovernanceStateCommand:
    run_plan_id: str
    run_plan_version_id: str
    target_state: str
    updated_by: str | None = None
    effective_from: datetime | None = None
    correlation_id: str | None = None


@dataclass(slots=True)
class ValidateGxRunPlanVersionCommand:
    run_plan_id: str
    run_plan_version_id: str
    updated_by: str | None = None
    correlation_id: str | None = None


@dataclass(slots=True)
class ActivateGxRunPlanVersionCommand:
    run_plan_id: str
    run_plan_version_id: str
    activated_by: str | None = None
    correlation_id: str | None = None


@dataclass(slots=True)
class GxRunPlanValidationResult:
    plan: GxRunPlanEntity
    validation_status: str
    message: str
    diagnostics: list[GxRunPlanValidationDiagnosticEntity]


@dataclass(slots=True)
class GxRunPlanActivationResult:
    plan: GxRunPlanEntity
    dispatch: GxDispatchPayloadEntity


def _as_dispatch_payload_entity(payload: Any) -> GxDispatchPayloadEntity:
    if isinstance(payload, dict) and isinstance(payload.get("scheduled_at"), datetime):
        payload = {
            **payload,
            "scheduled_at": payload["scheduled_at"].isoformat(),
        }
    try:
        dispatch_payload = build_gx_dispatch_payload_entity(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_dispatch_payload",
                "message": str(exc),
            },
        ) from exc
    if dispatch_payload is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "invalid_dispatch_payload",
                "message": "GX run plan activation could not normalize dispatch payload",
            },
        )
    return dispatch_payload


def _select_latest_pending_run_plan_version(
    version_rows: list[GxRunPlanVersionEntity],
) -> GxRunPlanVersionEntity | None:
    for row in reversed(version_rows):
        state = str(row.governanceState or "").strip()
        if state in {"draft", "pending_validation", "validation_failed", "pending_review", "approved_pending_activation"}:
            return row
    return None


def _list_pending_gx_run_plan_approvals(
    approvals_repository: ApprovalsRepository,
    *,
    run_plan_id: str,
    run_plan_version_id: str,
    request_type: str,
) -> list[dict[str, Any]]:
    pending_approvals: list[dict[str, Any]] = []
    for row in approvals_repository.list_approvals(None) or []:
        approval = build_approval_entity(row)
        if str(approval.gxRunPlanId or "").strip() != run_plan_id:
            continue
        if str(approval.gxRunPlanVersionId or "").strip() != run_plan_version_id:
            continue
        if str(approval.status or "").strip() != "pending":
            continue
        if str(approval.requestType or "").strip() != request_type:
            continue
        pending_approvals.append(approval.model_dump())
    return pending_approvals


def _first_diagnostic_message(diagnostics: list[GxRunPlanValidationDiagnosticEntity]) -> str | None:
    for diagnostic in diagnostics:
        message = str(diagnostic.message or "").strip()
        if message:
            return message
    return None


def _as_gx_run_plan_entity(plan: Any) -> GxRunPlanEntity:
    if isinstance(plan, GxRunPlanEntity):
        return plan
    return build_gx_run_plan_entity_from_validation_run_plan(plan)


async def _get_plan_or_404(run_plan_repository: ValidationRunPlanRepository, run_plan_id: str) -> GxRunPlanEntity:
    plan = await run_plan_repository.get_plan(run_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"GX run plan '{run_plan_id}' not found")
    return _as_gx_run_plan_entity(plan)


def _get_version_or_404(plan: GxRunPlanEntity, run_plan_version_id: str) -> GxRunPlanVersionEntity:
    version = next((item for item in plan.versions if item.runPlanVersionId == run_plan_version_id), None)
    if version is None:
        raise HTTPException(status_code=404, detail=f"GX run plan version '{run_plan_version_id}' not found")
    return version


async def create_gx_run_plan(
    command: CreateGxRunPlanCommand,
    run_plan_repository: ValidationRunPlanRepository,
    seed_resolver: GxRunPlanSeedResolver,
) -> GxRunPlanEntity:
    seed = await seed_resolver.resolve_seed(command.seed_command())
    return _as_gx_run_plan_entity(
        await run_plan_repository.create_plan(
        run_plan_id=f"run-plan-{uuid4().hex[:12]}",
        run_plan_version_id=f"run-plan-version-{uuid4().hex[:12]}",
        workspace_id=command.workspace_id,
        scope_selector=build_validation_run_plan_scope_selector_entity(
            seed.scopeSelector.model_dump(mode="python", by_alias=False, exclude_none=True)
        ),
        planning_mode=command.planning_mode,
        status="draft",
        created_by=command.created_by,
        validation_artifact_selection=build_validation_run_plan_artifact_selection_entity(
            build_validation_artifact_selection_payload_from_gx_suite_selection(
                seed.gxSuiteSelection.model_dump(mode="python", by_alias=False, exclude_none=True)
            )
        ),
        artifact_id=seed.suiteId,
        artifact_version=seed.suiteVersion,
        artifact_snapshot=build_validation_artifact_snapshot_payload_from_gx_snapshot(
            seed.suiteSnapshot.model_dump(mode="python", by_alias=False, exclude_none=True)
            if seed.suiteSnapshot is not None
            else None
        ),
        execution_contract_snapshot=seed.executionContractSnapshot,
        schedule_definition=build_validation_run_plan_schedule_definition_entity(
            {"scheduledAt": command.scheduled_at.isoformat()}
        ),
        correlation_id=command.correlation_id,
        )
    )


async def create_gx_run_plan_version(
    command: CreateGxRunPlanVersionCommand,
    run_plan_repository: ValidationRunPlanRepository,
    seed_resolver: GxRunPlanSeedResolver,
) -> GxRunPlanEntity:
    plan = await _get_plan_or_404(run_plan_repository, command.run_plan_id)
    seed = await seed_resolver.resolve_seed(command.seed_command())

    previous_version = _select_latest_pending_run_plan_version(plan.versions)
    if previous_version is None:
        previous_version = next(
            (
                item
                for item in reversed(plan.versions)
                if str(item.governanceState or "").strip() in {"active", "superseded"}
            ),
            None,
        )
    previous_version_id = previous_version.runPlanVersionId if previous_version is not None else None

    return _as_gx_run_plan_entity(
        await run_plan_repository.create_plan_version(
        run_plan_id=command.run_plan_id,
        run_plan_version_id=f"run-plan-version-{uuid4().hex[:12]}",
        validation_artifact_selection=build_validation_run_plan_artifact_selection_entity(
            build_validation_artifact_selection_payload_from_gx_suite_selection(
                seed.gxSuiteSelection.model_dump(mode="python", by_alias=False, exclude_none=True)
            )
        ),
        artifact_id=seed.suiteId,
        artifact_version=seed.suiteVersion,
        artifact_snapshot=build_validation_artifact_snapshot_payload_from_gx_snapshot(
            seed.suiteSnapshot.model_dump(mode="python", by_alias=False, exclude_none=True)
            if seed.suiteSnapshot is not None
            else None
        ),
        execution_contract_snapshot=seed.executionContractSnapshot,
        schedule_definition=build_validation_run_plan_schedule_definition_entity(
            {"scheduledAt": command.scheduled_at.isoformat()}
        ),
        created_by=command.created_by,
        supersedes_version_id=previous_version_id,
        correlation_id=command.correlation_id,
        )
    )


async def transition_gx_run_plan_version_governance_state(
    command: TransitionGxRunPlanVersionGovernanceStateCommand,
    approvals_repository: ApprovalsRepository,
    run_plan_repository: ValidationRunPlanRepository,
) -> GxRunPlanEntity:
    plan = await _get_plan_or_404(run_plan_repository, command.run_plan_id)
    version_row = _get_version_or_404(plan, command.run_plan_version_id)

    current_state = str(version_row.governanceState or "")
    if not is_valid_run_plan_version_transition(current_state, command.target_state):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_run_plan_transition",
                "message": f"Run plan version cannot transition from {current_state} to {command.target_state}",
                "run_plan_id": command.run_plan_id,
                "run_plan_version_id": command.run_plan_version_id,
                "current_state": current_state,
                "target_state": command.target_state,
            },
        )

    request_type: str | None = None
    if command.target_state in {"activation-requested", "deactivation-requested"}:
        request_type = "activation" if command.target_state == "activation-requested" else "deactivation"
        pending_approvals = _list_pending_gx_run_plan_approvals(
            approvals_repository,
            run_plan_id=command.run_plan_id,
            run_plan_version_id=command.run_plan_version_id,
            request_type=request_type,
        )
        if pending_approvals:
            raise HTTPException(
                status_code=409,
                detail=f"A pending {request_type} request already exists for GX run plan version '{command.run_plan_version_id}'",
            )

    row = _as_gx_run_plan_entity(
        await run_plan_repository.transition_plan_version(
        run_plan_id=command.run_plan_id,
        run_plan_version_id=command.run_plan_version_id,
        target_state=command.target_state,
        updated_by=command.updated_by,
        effective_from=command.effective_from.isoformat() if command.effective_from is not None else None,
        correlation_id=command.correlation_id,
        )
    )

    if request_type is None:
        return row

    try:
        approvals_repository.create_approval(
            {
                "rule_id": "",
                "gx_run_plan_id": command.run_plan_id,
                "gx_run_plan_version_id": command.run_plan_version_id,
                "request_type": request_type,
                "workspace_id": plan.workspaceId or "default",
                "comments": f"GX run plan version {command.run_plan_version_id} requested {request_type}",
                "status": "pending",
                "effective_at": command.effective_from.isoformat() if command.effective_from is not None else None,
            },
            command.updated_by,
        )
    except Exception as exc:
        await run_plan_repository.transition_plan_version(
            run_plan_id=command.run_plan_id,
            run_plan_version_id=command.run_plan_version_id,
            target_state=current_state,
            updated_by=command.updated_by,
            effective_from=None,
            correlation_id=command.correlation_id,
        )
        raise HTTPException(status_code=500, detail=f"Failed to create GX approval request: {exc}") from exc

    return row


async def validate_gx_run_plan_version(
    command: ValidateGxRunPlanVersionCommand,
    run_plan_repository: ValidationRunPlanRepository,
) -> GxRunPlanValidationResult:
    plan = await _get_plan_or_404(run_plan_repository, command.run_plan_id)
    version_row = _get_version_or_404(plan, command.run_plan_version_id)

    current_state = str(version_row.governanceState or "").strip()
    if current_state not in {"draft", "validation_failed"}:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_run_plan_state",
                "message": "Only draft or validation_failed run plan versions can be validated",
                "run_plan_id": command.run_plan_id,
                "run_plan_version_id": command.run_plan_version_id,
                "state": version_row.governanceState,
            },
        )

    validated_row = _as_gx_run_plan_entity(
        await run_plan_repository.transition_plan_version(
        run_plan_id=command.run_plan_id,
        run_plan_version_id=command.run_plan_version_id,
        target_state="pending_validation",
        updated_by=command.updated_by,
        correlation_id=command.correlation_id,
        )
    )
    validated_version = _get_version_or_404(validated_row, command.run_plan_version_id)
    diagnostics = validate_gx_run_plan_version_snapshot(validated_version)
    final_state = "pending_review" if not diagnostics else "validation_failed"
    final_row = _as_gx_run_plan_entity(
        await run_plan_repository.transition_plan_version(
        run_plan_id=command.run_plan_id,
        run_plan_version_id=command.run_plan_version_id,
        target_state=final_state,
        updated_by=command.updated_by,
        correlation_id=command.correlation_id,
        )
    )

    message = (
        f"Validation passed for run plan version '{command.run_plan_version_id}'. Review is now pending."
        if not diagnostics
        else f"Validation failed for run plan version '{command.run_plan_version_id}': {_first_diagnostic_message(diagnostics) or 'validation failed'}"
    )
    return GxRunPlanValidationResult(
        plan=final_row,
        validation_status="passed" if not diagnostics else "failed",
        message=message,
        diagnostics=diagnostics,
    )


async def activate_gx_run_plan_version(
    command: ActivateGxRunPlanVersionCommand,
    run_plan_repository: ValidationRunPlanRepository,
    dispatcher: GxRunPlanActivationDispatcher,
) -> GxRunPlanActivationResult:
    plan = await _get_plan_or_404(run_plan_repository, command.run_plan_id)
    version_row = _get_version_or_404(plan, command.run_plan_version_id)

    if str(version_row.governanceState or "") != "approved_pending_activation":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_run_plan_state",
                "message": "Only approved_pending_activation run plan versions can be activated",
                "run_plan_id": command.run_plan_id,
                "run_plan_version_id": command.run_plan_version_id,
                "state": version_row.governanceState,
            },
        )

    schedule_definition = build_gx_run_plan_schedule_definition_entity(version_row.scheduleDefinition)
    scheduled_at_raw = str(schedule_definition.scheduledAt or "").strip()
    if not scheduled_at_raw:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_schedule_definition",
                "message": "GX run plan version is missing scheduled_at",
                "run_plan_id": command.run_plan_id,
                "run_plan_version_id": command.run_plan_version_id,
            },
        )
    scheduled_at = datetime.fromisoformat(scheduled_at_raw.replace("Z", "+00:00"))

    gx_suite_selection = build_gx_run_plan_suite_selection_entity(version_row.gxSuiteSelection)
    if str(gx_suite_selection.selectionMode or "") == "grouped_scope":
        grouped_execution_plan = (
            gx_suite_selection.groupedExecutionPlan.model_dump(by_alias=True, exclude_none=True)
            if gx_suite_selection.groupedExecutionPlan is not None
            else {}
        )
        scope_selector = gx_suite_selection.scopeSelector.model_dump(by_alias=True, exclude_none=True)
        suite_refs = [item.model_dump(by_alias=True, exclude_none=True) for item in gx_suite_selection.suiteRefs]
        dispatch_payload = _as_dispatch_payload_entity(
            await dispatcher.enqueue_grouped_scope_run(
                ActivateGroupedScopeRunRequest(
                    grouped_execution_plan=grouped_execution_plan,
                    scope_selector=scope_selector,
                    suite_refs=suite_refs,
                    scheduled_at=scheduled_at,
                    requested_by=command.activated_by,
                    run_plan_id=command.run_plan_id,
                    run_plan_version_id=command.run_plan_version_id,
                )
            )
        )
        activated = _as_gx_run_plan_entity(
            await run_plan_repository.activate_plan(
            run_plan_id=command.run_plan_id,
            run_plan_version_id=command.run_plan_version_id,
            activated_by=command.activated_by,
            dispatched_run_id=str(dispatch_payload.queueMessageId or ""),
            correlation_id=command.correlation_id,
            )
        )
        return GxRunPlanActivationResult(plan=activated, dispatch=dispatch_payload)

    if version_row.suiteSnapshot is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_suite_snapshot",
                "message": "GX run plan version is missing the suite snapshot required for activation",
                "run_plan_id": command.run_plan_id,
                "run_plan_version_id": command.run_plan_version_id,
            },
        )

    try:
        suite = resolve_single_suite_activation_snapshot(version_row)
    except GxRunPlanActivationSnapshotError as exc:
        detail = {
            "error": exc.code,
            "message": exc.message,
            "run_plan_id": command.run_plan_id,
            "run_plan_version_id": command.run_plan_version_id,
        }
        if exc.code == "invalid_suite_snapshot" and isinstance(exc.details, list):
            detail["validation_errors"] = exc.details
        elif exc.details is not None:
            detail["details"] = exc.details
        raise HTTPException(status_code=422, detail=detail) from exc

    dispatch_payload = _as_dispatch_payload_entity(
        await dispatcher.enqueue_scheduled_suite_run(
            ActivateScheduledSuiteRunRequest(
                suite=suite,
                scheduled_at=scheduled_at,
                requested_by=command.activated_by,
                status_source="gx.run_plan.activate",
                status_reason="GX run plan activated",
                run_plan_id=command.run_plan_id,
                run_plan_version_id=command.run_plan_version_id,
            )
        )
    )
    activated = _as_gx_run_plan_entity(
        await run_plan_repository.activate_plan(
        run_plan_id=command.run_plan_id,
        run_plan_version_id=command.run_plan_version_id,
        activated_by=command.activated_by,
        dispatched_run_id=str(dispatch_payload.queueMessageId or ""),
        correlation_id=command.correlation_id,
        )
    )
    return GxRunPlanActivationResult(plan=activated, dispatch=dispatch_payload)