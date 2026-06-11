from typing import Protocol

from app.domain.entities import GxExecutionContractEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationRunPlanArtifactSelectionEntity
from app.domain.entities import ValidationRunPlanEntity
from app.domain.entities import ValidationRunPlanGroupedArtifactSnapshotEntity
from app.domain.entities import ValidationRunPlanScheduleDefinitionEntity
from app.domain.entities import ValidationRunPlanScopeSelectorEntity


class ValidationRunPlanRepository(Protocol):
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
        ...

    async def get_plan(self, run_plan_id: str) -> ValidationRunPlanEntity | None:
        ...

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
        ...

    async def list_plans(
        self,
        *,
        workspace_id: str | None = None,
        business_key: str | None = None,
        status: str | None = None,
        artifact_id: str | None = None,
    ) -> list[ValidationRunPlanEntity]:
        ...

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
        ...

    async def activate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        activated_by: str | None,
        dispatched_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        ...

    async def deactivate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        deactivated_by: str | None,
        correlation_id: str | None = None,
    ) -> ValidationRunPlanEntity:
        ...

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
        ...