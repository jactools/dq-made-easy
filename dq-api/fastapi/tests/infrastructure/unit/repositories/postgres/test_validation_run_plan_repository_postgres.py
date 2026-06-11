from __future__ import annotations

from datetime import datetime, timezone

import pytest

import app.infrastructure.repositories.postgres_validation_run_plan_repository as repo_module
from app.domain.entities import build_validation_run_plan_entity
from app.domain.entities import ValidationRunPlanArtifactSelectionEntity
from app.domain.entities import ValidationRunPlanArtifactRefEntity
from app.domain.entities import ValidationRunPlanScheduleDefinitionEntity
from app.domain.entities import ValidationRunPlanScopeSelectorEntity
from app.infrastructure.orm.models import ValidationRunPlanRow
from app.infrastructure.orm.models import ValidationRunPlanTransitionRow
from app.infrastructure.orm.models import ValidationRunPlanVersionRow
from app.infrastructure.repositories.postgres_validation_run_plan_repository import PostgresValidationRunPlanRepository


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return []


class _Session:
    def __init__(self, execute_results: list[object] | None = None, get_results: dict[tuple[type, str], object] | None = None) -> None:
        self._execute_results = iter(execute_results or [])
        self._get_results = dict(get_results or {})
        self.added: list[object] = []
        self.flushed = False
        self.committed = False

    def execute(self, _statement):
        return _Result(next(self._execute_results))

    def get(self, model: type, key: str):
        return self._get_results.get((model, key))

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed = True

    def commit(self) -> None:
        self.committed = True


class _Ctx:
    def __init__(self, session: _Session) -> None:
        self._session = session

    def __enter__(self) -> _Session:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _artifact_snapshot(*, artifact_id: str = "va-1", artifact_version: int = 1, engine_type: str = "gx") -> dict:
    return {
        "validationArtifactId": artifact_id,
        "validationArtifactVersion": artifact_version,
        "engineType": engine_type,
        "assignmentScope": {"dataObjectId": "do-1", "datasetId": "ds-1", "dataProductId": "prod-1"},
        "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
        "compiledFrom": {"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-04-26T10:30:00Z"},
        "executionHints": {"recommendedEngineTarget": "pyspark", "primaryKeyFields": []},
        "runPlanning": {
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "traceability": {
                "ruleId": "r-1",
                "ruleVersionId": "rv-1",
                "validationArtifactId": artifact_id,
                "validationArtifactVersion": artifact_version,
            },
        },
        "engineArtifact": {
            "engineType": engine_type,
            "artifactKind": "gx_expectation_suite" if engine_type == "gx" else "soda_scan",
            "artifactSchemaVersion": "gx-artifact-envelope/v1" if engine_type == "gx" else "soda-scan/v1",
            "payload": {"suiteId": artifact_id, "suiteVersion": artifact_version}
            if engine_type == "gx"
            else {"scanName": artifact_id, "checks": []},
        },
    }


