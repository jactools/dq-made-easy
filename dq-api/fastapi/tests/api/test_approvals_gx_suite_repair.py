import pytest

from types import SimpleNamespace

from fastapi import HTTPException

from app.api.presenters.approvals import parse_approval_suite_repair
from app.api.v1.endpoints import approvals as approvals_endpoints
from app.core.request_context import clear_auth_context, set_scopes
from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact
from app.domain.entities import build_rule_record_entity
from app.domain.entities.approvals import ApprovalAuditEntity, ApprovalEntity


@pytest.fixture
def approve_scopes() -> None:
    set_scopes(["dq:rules:approve"])
    yield
    clear_auth_context()


def _request_with_user(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(user_id=user_id))


def test_parse_suite_repair_valid_and_invalid_payloads() -> None:
    payload = {
        "suite_repair": {
            "data_object_id": "do-1",
            "dataset_id": "",
            "data_product_id": "",
            "data_object_version_ids": ["dov-1", ""],
            "primary_key_fields": ["pk1", None],
        }
    }
    parsed = parse_approval_suite_repair(payload)
    assert parsed["data_object_id"] == "do-1"
    assert parsed["data_object_version_ids"] == ["dov-1"]
    assert parsed["primary_key_fields"] == ["pk1"]

    with pytest.raises(HTTPException):
        parse_approval_suite_repair({})

    with pytest.raises(HTTPException):
        parse_approval_suite_repair({"suite_repair": "wrong"})

    with pytest.raises(HTTPException):
        parse_approval_suite_repair({"suite_repair": {"data_object_version_ids": []}})

    with pytest.raises(HTTPException):
        parse_approval_suite_repair(
            {
                "suite_repair": {
                    "data_object_id": "",
                    "dataset_id": "",
                    "data_product_id": "",
                    "data_object_version_ids": ["dov-1"],
                }
            }
        )



@pytest.fixture
def rules_repo_activated() -> object:
    class _RulesRepo:
        async def list_rule_records(self, **kwargs):
            return [
                build_rule_record_entity(
                    {
                        "id": "r1",
                        "active": True,
                        "removed": False,
                        "removed_at": None,
                        "deleted_on": None,
                        "last_approval_status": "activated",
                        "name": "Rule 1",
                        "expression": "col IS NOT NULL",
                        "dimension": "validity",
                    }
                )
            ]

        async def record_rule_status_transition(self, *args, **kwargs):
            raise AssertionError("record_rule_status_transition must not be called for gx_suite_repair")

        async def list_rule_versions(self, rule_id: str, limit: int, offset: int):
            return {"versions": [{"id": "v1", "isCurrentVersion": True}]}

        async def get_rule_by_id(self, rule_id: str):
            return SimpleNamespace(expression="col IS NOT NULL")

    return _RulesRepo()


@pytest.fixture
def gx_repo_spy() -> object:
    class _GxRepo:
        def __init__(self) -> None:
            self.saved_envelope = None

        async def list_artifact_status_history(self, *, artifact_id: str, artifact_version: int | None):
            del artifact_id, artifact_version
            return []

        async def save_artifact(self, *, envelope: dict, status: str, saved_by: str | None, source_pipeline: str):
            payload = build_gx_artifact_envelope_from_validation_artifact(envelope).model_dump(
                mode="python",
                by_alias=False,
                exclude_none=False,
            )
            self.saved_envelope = {
                "envelope": payload,
                "status": status,
                "saved_by": saved_by,
                "source_pipeline": source_pipeline,
            }

    return _GxRepo()


@pytest.fixture
def gx_run_plan_repo_spy() -> object:
    return object()


