from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.application.services.gx_run_plan_dispatcher import ActivateGroupedScopeRunRequest
from app.application.services.gx_run_plan_dispatcher import ActivateScheduledSuiteRunRequest
from app.application.services.gx_run_plan_seed_resolver import ResolveGxRunPlanSeedCommand
from app.application.use_cases.gx_run_plans import ActivateGxRunPlanVersionCommand
from app.application.use_cases.gx_run_plans import activate_gx_run_plan_version
from app.application.use_cases.gx_run_plans import CreateGxRunPlanCommand
from app.application.use_cases.gx_run_plans import create_gx_run_plan
from app.application.use_cases.gx_run_plans import CreateGxRunPlanVersionCommand
from app.application.use_cases.gx_run_plans import create_gx_run_plan_version
from app.application.use_cases.gx_run_plans import GxRunPlanActivationResult
from app.application.use_cases.gx_run_plans import TransitionGxRunPlanVersionGovernanceStateCommand
from app.application.use_cases.gx_run_plans import transition_gx_run_plan_version_governance_state
from app.application.use_cases.gx_run_plans import ValidateGxRunPlanVersionCommand
from app.application.use_cases.gx_run_plans import validate_gx_run_plan_version
from app.domain.entities.approvals import build_approval_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_scope_selector_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_entity
from app.domain.entities.gx_run_plan import GxRunPlanGroupedSuiteSnapshotEntity
from app.domain.entities.gx_run_plan import GxRunPlanSingleSuiteSnapshotEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_version_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_suite_selection_entity
from app.domain.entities.gx_run_plan import build_gx_run_plan_version_validation_snapshot_entity
from app.domain.entities.gx_run_plan import GxRunPlanSeedEntity
from app.domain.entities.gx_run_plan import GxRunPlanScheduleDefinitionEntity
from app.domain.entities.gx_run_plan import GxRunPlanScopeSelectorEntity
from app.domain.entities.gx_run_plan import GxRunPlanAssignmentScopeEntity
from app.domain.entities.gx_run_plan import GxRunPlanSuiteSelectionEntity
from app.domain.entities.gx_run_plan import GxRunPlanSuiteRefEntity
from app.domain.entities.gx_execution_run import GxExecutionContractEntity
from app.domain.entities.gx_execution_run import GxExecutionTraceabilityEntity
from app.domain.entities.validation_run_plan import build_validation_run_plan_entity_from_gx_run_plan


pytestmark = pytest.mark.usefixtures("clone_payload")


@pytest.fixture
def single_suite_seed() -> GxRunPlanSeedEntity:
    return GxRunPlanSeedEntity(
        scopeSelector=GxRunPlanScopeSelectorEntity(
            assignmentScope=GxRunPlanAssignmentScopeEntity(dataObjectId="do-1")
        ),
        gxSuiteSelection=GxRunPlanSuiteSelectionEntity(
            selectionMode="single_suite",
            suiteRefs=[GxRunPlanSuiteRefEntity(suiteId="gx-suite-1", suiteVersion=1, engineType="gx")],
        ),
        suiteId="gx-suite-1",
        suiteVersion=1,
        suiteSnapshot=GxRunPlanSingleSuiteSnapshotEntity(
            suiteId="gx-suite-1",
            suiteVersion=1,
            artifactVersion="v1",
            assignmentScope={"dataObjectId": "do-1"},
            resolvedExecutionScope={"dataObjectVersionIds": ["dov-1"]},
            gxSuite={
                "expectation_suite_name": "suite",
                "expectations": [{"expectationType": "expect_column_values_to_not_be_null", "kwargs": {"column": "id"}}],
                "meta": {},
            },
            compiledFrom={"ruleIds": ["rule-1"], "compilerVersion": "dq-7.3", "generatedAt": "2026-04-24T10:00:00Z"},
            executionHints={"recommendedEngine": "pyspark", "primaryKeyFields": ["id"]},
            executionContract=GxExecutionContractEntity(
                engineTarget="pyspark",
                executionShape="single_object",
                traceability=GxExecutionTraceabilityEntity(
                    ruleId="rule-1",
                    ruleVersionId="rule-version-1",
                    gxSuiteId="gx-suite-1",
                    gxSuiteVersion=1,
                    dataObjectVersionId="dov-1",
                ),
            ),
        ),
        executionContractSnapshot=GxExecutionContractEntity(
            engineTarget="pyspark",
            executionShape="single_object",
            traceability=GxExecutionTraceabilityEntity(
                ruleId="rule-1",
                ruleVersionId="rule-version-1",
                gxSuiteId="gx-suite-1",
                gxSuiteVersion=1,
                dataObjectVersionId="dov-1",
            ),
        ),
    )


