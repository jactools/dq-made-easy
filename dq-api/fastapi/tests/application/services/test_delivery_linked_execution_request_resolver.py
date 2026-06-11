from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.application.services.delivery_linked_execution_request_resolver as resolver_module
from app.application.services.delivery_linked_execution_request_resolver import DeliveryLinkedExecutionRequestError
from app.application.services.delivery_linked_execution_request_resolver import DeliveryLinkedExecutionRequestResolver
from app.domain.entities import build_validation_artifact_envelope_entity
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities import GxArtifactAssignmentScopeEntity
from app.domain.entities import GxArtifactCompiledFromEntity
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import GxArtifactExecutionHintsEntity
from app.domain.entities import GxArtifactResolvedExecutionScopeEntity
from app.domain.entities import ValidationRunPlanEntity


class Note(SimpleNamespace):
    def model_dump(self) -> dict[str, object]:
        return {
            "data_delivery_id": getattr(self, "data_delivery_id", "del-31"),
            "data_object_version_id": getattr(self, "data_object_version_id", None),
            "delivery_location": getattr(self, "delivery_location", None),
        }


class FakeCatalogRepository:
    def __init__(self, note: object | None) -> None:
        self._note = note

    def get_data_delivery_note(self, delivery_id: str) -> object | None:
        del delivery_id
        return self._note


class FakeArtifactRepository:
    def __init__(self, rows: list[object] | None = None, artifact_row: object | None = None) -> None:
        self._rows = rows or []
        self._artifact_row = artifact_row

    async def list_artifacts(self, **kwargs) -> list[object]:
        del kwargs
        return list(self._rows)

    async def get_artifact_by_id(self, **kwargs) -> object | None:
        del kwargs
        return self._artifact_row


class FakeRunPlanRepository:
    def __init__(self, rows: list[object] | None = None, plan_row: dict[str, object] | None = None) -> None:
        self._rows = rows or []
        self._plan_row = plan_row

    async def list_plans(self, **kwargs) -> list[object]:
        del kwargs
        return list(self._rows)

    async def get_plan(self, run_plan_id: str) -> dict[str, object] | None:
        del run_plan_id
        return self._plan_row


def _artifact_payload(
    *,
    artifact_id: str = "suite-a",
    artifact_version: int = 1,
    data_object_version_ids: list[str] | None = None,
    engine_type: str = "gx",
) -> dict[str, object]:
    return _artifact_entity(
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        data_object_version_ids=data_object_version_ids,
        engine_type=engine_type,
    ).model_dump(by_alias=False, exclude_none=True)


def _gx_suite_entity(
    *,
    artifact_id: str = "suite-a",
    artifact_version: int = 1,
    data_object_version_ids: list[str] | None = None,
) -> GxArtifactEnvelopeEntity:
    return GxArtifactEnvelopeEntity(
        suiteId=artifact_id,
        suiteVersion=artifact_version,
        artifactVersion="v1",
        assignmentScope=GxArtifactAssignmentScopeEntity(dataObjectId="do-1"),
        resolvedExecutionScope=GxArtifactResolvedExecutionScopeEntity(
            dataObjectVersionIds=list(data_object_version_ids or ["dov-1"])
        ),
        gxSuite={"expectation_suite_name": artifact_id, "expectations": [], "meta": {}},
        compiledFrom=GxArtifactCompiledFromEntity(
            ruleIds=["rule-1"],
            compilerVersion="dq-compiler-7.3",
            generatedAt="2026-04-25T00:00:00Z",
        ),
        executionHints=GxArtifactExecutionHintsEntity(recommendedEngine="pyspark", primaryKeyFields=["id"]),
    )


def _artifact_entity(**kwargs):
    engine_type = kwargs.get("engine_type", "gx")
    if engine_type == "gx":
        return build_validation_artifact_envelope_from_gx_artifact(
            _gx_suite_entity(
                artifact_id=kwargs.get("artifact_id", "suite-a"),
                artifact_version=kwargs.get("artifact_version", 1),
                data_object_version_ids=kwargs.get("data_object_version_ids"),
            )
        )
    return build_validation_artifact_envelope_entity(
        {
            "validationArtifactId": kwargs.get("artifact_id", "suite-a"),
            "validationArtifactVersion": kwargs.get("artifact_version", 1),
            "artifactContractVersion": "v1",
            "engineType": engine_type,
            "resolvedExecutionScope": {"dataObjectVersionIds": list(kwargs.get("data_object_version_ids") or ["dov-1"])},
            "engineArtifact": {
                "engineType": engine_type,
                "artifactKind": "scan",
                "artifactSchemaVersion": "v1",
                "payload": {"scan_name": kwargs.get("artifact_id", "suite-a")},
            },
        }
    )


