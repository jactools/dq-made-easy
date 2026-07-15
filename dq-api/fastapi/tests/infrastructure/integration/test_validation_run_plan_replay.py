from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

import app.api.v1.validation_run_plan_api as validation_run_plan_api
import app.infrastructure.repositories.postgres_validation_run_plan_repository as repo_module
from app.domain.entities import GxGroupedExecutionPlanEntity
from app.domain.entities import ValidationRunPlanArtifactRefEntity
from app.domain.entities import ValidationRunPlanArtifactSelectionEntity
from app.domain.entities import ValidationRunPlanScheduleDefinitionEntity
from app.domain.entities import ValidationRunPlanScopeSelectorEntity
from app.domain.entities.validation_run_plan import build_gx_run_plan_entity_from_validation_run_plan
from app.infrastructure.repositories.postgres_data_catalog_repository import PostgresDataCatalogRepository
from app.infrastructure.repositories.postgres_gx_execution_run_repository import PostgresGxExecutionRunRepository
from app.infrastructure.repositories.postgres_validation_run_plan_repository import PostgresValidationRunPlanRepository

pytestmark = pytest.mark.integration


def _grouped_validation_artifact_snapshot() -> dict[str, object]:
    return {
        "validationArtifactId": "gx-suite-1",
        "validationArtifactVersion": 1,
        "engineType": "gx",
        "assignmentScope": {"dataObjectId": "do-1", "datasetId": "ds-1", "dataProductId": "prod-1"},
        "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
        "compiledFrom": {
            "ruleIds": ["rule-1"],
            "compilerVersion": "dq-compiler-7.3",
            "generatedAt": "2026-04-10T08:00:00Z",
        },
        "executionHints": {"recommendedEngineTarget": "pyspark", "primaryKeyFields": ["id"]},
        "runPlanning": {
            "engineTarget": "pyspark",
            "executionShape": "grouped_scope",
            "traceability": {
                "ruleId": "rule-1",
                "ruleVersionId": "rule-version-1",
                "validationArtifactId": "gx-suite-1",
                "validationArtifactVersion": 1,
            },
        },
        "engineArtifact": {
            "engineType": "gx",
            "artifactKind": "gx_expectation_suite",
            "artifactSchemaVersion": "gx-artifact-envelope/v1",
            "payload": {
                "suiteId": "gx-suite-1",
                "suiteVersion": 1,
                "expectation_suite_name": "gx-suite-1",
                "expectations": [
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": "customer_id"},
                    }
                ],
                "meta": {},
            },
        },
    }