@pytest.fixture
def approvals_repo_spy() -> object:
    class _ApprovalsRepo:
        def __init__(self) -> None:
            self.update_called = False
            self.appended_events: list[ApprovalAuditEntity] = []

        def list_approvals(self, workspace):
            return [
                ApprovalEntity(
                    id="a1",
                    ruleId="r1",
                    status="pending",
                    requesterId="requester",
                    requestType="gx_suite_repair",
                    workspaceId="default",
                )
            ]

        def list_approval_audit(self):
            return [
                ApprovalAuditEntity(
                    id="a1-a",
                    approvalId="a1",
                    action="created",
                    actorId="requester",
                    timestamp="2026-03-15T00:00:00Z",
                    details={
                        "requester_id": "requester",
                        "request_type": "gx_suite_repair",
                        "suite_repair": {
                            "data_object_id": "obj-1",
                            "dataset_id": "ds-1",
                            "data_product_id": "odcs.product",
                            "data_object_version_ids": ["dov-1"],
                            "primary_key_fields": [],
                        },
                    },
                )
            ]

        def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None):
            self.update_called = True
            return ApprovalEntity(
                id=approval_id,
                ruleId="r1",
                status=str(payload.get("status") or "approved"),
                requesterId="requester",
                requestType="gx_suite_repair",
                workspaceId="default",
                reviewedBy=actor_id,
                reviewedAt="2026-03-15T00:00:10Z",
            )

        def append_audit_event(self, *, approval_id: str, action: str, actor_id: str | None, details: dict):
            event = ApprovalAuditEntity(
                id=f"{approval_id}-x-1",
                approvalId=approval_id,
                action=action,
                actorId=actor_id,
                timestamp="2026-03-15T00:00:11Z",
                details=details,
            )
            self.appended_events.append(event)
            return event

    return _ApprovalsRepo()


@pytest.fixture
def patch_compiler_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.services as services

    monkeypatch.setattr(
        services,
        "compile_rule_to_intermediate_model",
        lambda **kwargs: {
            "compilable": True,
            "compilerVersion": "test",
            "artifactKey": "ak",
        },
        raising=True,
    )
    monkeypatch.setattr(
        services,
        "build_gx_expectations_from_intermediate_model",
        lambda *args, **kwargs: [{"expectation_type": "expect_column_values_to_not_be_null"}],
        raising=True,
    )


