from __future__ import annotations

import pytest

from app.infrastructure.repositories.in_memory_gx_run_plan_repository import InMemoryGxRunPlanRepository


@pytest.mark.anyio
async def test_in_memory_gx_run_plan_repository_lifecycle() -> None:
    repo = InMemoryGxRunPlanRepository()

    plan = await repo.create_plan(
        run_plan_id="plan-1",
        run_plan_version_id="version-1",
        workspace_id="workspace-1",
        scope_selector={"selector": "all"},
        planning_mode="manual",
        status="draft",
        created_by="creator",
        gx_suite_selection={"suite": "s1"},
        suite_id="suite-1",
        suite_version=1,
        suite_snapshot={"snapshot": True},
        execution_contract_snapshot={"contract": True},
        schedule_definition={"cron": "0 0 * * *"},
        effective_from="2026-01-01T00:00:00Z",
        correlation_id="corr-1",
    )
    plan_payload = plan.model_dump()

    assert plan_payload["runPlanId"] == "plan-1"
    assert plan_payload["workspaceId"] == "workspace-1"
    assert plan_payload["pendingVersionId"] == "version-1"
    assert plan_payload["pendingVersionGovernanceState"] == "draft"
    assert len(plan_payload["versions"]) == 1
    assert plan_payload["transitionEvents"][0]["action"] == "created"

    with pytest.raises(ValueError):
        await repo.create_plan(
            run_plan_id="plan-1",
            run_plan_version_id="version-1",
            workspace_id="workspace-1",
            scope_selector={"selector": "all"},
            planning_mode="manual",
            status="draft",
            created_by="creator",
            gx_suite_selection={"suite": "s1"},
            suite_id="suite-1",
            suite_version=1,
            suite_snapshot={"snapshot": True},
            execution_contract_snapshot={"contract": True},
            schedule_definition={"cron": "0 0 * * *"},
        )

    next_plan = await repo.create_plan_version(
        run_plan_id="plan-1",
        run_plan_version_id="version-2",
        gx_suite_selection={"suite": "s1"},
        suite_id="suite-1",
        suite_version=2,
        suite_snapshot={"snapshot": True},
        execution_contract_snapshot={"contract": True},
        schedule_definition={"cron": "0 0 * * *"},
        created_by="creator",
    )
    next_plan_payload = next_plan.model_dump()

    assert len(next_plan_payload["versions"]) == 2
    assert next_plan_payload["status"] == "draft"
    assert any(version["runPlanVersionId"] == "version-2" for version in next_plan_payload["versions"])

    plans = await repo.list_plans(workspace_id="workspace-1", status="draft")
    assert len(plans) == 1
    assert plans[0].runPlanId == "plan-1"

    transitioned = await repo.transition_plan_version(
        run_plan_id="plan-1",
        run_plan_version_id="version-2",
        target_state="pending_validation",
        updated_by="reviewer",
        effective_from="2026-01-02T00:00:00Z",
        correlation_id="corr-2",
    )
    assert any(version.governanceState == "pending_validation" for version in transitioned.versions)

    approved = await repo.transition_plan_version(
        run_plan_id="plan-1",
        run_plan_version_id="version-2",
        target_state="approved_pending_activation",
        updated_by="reviewer",
        correlation_id="corr-3",
    )
    assert any(version.governanceState == "approved_pending_activation" for version in approved.versions)

    activated = await repo.activate_plan(
        run_plan_id="plan-1",
        run_plan_version_id="version-2",
        activated_by="activator",
        dispatched_run_id="run-1",
        correlation_id="corr-4",
    )
    assert activated.status == "active"
    assert activated.currentActiveVersionId == "version-2"
    assert activated.lastDispatchedRunId == "run-1"

    pending = await repo.transition_plan_version(
        run_plan_id="plan-1",
        run_plan_version_id="version-2",
        target_state="deactivation-requested",
        updated_by="deactivator",
        correlation_id="corr-5",
    )
    assert any(version.governanceState == "deactivation-requested" for version in pending.versions)

    deactivated = await repo.deactivate_plan(
        run_plan_id="plan-1",
        run_plan_version_id="version-2",
        deactivated_by="deactivator",
        correlation_id="corr-6",
    )
    assert deactivated.status == "deactivated"
    assert deactivated.currentActiveVersionId is None


@pytest.mark.anyio
async def test_in_memory_gx_run_plan_repository_records_active_dispatch() -> None:
    repo = InMemoryGxRunPlanRepository()
    await repo.create_plan(
        run_plan_id="plan-dispatch",
        run_plan_version_id="version-1",
        workspace_id="workspace-1",
        scope_selector={"selector": "all"},
        planning_mode="manual",
        status="draft",
        created_by="creator",
        gx_suite_selection={"suite": "s1"},
        suite_id="suite-1",
        suite_version=1,
        suite_snapshot={"snapshot": True},
        execution_contract_snapshot={"contract": True},
        schedule_definition={"scheduledAt": "2026-06-01T00:00:00Z"},
    )
    await repo.transition_plan_version(
        run_plan_id="plan-dispatch",
        run_plan_version_id="version-1",
        target_state="pending_validation",
        updated_by="reviewer",
    )
    await repo.transition_plan_version(
        run_plan_id="plan-dispatch",
        run_plan_version_id="version-1",
        target_state="approved_pending_activation",
        updated_by="reviewer",
    )
    await repo.activate_plan(
        run_plan_id="plan-dispatch",
        run_plan_version_id="version-1",
        activated_by="activator",
        dispatched_run_id="run-1",
    )

    dispatched = await repo.record_plan_dispatch(
        run_plan_id="plan-dispatch",
        run_plan_version_id="version-1",
        dispatched_run_id="run-2",
        dispatched_by="pipeline",
        correlation_id="corr-2",
        details={"trigger_type": "pipeline_run", "source_pipeline": "airflow"},
    )

    assert dispatched.lastDispatchedRunId == "run-2"
    assert dispatched.transitionEvents[-1].action == "dispatched"
    assert dispatched.transitionEvents[-1].details["trigger_type"] == "pipeline_run"
    assert dispatched.transitionEvents[-1].details["source_pipeline"] == "airflow"


@pytest.mark.anyio
async def test_transition_plan_version_invalid_states_raise() -> None:
    repo = InMemoryGxRunPlanRepository()
    await repo.create_plan(
        run_plan_id="plan-2",
        run_plan_version_id="version-10",
        workspace_id="workspace-2",
        scope_selector={"selector": "all"},
        planning_mode="manual",
        status="draft",
        created_by="creator",
        gx_suite_selection={"suite": "s2"},
        suite_id="suite-2",
        suite_version=1,
        suite_snapshot={"snapshot": True},
        execution_contract_snapshot={"contract": True},
        schedule_definition={"cron": "0 0 * * *"},
    )

    with pytest.raises(ValueError):
        await repo.transition_plan_version(
            run_plan_id="plan-2",
            run_plan_version_id="version-10",
            target_state="invalid_state",
            updated_by="reviewer",
        )

    with pytest.raises(ValueError):
        await repo.activate_plan(
            run_plan_id="plan-2",
            run_plan_version_id="version-10",
            activated_by="activator",
        )

    with pytest.raises(ValueError):
        await repo.deactivate_plan(
            run_plan_id="plan-2",
            run_plan_version_id="version-10",
            deactivated_by="deactivator",
        )