@pytest.fixture
def grouped_scope_seed(single_suite_seed: GxRunPlanSeedEntity) -> GxRunPlanSeedEntity:
    return GxRunPlanSeedEntity(
        scopeSelector=GxRunPlanScopeSelectorEntity(dataObjectVersionId="dov-1"),
        gxSuiteSelection=GxRunPlanSuiteSelectionEntity(
            selectionMode="grouped_scope",
            scopeSelector=GxRunPlanScopeSelectorEntity(dataObjectVersionId="dov-1"),
            suiteRefs=[GxRunPlanSuiteRefEntity(suiteId="gx-suite-1", suiteVersion=1, engineType="gx")],
        ),
        suiteId=None,
        suiteVersion=None,
        suiteSnapshot=GxRunPlanGroupedSuiteSnapshotEntity(
            suiteEnvelopes=[single_suite_seed.suiteSnapshot],
        ),
        executionContractSnapshot=None,
    )


class _ActivationDispatcher:
    def __init__(
        self,
        *,
        enqueue_grouped_scope_run=None,
        enqueue_scheduled_suite_run=None,
    ) -> None:
        self._enqueue_grouped_scope_run = enqueue_grouped_scope_run
        self._enqueue_scheduled_suite_run = enqueue_scheduled_suite_run

    async def enqueue_grouped_scope_run(self, request: ActivateGroupedScopeRunRequest):
        if self._enqueue_grouped_scope_run is None:
            pytest.fail(f"unexpected grouped enqueue: {request}")
        return await self._enqueue_grouped_scope_run(request)

    async def enqueue_scheduled_suite_run(self, request: ActivateScheduledSuiteRunRequest):
        if self._enqueue_scheduled_suite_run is None:
            pytest.fail(f"unexpected scheduled enqueue: {request}")
        return await self._enqueue_scheduled_suite_run(request)


class _SeedResolver:
    def __init__(self, resolve_seed) -> None:
        self._resolve_seed = resolve_seed

    async def resolve_seed(self, command: ResolveGxRunPlanSeedCommand):
        return await self._resolve_seed(command)