def _plan_entity(*, run_plan_id: str, version_id: str, artifact_id: str, status: str) -> object:
    return build_validation_run_plan_entity(
        {
            "runPlanId": run_plan_id,
            "businessKey": run_plan_id,
            "workspaceId": "ws-1",
            "scopeSelector": {"dataObjectId": "do-1"},
            "planningMode": "manual",
            "status": status,
            "pendingVersionId": version_id,
            "pendingVersionGovernanceState": status,
            "createdBy": "user-a",
            "createdAt": "2026-04-26T10:30:00Z",
            "updatedAt": "2026-04-26T10:30:00Z",
            "versions": [
                {
                    "runPlanVersionId": version_id,
                    "runPlanId": run_plan_id,
                    "governanceState": status,
                    "validationArtifactSelection": {
                        "selectionMode": "explicit_refs",
                        "artifactRefs": [{"artifactId": artifact_id, "artifactVersion": 1}],
                    },
                    "artifactId": artifact_id,
                    "artifactVersion": 1,
                    "artifactSnapshot": _artifact_snapshot(artifact_id=artifact_id, engine_type="soda"),
                    "scheduleDefinition": {},
                    "createdAt": "2026-04-26T10:30:00Z",
                }
            ],
            "transitionEvents": [],
        }
    )


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_saves_non_gx_plan_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session([None])
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    async def _get_plan(_run_plan_id: str):
        return _plan_entity(run_plan_id="rp-1", version_id="v-1", artifact_id="soda-art-1", status="draft")

    monkeypatch.setattr(repository, "get_plan", _get_plan)

    plan = await repository.create_plan(
        run_plan_id="rp-1",
        run_plan_version_id="v-1",
        workspace_id="ws-1",
        scope_selector=ValidationRunPlanScopeSelectorEntity(dataObjectId="do-1"),
        planning_mode="manual",
        status="draft",
        created_by="user-a",
        validation_artifact_selection=ValidationRunPlanArtifactSelectionEntity(
            selectionMode="explicit_refs",
            artifactRefs=[ValidationRunPlanArtifactRefEntity(artifactId="soda-art-1", artifactVersion=1)],
        ),
        artifact_id="soda-art-1",
        artifact_version=1,
        artifact_snapshot=_artifact_snapshot(artifact_id="soda-art-1", engine_type="soda"),
        execution_contract_snapshot=None,
        schedule_definition=ValidationRunPlanScheduleDefinitionEntity(),
    )

    plan_row = next(obj for obj in session.added if isinstance(obj, ValidationRunPlanRow))
    version_row = next(obj for obj in session.added if isinstance(obj, ValidationRunPlanVersionRow))
    transition_row = next(obj for obj in session.added if isinstance(obj, ValidationRunPlanTransitionRow))

    assert plan.runPlanId == "rp-1"
    assert plan_row.id == "rp-1"
    assert version_row.artifact_id == "soda-art-1"
    assert version_row.validation_artifact_selection_json["artifactRefs"][0]["artifactId"] == "soda-art-1"
    assert version_row.artifact_snapshot_json["engineArtifact"]["engineType"] == "soda"
    assert transition_row.to_state == "draft"
    assert session.flushed is True
    assert session.committed is True


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_normalizes_seeded_gx_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_row = ValidationRunPlanRow(
        id="rp-gx-1",
        business_key="rp-gx-1",
        workspace_id="ws-1",
        scope_selector_json={"dataObjectId": "do-1"},
        planning_mode="manual",
        current_active_version_id=None,
        status="draft",
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        activated_by=None,
        activated_at=None,
        last_dispatched_run_id=None,
    )
    version_row = ValidationRunPlanVersionRow(
        id="rp-gx-1-v1",
        run_plan_id="rp-gx-1",
        validation_artifact_selection_json={
            "selectionMode": "explicit_refs",
            "artifactRefs": [{"artifactId": "gx_suite_1", "artifactVersion": 2}],
        },
        artifact_id="gx_suite_1",
        artifact_version=2,
        artifact_snapshot_json={
            "suiteId": "gx_suite_1",
            "suiteVersion": 2,
            "assignmentScope": {"dataObjectId": "do-1", "datasetId": "ds-1", "dataProductId": "prod-1"},
            "resolvedExecutionScope": {"dataObjectVersionIds": ["dov-1"]},
            "gxSuite": {"expectation_suite_name": "dq_suite", "expectations": [], "meta": {}},
            "compiledFrom": {"ruleIds": ["r-1"], "compilerVersion": "v1", "generatedAt": "2026-04-26T10:30:00Z"},
            "executionHints": {"recommendedEngineTarget": "pyspark", "primaryKeyFields": []},
            "executionContract": {
                "engineTarget": "pyspark",
                "executionShape": "single_object",
                "traceability": {
                    "ruleId": "r-1",
                    "ruleVersionId": "rv-1",
                    "gxSuiteId": "gx_suite_1",
                    "gxSuiteVersion": 2,
                    "dataObjectVersionId": "dov-1",
                },
            },
        },
        execution_contract_snapshot_json={"engineTarget": "pyspark", "executionShape": "single_object"},
        schedule_definition_json={"scheduledAt": "2026-04-26T10:30:00Z"},
        governance_state="draft",
        validation_status="not_requested",
        review_status=None,
        effective_from=None,
        supersedes_version_id=None,
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
    )
    session = _Session([[version_row], []], {(ValidationRunPlanRow, "rp-gx-1"): plan_row})
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    loaded = await repository.get_plan("rp-gx-1")

    assert loaded is not None
    assert loaded.versions[0].artifactId == "gx_suite_1"
    assert loaded.versions[0].artifactSnapshot["validationArtifactId"] == "gx_suite_1"
    assert loaded.versions[0].artifactSnapshot["engineType"] == "gx"


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_transition_updates_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_row = ValidationRunPlanRow(
        id="rp-1",
        business_key="rp-1",
        workspace_id="ws-1",
        scope_selector_json={"dataObjectId": "do-1"},
        planning_mode="manual",
        current_active_version_id=None,
        status="draft",
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        activated_by=None,
        activated_at=None,
        last_dispatched_run_id=None,
    )
    version_row = ValidationRunPlanVersionRow(
        id="v-1",
        run_plan_id="rp-1",
        validation_artifact_selection_json={"selectionMode": "explicit_refs", "artifactRefs": []},
        artifact_id="gx_suite_1",
        artifact_version=1,
        artifact_snapshot_json=_artifact_snapshot(),
        execution_contract_snapshot_json=None,
        schedule_definition_json={},
        governance_state="draft",
        validation_status="not_requested",
        review_status=None,
        effective_from=None,
        supersedes_version_id=None,
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
    )
    session = _Session([], {(ValidationRunPlanRow, "rp-1"): plan_row, (ValidationRunPlanVersionRow, "v-1"): version_row})
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    async def _get_plan(_run_plan_id: str):
        return _plan_entity(run_plan_id="rp-1", version_id="v-1", artifact_id="gx_suite_1", status="pending_validation")

    monkeypatch.setattr(repository, "get_plan", _get_plan)

    updated = await repository.transition_plan_version(
        run_plan_id="rp-1",
        run_plan_version_id="v-1",
        target_state="pending_validation",
        updated_by="reviewer",
    )

    transition_row = next(obj for obj in session.added if isinstance(obj, ValidationRunPlanTransitionRow))
    assert updated is not None
    assert version_row.governance_state == "pending_validation"
    assert version_row.validation_status == "pending"
    assert plan_row.status == "pending_validation"
    assert transition_row.from_state == "draft"
    assert transition_row.to_state == "pending_validation"
    assert session.committed is True


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_returns_none_when_plan_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session([], {(ValidationRunPlanRow, "missing"): None})
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    assert await repository.get_plan("missing") is None


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_create_plan_version_updates_existing_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_row = ValidationRunPlanRow(
        id="rp-2",
        business_key="rp-2",
        workspace_id="ws-1",
        scope_selector_json={"dataObjectId": "do-1"},
        planning_mode="manual",
        current_active_version_id=None,
        status="draft",
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        activated_by=None,
        activated_at=None,
        last_dispatched_run_id=None,
    )
    session = _Session([], {(ValidationRunPlanRow, "rp-2"): plan_row})
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    async def _get_plan(_run_plan_id: str):
        return _plan_entity(run_plan_id="rp-2", version_id="v-2", artifact_id="gx_suite_1", status="draft")

    monkeypatch.setattr(repository, "get_plan", _get_plan)

    plan = await repository.create_plan_version(
        run_plan_id="rp-2",
        run_plan_version_id="v-2",
        validation_artifact_selection=ValidationRunPlanArtifactSelectionEntity(
            selectionMode="explicit_refs",
            artifactRefs=[ValidationRunPlanArtifactRefEntity(artifactId="gx_suite_1", artifactVersion=1)],
        ),
        artifact_id="gx_suite_1",
        artifact_version=1,
        artifact_snapshot=_artifact_snapshot(artifact_id="gx_suite_1", engine_type="gx"),
        execution_contract_snapshot=None,
        schedule_definition=ValidationRunPlanScheduleDefinitionEntity(),
        created_by="user-a",
        effective_from="2026-04-26T10:30:00Z",
        correlation_id="corr-1",
    )

    version_row = next(obj for obj in session.added if isinstance(obj, ValidationRunPlanVersionRow))
    transition_row = next(obj for obj in session.added if isinstance(obj, ValidationRunPlanTransitionRow))

    assert plan.runPlanId == "rp-2"
    assert plan_row.status == "draft"
    assert version_row.id == "v-2"
    assert version_row.validation_status == "not_requested"
    assert version_row.governance_state == "draft"
    assert transition_row.action == "version_created"
    assert session.committed is True


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_create_plan_version_raises_when_plan_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session([], {(ValidationRunPlanRow, "missing"): None})
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    with pytest.raises(ValueError, match="Validation run plan 'missing' not found"):
        await repository.create_plan_version(
            run_plan_id="missing",
            run_plan_version_id="v-1",
            validation_artifact_selection=ValidationRunPlanArtifactSelectionEntity(selectionMode="explicit_refs", artifactRefs=[]),
            artifact_id=None,
            artifact_version=None,
            artifact_snapshot=None,
            execution_contract_snapshot=None,
            schedule_definition=ValidationRunPlanScheduleDefinitionEntity(),
            created_by=None,
        )


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_list_plans_filters_by_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_row_1 = ValidationRunPlanRow(
        id="rp-1",
        business_key="rp-1",
        workspace_id="ws-1",
        scope_selector_json={"dataObjectId": "do-1"},
        planning_mode="manual",
        current_active_version_id=None,
        status="draft",
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        activated_by=None,
        activated_at=None,
        last_dispatched_run_id=None,
    )
    plan_row_2 = ValidationRunPlanRow(
        id="rp-2",
        business_key="rp-2",
        workspace_id="ws-1",
        scope_selector_json={"dataObjectId": "do-2"},
        planning_mode="manual",
        current_active_version_id=None,
        status="draft",
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 31, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 31, tzinfo=timezone.utc),
        activated_by=None,
        activated_at=None,
        last_dispatched_run_id=None,
    )
    version_row_1 = ValidationRunPlanVersionRow(
        id="rp-1-v1",
        run_plan_id="rp-1",
        validation_artifact_selection_json={"selectionMode": "explicit_refs", "artifactRefs": [{"artifactId": "gx_suite_1", "artifactVersion": 1}]},
        artifact_id="gx_suite_1",
        artifact_version=1,
        artifact_snapshot_json=_artifact_snapshot(artifact_id="gx_suite_1", engine_type="gx"),
        execution_contract_snapshot_json=None,
        schedule_definition_json={},
        governance_state="draft",
        validation_status="not_requested",
        review_status=None,
        effective_from=None,
        supersedes_version_id=None,
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
    )
    version_row_2 = ValidationRunPlanVersionRow(
        id="rp-2-v1",
        run_plan_id="rp-2",
        validation_artifact_selection_json={"selectionMode": "explicit_refs", "artifactRefs": [{"artifactId": "gx_suite_2", "artifactVersion": 1}]},
        artifact_id="gx_suite_2",
        artifact_version=1,
        artifact_snapshot_json=_artifact_snapshot(artifact_id="gx_suite_2", engine_type="gx"),
        execution_contract_snapshot_json=None,
        schedule_definition_json={},
        governance_state="draft",
        validation_status="not_requested",
        review_status=None,
        effective_from=None,
        supersedes_version_id=None,
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 31, tzinfo=timezone.utc),
    )
    transition_row = ValidationRunPlanTransitionRow(
        id="transition-1",
        run_plan_id="rp-1",
        run_plan_version_id="rp-1-v1",
        action="created",
        from_state=None,
        to_state="draft",
        actor_id="user-a",
        correlation_id="corr-1",
        effective_from=None,
        details_json={"planning_mode": "manual"},
        occurred_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
    )
    session = _Session([
        [plan_row_1, plan_row_2],
        [version_row_1, version_row_2],
        [transition_row],
    ])
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    rows = await repository.list_plans(workspace_id="ws-1", artifact_id="gx_suite_2")

    assert [row.runPlanId for row in rows] == ["rp-2"]
    assert rows[0].versions[0].artifactId == "gx_suite_2"


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_transition_rejects_invalid_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_row = ValidationRunPlanRow(
        id="rp-3",
        business_key="rp-3",
        workspace_id="ws-1",
        scope_selector_json={"dataObjectId": "do-1"},
        planning_mode="manual",
        current_active_version_id=None,
        status="draft",
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        activated_by=None,
        activated_at=None,
        last_dispatched_run_id=None,
    )
    version_row = ValidationRunPlanVersionRow(
        id="rp-3-v1",
        run_plan_id="rp-3",
        validation_artifact_selection_json={"selectionMode": "explicit_refs", "artifactRefs": []},
        artifact_id="gx_suite_1",
        artifact_version=1,
        artifact_snapshot_json=_artifact_snapshot(),
        execution_contract_snapshot_json=None,
        schedule_definition_json={},
        governance_state="draft",
        validation_status="not_requested",
        review_status=None,
        effective_from=None,
        supersedes_version_id=None,
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
    )
    session = _Session([], {(ValidationRunPlanRow, "rp-3"): plan_row, (ValidationRunPlanVersionRow, "rp-3-v1"): version_row})
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    with pytest.raises(ValueError, match="Invalid validation run plan version transition"):
        await repository.transition_plan_version(
            run_plan_id="rp-3",
            run_plan_version_id="rp-3-v1",
            target_state="bogus",
            updated_by="reviewer",
        )


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_activate_plan_supersedes_previous_active_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_row = ValidationRunPlanRow(
        id="rp-4",
        business_key="rp-4",
        workspace_id="ws-1",
        scope_selector_json={"dataObjectId": "do-1"},
        planning_mode="manual",
        current_active_version_id="rp-4-v0",
        status="pending_review",
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        activated_by=None,
        activated_at=None,
        last_dispatched_run_id=None,
    )
    current_version = ValidationRunPlanVersionRow(
        id="rp-4-v1",
        run_plan_id="rp-4",
        validation_artifact_selection_json={"selectionMode": "explicit_refs", "artifactRefs": []},
        artifact_id="gx_suite_1",
        artifact_version=1,
        artifact_snapshot_json=_artifact_snapshot(),
        execution_contract_snapshot_json=None,
        schedule_definition_json={},
        governance_state="approved_pending_activation",
        validation_status="passed",
        review_status="approved",
        effective_from=None,
        supersedes_version_id=None,
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
    )
    previous_version = ValidationRunPlanVersionRow(
        id="rp-4-v0",
        run_plan_id="rp-4",
        validation_artifact_selection_json={"selectionMode": "explicit_refs", "artifactRefs": []},
        artifact_id="gx_suite_0",
        artifact_version=1,
        artifact_snapshot_json=_artifact_snapshot(artifact_id="gx_suite_0", engine_type="gx"),
        execution_contract_snapshot_json=None,
        schedule_definition_json={},
        governance_state="active",
        validation_status="passed",
        review_status="approved",
        effective_from=None,
        supersedes_version_id=None,
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 29, tzinfo=timezone.utc),
    )
    session = _Session([], {(ValidationRunPlanRow, "rp-4"): plan_row, (ValidationRunPlanVersionRow, "rp-4-v1"): current_version, (ValidationRunPlanVersionRow, "rp-4-v0"): previous_version})
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    async def _get_plan(_run_plan_id: str):
        return _plan_entity(run_plan_id="rp-4", version_id="rp-4-v1", artifact_id="gx_suite_1", status="active")

    monkeypatch.setattr(repository, "get_plan", _get_plan)

    plan = await repository.activate_plan(
        run_plan_id="rp-4",
        run_plan_version_id="rp-4-v1",
        activated_by="reviewer",
        dispatched_run_id="run-1",
    )

    superseded_row = next(obj for obj in session.added if isinstance(obj, ValidationRunPlanTransitionRow) and obj.action == "superseded")
    activated_row = next(obj for obj in session.added if isinstance(obj, ValidationRunPlanTransitionRow) and obj.action == "activated")

    assert plan.runPlanId == "rp-4"
    assert plan_row.current_active_version_id == "rp-4-v1"
    assert previous_version.governance_state == "superseded"
    assert activated_row.to_state == "active"
    assert superseded_row.to_state == "superseded"
    assert session.committed is True