def _run_plan_payload(
    *,
    run_plan_id: str,
    version_id: str,
    artifact_id: str,
    artifact_version: int,
    planning_mode: str = "single_suite",
    governance_state: str = "active",
    engine_type: str = "gx",
    scope_selector: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "runPlanId": run_plan_id,
        "workspaceId": "ws-1",
        "planningMode": planning_mode,
        "currentActiveVersionId": version_id,
        "status": "active",
        "scopeSelector": dict(scope_selector or {}),
        "createdAt": "2026-04-26T00:00:00Z",
        "updatedAt": "2026-04-26T00:00:00Z",
        "versions": [
            {
                "runPlanVersionId": version_id,
                "runPlanId": run_plan_id,
                "governanceState": governance_state,
                "artifactId": artifact_id,
                "artifactVersion": artifact_version,
                "artifactSnapshot": _artifact_payload(
                    artifact_id=artifact_id,
                    artifact_version=artifact_version,
                    engine_type=engine_type,
                ),
                "validationArtifactSelection": {},
                "scheduleDefinition": {},
                "createdAt": "2026-04-26T00:00:00Z",
            }
        ],
    }


@pytest.fixture
def failure_reasons(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    reasons: list[str] = []
    monkeypatch.setattr(
        resolver_module,
        "increment_gx_failure",
        lambda *, surface, operation, reason: reasons.append(f"{surface}:{operation}:{reason}"),
    )
    return reasons


def _resolver(
    *,
    note: object | None = None,
    artifact_rows: list[object] | None = None,
    artifact_row: object | None = None,
    plan_rows: list[object] | None = None,
    plan_row: dict[str, object] | None = None,
) -> DeliveryLinkedExecutionRequestResolver:
    return DeliveryLinkedExecutionRequestResolver(
        catalog_repository=FakeCatalogRepository(note),
        validation_artifact_repository=FakeArtifactRepository(rows=artifact_rows, artifact_row=artifact_row),
        validation_run_plan_repository=FakeRunPlanRepository(rows=plan_rows, plan_row=plan_row),
    )


def test_helper_methods_cover_text_row_value_and_candidate_selection() -> None:
    mapping_row = {"field": "value-from-mapping"}
    object_row = SimpleNamespace(field="value-from-object")
    suite_v1 = _artifact_entity(artifact_id="suite-a", artifact_version=1)
    suite_v2 = _artifact_entity(artifact_id="suite-a", artifact_version=2)
    run_plan = {
        "run_plan_id": "plan-a",
        "active_version": {"run_plan_version_id": "v2"},
    }

    assert DeliveryLinkedExecutionRequestResolver._text("  abc  ") == "abc"
    assert DeliveryLinkedExecutionRequestResolver._row_value(mapping_row, "field") == "value-from-mapping"
    assert DeliveryLinkedExecutionRequestResolver._row_value(object_row, "field") == "value-from-object"
    assert DeliveryLinkedExecutionRequestResolver._active_run_plan_version(
        SimpleNamespace(currentActiveVersionId="", versions=[])
    ) is None
    assert DeliveryLinkedExecutionRequestResolver._active_run_plan_version(
        SimpleNamespace(
            currentActiveVersionId="rv-2",
            versions=[SimpleNamespace(runPlanVersionId="rv-1"), SimpleNamespace(runPlanVersionId="rv-2")],
        )
    ).runPlanVersionId == "rv-2"
    assert DeliveryLinkedExecutionRequestResolver._select_suite_candidate(
        applicable_suites=[suite_v1, suite_v2],
        suite_id="suite-a",
        suite_version=None,
    ) is suite_v2
    assert DeliveryLinkedExecutionRequestResolver._select_suite_candidate(
        applicable_suites=[suite_v1],
        suite_id="suite-a",
        suite_version=9,
    ) is None
    assert DeliveryLinkedExecutionRequestResolver._select_run_plan_candidate(
        applicable_run_plans=[run_plan],
        run_plan_id="plan-a",
        run_plan_version_id="v2",
    ) == run_plan
    assert DeliveryLinkedExecutionRequestResolver._select_run_plan_candidate(
        applicable_run_plans=[run_plan],
        run_plan_id="plan-a",
        run_plan_version_id="missing",
    ) is None


@pytest.mark.anyio
async def test_resolve_applicable_gx_suites_rejects_invalid_envelope(
    failure_reasons: list[str],
) -> None:
    resolver = _resolver(note=Note(data_object_version_id="dov-1", delivery_location="s3://bucket/path"), artifact_rows=[{}])

    with pytest.raises(DeliveryLinkedExecutionRequestError, match="GX suite envelope is invalid") as error:
        await resolver._resolve_applicable_gx_suites(data_object_version_id="dov-1")

    assert error.value.reason == "invalid_gx_suite_envelope"
    assert failure_reasons == ["data_catalog:submit_delivery_linked_execution:invalid_gx_suite_envelope"]


@pytest.mark.anyio
async def test_resolve_applicable_run_plans_filters_grouped_scope_suite_refs_and_invalid_rows(
    monkeypatch: pytest.MonkeyPatch,
    failure_reasons: list[str],
) -> None:
    grouped_mismatch = _run_plan_payload(
        run_plan_id="plan-mismatch",
        version_id="rv-1",
        artifact_id="suite-a",
        artifact_version=1,
        planning_mode="grouped_scope",
        scope_selector={"dataObjectVersionId": "other-dov"},
    )
    grouped_match = _run_plan_payload(
        run_plan_id="plan-grouped",
        version_id="rv-2",
        artifact_id="suite-a",
        artifact_version=1,
        planning_mode="grouped_scope",
        scope_selector={"dataObjectVersionId": "dov-1"},
    )
    grouped_non_gx = _run_plan_payload(
        run_plan_id="plan-grouped-soda",
        version_id="rv-2b",
        artifact_id="suite-a",
        artifact_version=1,
        planning_mode="grouped_scope",
        engine_type="soda",
        scope_selector={"dataObjectVersionId": "dov-1"},
    )
    suite_ref_mismatch = _run_plan_payload(
        run_plan_id="plan-unrelated",
        version_id="rv-3",
        artifact_id="suite-z",
        artifact_version=9,
    )
    suite_ref_match = _run_plan_payload(
        run_plan_id="plan-suite",
        version_id="rv-4",
        artifact_id="suite-a",
        artifact_version=1,
    )
    inactive_version = _run_plan_payload(
        run_plan_id="plan-draft",
        version_id="rv-5",
        artifact_id="suite-a",
        artifact_version=1,
        governance_state="draft",
    )
    no_active_version = {
        "runPlanId": "plan-no-active",
        "workspaceId": "ws-1",
        "planningMode": "single_suite",
        "currentActiveVersionId": "",
        "status": "active",
        "scopeSelector": {},
        "createdAt": "2026-04-26T00:00:00Z",
        "updatedAt": "2026-04-26T00:00:00Z",
        "versions": [],
    }

    resolver = _resolver(
        note=Note(data_object_version_id="dov-1", delivery_location="s3://bucket/path"),
        plan_rows=[grouped_mismatch, grouped_match, grouped_non_gx, suite_ref_mismatch, suite_ref_match, inactive_version, no_active_version],
    )

    plans = await resolver._resolve_applicable_run_plans(
        data_object_version_id="dov-1",
        applicable_suites=[_artifact_entity(artifact_id="suite-a", artifact_version=1)],
    )

    assert [item["run_plan_id"] for item in plans] == ["plan-grouped", "plan-suite"]
    assert plans[0]["active_version"]["engine_type"] == "gx"
    assert failure_reasons == []

    invalid_resolver = _resolver(
        note=Note(data_object_version_id="dov-1", delivery_location="s3://bucket/path"),
        plan_rows=[{}],
    )
    try:
        ValidationRunPlanEntity.model_validate({"versions": "invalid"})
    except ValidationError as exc:
        validation_error = exc
    monkeypatch.setattr(invalid_resolver, "_coerce_run_plan", lambda row: (_ for _ in ()).throw(validation_error))
    with pytest.raises(DeliveryLinkedExecutionRequestError, match="GX run plan envelope is invalid") as error:
        await invalid_resolver._resolve_applicable_run_plans(
            data_object_version_id="dov-1",
            applicable_suites=[_artifact_entity(artifact_id="suite-a", artifact_version=1)],
        )
    assert error.value.reason == "invalid_run_plan_envelope"


@pytest.mark.anyio
async def test_resolve_submission_rejects_missing_delivery_fields_and_invalid_selector_type(
    monkeypatch: pytest.MonkeyPatch,
    failure_reasons: list[str],
) -> None:
    missing_delivery_id = _resolver(note=None)
    with pytest.raises(DeliveryLinkedExecutionRequestError, match="data_delivery_id is required") as error:
        await missing_delivery_id.resolve_submission(data_delivery_id="   ")
    assert error.value.reason == "missing_data_delivery_id"

    missing_object_version = _resolver(note=Note(data_object_version_id="", delivery_location="s3://bucket/path"))
    with pytest.raises(DeliveryLinkedExecutionRequestError, match="does not define data_object_version_id") as error:
        await missing_object_version.resolve_submission(data_delivery_id="del-31")
    assert error.value.reason == "missing_data_object_version_id"

    missing_delivery_location = _resolver(note=Note(data_object_version_id="dov-1", delivery_location=""))
    with pytest.raises(DeliveryLinkedExecutionRequestError, match="does not define delivery_location") as error:
        await missing_delivery_location.resolve_submission(data_delivery_id="del-31")
    assert error.value.reason == "missing_delivery_location"

    resolver = _resolver(note=Note(data_object_version_id="dov-1", delivery_location="s3://bucket/path"))

    async def _fake_suites(*, data_object_version_id: str):
        del data_object_version_id
        return [_artifact_entity(artifact_id="suite-a", artifact_version=2)]

    async def _fake_run_plans(*, data_object_version_id: str, applicable_suites: list[object]):
        del data_object_version_id, applicable_suites
        return []

    class _FakePlanner:
        async def build_plan(self, applicable_suites: list[object]) -> dict[str, object]:
            assert len(applicable_suites) == 1
            assert isinstance(applicable_suites[0], resolver_module.ValidationArtifactEnvelopeEntity)
            return {"suiteCount": 1, "batchCount": 1}

    monkeypatch.setattr(resolver, "_resolve_applicable_gx_suites", _fake_suites)
    monkeypatch.setattr(resolver, "_resolve_applicable_run_plans", _fake_run_plans)
    monkeypatch.setattr(resolver_module, "GroupedExecutionPlanner", lambda: _FakePlanner())
    monkeypatch.setattr(
        resolver_module,
        "build_gx_grouped_execution_plan_entity",
        lambda payload: SimpleNamespace(model_dump=lambda exclude_none=True: dict(payload)),
    )

    with pytest.raises(DeliveryLinkedExecutionRequestError, match="is not supported") as error:
        await resolver.resolve_submission(
            data_delivery_id="del-31",
            execution_selector={"selector_type": "unsupported"},
        )
    assert error.value.reason == "invalid_execution_selector_type"
    assert failure_reasons[-1] == "data_catalog:submit_delivery_linked_execution:invalid_execution_selector_type"


@pytest.mark.anyio
async def test_resolve_submission_threads_engine_type_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = _resolver(note=Note(data_object_version_id="dov-1", delivery_location="s3://bucket/path"))

    async def _fake_suites(*, data_object_version_id: str):
        del data_object_version_id
        return [_artifact_entity(artifact_id="suite-a", artifact_version=2)]

    async def _fake_run_plans(*, data_object_version_id: str, applicable_suites: list[object]):
        del data_object_version_id, applicable_suites
        return [
            {
                "run_plan_id": "plan-a",
                "workspace_id": "ws-1",
                "planning_mode": "single_suite",
                "status": "active",
                "scope_selector": {},
                "current_active_version_id": "rv-1",
                "active_version": {
                    "run_plan_version_id": "rv-1",
                    "governance_state": "active",
                    "engine_type": "gx",
                    "suite_id": "suite-a",
                    "suite_version": 2,
                },
            }
        ]

    class _FakePlanner:
        async def build_plan(self, applicable_suites: list[object]) -> dict[str, object]:
            assert len(applicable_suites) == 1
            assert isinstance(applicable_suites[0], resolver_module.ValidationArtifactEnvelopeEntity)
            return {"suiteCount": 1, "batchCount": 1}

    monkeypatch.setattr(resolver, "_resolve_applicable_gx_suites", _fake_suites)
    monkeypatch.setattr(resolver, "_resolve_applicable_run_plans", _fake_run_plans)
    monkeypatch.setattr(resolver_module, "GroupedExecutionPlanner", lambda: _FakePlanner())
    monkeypatch.setattr(
        resolver_module,
        "build_gx_grouped_execution_plan_entity",
        lambda payload: SimpleNamespace(model_dump=lambda exclude_none=True: dict(payload)),
    )

    result = await resolver.resolve_submission(data_delivery_id="del-31")

    assert result["resolved_engine_type"] == "gx"
    assert result["execution_resolution"]["applicable_gx_suites"][0]["engine_type"] == "gx"
    assert result["execution_resolution"]["applicable_run_plans"][0]["active_version"]["engine_type"] == "gx"


@pytest.mark.anyio
async def test_resolve_gx_suite_selector_rejects_missing_or_unknown_suite(
    failure_reasons: list[str],
) -> None:
    resolver = _resolver(
        note=Note(data_object_version_id="dov-1", delivery_location="s3://bucket/path"),
        artifact_row=None,
    )

    with pytest.raises(DeliveryLinkedExecutionRequestError, match="gx_suite_id is required") as error:
        await resolver._resolve_gx_suite_selector(
            applicable_suites=[],
            data_object_version_id="dov-1",
            selector_payload={},
        )
    assert error.value.reason == "missing_gx_suite_id"

    with pytest.raises(DeliveryLinkedExecutionRequestError, match="not found") as error:
        await resolver._resolve_gx_suite_selector(
            applicable_suites=[],
            data_object_version_id="dov-1",
            selector_payload={"gx_suite_id": "suite-missing", "suite_version": 3},
        )
    assert error.value.reason == "gx_suite_not_found"
    assert error.value.status_code == 404
    assert failure_reasons[-1] == "data_catalog:submit_delivery_linked_execution:gx_suite_not_found"


@pytest.mark.anyio
async def test_resolve_run_plan_selector_rejects_missing_unknown_version_missing_and_not_applicable(
    failure_reasons: list[str],
) -> None:
    resolver = _resolver(
        note=Note(data_object_version_id="dov-1", delivery_location="s3://bucket/path"),
        plan_row=None,
    )

    with pytest.raises(DeliveryLinkedExecutionRequestError, match="run_plan_id is required") as error:
        await resolver._resolve_run_plan_selector(
            applicable_run_plans=[],
            data_object_version_id="dov-1",
            selector_payload={},
        )
    assert error.value.reason == "missing_run_plan_id"

    with pytest.raises(DeliveryLinkedExecutionRequestError, match="not found") as error:
        await resolver._resolve_run_plan_selector(
            applicable_run_plans=[],
            data_object_version_id="dov-1",
            selector_payload={"run_plan_id": "plan-missing"},
        )
    assert error.value.reason == "run_plan_not_found"
    assert error.value.status_code == 404

    version_missing_resolver = _resolver(
        note=Note(data_object_version_id="dov-1", delivery_location="s3://bucket/path"),
        plan_row={"versions": [{"runPlanVersionId": "rv-1"}]},
    )
    with pytest.raises(DeliveryLinkedExecutionRequestError, match="version 'rv-missing' not found") as error:
        await version_missing_resolver._resolve_run_plan_selector(
            applicable_run_plans=[],
            data_object_version_id="dov-1",
            selector_payload={"run_plan_id": "plan-a", "run_plan_version_id": "rv-missing"},
        )
    assert error.value.reason == "run_plan_version_not_found"
    assert error.value.status_code == 404

    not_applicable_resolver = _resolver(
        note=Note(data_object_version_id="dov-1", delivery_location="s3://bucket/path"),
        plan_row={"versions": "not-a-list"},
    )
    with pytest.raises(DeliveryLinkedExecutionRequestError, match="not applicable") as error:
        await not_applicable_resolver._resolve_run_plan_selector(
            applicable_run_plans=[],
            data_object_version_id="dov-1",
            selector_payload={"run_plan_id": "plan-a"},
        )
    assert error.value.reason == "run_plan_not_applicable"
    assert error.value.status_code == 422
    assert failure_reasons[-1] == "data_catalog:submit_delivery_linked_execution:run_plan_not_applicable"