class _RunPlanRepository:
    def __init__(self) -> None:
        self.last_create_kwargs: dict | None = None
        self.last_create_version_kwargs: dict | None = None
        self.last_transition_kwargs: list[dict] = []
        self.last_activate_kwargs: dict | None = None
        self.plans: dict[str, dict] = {}

    async def create_plan(self, **kwargs):
        self.last_create_kwargs = kwargs
        run_plan_id = str(kwargs["run_plan_id"])
        version_id = str(kwargs["run_plan_version_id"])
        if "validation_artifact_selection" in kwargs:
            gx_suite_selection = {
                "selectionMode": kwargs["validation_artifact_selection"].selectionMode,
                "scopeSelector": kwargs["validation_artifact_selection"].scopeSelector.model_dump(mode="python", by_alias=False, exclude_none=True),
                "suiteRefs": [
                    {"suiteId": item.artifactId, "suiteVersion": item.artifactVersion, "engineType": item.engineType}
                    for item in kwargs["validation_artifact_selection"].artifactRefs
                ],
                "groupedExecutionPlan": (
                    kwargs["validation_artifact_selection"].groupedExecutionPlan.model_dump(mode="python", by_alias=False, exclude_none=True)
                    if kwargs["validation_artifact_selection"].groupedExecutionPlan is not None
                    else None
                ),
            }
        else:
            gx_suite_selection = (
                kwargs["gx_suite_selection"].model_dump(mode="python", by_alias=False, exclude_none=True)
                if hasattr(kwargs["gx_suite_selection"], "model_dump")
                else dict(kwargs["gx_suite_selection"])
            )
        suite_snapshot = kwargs.get("artifact_snapshot", kwargs.get("suite_snapshot"))
        suite_id = kwargs.get("artifact_id", kwargs.get("suite_id"))
        suite_version = kwargs.get("artifact_version", kwargs.get("suite_version"))
        plan = {
            "runPlanId": run_plan_id,
            "businessKey": run_plan_id,
            "workspaceId": kwargs["workspace_id"],
            "scopeSelector": kwargs["scope_selector"],
            "planningMode": kwargs["planning_mode"],
            "currentActiveVersionId": None,
            "status": kwargs["status"],
            "pendingVersionId": version_id,
            "pendingVersionGovernanceState": "draft",
            "createdBy": kwargs.get("created_by"),
            "createdAt": "2026-04-24T10:00:00Z",
            "updatedAt": "2026-04-24T10:00:00Z",
            "activatedBy": None,
            "activatedAt": None,
            "lastDispatchedRunId": None,
            "versions": [
                {
                    "runPlanVersionId": version_id,
                    "runPlanId": run_plan_id,
                    "governanceState": "draft",
                    "gxSuiteSelection": gx_suite_selection,
                    "suiteId": suite_id,
                    "suiteVersion": suite_version,
                    "suiteSnapshot": suite_snapshot,
                    "scheduleDefinition": kwargs["schedule_definition"],
                    "executionContractSnapshot": kwargs.get("execution_contract_snapshot"),
                    "validationStatus": None,
                    "reviewStatus": None,
                    "effectiveFrom": kwargs.get("effective_from"),
                    "supersedesVersionId": kwargs.get("supersedes_version_id"),
                    "createdBy": kwargs.get("created_by"),
                    "createdAt": "2026-04-24T10:00:00Z",
                }
            ],
            "transitionEvents": [],
        }
        self.plans[run_plan_id] = plan
        return build_validation_run_plan_entity_from_gx_run_plan(build_gx_run_plan_entity(plan))

    async def get_plan(self, run_plan_id: str):
        plan = self.plans.get(run_plan_id)
        return build_validation_run_plan_entity_from_gx_run_plan(build_gx_run_plan_entity(plan)) if plan is not None else None

    async def create_plan_version(self, **kwargs):
        self.last_create_version_kwargs = kwargs
        plan = self.plans[str(kwargs["run_plan_id"])]
        if "validation_artifact_selection" in kwargs:
            gx_suite_selection = {
                "selectionMode": kwargs["validation_artifact_selection"].selectionMode,
                "scopeSelector": kwargs["validation_artifact_selection"].scopeSelector.model_dump(mode="python", by_alias=False, exclude_none=True),
                "suiteRefs": [
                    {"suiteId": item.artifactId, "suiteVersion": item.artifactVersion, "engineType": item.engineType}
                    for item in kwargs["validation_artifact_selection"].artifactRefs
                ],
                "groupedExecutionPlan": (
                    kwargs["validation_artifact_selection"].groupedExecutionPlan.model_dump(mode="python", by_alias=False, exclude_none=True)
                    if kwargs["validation_artifact_selection"].groupedExecutionPlan is not None
                    else None
                ),
            }
        else:
            gx_suite_selection = (
                kwargs["gx_suite_selection"].model_dump(mode="python", by_alias=False, exclude_none=True)
                if hasattr(kwargs["gx_suite_selection"], "model_dump")
                else dict(kwargs["gx_suite_selection"])
            )
        suite_snapshot = kwargs.get("artifact_snapshot", kwargs.get("suite_snapshot"))
        suite_id = kwargs.get("artifact_id", kwargs.get("suite_id"))
        suite_version = kwargs.get("artifact_version", kwargs.get("suite_version"))
        version = {
            "runPlanVersionId": kwargs["run_plan_version_id"],
            "runPlanId": kwargs["run_plan_id"],
            "governanceState": "draft",
            "gxSuiteSelection": gx_suite_selection,
            "suiteId": suite_id,
            "suiteVersion": suite_version,
            "suiteSnapshot": suite_snapshot,
            "scheduleDefinition": kwargs["schedule_definition"],
            "executionContractSnapshot": kwargs.get("execution_contract_snapshot"),
            "validationStatus": None,
            "reviewStatus": None,
            "effectiveFrom": kwargs.get("effective_from"),
            "supersedesVersionId": kwargs.get("supersedes_version_id"),
            "createdBy": kwargs.get("created_by"),
            "createdAt": "2026-04-24T11:00:00Z",
        }
        plan["versions"].append(version)
        plan["pendingVersionId"] = kwargs["run_plan_version_id"]
        plan["pendingVersionGovernanceState"] = "draft"
        plan["updatedAt"] = "2026-04-24T11:00:00Z"
        return build_validation_run_plan_entity_from_gx_run_plan(build_gx_run_plan_entity(plan))

    async def transition_plan_version(self, **kwargs):
        self.last_transition_kwargs.append(kwargs)
        plan = self.plans[str(kwargs["run_plan_id"])]
        for version in plan["versions"]:
            if version["runPlanVersionId"] != kwargs["run_plan_version_id"]:
                continue
            version["governanceState"] = kwargs["target_state"]
            if kwargs["target_state"] == "pending_validation":
                version["validationStatus"] = "pending"
            elif kwargs["target_state"] == "pending_review":
                version["validationStatus"] = "passed"
                version["reviewStatus"] = "pending"
            elif kwargs["target_state"] == "validation_failed":
                version["validationStatus"] = "failed"
                version["reviewStatus"] = None
            elif kwargs["target_state"] == "approved_pending_activation":
                version["reviewStatus"] = "approved"
            plan["pendingVersionGovernanceState"] = kwargs["target_state"]
            plan["status"] = kwargs["target_state"]
            plan["updatedAt"] = "2026-04-24T12:00:00Z"
            return build_validation_run_plan_entity_from_gx_run_plan(build_gx_run_plan_entity(plan))
        raise AssertionError("run plan version not found")

    async def activate_plan(self, **kwargs):
        self.last_activate_kwargs = kwargs
        plan = self.plans[str(kwargs["run_plan_id"])]
        for version in plan["versions"]:
            if version["runPlanVersionId"] == kwargs["run_plan_version_id"]:
                version["governanceState"] = "active"
            elif version["governanceState"] == "active":
                version["governanceState"] = "superseded"
        plan["status"] = "active"
        plan["currentActiveVersionId"] = kwargs["run_plan_version_id"]
        plan["pendingVersionId"] = None
        plan["pendingVersionGovernanceState"] = None
        plan["activatedBy"] = kwargs.get("activated_by")
        plan["activatedAt"] = "2026-04-24T13:00:00Z"
        plan["lastDispatchedRunId"] = kwargs.get("dispatched_run_id")
        plan["updatedAt"] = "2026-04-24T13:00:00Z"
        return build_validation_run_plan_entity_from_gx_run_plan(build_gx_run_plan_entity(plan))


