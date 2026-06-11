from app.domain.entities import build_gx_artifact_snapshot_payload_from_validation_snapshot
from app.domain.entities import build_gx_run_plan_entity_from_validation_run_plan
from app.domain.entities import build_gx_suite_selection_payload_from_validation_artifact_selection
from app.domain.entities import build_validation_run_plan_entity_from_gx_run_plan
from app.domain.entities import GxExecutionContractEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationRunPlanArtifactSelectionEntity
from app.domain.entities import ValidationRunPlanEntity
from app.domain.entities import ValidationRunPlanGroupedArtifactSnapshotEntity
from app.domain.entities import ValidationRunPlanScheduleDefinitionEntity
from app.domain.entities import ValidationRunPlanScopeSelectorEntity
from app.domain.interfaces.v1.validation_run_plan_repository import ValidationRunPlanRepository
from app.infrastructure.repositories.in_memory_gx_run_plan_repository import InMemoryGxRunPlanRepository


class InMemoryValidationRunPlanRepository(ValidationRunPlanRepository):
    def __init__(self, gx_repository: InMemoryGxRunPlanRepository | None = None) -> None:
        self._gx_repository = gx_repository or InMemoryGxRunPlanRepository()

    async def create_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        workspace_id: str,
        scope_selector: ValidationRunPlanScopeSelectorEntity,
        planning_mode: str,
        status: str,
        created_by: str | None,
        validation_artifact_selection: ValidationRunPlanArtifactSelectionEntity,
        artifact_id: str | None,
        artifact_version: int | None,
        artifact_snapshot: ValidationArtifactEnvelopeEntity | ValidationRunPlanGroupedArtifactSnapshotEntity | dict | None,
        execution_contract_snapshot: GxExecutionContractEntity | None,
        schedule_definition: ValidationRunPlanScheduleDefinitionEntity,
        effective_from: str | None = None,
        validation_status: str | None = None,
        review_status: str | None = None,
        supersedes_version_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        plan = await self._gx_repository.create_plan(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            workspace_id=workspace_id,
            scope_selector=scope_selector.model_dump(mode="python", by_alias=False, exclude_none=True),
            planning_mode=planning_mode,
            status=status,
            created_by=created_by,
            gx_suite_selection=build_gx_suite_selection_payload_from_validation_artifact_selection(validation_artifact_selection),
            suite_id=artifact_id,
            suite_version=artifact_version,
            suite_snapshot=build_gx_artifact_snapshot_payload_from_validation_snapshot(artifact_snapshot),
            execution_contract_snapshot=execution_contract_snapshot.model_dump(mode="python", by_alias=False, exclude_none=True)
            if execution_contract_snapshot is not None
            else None,
            schedule_definition=schedule_definition.model_dump(mode="python", by_alias=False, exclude_none=True),
            effective_from=effective_from,
            validation_status=validation_status,
            review_status=review_status,
            supersedes_version_id=supersedes_version_id,
            correlation_id=correlation_id,
        )
        return build_validation_run_plan_entity_from_gx_run_plan(plan)

    async def get_plan(self, run_plan_id: str) -> ValidationRunPlanEntity | None:
        plan = await self._gx_repository.get_plan(run_plan_id)
        if plan is None:
            return None
        return build_validation_run_plan_entity_from_gx_run_plan(plan)

    async def create_plan_version(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        validation_artifact_selection: ValidationRunPlanArtifactSelectionEntity,
        artifact_id: str | None,
        artifact_version: int | None,
        artifact_snapshot: ValidationArtifactEnvelopeEntity | ValidationRunPlanGroupedArtifactSnapshotEntity | dict | None,
        execution_contract_snapshot: GxExecutionContractEntity | None,
        schedule_definition: ValidationRunPlanScheduleDefinitionEntity,
        created_by: str | None,
        effective_from: str | None = None,
        validation_status: str | None = None,
        review_status: str | None = None,
        supersedes_version_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        plan = await self._gx_repository.create_plan_version(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            gx_suite_selection=build_gx_suite_selection_payload_from_validation_artifact_selection(validation_artifact_selection),
            suite_id=artifact_id,
            suite_version=artifact_version,
            suite_snapshot=build_gx_artifact_snapshot_payload_from_validation_snapshot(artifact_snapshot),
            execution_contract_snapshot=execution_contract_snapshot.model_dump(mode="python", by_alias=False, exclude_none=True)
            if execution_contract_snapshot is not None
            else None,
            schedule_definition=schedule_definition.model_dump(mode="python", by_alias=False, exclude_none=True),
            created_by=created_by,
            effective_from=effective_from,
            validation_status=validation_status,
            review_status=review_status,
            supersedes_version_id=supersedes_version_id,
            correlation_id=correlation_id,
        )
        return build_validation_run_plan_entity_from_gx_run_plan(plan)

    async def list_plans(
        self,
        *,
        workspace_id: str | None = None,
        business_key: str | None = None,
        status: str | None = None,
        artifact_id: str | None = None,
    ) -> list[ValidationRunPlanEntity]:
        plans = await self._gx_repository.list_plans(
            workspace_id=workspace_id,
            business_key=business_key,
            status=status,
            suite_id=artifact_id,
        )
        return [build_validation_run_plan_entity_from_gx_run_plan(plan) for plan in plans]

    async def transition_plan_version(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        target_state: str,
        updated_by: str | None,
        effective_from: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        plan = await self._gx_repository.transition_plan_version(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            target_state=target_state,
            updated_by=updated_by,
            effective_from=effective_from,
            correlation_id=correlation_id,
        )
        return build_validation_run_plan_entity_from_gx_run_plan(plan)

    async def activate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        activated_by: str | None,
        dispatched_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        plan = await self._gx_repository.activate_plan(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            activated_by=activated_by,
            dispatched_run_id=dispatched_run_id,
            correlation_id=correlation_id,
        )
        return build_validation_run_plan_entity_from_gx_run_plan(plan)

    async def deactivate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        deactivated_by: str | None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        plan = await self._gx_repository.deactivate_plan(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            deactivated_by=deactivated_by,
            correlation_id=correlation_id,
        )
        return build_validation_run_plan_entity_from_gx_run_plan(plan)

    async def record_plan_dispatch(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        dispatched_run_id: str,
        dispatched_by: str | None,
        correlation_id: str | None = None,
        details: dict | None = None,
    ) -> ValidationRunPlanEntity:
        plan = await self._gx_repository.record_plan_dispatch(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            dispatched_run_id=dispatched_run_id,
            dispatched_by=dispatched_by,
            correlation_id=correlation_id,
            details=details,
        )
        return build_validation_run_plan_entity_from_gx_run_plan(plan)