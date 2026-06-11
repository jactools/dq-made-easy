from __future__ import annotations

import importlib
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.endpoints import admin as admin_endpoints
from app.api.v1.endpoints import app_config as app_config_endpoints
from app.api.v1.endpoints import approvals as approvals_endpoints
from app.api.v1.endpoints import data_catalog as data_catalog_endpoints
from app.api.v1.endpoints import rules as rules_endpoints
from app.api.v1.endpoints import system as system_endpoints
from app.api.v1.endpoints import testing as testing_endpoints
from app.api.v1.endpoints import workspaces as workspaces_endpoints
from app.api.v1 import testing_api as testing_bundles
from app.domain.entities import rule_testing_context as testing_context
from app.domain.entities.admin import AdminUserEntity
from app.domain.entities.app_config import AppConfigEntity
from app.domain.entities.approvals import ApprovalEntity
from app.domain.entities.data_catalog import DataProductEntity
from app.domain.entities.testing import BatchTestRequestEntity
from app.domain.entities.testing import BatchTestRunResultEntity
from app.domain.entities.testing import StoreTestProofResultEntity as ProofResultEntity
from app.domain.entities.testing import TestProofEntity as ProofEntity
from app.domain.entities.testing import TestRunResultEntity as RunResultEntity
from app.domain.entities.workspaces import WorkspaceEntity


activate_rule_module = importlib.import_module("app.application.use_cases.activate_rule")


def _request_with_state(user_id: str | None = None, claims: dict | None = None) -> Request:
    request = Request({"type": "http", "method": "GET", "path": "/"})
    request.state.user_id = user_id
    request.state.auth_claims = claims or {}
    return request


@pytest.mark.anyio
async def test_admin_get_users_filters_sorts_and_paginates() -> None:
    users = [
        AdminUserEntity(id="2", first_name="Zoe", last_name="Zimmer", email="zoe@example.com", roles=["viewer"], workspaces=["w1"]),
        AdminUserEntity(id="1", first_name="Alice", last_name="Admin", email="alice@example.com", roles=["admin"], workspaces=["w1"]),
    ]
    repo = SimpleNamespace(list_users=lambda: users)

    result = await admin_endpoints.get_users(
        page=1,
        limit=1,
        q="alice",
        sort="name",
        order="asc",
        repository=repo,
    )

    assert result.pagination.total == 1
    assert result.pagination.limit == 1
    assert result.data[0].first_name == "Alice"
    assert result.data[0].last_name == "Admin"


@pytest.mark.anyio
async def test_admin_update_user_raises_400_on_value_error() -> None:
    repo = SimpleNamespace(update_user=lambda user_id, payload, max_users: (_ for _ in ()).throw(ValueError("limit")))
    config_repo = SimpleNamespace(get_app_config=lambda: AppConfigEntity(maxUsersPerWorkspace=10))

    with pytest.raises(HTTPException) as error:
        await admin_endpoints.update_user("u1", {"first_name": "A", "last_name": "Admin"}, repo, config_repo)

    assert error.value.status_code == 400


@pytest.mark.anyio
async def test_admin_get_me_raises_401_when_missing() -> None:
    repo = SimpleNamespace(get_current_user=lambda user_id, claims: None)

    with pytest.raises(HTTPException) as error:
        await admin_endpoints.get_me(_request_with_state(None, {}), repo)

    assert error.value.status_code == 401