def test_build_gx_run_plan_validation_snapshot_types_execution_contract(
    single_suite_seed: GxRunPlanSeedEntity,
) -> None:
    version = build_gx_run_plan_version_entity(
        {
            "runPlanVersionId": "run-plan-version-1",
            "runPlanId": "run-plan-1",
            "governanceState": "draft",
            "gxSuiteSelection": {"selectionMode": "single_suite"},
            "suiteId": "gx-suite-1",
            "suiteVersion": 1,
            "suiteSnapshot": single_suite_seed.suiteSnapshot,
            "scheduleDefinition": {"scheduledAt": "2026-04-24T10:30:00+00:00"},
            "executionContractSnapshot": single_suite_seed.executionContractSnapshot,
            "createdAt": "2026-04-24T10:00:00Z",
        }
    )

    snapshot = build_gx_run_plan_version_validation_snapshot_entity(version)

    assert snapshot.executionContractSnapshot is not None
    assert snapshot.executionContractSnapshot.engineTarget == "pyspark"
    assert snapshot.executionContractSnapshot.executionShape == "single_object"
    assert isinstance(snapshot.suiteSnapshot, GxRunPlanSingleSuiteSnapshotEntity)
    assert snapshot.suiteSnapshot.suiteId == "gx-suite-1"


