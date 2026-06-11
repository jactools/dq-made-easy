from __future__ import annotations

import pytest

from app.domain.entities import ValidationRunPlanArtifactSelectionEntity
from app.domain.entities import ValidationRunPlanArtifactRefEntity
from app.domain.entities import ValidationRunPlanScheduleDefinitionEntity
from app.domain.entities import ValidationRunPlanScopeSelectorEntity
from app.infrastructure.repositories.in_memory_validation_run_plan_repository import InMemoryValidationRunPlanRepository


@pytest.mark.anyio
async def test_in_memory_validation_run_plan_repository_round_trip() -> None:
    repository = InMemoryValidationRunPlanRepository()

    plan = await repository.create_plan(
        run_plan_id="plan-1",
        run_plan_version_id="version-1",
        workspace_id="workspace-1",
        scope_selector=ValidationRunPlanScopeSelectorEntity(dataObjectId="do-1"),
        planning_mode="manual",
        status="draft",
        created_by="creator",
        validation_artifact_selection=ValidationRunPlanArtifactSelectionEntity(
            selectionMode="explicit_refs",
            artifactRefs=[ValidationRunPlanArtifactRefEntity(artifactId="suite-1", artifactVersion=1)],
        ),
        artifact_id="suite-1",
        artifact_version=1,
        artifact_snapshot=None,
        execution_contract_snapshot=None,
        schedule_definition=ValidationRunPlanScheduleDefinitionEntity(),
        effective_from="2026-01-01T00:00:00Z",
        correlation_id="corr-1",
    )

    assert plan.runPlanId == "plan-1"
    assert plan.pendingVersionId == "version-1"
    assert plan.versions[0].artifactId == "suite-1"
    assert plan.versions[0].validationArtifactSelection["artifactRefs"][0]["artifactId"] == "suite-1"

    activated = await repository.transition_plan_version(
        run_plan_id="plan-1",
        run_plan_version_id="version-1",
        target_state="pending_validation",
        updated_by="reviewer",
    )
    assert any(version.governanceState == "pending_validation" for version in activated.versions)