@pytest.mark.anyio
async def test_admin_get_me_emits_custom_span(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _Span:
        def __init__(self, attrs: dict[str, object]) -> None:
            self.attrs = attrs

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

        def record_exception(self, exc: Exception) -> None:
            return None

        def set_status(self, status) -> None:
            return None

    @contextmanager
    def _fake_traced_span(name: str, **attrs: object):
        calls.append((name, dict(attrs)))
        yield _Span(calls[-1][1])

    repo = SimpleNamespace(get_current_user=lambda user_id, claims: AdminUserEntity(id="u1", first_name="Alice", last_name="Admin", email="a@example.com", roles=["admin"], workspaces=["default"]))
    monkeypatch.setattr(admin_endpoints, "traced_span", _fake_traced_span)

    result = await admin_endpoints.get_me(_request_with_state("u1", {"sub": "u1"}), repo)

    assert result.id == "u1"
    assert calls[0][0] == "admin.me.get"
    assert calls[0][1]["user_authenticated"] is True


@pytest.mark.anyio
async def test_activate_rule_emits_custom_spans(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _Span:
        def __init__(self, attrs: dict[str, object]) -> None:
            self.attrs = attrs

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

        def record_exception(self, exc: Exception) -> None:
            return None

        def set_status(self, status) -> None:
            return None

    @contextmanager
    def _fake_traced_span(name: str, **attrs: object):
        calls.append((name, dict(attrs)))
        yield _Span(calls[-1][1])

    class _Repo:
        async def list_rule_records(self, **kwargs) -> list[dict]:
            return [{"id": "rule-1", "active": False, "last_approval_status": "approved"}]

        async def activate_rule_record(self, rule_id: str):
            return SimpleNamespace(to_payload=lambda: {"id": rule_id, "active": True})

        async def get_rule_by_id(self, rule_id: str):
            return SimpleNamespace(expression="email IS NOT NULL")

        async def list_rule_versions(self, rule_id: str, limit: int = 1, offset: int = 0) -> dict:
            return {"versions": [{"id": "rv-1", "isCurrentVersion": True}]}

        async def upsert_active_compiler_artifact(self, **kwargs) -> dict:
            return {"id": "artifact-1"}

    class _ValidationArtifactRepo:
        def __init__(self) -> None:
            self.last_envelope: dict[str, object] | None = None

        async def list_artifact_status_history(self, *, artifact_id: str, artifact_version: int | None = None):
            del artifact_id, artifact_version
            return []

        async def save_artifact(self, **kwargs) -> dict:
            envelope = kwargs["envelope"]
            self.last_envelope = envelope.model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(envelope, "model_dump") else dict(envelope)
            return self.last_envelope

    class _GxSuiteRepo:
        def __init__(self) -> None:
            self.last_envelope: dict[str, object] | None = None

        async def list_suite_status_history(self, *, suite_id: str, suite_version: int | None = None):
            del suite_id, suite_version
            return []

        async def save_suite(self, **kwargs) -> dict:
            envelope = kwargs["envelope"]
            self.last_envelope = envelope.model_dump(mode="python", by_alias=False, exclude_none=False) if hasattr(envelope, "model_dump") else dict(envelope)
            return self.last_envelope

    monkeypatch.setattr(rules_endpoints, "traced_span", _fake_traced_span)
    monkeypatch.setattr(rules_endpoints.rule_autopublish_policy, "traced_span", _fake_traced_span)
    monkeypatch.setattr(rules_endpoints, "get_scopes", lambda: ["dq:rules:activate"])
    monkeypatch.setattr(
        rules_endpoints,
        "compile_rule_to_intermediate_model",
        lambda **kwargs: {
            "compilerVersion": "dq-7.3.0",
            "artifactKey": "artifact-key",
            "compilable": True,
            "filter": {"normalized": "email IS NOT NULL"},
            "diagnostics": [],
        },
    )

    gx_suite_calls: list[dict[str, object]] = []

    async def _fake_persist_validation_artifact_from_compiler(
        validation_artifact_repository,
        *,
        rule_id,
        rule_version_id,
        rule,
        catalog_repository,
        intermediate_model,
        publish_request,
        saved_by,
    ):
        del rule, catalog_repository, intermediate_model, publish_request, saved_by
        envelope = {
            "validationArtifactId": f"gx_{rule_id}",
            "validationArtifactVersion": 1,
            "engineType": "gx",
            "engineArtifact": {
                "engineType": "gx",
                "artifactKind": "expectation_suite",
                "artifactSchemaVersion": "v1",
                "payload": {},
            },
            "runPlanning": {
                "traceability": {
                    "ruleId": rule_id,
                    "ruleVersionId": rule_version_id,
                    "validationArtifactId": f"gx_{rule_id}",
                }
            },
        }
        with _fake_traced_span("rules.gx.auto_publish", endpoint_group="rules", operation="gx_auto_publish"):
            return await validation_artifact_repository.save_artifact(envelope=envelope)

    monkeypatch.setattr(
        rules_endpoints.rule_autopublish_policy,
        "persist_validation_artifact_from_compiler",
        _fake_persist_validation_artifact_from_compiler,
    )

    async def _fake_persist_gx_suite_from_compiler(
        gx_suite_repository,
        *,
        rule_id,
        rule_version_id,
        rule,
        catalog_repository,
        intermediate_model,
        publish_request,
        saved_by,
    ):
        del gx_suite_repository, rule, catalog_repository, intermediate_model, publish_request, saved_by
        gx_suite_calls.append({"rule_id": rule_id, "rule_version_id": rule_version_id})

    monkeypatch.setattr(
        activate_rule_module,
        "persist_gx_suite_from_compiler",
        _fake_persist_gx_suite_from_compiler,
    )

    validation_artifact_repo = _ValidationArtifactRepo()
    gx_suite_repo = _GxSuiteRepo()

    payload = await rules_endpoints.activate_rule(
        "rule-1",
        effective_at=None,
        body=rules_endpoints.GxSuiteAutoPublishRequest(dataObjectId="do-1", dataObjectVersionIds=["dov-1"]),
        repository=_Repo(),
        validation_artifact_repository=validation_artifact_repo,
        gx_suite_repository=gx_suite_repo,
    )

    assert payload["active"] is True
    assert [name for name, _ in calls] == [
        "rules.activate",
        "rules.compiler.persist_artifact",
        "rules.gx.auto_publish",
    ]
    assert calls[0][1]["rule_id"] == "rule-1"
    assert validation_artifact_repo.last_envelope is not None
    assert validation_artifact_repo.last_envelope["runPlanning"]["traceability"]["ruleId"] == "rule-1"
    assert validation_artifact_repo.last_envelope["runPlanning"]["traceability"]["ruleVersionId"] == "rv-1"
    assert validation_artifact_repo.last_envelope["runPlanning"]["traceability"]["validationArtifactId"] == "gx_rule-1"
    assert gx_suite_calls == [{"rule_id": "rule-1", "rule_version_id": "rv-1"}]


@pytest.mark.anyio
async def test_run_batch_test_request_emits_execution_span(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _Span:
        def __init__(self, attrs: dict[str, object]) -> None:
            self.attrs = attrs

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

        def record_exception(self, exc: Exception) -> None:
            return None

        def set_status(self, status) -> None:
            return None

    @contextmanager
    def _fake_traced_span(name: str, **attrs: object):
        calls.append((name, dict(attrs)))
        yield _Span(calls[-1][1])

    repo = SimpleNamespace(
        run_batch_test_request=lambda request_id: BatchTestRunResultEntity(id=request_id, status="running"),
        get_batch_test_request=lambda request_id: BatchTestRequestEntity(
            id=request_id,
            ruleId="rule-1",
            requestedBy="u1",
            requestedAt="2026-03-15T00:00:00Z",
            status="pending",
            workspace="default",
        ),
    )

    async def _context(*args, **kwargs):
        return {"handoffReady": True, "executionContract": {"engineTarget": "dq-engine"}}

    monkeypatch.setattr(testing_endpoints, "traced_span", _fake_traced_span)
    monkeypatch.setattr(testing_context, "build_execution_context", _context)

    result = await testing_endpoints.run_batch_test_request("batch-1", repo, SimpleNamespace())

    assert result.id == "batch-1"
    assert calls[0][0] == "rules.execute.batch_request"
    assert calls[0][1]["rule_id"] == "rule-1"
    assert calls[0][1]["execution_status"] == "running"
    assert calls[0][1]["executor_target"] == "dq-engine"


@pytest.mark.anyio
async def test_test_rule_with_data_emits_execution_span(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _Span:
        def __init__(self, attrs: dict[str, object]) -> None:
            self.attrs = attrs

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

        def record_exception(self, exc: Exception) -> None:
            return None

        def set_status(self, status) -> None:
            return None

    @contextmanager
    def _fake_traced_span(name: str, **attrs: object):
        calls.append((name, dict(attrs)))
        yield _Span(calls[-1][1])

    repo = SimpleNamespace(
        run_rule_against_test_data=lambda rule_id, test_data, version_id_source, compiled_expression=None, semantic_config=None: RunResultEntity(
            ruleId=rule_id,
            expression=compiled_expression or "x='y'",
            testDataSource=version_id_source,
            totalTests=len(test_data),
            passedCount=1,
            failedCount=max(0, len(test_data) - 1),
            successRate=50.0,
            timestamp="2026-03-15T00:00:00Z",
            results=[],
            ruleDetails={},
        ),
    )

    async def _context(*args, **kwargs):
        return {"compiledExpression": "email IS NOT NULL", "ruleVersionId": "rv-1"}

    monkeypatch.setattr(testing_endpoints, "traced_span", _fake_traced_span)
    monkeypatch.setattr(testing_context, "build_execution_context", _context)

    result = await testing_endpoints.test_rule_with_data(
        "rule-1",
        testing_endpoints.TestRuleWithDataRequest(testData=[{"email": "a"}, {"email": None}], versionIdSource="v1"),
        repo,
        SimpleNamespace(),
    )

    assert result.ruleId == "rule-1"
    assert calls[0][0] == "rules.execute.with_data"
    assert calls[0][1]["executed_expression_source"] == "compiled-artifact"
    assert calls[0][1]["total_tests"] == 2


@pytest.mark.anyio
async def test_test_rule_with_generated_data_emits_execution_span(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _Span:
        def __init__(self, attrs: dict[str, object]) -> None:
            self.attrs = attrs

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

        def record_exception(self, exc: Exception) -> None:
            return None

        def set_status(self, status) -> None:
            return None

    @contextmanager
    def _fake_traced_span(name: str, **attrs: object):
        calls.append((name, dict(attrs)))
        yield _Span(calls[-1][1])

    async def _enqueue(**_kwargs):
        return {"request_id": "tdr-queue-1", "correlation_id": "corr-queue-1"}

    async def _wait(_request_id: str):
        return {
            "request_id": "tdr-queue-1",
            "status": "completed",
            "result": {
                "samples": [{"email": "user@example.com"} for _ in range(3)],
            },
        }

    class _Repo:
        def create_test_proof(self, rule_id, payload, status="pending"):
            return {
                "id": "tp-generated-1",
                "ruleId": rule_id,
                "testDate": "2026-03-15T00:00:00Z",
                "coverage": payload.get("coverage", 0.0),
                "status": status,
                "recordsTestedCount": payload.get("recordsTestedCount", 0),
                "failuresFound": payload.get("failuresFound", 0),
                "proofData": payload.get("proofData", {}),
            }

        def update_test_proof(self, proof_id, payload, status="pending"):
            return {
                "id": proof_id,
                "ruleId": "rule-1",
                "testDate": "2026-03-15T00:00:00Z",
                "coverage": payload.get("coverage", 0.0),
                "status": status,
                "recordsTestedCount": payload.get("recordsTestedCount", 0),
                "failuresFound": payload.get("failuresFound", 0),
                "proofData": payload.get("proofData", {}),
                "executionTrace": payload.get("executionTrace"),
            }

        async def list_rules(self, **kwargs) -> list[dict]:
            del kwargs
            return [{"id": "rule-1", "active": False, "last_approval_status": "draft"}]

        async def record_rule_status_transition(self, *args, **kwargs):
            del args, kwargs
            return None

        async def list_rule_status_history(self, *args, **kwargs):
            del args, kwargs
            return []

        def run_rule_against_test_data(self, rule_id, test_data, version_id_source=None, compiled_expression=None, semantic_config=None):
            return RunResultEntity(
                ruleId=rule_id,
                expression=compiled_expression or "x='y'",
                testDataSource=version_id_source,
                totalTests=len(test_data),
                passedCount=len(test_data),
                failedCount=0,
                successRate=100.0,
                timestamp="2026-03-15T00:00:00Z",
                results=[],
                ruleDetails={},
            )

    class _CatalogRepo:
        def list_data_object_versions(self):
            return [SimpleNamespace(id="dov-1", version=1, data_object_id="do-1")]

        def list_attributes_catalog(self, version_id: str | None = None):
            return [SimpleNamespace(name="email", type="text", nullable=True, format="", is_primary_key=False)]

        def list_data_objects_catalog(self):
            return [SimpleNamespace(id="do-1", name="Data Object 1")]

    async def _context(*args, **kwargs):
        return {"compiledExpression": "email IS NOT NULL", "ruleVersionId": "rv-1"}

    async def _record_rule_status_transition(*args, **kwargs):
        del args, kwargs
        return None

    async def _list_rule_status_history(*args, **kwargs):
        del args, kwargs
        return []

    monkeypatch.setattr(testing_endpoints, "traced_span", _fake_traced_span)
    monkeypatch.setattr(testing_context, "build_execution_context", _context)
    monkeypatch.setattr(testing_bundles._testing_data_requests_api, "bind_queued_test_data_request_enqueuer", lambda _request: _enqueue)
    monkeypatch.setattr(testing_bundles._testing_data_requests_api, "wait_for_test_data_request_result", _wait)

    result = await testing_endpoints.test_rule_with_generated_data(
        SimpleNamespace(headers={}),
        "rule-1",
        testing_endpoints.TestRuleWithGeneratedDataRequest(versionId="dov-1", sampleCount=3),
        _Repo(),
        SimpleNamespace(
            record_rule_status_transition=_record_rule_status_transition,
            list_rule_status_history=_list_rule_status_history,
        ),
        _CatalogRepo(),
    )

    assert result.ruleId == "rule-1"
    assert calls[0][0] == "rules.execute.with_generated_data"
    assert calls[0][1]["execution_status"] == "completed"
    assert calls[0][1]["total_tests"] == 3


@pytest.mark.anyio
async def test_workspaces_create_workspace_raises_400_on_limit() -> None:
    repo = SimpleNamespace(create_workspace=lambda payload, max_workspaces: (_ for _ in ()).throw(ValueError("max reached")))
    config_repo = SimpleNamespace(get_app_config=lambda: AppConfigEntity(maxWorkspaces=1))

    with pytest.raises(HTTPException) as error:
        await workspaces_endpoints.create_workspace({"id": "w2", "name": "W2"}, repo, config_repo)

    assert error.value.status_code == 400


@pytest.mark.anyio
async def test_workspaces_delete_default_rejected() -> None:
    repo = SimpleNamespace(delete_workspace=lambda workspace_id: True)

    with pytest.raises(HTTPException) as error:
        await workspaces_endpoints.delete_workspace("default", repo)

    assert error.value.status_code == 400


@pytest.mark.anyio
async def test_approvals_update_requires_actor() -> None:
    repo = SimpleNamespace(update_approval=lambda approval_id, payload, actor_id: None)

    class _GxRepo:
        async def list_suites_for_rule(self, *, rule_id: str, status: str = "active", latest_only: bool = True):
            del rule_id, status, latest_only
            return []

    with pytest.raises(HTTPException) as error:
        await approvals_endpoints.update_approval(
            "a1",
            {"status": "approved"},
            _request_with_state(None, {}),
            repo,
            object(),
            object(),
            _GxRepo(),
        )

    assert error.value.status_code == 401


@pytest.mark.anyio
async def test_approvals_update_maps_permission_error_to_403() -> None:
    class _RulesRepo:
        async def list_rule_records(self, **kwargs):
            return [{"id": "r1", "active": False, "last_approval_status": "approved"}]

    class _GxRepo:
        async def list_suites_for_rule(self, *, rule_id: str, status: str = "active", latest_only: bool = True):
            del rule_id, status, latest_only
            return []

    repo = SimpleNamespace(
        list_approvals=lambda workspace: [
            ApprovalEntity(id="a1", ruleId="r1", status="approved", requesterId="u2")
        ],
        update_approval=lambda approval_id, payload, actor_id: (_ for _ in ()).throw(PermissionError("forbidden"))
    )

    with pytest.raises(HTTPException) as error:
        await approvals_endpoints.update_approval(
            "a1",
            {"status": "approved"},
            _request_with_state("u1", {}),
            repo,
            _RulesRepo(),
            object(),
            _GxRepo(),
        )

    assert error.value.status_code == 403


@pytest.mark.anyio
async def test_approvals_update_returns_404_when_not_found() -> None:
    repo = SimpleNamespace(
        list_approvals=lambda workspace: [],
        update_approval=lambda approval_id, payload, actor_id: None,
    )

    class _GxRepo:
        async def list_suites_for_rule(self, *, rule_id: str, status: str = "active", latest_only: bool = True):
            del rule_id, status, latest_only
            return []

    with pytest.raises(HTTPException) as error:
        await approvals_endpoints.update_approval(
            "a1",
            {"status": "approved"},
            _request_with_state("u1", {}),
            repo,
            object(),
            object(),
            _GxRepo(),
        )

    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_data_catalog_get_data_products_returns_paginated_view() -> None:
    repo = SimpleNamespace(
        list_data_products=lambda workspace: [
            DataProductEntity(id="p1", name="DP1", workspace_id="w1"),
            DataProductEntity(id="p2", name="DP2", workspace_id="w1"),
        ]
    )

    result = await data_catalog_endpoints.get_data_products(workspace="w1", businessKey=None, page=1, limit=1, repository=repo)

    assert result.pagination.total == 2
    assert len(result.data) == 1
    assert result.data[0].id == "p1"


@pytest.mark.anyio
async def test_testing_batch_endpoints_map_outputs(monkeypatch) -> None:
    class _Repo:
        def list_batch_test_requests(self, workspace, status):
            return [
                BatchTestRequestEntity(
                    id="b1",
                    ruleId="r1",
                    requestedBy="u1",
                    requestedAt="2026-03-15T00:00:00Z",
                    status="pending",
                    workspace="default",
                )
            ]

        def create_batch_test_requests(self, rule_ids, cfg, by, workspace):
            return [
                BatchTestRequestEntity(
                    id="b2",
                    ruleId="r2",
                    requestedBy=by or "u1",
                    requestedAt="2026-03-15T00:00:00Z",
                    status="pending",
                    workspace=workspace or "default",
                )
            ]

        def get_batch_test_request(self, request_id):
            return BatchTestRequestEntity(
                id=request_id,
                ruleId="r2",
                requestedBy="u2",
                requestedAt="2026-03-15T00:00:00Z",
                status="pending",
                workspace="w2",
            )

        def run_batch_test_request(self, request_id):
            return BatchTestRunResultEntity(id=request_id, status="running")

        async def list_rules(self, **kwargs) -> list[dict]:
            del kwargs
            return [{"id": "r2", "active": False, "last_approval_status": "draft"}]

        async def list_rule_records(self, **kwargs) -> list[dict]:
            del kwargs
            return [{"id": "r2", "active": False, "last_approval_status": "draft"}]

        async def record_rule_status_transition(self, *args, **kwargs):
            del args, kwargs
            return None

        async def list_rule_status_history(self, *args, **kwargs):
            del args, kwargs
            return []

        def store_test_proof(self, rule_id, payload):
            return ProofResultEntity(
                proofId="p1",
                ruleId=rule_id,
                testDate="2026-03-15T00:00:00Z",
                coverage=90.0,
                passed=True,
                recordsTestedCount=10,
                failuresFound=0,
                successRate=100.0,
                proofData={},
            )

        def create_test_proof(self, rule_id, payload, status="pending"):
            return {
                "id": "p-generated-1",
                "ruleId": rule_id,
                "testDate": "2026-03-15T00:00:00Z",
                "coverage": payload.get("coverage", 0.0),
                "status": status,
                "recordsTestedCount": payload.get("recordsTestedCount", 0),
                "failuresFound": payload.get("failuresFound", 0),
                "proofData": payload.get("proofData", {}),
            }

        def update_test_proof(self, proof_id, payload, status="pending"):
            return {
                "id": proof_id,
                "ruleId": "r2",
                "testDate": "2026-03-15T00:00:00Z",
                "coverage": payload.get("coverage", 0.0),
                "status": status,
                "recordsTestedCount": payload.get("recordsTestedCount", 0),
                "failuresFound": payload.get("failuresFound", 0),
                "proofData": payload.get("proofData", {}),
                "executionTrace": payload.get("executionTrace"),
            }

        def run_rule_against_test_data(self, rule_id, test_data, version_id_source=None, compiled_expression=None, semantic_config=None):
            return RunResultEntity(
                ruleId=rule_id,
                expression=compiled_expression or "x='y'",
                testDataSource=version_id_source,
                totalTests=len(test_data),
                passedCount=len(test_data),
                failedCount=0,
                successRate=100.0,
                timestamp="2026-03-15T00:00:00Z",
                results=[],
                ruleDetails={},
            )

        def list_test_proofs(self, rule_id):
            return [
                ProofEntity(
                    id="p1",
                    ruleId=rule_id,
                    testDate="2026-03-15T00:00:00Z",
                    coverage=98.0,
                    status="passed",
                    recordsTestedCount=100,
                    failuresFound=2,
                )
            ]

    repo = _Repo()

    async def _enqueue(**_kwargs):
        return {"request_id": "tdr-queue-2", "correlation_id": "corr-queue-2"}

    async def _wait(_request_id: str):
        return {
            "request_id": "tdr-queue-2",
            "status": "completed",
            "result": {
                "samples": [{"email": "user@example.com"} for _ in range(3)],
            },
        }

    async def list_rule_versions(rule_id, limit=1, offset=0):
        return {
            "versions": [{"id": f"{rule_id}-v1", "versionNumber": 1, "isCurrentVersion": True}]
        }

    async def get_active_compiler_artifact(rule_version_id):
        return {
            "artifactKey": f"artifact-{rule_version_id}",
            "compilerVersion": "dq-7.3.0",
            "compilerRevision": 1,
            "compileStatus": "compiled",
            "artifactPayload": {
                "schemaVersion": "1",
                "filter": {"normalized": "email IS NOT NULL"},
                "executionContract": {"engineTarget": "dq-engine"},
            },
        }

    async def get_rule_version(rule_id, version_id):
        return {
            "id": version_id,
            "ruleId": rule_id,
            "expression": "email IS NOT NULL",
        }

    async def record_rule_status_transition(*args, **kwargs):
        del args, kwargs
        return None

    async def list_rule_status_history(*args, **kwargs):
        del args, kwargs
        return []

    async def list_rules(**kwargs):
        del kwargs
        return [{"id": "r2", "active": False, "last_approval_status": "draft"}]

    async def list_rule_records(**kwargs):
        del kwargs
        return [{"id": "r2", "active": False, "last_approval_status": "draft"}]

    class _CatalogRepo:
        def list_data_object_versions(self):
            return [SimpleNamespace(id="v1", version=1, data_object_id="do-1")]

        def list_attributes_catalog(self, version_id: str | None = None):
            return [SimpleNamespace(name="email", type="text", nullable=True, format="", is_primary_key=False)]

        def list_data_objects_catalog(self):
            return [SimpleNamespace(id="do-1", name="Data Object 1")]

    rules_repo = SimpleNamespace(
        list_rule_versions=list_rule_versions,
        get_rule_version=get_rule_version,
        get_active_compiler_artifact=get_active_compiler_artifact,
        list_rule_records=list_rule_records,
        list_rules=list_rules,
        record_rule_status_transition=record_rule_status_transition,
        list_rule_status_history=list_rule_status_history,
    )

    monkeypatch.setattr(testing_bundles._testing_data_requests_api, "bind_queued_test_data_request_enqueuer", lambda _request: _enqueue)
    monkeypatch.setattr(testing_bundles._testing_data_requests_api, "wait_for_test_data_request_result", _wait)

    list_result = await testing_endpoints.get_batch_test_requests("default", "pending", 1, 20, repo)
    create_result = await testing_endpoints.create_batch_test_request(
        testing_endpoints.CreateBatchTestRequest(ruleIds=["r2"], requestedBy="u2", workspace="w2"),
        repo,
    )
    run_result = await testing_endpoints.run_batch_test_request("b2", repo, rules_repo)
    log_result = await testing_endpoints.log_test_action(
        "r2",
        testing_endpoints.LogTestActionRequest(
            coverage=90.0,
            passed=True,
            recordsTestedCount=10,
            failuresFound=0,
            proofData={},
        ),
        repo,
        rules_repo,
    )
    generated_result = await testing_endpoints.test_rule_with_generated_data(
        SimpleNamespace(headers={}),
        "r2",
        testing_endpoints.TestRuleWithGeneratedDataRequest(versionId="v1", sampleCount=3),
        repo,
        rules_repo,
        _CatalogRepo(),
    )
    proofs_result = await testing_endpoints.get_test_proofs("r2", repo)

    assert list_result.pagination.total == 1
    assert create_result[0].workspace == "w2"
    assert run_result.status == "running"
    assert run_result.executionContext is not None
    assert run_result.executionContext.ruleVersionId == "r2-v1"
    assert log_result.ruleId == "r2"
    assert generated_result.totalTests == 3
    assert proofs_result[0].status == "passed"


@pytest.mark.anyio
async def test_app_config_get_and_put() -> None:
    repo = SimpleNamespace(
        get_app_config=lambda: AppConfigEntity(apiVersion="v1"),
        set_app_config=lambda payload: AppConfigEntity(apiVersion=payload.get("apiVersion", "v1")),
    )

    current = await app_config_endpoints.get_app_config(repo)
    updated = await app_config_endpoints.put_app_config({"apiVersion": "v2"}, repo)

    assert current.apiVersion == "v1"
    assert updated.apiVersion == "v2"


def test_system_read_version_and_build_date_fallback(monkeypatch) -> None:
    monkeypatch.setenv("BUILD_DATE", "2026-03-15T00:00:00Z")
    assert system_endpoints._build_date() == "2026-03-15T00:00:00Z"


@pytest.mark.anyio
async def test_system_endpoint_maps_repository_values(monkeypatch) -> None:
    monkeypatch.setattr(system_endpoints, "_build_date", lambda: "2026-03-15T00:00:00Z")
    repo = SimpleNamespace(
        get_system_info=lambda: SimpleNamespace(
            db_schema_version="5",
            db_schema_updated="today",
            db_git_commit="abc",
        )
    )
    app_config_repo = SimpleNamespace(get_app_config=lambda: AppConfigEntity())
    request = SimpleNamespace(app=SimpleNamespace(version="0.6.2", openapi=lambda: {"info": {"version": "0.6.2"}}))

    result = await system_endpoints.get_system_info(request=request, repository=repo, app_config_repository=app_config_repo)

    assert isinstance(result.api.version, str)
    assert result.api.version.strip() != ""
    assert result.database.schemaVersion == "5"


@pytest.mark.anyio
async def test_workspaces_get_and_update_paths() -> None:
    repo = SimpleNamespace(
        list_workspaces=lambda: [WorkspaceEntity(id="default", name="Default")],
        update_workspace=lambda workspace_id, payload: WorkspaceEntity(id=workspace_id, name=payload.get("name", "Default")),
    )

    page = await workspaces_endpoints.get_workspaces(1, 20, repo)
    updated = await workspaces_endpoints.update_workspace("default", {"name": "Updated"}, repo)

    assert page.pagination.total == 1
    assert updated.name == "Updated"


@pytest.mark.anyio
async def test_approvals_list_and_create_paths() -> None:
    class _RulesRepo:
        async def list_rule_records(self, **kwargs):
            return []

    repo = SimpleNamespace(
        list_approvals=lambda workspace, business_key=None: [ApprovalEntity(id="a1", ruleId="r1", status="pending", requesterId="u1")],
        create_approval=lambda payload, actor_id: ApprovalEntity(id="a2", ruleId=payload["rule_id"], status="pending", requesterId=actor_id),
    )

    listed = await approvals_endpoints.get_approvals(workspace="w1", page=1, limit=20, repository=repo)
    created = await approvals_endpoints.create_approval(
        {"rule_id": "r2"},
        _request_with_state("u2", {}),
        repo,
        _RulesRepo(),
    )

    assert listed.pagination.total == 1
    assert created.ruleId == "r2"