def test_build_grouped_gx_run_plan_validation_snapshot_types_grouped_suite_envelopes(
    single_suite_seed: GxRunPlanSeedEntity,
    grouped_scope_seed: GxRunPlanSeedEntity,
) -> None:
    version = build_gx_run_plan_version_entity(
        {
            "runPlanVersionId": "run-plan-version-1",
            "runPlanId": "run-plan-1",
            "governanceState": "draft",
            "gxSuiteSelection": grouped_scope_seed.gxSuiteSelection,
            "suiteSnapshot": grouped_scope_seed.suiteSnapshot,
            "scheduleDefinition": {"scheduledAt": "2026-04-24T10:30:00+00:00"},
            "executionContractSnapshot": grouped_scope_seed.executionContractSnapshot,
            "createdAt": "2026-04-24T10:00:00Z",
        }
    )

    snapshot = build_gx_run_plan_version_validation_snapshot_entity(version)

    assert isinstance(snapshot.suiteSnapshot, GxRunPlanGroupedSuiteSnapshotEntity)
    assert len(snapshot.groupedSuiteEnvelopes) == 1
    assert isinstance(snapshot.groupedSuiteEnvelopes[0], GxRunPlanSingleSuiteSnapshotEntity)
    assert snapshot.groupedSuiteEnvelopes[0].suiteId == "gx-suite-1"


def test_build_gx_run_plan_scope_selector_types_known_fields_and_preserves_extra() -> None:
    selector = build_gx_run_plan_scope_selector_entity(
        {
            "assignmentScope": {"dataObjectId": "do-1"},
            "workspace_id": "retail-banking",
            "selector": "all",
        }
    )

    assert selector.assignmentScope is not None
    assert selector.assignmentScope.dataObjectId == "do-1"
    assert selector.workspaceId == "retail-banking"
    assert selector.model_dump(by_alias=True)["selector"] == "all"


@pytest.mark.anyio
async def test_create_gx_run_plan_resolves_seed_and_persists_draft(
    single_suite_seed: GxRunPlanSeedEntity,
) -> None:
    repo = _RunPlanRepository()
    seen: list[ResolveGxRunPlanSeedCommand] = []

    async def resolve_seed(command: ResolveGxRunPlanSeedCommand) -> GxRunPlanSeedEntity:
        seen.append(command)
        return single_suite_seed

    result = await create_gx_run_plan(
        CreateGxRunPlanCommand(
            workspace_id="retail-banking",
            planning_mode="single_suite",
            suite_id="gx-suite-1",
            suite_version=1,
            scheduled_at=datetime(2026, 4, 24, 10, 30, tzinfo=UTC),
            created_by="user-1",
            correlation_id="corr-1",
        ),
        run_plan_repository=repo,
        seed_resolver=_SeedResolver(resolve_seed),
    )

    assert seen == [
        ResolveGxRunPlanSeedCommand(
            planning_mode="single_suite",
            suite_id="gx-suite-1",
            suite_version=1,
            data_object_id=None,
            data_object_version_id=None,
            dataset_id=None,
            data_product_id=None,
        )
    ]
    assert result.workspaceId == "retail-banking"
    assert repo.last_create_kwargs is not None
    assert repo.last_create_kwargs["artifact_id"] == "gx-suite-1"
    assert repo.last_create_kwargs["validation_artifact_selection"].artifactRefs[0].engineType == "gx"
    assert repo.last_create_kwargs["schedule_definition"].scheduledAt == "2026-04-24T10:30:00+00:00"
    assert build_gx_run_plan_suite_selection_entity(result.versions[0].gxSuiteSelection).suiteRefs[0].engineType == "gx"


@pytest.mark.anyio
async def test_create_gx_run_plan_version_supersedes_active_version_when_no_pending_branch(
    single_suite_seed: GxRunPlanSeedEntity,
) -> None:
    repo = _RunPlanRepository()
    created = await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector=single_suite_seed.scopeSelector,
        planning_mode="single_suite",
        status="active",
        created_by="user-1",
        gx_suite_selection=single_suite_seed.gxSuiteSelection,
        suite_id="gx-suite-1",
        suite_version=1,
        suite_snapshot=single_suite_seed.suiteSnapshot,
        execution_contract_snapshot=single_suite_seed.executionContractSnapshot,
        schedule_definition=GxRunPlanScheduleDefinitionEntity(scheduledAt="2026-04-24T10:30:00+00:00"),
        correlation_id="corr-1",
    )
    await repo.activate_plan(
        run_plan_id=created.runPlanId,
        run_plan_version_id=created.versions[0].runPlanVersionId,
        activated_by="user-1",
        dispatched_run_id="dispatch-1",
        correlation_id="corr-1",
    )

    async def resolve_seed(command: ResolveGxRunPlanSeedCommand) -> GxRunPlanSeedEntity:
        del command
        return single_suite_seed

    result = await create_gx_run_plan_version(
        CreateGxRunPlanVersionCommand(
            run_plan_id="run-plan-1",
            planning_mode="single_suite",
            suite_id="gx-suite-2",
            suite_version=2,
            scheduled_at=datetime(2026, 4, 25, 10, 30, tzinfo=UTC),
            created_by="user-2",
            correlation_id="corr-2",
        ),
        run_plan_repository=repo,
        seed_resolver=_SeedResolver(resolve_seed),
    )

    assert result.currentActiveVersionId == "run-plan-version-1"
    assert repo.last_create_version_kwargs is not None
    assert repo.last_create_version_kwargs["supersedes_version_id"] == "run-plan-version-1"
    assert repo.last_create_version_kwargs["validation_artifact_selection"].artifactRefs[0].engineType == "gx"
    assert build_gx_run_plan_suite_selection_entity(result.versions[-1].gxSuiteSelection).suiteRefs[0].engineType == "gx"