@pytest.mark.anyio
async def test_replay_grouped_validation_run_plan_persists_dispatch_in_postgres(
    monkeypatch: pytest.MonkeyPatch,
    live_engine,
    live_db_url: str,
) -> None:
    run_plan_id = f"copilot-postgres-replay-{uuid4().hex[:8]}"
    run_plan_version_id = f"{run_plan_id}-v1"

    repository = PostgresValidationRunPlanRepository(live_db_url)
    execution_run_repository = PostgresGxExecutionRunRepository(live_db_url)
    data_catalog_repository = PostgresDataCatalogRepository(live_db_url)

    monkeypatch.setattr(repo_module, "_append_transition_event", lambda *args, **kwargs: None)

    async def _enqueue_grouped_scope_run(**kwargs):
        return SimpleNamespace(
            runId="replay-run-123",
            queueMessageId="queue-msg-123",
            suiteId=None,
            suiteVersion=None,
            engineType="gx",
            engineTarget="pyspark",
            executionShape="grouped_scope",
            dispatchMode="queued",
            queueKey="dq-gx:execution-dispatch",
            scheduledAt="2026-06-28T10:00:00+00:00",
            correlationId=kwargs.get("correlation_id"),
        )

    monkeypatch.setattr(
        validation_run_plan_api._gx_runtime_api,
        "bind_grouped_scope_run_enqueue",
        lambda **_kwargs: _enqueue_grouped_scope_run,
    )

    try:
        created_plan = await repository.create_plan(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            workspace_id="integration-workspace",
            scope_selector=ValidationRunPlanScopeSelectorEntity(
                dataObjectId="do-1",
                workspaceId="integration-workspace",
            ),
            planning_mode="manual",
            status="activation-requested",
            created_by="copilot",
            validation_artifact_selection=ValidationRunPlanArtifactSelectionEntity(
                selectionMode="grouped_scope",
                scopeSelector=ValidationRunPlanScopeSelectorEntity(
                    dataObjectId="do-1",
                    workspaceId="integration-workspace",
                ),
                artifactRefs=[ValidationRunPlanArtifactRefEntity(artifactId="gx-suite-1", artifactVersion=1)],
                groupedExecutionPlan=GxGroupedExecutionPlanEntity(suiteCount=1, batchCount=1),
            ),
            artifact_id="gx-suite-1",
            artifact_version=1,
            artifact_snapshot=_grouped_validation_artifact_snapshot(),
            execution_contract_snapshot=None,
            schedule_definition=ValidationRunPlanScheduleDefinitionEntity(),
            correlation_id="corr-create",
        )
        assert created_plan.status == "activation-requested"

        transitioned_plan = await repository.transition_plan_version(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            target_state="approved_pending_activation",
            updated_by="copilot",
            correlation_id="corr-transition",
        )
        assert transitioned_plan.versions[0].governanceState == "approved_pending_activation"

        activated_plan = await repository.activate_plan(
            run_plan_id=run_plan_id,
            run_plan_version_id=run_plan_version_id,
            activated_by="copilot",
            dispatched_run_id=None,
            correlation_id="corr-activate",
        )
        assert activated_plan.status == "active"
        assert activated_plan.currentActiveVersionId == run_plan_version_id

        plan = await repository.get_plan(run_plan_id)
        assert plan is not None
        gx_plan = build_gx_run_plan_entity_from_validation_run_plan(plan)
        active_version = next(
            (version for version in gx_plan.versions if version.runPlanVersionId == gx_plan.currentActiveVersionId),
            None,
        )
        assert active_version is not None
        selection_mode = getattr(active_version.gxSuiteSelection, "selectionMode", None)
        if selection_mode is None and isinstance(active_version.gxSuiteSelection, dict):
            selection_mode = active_version.gxSuiteSelection.get("selectionMode")
        assert selection_mode == "grouped_scope"

        result = await validation_run_plan_api.replay_run_plan(
            request=SimpleNamespace(headers={}),
            run_plan_id=run_plan_id,
            repository=repository,
            execution_run_repository=execution_run_repository,
            data_catalog_repository=data_catalog_repository,
            requested_by="copilot",
            correlation_id="corr-postgres-replay",
            trigger_type="manual",
            source_pipeline=None,
            scheduled_at=None,
            settings_provider=lambda: None,
            async_redis_module=SimpleNamespace(),
            sync_redis_module=SimpleNamespace(),
            logger=SimpleNamespace(),
        )

        assert result.run_plan_id == run_plan_id
        assert result.run_plan_version_id == run_plan_version_id
        assert result.selection_mode == "grouped_scope"
        assert result.dispatch.runId == "replay-run-123"

        plan_after = await repository.get_plan(run_plan_id)
        assert plan_after is not None
        assert plan_after.lastDispatchedRunId == "replay-run-123"
    finally:
        with live_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM validation_run_plan_transitions WHERE run_plan_id = :run_plan_id"),
                {"run_plan_id": run_plan_id},
            )
            conn.execute(
                text("DELETE FROM validation_run_plan_versions WHERE run_plan_id = :run_plan_id"),
                {"run_plan_id": run_plan_id},
            )
            conn.execute(
                text("DELETE FROM validation_run_plans WHERE id = :run_plan_id"),
                {"run_plan_id": run_plan_id},
            )