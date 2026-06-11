from typing import Protocol

from app.domain.entities import GxRunPlanEntity
from app.domain.entities.gx_execution_run import GxExecutionContractEntity
from app.domain.entities.gx_run_plan import (
    GxRunPlanScheduleDefinitionEntity,
    GxRunPlanScopeSelectorEntity,
    GxRunPlanSuiteSelectionEntity,
    GxRunPlanSingleSuiteSnapshotEntity,
    GxRunPlanGroupedSuiteSnapshotEntity,
)


class GxRunPlanRepository(Protocol):
    async def create_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        workspace_id: str,
        scope_selector: GxRunPlanScopeSelectorEntity,
        planning_mode: str,
        status: str,
        created_by: str | None,
        gx_suite_selection: GxRunPlanSuiteSelectionEntity,
        suite_id: str | None,
        suite_version: int | None,
        suite_snapshot: GxRunPlanSingleSuiteSnapshotEntity | GxRunPlanGroupedSuiteSnapshotEntity | None,
        execution_contract_snapshot: GxExecutionContractEntity | None,
        schedule_definition: GxRunPlanScheduleDefinitionEntity,
        effective_from: str | None = None,
        validation_status: str | None = None,
        review_status: str | None = None,
        supersedes_version_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GxRunPlanEntity:
        ...

    async def get_plan(self, run_plan_id: str) -> GxRunPlanEntity | None:
        ...

    async def create_plan_version(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        gx_suite_selection: GxRunPlanSuiteSelectionEntity,
        suite_id: str | None,
        suite_version: int | None,
        suite_snapshot: GxRunPlanSingleSuiteSnapshotEntity | GxRunPlanGroupedSuiteSnapshotEntity | None,
        execution_contract_snapshot: GxExecutionContractEntity | None,
        schedule_definition: GxRunPlanScheduleDefinitionEntity,
        created_by: str | None,
        effective_from: str | None = None,
        validation_status: str | None = None,
        review_status: str | None = None,
        supersedes_version_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GxRunPlanEntity:
        ...

    async def list_plans(
        self,
        *,
        workspace_id: str | None = None,
        business_key: str | None = None,
        status: str | None = None,
        suite_id: str | None = None,
    ) -> list[GxRunPlanEntity]:
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
    ) -> GxRunPlanEntity:
        ...

    async def activate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        activated_by: str | None,
        dispatched_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GxRunPlanEntity:
        ...

    async def deactivate_plan(
        self,
        *,
        run_plan_id: str,
        run_plan_version_id: str,
        deactivated_by: str | None,
        correlation_id: str | None = None,
    ) -> GxRunPlanEntity:
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
    ) -> GxRunPlanEntity:
        ...