@pytest.mark.anyio
async def test_transition_activation_request_creates_pending_approval(
    single_suite_seed: GxRunPlanSeedEntity,
) -> None:
    repo = _RunPlanRepository()
    await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector=single_suite_seed.scopeSelector,
        planning_mode="single_suite",
        status="draft",
        created_by="user-1",
        gx_suite_selection=single_suite_seed.gxSuiteSelection,
        suite_id="gx-suite-1",
        suite_version=1,
        suite_snapshot=single_suite_seed.suiteSnapshot,
        execution_contract_snapshot=single_suite_seed.executionContractSnapshot,
        schedule_definition=GxRunPlanScheduleDefinitionEntity(scheduledAt="2026-04-24T10:30:00+00:00"),
        correlation_id="corr-1",
    )
    created_payloads: list[dict] = []

    class _ApprovalsRepository:
        def list_approvals(self, workspace_id: str | None = None, business_key: str | None = None):
            del workspace_id, business_key
            return []

        def create_approval(self, payload: dict, actor_id: str | None = None):
            created_payloads.append({"payload": dict(payload), "actor_id": actor_id})
            return build_approval_entity({"id": "approval-1", **payload, "requester_id": actor_id})

    result = await transition_gx_run_plan_version_governance_state(
        TransitionGxRunPlanVersionGovernanceStateCommand(
            run_plan_id="run-plan-1",
            run_plan_version_id="run-plan-version-1",
            target_state="activation-requested",
            updated_by="approver-1",
            effective_from=datetime(2026, 4, 26, 10, 30, tzinfo=UTC),
            correlation_id="corr-approval",
        ),
        approvals_repository=_ApprovalsRepository(),
        run_plan_repository=repo,
    )

    assert result.status == "activation-requested"
    assert created_payloads == [
        {
            "payload": {
                "rule_id": "",
                "gx_run_plan_id": "run-plan-1",
                "gx_run_plan_version_id": "run-plan-version-1",
                "request_type": "activation",
                "workspace_id": "retail-banking",
                "comments": "GX run plan version run-plan-version-1 requested activation",
                "status": "pending",
                "effective_at": "2026-04-26T10:30:00+00:00",
            },
            "actor_id": "approver-1",
        }
    ]


@pytest.mark.anyio
async def test_validate_run_plan_version_marks_failure_when_snapshot_is_invalid(
    single_suite_seed: GxRunPlanSeedEntity,
) -> None:
    repo = _RunPlanRepository()
    await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector=single_suite_seed.scopeSelector,
        planning_mode="single_suite",
        status="draft",
        created_by="user-1",
        gx_suite_selection=single_suite_seed.gxSuiteSelection,
        suite_id="gx-suite-1",
        suite_version=1,
        suite_snapshot=single_suite_seed.suiteSnapshot,
        execution_contract_snapshot=single_suite_seed.executionContractSnapshot,
        schedule_definition=GxRunPlanScheduleDefinitionEntity(scheduledAt="2026-04-24T10:30:00+00:00"),
        correlation_id="corr-1",
    )
    repo.plans["run-plan-1"]["versions"][0]["suiteSnapshot"] = {
        "suiteId": "gx-suite-1",
        "suiteVersion": 1,
    }

    result = await validate_gx_run_plan_version(
        ValidateGxRunPlanVersionCommand(
            run_plan_id="run-plan-1",
            run_plan_version_id="run-plan-version-1",
            updated_by="validator-1",
            correlation_id="corr-validate",
        ),
        run_plan_repository=repo,
    )

    assert result.validation_status == "failed"
    assert result.plan.versions[0].governanceState == "validation_failed"
    assert result.diagnostics[0].code == "invalid_suite_snapshot"
    assert [item["target_state"] for item in repo.last_transition_kwargs] == ["pending_validation", "validation_failed"]