@pytest.fixture
def patch_compiler_empty_expectations(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.services as services

    monkeypatch.setattr(
        services,
        "compile_rule_to_intermediate_model",
        lambda **kwargs: {
            "compilable": True,
            "compilerVersion": "test",
            "artifactKey": "ak",
        },
        raising=True,
    )
    monkeypatch.setattr(
        services,
        "build_gx_expectations_from_intermediate_model",
        lambda *args, **kwargs: [],
        raising=True,
    )


@pytest.mark.anyio
async def test_create_approval_accepts_gx_suite_repair_without_rule_transition(approve_scopes, rules_repo_activated):
    class _ApprovalsRepo:
        def list_approvals(self, workspace):
            return []

        def create_approval(self, payload: dict, actor_id: str | None):
            return ApprovalEntity(
                id="a2",
                ruleId=payload["rule_id"],
                status="pending",
                requesterId=actor_id,
                requestType=payload.get("request_type") or "activation",
                workspaceId=payload.get("workspace_id") or "default",
            )

    repo = _ApprovalsRepo()

    created = await approvals_endpoints.create_approval(
        {
            "rule_id": "r1",
            "workspace_id": "default",
            "request_type": "gx_suite_repair",
            "suite_repair": {
                "data_object_id": "obj-1",
                "data_object_version_ids": ["dov-1"],
            },
        },
        _request_with_user("requester"),
        repo,
        rules_repo_activated,
    )

    assert created.requestType == "gx_suite_repair"


@pytest.mark.anyio
async def test_update_approval_executes_gx_suite_repair_before_marking_approved(
    approve_scopes,
    approvals_repo_spy,
    rules_repo_activated,
    gx_run_plan_repo_spy,
    gx_repo_spy,
    patch_compiler_success,
):
    result = await approvals_endpoints.update_approval(
        "a1",
        {"status": "approved"},
        _request_with_user("approver"),
        approvals_repo_spy,
        rules_repo_activated,
        gx_run_plan_repo_spy,
        gx_repo_spy,
    )

    assert result.status == "approved"
    assert approvals_repo_spy.update_called is True

    saved = gx_repo_spy.saved_envelope
    assert saved is not None
    assert saved["status"] == "active"
    assert saved["saved_by"] == "approver"
    assert saved["envelope"]["suiteId"] == "gx_r1"
    assert saved["envelope"]["suiteVersion"] == 1
    assert "gxRowCondition" in saved["envelope"]["gxSuite"]["meta"]

    assert any(event.action == "gx_suite.repair.completed" for event in approvals_repo_spy.appended_events)


@pytest.mark.anyio
async def test_update_approval_repair_fails_fast_when_expectations_empty(
    approve_scopes,
    approvals_repo_spy,
    rules_repo_activated,
    gx_run_plan_repo_spy,
    gx_repo_spy,
    patch_compiler_empty_expectations,
):
    with pytest.raises(HTTPException) as excinfo:
        await approvals_endpoints.update_approval(
            "a1",
            {"status": "approved"},
            _request_with_user("approver"),
            approvals_repo_spy,
            rules_repo_activated,
            gx_run_plan_repo_spy,
            gx_repo_spy,
        )

    assert excinfo.value.status_code == 422
    assert approvals_repo_spy.update_called is False
    assert gx_repo_spy.saved_envelope is None


@pytest.mark.anyio
async def test_update_approval_repair_fails_when_audit_details_are_missing(approve_scopes, rules_repo_activated):
    class _ApprovalsRepo:
        def __init__(self) -> None:
            self.update_called = False

        def list_approvals(self, workspace):
            del workspace
            return [
                ApprovalEntity(
                    id="a1",
                    ruleId="r1",
                    status="pending",
                    requesterId="requester",
                    requestType="gx_suite_repair",
                    workspaceId="default",
                )
            ]

        def list_approval_audit(self):
            return [
                SimpleNamespace(
                    id="a1-a",
                    approvalId="a1",
                    action="created",
                    actorId="requester",
                    timestamp="2026-03-15T00:00:00Z",
                    details=None,
                )
            ]

        def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None):
            del approval_id, payload, actor_id
            self.update_called = True
            return None

    repo = _ApprovalsRepo()

    with pytest.raises(HTTPException) as excinfo:
        await approvals_endpoints.update_approval(
            "a1",
            {"status": "approved"},
            _request_with_user("approver"),
            repo,
            rules_repo_activated,
            gx_run_plan_repo_spy,
            gx_repo_spy,
        )

    assert excinfo.value.status_code == 500
    assert str(excinfo.value.detail) == "Approval audit details unavailable"
    assert repo.update_called is False


@pytest.mark.anyio
async def test_update_approval_repair_fails_when_assignment_scope_is_missing(approve_scopes, rules_repo_activated, gx_run_plan_repo_spy, gx_repo_spy):
    class _ApprovalsRepo:
        def __init__(self) -> None:
            self.update_called = False

        def list_approvals(self, workspace):
            del workspace
            return [
                ApprovalEntity(
                    id="a1",
                    ruleId="r1",
                    status="pending",
                    requesterId="requester",
                    requestType="gx_suite_repair",
                    workspaceId="default",
                )
            ]

        def list_approval_audit(self):
            return [
                ApprovalAuditEntity(
                    id="a1-a",
                    approvalId="a1",
                    action="created",
                    actorId="requester",
                    timestamp="2026-03-15T00:00:00Z",
                    details={
                        "suite_repair": {
                            "data_object_id": "",
                            "dataset_id": "",
                            "data_product_id": "",
                            "data_object_version_ids": ["dov-1"],
                            "primary_key_fields": [],
                        }
                    },
                )
            ]

        def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None):
            del approval_id, payload, actor_id
            self.update_called = True
            return None

    repo = _ApprovalsRepo()

    with pytest.raises(HTTPException) as excinfo:
        await approvals_endpoints.update_approval(
            "a1",
            {"status": "approved"},
            _request_with_user("approver"),
            repo,
            rules_repo_activated,
            gx_run_plan_repo_spy,
            gx_repo_spy,
        )

    assert excinfo.value.status_code == 422
    assert str(excinfo.value.detail) == "suite_repair missing assignment scope"
    assert repo.update_called is False