@pytest.mark.anyio
async def test_postgres_validation_run_plan_repository_deactivate_plan_clears_active_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_row = ValidationRunPlanRow(
        id="rp-5",
        business_key="rp-5",
        workspace_id="ws-1",
        scope_selector_json={"dataObjectId": "do-1"},
        planning_mode="manual",
        current_active_version_id="rp-5-v1",
        status="active",
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
        activated_by=None,
        activated_at=None,
        last_dispatched_run_id=None,
    )
    version_row = ValidationRunPlanVersionRow(
        id="rp-5-v1",
        run_plan_id="rp-5",
        validation_artifact_selection_json={"selectionMode": "explicit_refs", "artifactRefs": []},
        artifact_id="gx_suite_1",
        artifact_version=1,
        artifact_snapshot_json=_artifact_snapshot(),
        execution_contract_snapshot_json=None,
        schedule_definition_json={},
        governance_state="deactivation-requested",
        validation_status="passed",
        review_status="approved",
        effective_from=None,
        supersedes_version_id=None,
        created_by="user-a",
        created_at=datetime(2026, 4, 26, 10, 30, tzinfo=timezone.utc),
    )
    session = _Session([], {(ValidationRunPlanRow, "rp-5"): plan_row, (ValidationRunPlanVersionRow, "rp-5-v1"): version_row})
    monkeypatch.setattr(repo_module, "session_scope", lambda _dsn: _Ctx(session))
    repository = PostgresValidationRunPlanRepository("postgresql://unused")

    async def _get_plan(_run_plan_id: str):
        return _plan_entity(run_plan_id="rp-5", version_id="rp-5-v1", artifact_id="gx_suite_1", status="deactivated")

    monkeypatch.setattr(repository, "get_plan", _get_plan)

    plan = await repository.deactivate_plan(
        run_plan_id="rp-5",
        run_plan_version_id="rp-5-v1",
        deactivated_by="reviewer",
    )

    transition_row = next(obj for obj in session.added if isinstance(obj, ValidationRunPlanTransitionRow))

    assert plan.runPlanId == "rp-5"
    assert plan_row.current_active_version_id is None
    assert version_row.governance_state == "deactivated"
    assert transition_row.to_state == "deactivated"
    assert session.committed is True