@pytest.mark.anyio
async def test_activate_single_suite_run_plan_enqueues_dispatch_and_activates_plan(
    single_suite_seed: GxRunPlanSeedEntity,
) -> None:
    repo = _RunPlanRepository()
    await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector=single_suite_seed.scopeSelector,
        planning_mode="single_suite",
        status="approved_pending_activation",
        created_by="user-1",
        gx_suite_selection=single_suite_seed.gxSuiteSelection,
        suite_id="gx-suite-1",
        suite_version=1,
        suite_snapshot=single_suite_seed.suiteSnapshot,
        execution_contract_snapshot=single_suite_seed.executionContractSnapshot,
        schedule_definition=GxRunPlanScheduleDefinitionEntity(scheduledAt="2026-04-24T10:30:00+00:00"),
        correlation_id="corr-1",
    )
    repo.plans["run-plan-1"]["versions"][0]["governanceState"] = "approved_pending_activation"

    captured: list[dict] = []

    async def enqueue_scheduled_suite_run(request: ActivateScheduledSuiteRunRequest) -> dict:
        captured.append(
            {
                "suite": request.suite,
                "scheduled_at": request.scheduled_at,
                "requested_by": request.requested_by,
                "status_source": request.status_source,
                "status_reason": request.status_reason,
                "run_plan_id": request.run_plan_id,
                "run_plan_version_id": request.run_plan_version_id,
            }
        )
        return {
            "queue_message_id": "dispatch-1",
            "queue_key": "dq-gx:execution-dispatch",
            "dispatch_mode": "queued",
            "engine_type": request.suite.executionContract.engineType,
            "correlation_id": "corr-activate",
        }

    result = await activate_gx_run_plan_version(
        ActivateGxRunPlanVersionCommand(
            run_plan_id="run-plan-1",
            run_plan_version_id="run-plan-version-1",
            activated_by="user-2",
            correlation_id="corr-activate",
        ),
        run_plan_repository=repo,
        dispatcher=_ActivationDispatcher(enqueue_scheduled_suite_run=enqueue_scheduled_suite_run),
    )

    assert isinstance(result, GxRunPlanActivationResult)
    assert result.plan.status == "active"
    assert result.dispatch.queueMessageId == "dispatch-1"
    assert result.dispatch.engineType == "gx"
    assert captured[0]["status_source"] == "gx.run_plan.activate"
    assert captured[0]["run_plan_id"] == "run-plan-1"
    assert captured[0]["run_plan_version_id"] == "run-plan-version-1"
    assert captured[0]["suite"].suiteId == "gx-suite-1"
    assert captured[0]["suite"].executionContract is not None
    assert captured[0]["suite"].executionContract.engineType == "gx"
    assert repo.last_activate_kwargs is not None
    assert repo.last_activate_kwargs["dispatched_run_id"] == "dispatch-1"


@pytest.mark.anyio
async def test_activate_grouped_scope_run_plan_enqueues_grouped_dispatch(
    grouped_scope_seed: GxRunPlanSeedEntity,
) -> None:
    repo = _RunPlanRepository()
    await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector={"dataObjectVersionId": "dov-1"},
        planning_mode="grouped_scope",
        status="approved_pending_activation",
        created_by="user-1",
        gx_suite_selection=grouped_scope_seed.gxSuiteSelection,
        suite_id=None,
        suite_version=None,
        suite_snapshot=grouped_scope_seed.suiteSnapshot,
        execution_contract_snapshot=grouped_scope_seed.executionContractSnapshot,
        schedule_definition=GxRunPlanScheduleDefinitionEntity(scheduledAt="2026-04-24T10:30:00+00:00"),
        correlation_id="corr-1",
    )
    repo.plans["run-plan-1"]["versions"][0]["governanceState"] = "approved_pending_activation"

    captured: dict[str, object] = {}

    async def enqueue_grouped_scope_run(request: ActivateGroupedScopeRunRequest) -> dict:
        captured["request"] = request
        return {
            "queue_message_id": "dispatch-grouped-1",
            "queue_key": "dq-gx:execution-dispatch",
            "dispatch_mode": "queued",
            "engine_type": "gx",
            "execution_shape": "grouped_scope",
            "correlation_id": "corr-grouped",
            "grouped_execution_plan": request.grouped_execution_plan,
            "scope_selector": request.scope_selector,
            "suite_refs": request.suite_refs,
            "scheduled_at": request.scheduled_at,
            "requested_by": request.requested_by,
        }

    result = await activate_gx_run_plan_version(
        ActivateGxRunPlanVersionCommand(
            run_plan_id="run-plan-1",
            run_plan_version_id="run-plan-version-1",
            activated_by="user-2",
            correlation_id="corr-grouped",
        ),
        run_plan_repository=repo,
        dispatcher=_ActivationDispatcher(enqueue_grouped_scope_run=enqueue_grouped_scope_run),
    )

    assert result.plan.status == "active"
    assert result.dispatch.executionShape == "grouped_scope"
    assert captured["request"].suite_refs[0]["engineType"] == "gx"
    assert captured["request"].run_plan_id == "run-plan-1"
    assert captured["request"].run_plan_version_id == "run-plan-version-1"
    assert (result.dispatch.suiteRefs[0].get("engineType") or result.dispatch.suiteRefs[0].get("engine_type")) == "gx"
    assert repo.last_activate_kwargs is not None
    assert repo.last_activate_kwargs["dispatched_run_id"] == "dispatch-grouped-1"


@pytest.mark.anyio
async def test_activate_run_plan_version_rejects_invalid_state(
    single_suite_seed: GxRunPlanSeedEntity,
) -> None:
    repo = _RunPlanRepository()
    await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector=single_suite_seed.scopeSelector,
        planning_mode="single_suite",
        status="draft",
        created_by="user-1",
        gx_suite_selection=single_suite_seed.gxSuiteSelection,
        suite_id="gx-suite-1",
        suite_version=1,
        suite_snapshot=single_suite_seed.suiteSnapshot,
        execution_contract_snapshot=single_suite_seed.executionContractSnapshot,
        schedule_definition=GxRunPlanScheduleDefinitionEntity(scheduledAt="2026-04-24T10:30:00+00:00"),
        correlation_id="corr-1",
    )

    with pytest.raises(HTTPException) as exc_info:
        await activate_gx_run_plan_version(
            ActivateGxRunPlanVersionCommand(
                run_plan_id="run-plan-1",
                run_plan_version_id="run-plan-version-1",
                activated_by="user-2",
                correlation_id="corr-activate",
            ),
            run_plan_repository=repo,
            dispatcher=_ActivationDispatcher(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "invalid_run_plan_state"


@pytest.mark.anyio
async def test_activate_run_plan_version_rejects_invalid_single_suite_snapshot(
    single_suite_seed: GxRunPlanSeedEntity,
) -> None:
    repo = _RunPlanRepository()
    await repo.create_plan(
        run_plan_id="run-plan-1",
        run_plan_version_id="run-plan-version-1",
        workspace_id="retail-banking",
        scope_selector=single_suite_seed.scopeSelector,
        planning_mode="single_suite",
        status="approved_pending_activation",
        created_by="user-1",
        gx_suite_selection=single_suite_seed.gxSuiteSelection,
        suite_id="gx-suite-1",
        suite_version=1,
        suite_snapshot={"suiteId": "gx-suite-1", "suiteVersion": 1},
        execution_contract_snapshot=single_suite_seed.executionContractSnapshot,
        schedule_definition=GxRunPlanScheduleDefinitionEntity(scheduledAt="2026-04-24T10:30:00+00:00"),
        correlation_id="corr-1",
    )
    repo.plans["run-plan-1"]["versions"][0]["governanceState"] = "approved_pending_activation"

    with pytest.raises(HTTPException) as exc_info:
        await activate_gx_run_plan_version(
            ActivateGxRunPlanVersionCommand(
                run_plan_id="run-plan-1",
                run_plan_version_id="run-plan-version-1",
                activated_by="user-2",
                correlation_id="corr-activate",
            ),
            run_plan_repository=repo,
            dispatcher=_ActivationDispatcher(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "invalid_suite_snapshot"