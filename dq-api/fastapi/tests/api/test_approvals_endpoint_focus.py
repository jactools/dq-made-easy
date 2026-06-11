from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.presenters.approvals import build_approvals_page_payload
from app.api.presenters.approvals import derive_approval_effective_status
from app.api.presenters.approvals import derive_approval_rule_status
from app.api.presenters.approvals import normalize_approval_request_type
from app.api.presenters.approvals import normalize_approval_string_list
from app.api.presenters.approvals import reject_camel_case_approval_keys
from app.api.v1.endpoints import approvals as approvals_endpoints
from app.core.request_context import clear_auth_context
from app.core.request_context import set_scopes
from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact
from app.domain.entities import build_rule_record_entity
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities.approvals import ApprovalAuditEntity
from app.domain.entities.approvals import ApprovalEntity
from app.domain.status_governance import canonicalize_status


@pytest.fixture
def approve_scopes() -> None:
    set_scopes(["dq:rules:approve"])
    yield
    clear_auth_context()


@pytest.fixture
def rules_repo_activated() -> object:
    class _RulesRepo:
        async def list_rule_records(self, **kwargs):
            del kwargs
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
            raise AssertionError("record_rule_status_transition must not be called in these tests")

        async def list_rule_versions(self, rule_id: str, limit: int, offset: int):
            del rule_id, limit, offset
            return {"versions": [{"id": "v1", "isCurrentVersion": True}]}

        async def get_rule_by_id(self, rule_id: str):
            del rule_id
            return SimpleNamespace(expression="col IS NOT NULL")

    return _RulesRepo()


@pytest.fixture
def approvals_repo_spy() -> object:
    class _ApprovalsRepo:
        def __init__(self) -> None:
            self.update_called = False
            self.appended_events: list[ApprovalAuditEntity] = []

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
def gx_run_plan_repo_spy() -> object:
    return object()


@pytest.fixture
def gx_repo_spy() -> object:
    return object()


def _request_with_user(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(user_id=user_id))


class _ApprovalRepo:
    def __init__(self, approvals: list[SimpleNamespace]) -> None:
        self._approvals = approvals
        self._audit: list[dict] = []

    def list_approvals(self, workspace_id: str | None = None):
        del workspace_id
        return list(self._approvals)

    def create_approval(self, payload: dict, actor_id: str | None = None):
        created = SimpleNamespace(
            id="a-created",
            ruleId=str(payload.get("rule_id") or ""),
            status=str(payload.get("status") or "pending"),
            requesterId=actor_id,
            workspaceId=str(payload.get("workspace_id") or "default"),
            requestType=str(payload.get("request_type") or "activation"),
            effectiveStatus=str(payload.get("effective_status") or ""),
        )
        self._approvals.append(created)
        return created

    def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None):
        del actor_id
        for item in self._approvals:
            if str(item.id or "") != str(approval_id):
                continue
            item.status = str(payload.get("status") or item.status)
            return item
        return None

    def list_approval_audit(self):
        return [SimpleNamespace(**item) for item in list(self._audit)]

    def append_audit_event(self, *, approval_id: str, action: str, actor_id: str | None, details: dict):
        item = {
            "id": f"{approval_id}-x-{len(self._audit) + 1}",
            "approvalId": approval_id,
            "action": action,
            "actorId": actor_id,
            "timestamp": "2026-04-08T00:00:00Z",
            "details": dict(details or {}),
        }
        self._audit.append(item)
        return SimpleNamespace(**item)


class _RulesRepo:
    def __init__(self, rule_row: dict | None) -> None:
        self._rule_row = rule_row
        self.deactivated_rule_id: str | None = None

    async def list_rule_records(self, **kwargs):
        del kwargs
        return [build_rule_record_entity(self._rule_row)] if self._rule_row is not None else []

    async def deactivate_rule(self, rule_id: str):
        self.deactivated_rule_id = rule_id
        if self._rule_row is not None:
            self._rule_row["active"] = False
            self._rule_row["last_approval_status"] = "deactivated"
        return self._rule_row

    async def record_rule_status_transition(self, *args, **kwargs):
        del args, kwargs
        return None

    async def list_rule_status_history(self, *args, **kwargs):
        del args, kwargs
        return []

    async def get_rule_by_id(self, rule_id: str):
        del rule_id
        return SimpleNamespace(created_by_user_id="user-owner")

class _NoopGxRepo:
    async def list_artifacts_for_rule(self, *, rule_id: str, status: str = "active", latest_only: bool = True):
        del rule_id, status, latest_only
        return []

class _CapturingGxRepo:
    def __init__(self, *, suites: list[dict], history_versions: list[int]):
        self._suites = [build_validation_artifact_envelope_from_gx_artifact(item) for item in suites]
        self._history_versions = list(history_versions)
        self.saved_envelopes: list[dict] = []
        self.saved_statuses: list[str] = []
        self.patched_status_updates: list[tuple[str, int | None, str, str | None]] = []

    async def list_artifacts_for_rule(self, *, rule_id: str, status: str = "active", latest_only: bool = True):
        del rule_id, status, latest_only
        return list(self._suites)

    async def list_artifact_status_history(self, *, artifact_id: str, artifact_version: int | None = None):
        del artifact_version
        return [
            {
                "validationArtifactId": artifact_id,
                "validationArtifactVersion": version,
                "fromStatus": None,
                "toStatus": "active",
                "changedBy": None,
                "changedAt": "2026-04-01T00:00:00Z",
                "reason": None,
            }
            for version in self._history_versions
        ]

    async def patch_artifact_status(
        self,
        *,
        artifact_id: str,
        new_status: str,
        artifact_version: int | None = None,
        changed_by: str | None = None,
        reason: str | None = None,
    ):
        self.patched_status_updates.append((artifact_id, artifact_version, new_status, reason))
        del changed_by
        return None

    async def save_artifact(
        self,
        *,
        envelope: dict,
        status: str = "active",
        expected_existing_hash: str | None = None,
        saved_by: str | None = None,
        source_pipeline: str | None = None,
    ) -> dict:
        del expected_existing_hash, saved_by, source_pipeline
        payload = build_gx_artifact_envelope_from_validation_artifact(envelope).model_dump(
            mode="python",
            by_alias=False,
            exclude_none=False,
        )
        self.saved_envelopes.append(payload)
        self.saved_statuses.append(str(status))
        return {**payload, "artifactHash": "hash"}


def test_normalize_request_type_and_string_list() -> None:
    assert normalize_approval_request_type(None) == "activation"
    assert normalize_approval_request_type("deactivation") == "deactivation"
    assert normalize_approval_request_type("GX-Suite-Repair") == "gx_suite_repair"

    assert normalize_approval_string_list(None) == []
    assert normalize_approval_string_list(["a", " ", None, "b"]) == ["a", "b"]

    with pytest.raises(HTTPException):
        normalize_approval_string_list("not-a-list")


def test_reject_camel_case_keys_and_effective_status() -> None:
    with pytest.raises(HTTPException):
        reject_camel_case_approval_keys({"ruleId": "x"}, "test")

    assert derive_approval_effective_status("activation") == "activated"
    assert derive_approval_effective_status("deactivation") == "deactivated"
    assert derive_approval_effective_status("unknown") is None


def test_paginate_and_derive_rule_status() -> None:
    page = build_approvals_page_payload([{"id": index} for index in range(7)], page=2, limit=3)
    assert page["pagination"]["page"] == 2
    assert page["pagination"]["has_next"] is True
    assert len(page["data"]) == 3

    assert derive_approval_rule_status({"active": True}, [], status_canonicalizer=canonicalize_status) == "activated"
    assert derive_approval_rule_status({"removed": True}, [], status_canonicalizer=canonicalize_status) == "removed"

    approval = SimpleNamespace(status="approved")
    assert derive_approval_rule_status(None, [approval], status_canonicalizer=canonicalize_status) == "approved"
    assert derive_approval_rule_status({"last_approval_status": "pending"}, [], status_canonicalizer=canonicalize_status) == "pending-approval"


def test_find_rule_row() -> None:
    class DummyRulesRepository:
        async def list_rule_records(self, workspace, include_deleted, is_template, limit, offset):
            del workspace, include_deleted, is_template, limit, offset
            return [{"id": "rule-1"}, {"id": "rule-2"}]

    async def _assert_find() -> None:
        repo = DummyRulesRepository()
        found = await approvals_endpoints._find_rule_row("rule-2", repo)
        assert found["id"] == "rule-2"

    import asyncio

    asyncio.run(_assert_find())


def test_read_and_serialize_gx_payload_helpers(monkeypatch):
    class _ModelDumpValue:
        def model_dump(self, *, mode: str, by_alias: bool, exclude_none: bool):
            return {
                "mode": mode,
                "by_alias": by_alias,
                "exclude_none": exclude_none,
                "marker": "ok",
            }

        marker = "from-attr"

    value = _ModelDumpValue()

    assert approvals_endpoints._read_gx_payload_field({"field": "dict-value"}, "field") == "dict-value"
    assert approvals_endpoints._read_gx_payload_field(value, "marker") == "from-attr"

    payload = approvals_endpoints._gx_payload_dict(value)
    assert payload["marker"] == "ok"
    assert payload["mode"] == "python"
    assert payload["by_alias"] is False
    assert payload["exclude_none"] is True
    assert approvals_endpoints._gx_payload_dict({"suiteId": "gx-1"}) == {"suiteId": "gx-1"}
    assert approvals_endpoints._gx_payload_dict(SimpleNamespace()) == {}

    monkeypatch.setattr(
        approvals_endpoints,
        "build_gx_artifact_envelope_from_validation_artifact",
        lambda _value: SimpleNamespace(converted=True),
    )
    converted = approvals_endpoints._coerce_gx_suite_from_validation_artifact({"engine_type": "gx"})
    assert converted.converted is True


def test_coerce_gx_suite_from_validation_artifact_wraps_value_error(monkeypatch):
    monkeypatch.setattr(
        approvals_endpoints,
        "build_gx_artifact_envelope_from_validation_artifact",
        lambda _value: (_ for _ in ()).throw(ValueError("unsupported engine")),
    )

    with pytest.raises(HTTPException) as excinfo:
        approvals_endpoints._coerce_gx_suite_from_validation_artifact({"engine_type": "bad"})

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail["error"] == "unsupported_engine_type"


@pytest.mark.anyio
async def test_create_approval_rejects_missing_rule_and_run_plan_identifiers(approve_scopes):
    class _ApprovalsRepo:
        def list_approvals(self, workspace):
            del workspace
            return []

        def create_approval(self, payload: dict, actor_id: str | None):
            del payload, actor_id
            raise AssertionError("create_approval should not be called")

    with pytest.raises(HTTPException) as excinfo:
        await approvals_endpoints.create_approval(
            {"workspace_id": "default"},
            _request_with_user("requester"),
            _ApprovalsRepo(),
            rules_repo_activated,
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail == "rule_id or gx_run_plan_id is required"


@pytest.mark.anyio
async def test_create_approval_rejects_duplicate_pending_gx_suite_repair(approve_scopes, rules_repo_activated):
    class _ApprovalsRepo:
        def list_approvals(self, workspace):
            del workspace
            return [
                ApprovalEntity(
                    id="a-pending",
                    ruleId="r1",
                    status="pending",
                    requesterId="requester",
                    requestType="gx_suite_repair",
                    workspaceId="default",
                )
            ]

        def create_approval(self, payload: dict, actor_id: str | None):
            del payload, actor_id
            raise AssertionError("create_approval should not be called")

    with pytest.raises(HTTPException) as excinfo:
        await approvals_endpoints.create_approval(
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
            _ApprovalsRepo(),
            rules_repo_activated,
        )

    assert excinfo.value.status_code == 409
    assert "pending gx_suite_repair" in str(excinfo.value.detail)


@pytest.mark.anyio
async def test_create_approval_rejects_gx_suite_repair_for_inactive_rule(approve_scopes):
    class _ApprovalsRepo:
        def list_approvals(self, workspace):
            del workspace
            return []

        def create_approval(self, payload: dict, actor_id: str | None):
            del payload, actor_id
            raise AssertionError("create_approval should not be called")

    class _InactiveRulesRepo:
        async def list_rule_records(self, **kwargs):
            del kwargs
            return [
                build_rule_record_entity(
                    {
                        "id": "r1",
                        "active": False,
                        "removed": False,
                        "removed_at": None,
                        "deleted_on": None,
                        "last_approval_status": "pending",
                    }
                )
            ]

    with pytest.raises(HTTPException) as excinfo:
        await approvals_endpoints.create_approval(
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
            _ApprovalsRepo(),
            _InactiveRulesRepo(),
        )

    assert excinfo.value.status_code == 409
    assert str(excinfo.value.detail) == "gx_suite_repair requires the rule to be activated"


@pytest.mark.anyio
async def test_create_approval_rejects_deactivation_for_inactive_rule(monkeypatch):
    approval_repo = _ApprovalRepo([])

    class _RulesRepo:
        async def list_rule_records(self, **kwargs):
            del kwargs
            return [
                build_rule_record_entity(
                    {
                        "id": "r1",
                        "active": False,
                        "removed": False,
                        "removed_at": None,
                        "deleted_on": None,
                        "last_approval_status": "draft",
                    }
                )
            ]

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:write"])
    monkeypatch.setattr(approvals_endpoints, "resolve_approval_view", lambda value: value)

    with pytest.raises(HTTPException) as excinfo:
        await approvals_endpoints.create_approval(
            {"rule_id": "r1", "workspace_id": "default", "request_type": "deactivation"},
            _request_with_user("requester"),
            approval_repo,
            _RulesRepo(),
        )

    assert excinfo.value.status_code == 409
    assert str(excinfo.value.detail) == "Transition 'draft' -> 'deactivated' is not allowed"


@pytest.mark.anyio
async def test_update_approval_rejects_unauthenticated_and_effective_at_mutation():
    class _ApprovalsRepo:
        def list_approvals(self, workspace):
            del workspace
            return []

        def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None):
            del approval_id, payload, actor_id
            raise AssertionError("update_approval should not be called")

    repo = _ApprovalsRepo()

    with pytest.raises(HTTPException) as unauthenticated_error:
        await approvals_endpoints.update_approval(
            "approval-1",
            {"status": "approved"},
            SimpleNamespace(state=SimpleNamespace(user_id=None)),
            repo,
            object(),
            object(),
            object(),
        )

    assert unauthenticated_error.value.status_code == 401

    with pytest.raises(HTTPException) as effective_at_error:
        await approvals_endpoints.update_approval(
            "approval-1",
            {"status": "approved", "effective_at": "2026-05-22T00:00:00Z"},
            _request_with_user("approver"),
            repo,
            object(),
            object(),
            object(),
        )

    assert effective_at_error.value.status_code == 409
    assert str(effective_at_error.value.detail) == "effective_at cannot be modified after creation"


@pytest.mark.anyio
async def test_update_approval_rejects_gx_suite_repair_and_deactivation_rule_transitions(approve_scopes):
    class _ApprovalsRepo:
        def __init__(self, request_type: str) -> None:
            self.request_type = request_type

        def list_approvals(self, workspace):
            del workspace
            return [
                ApprovalEntity(
                    id="approval-1",
                    ruleId="r1",
                    status="approved",
                    requesterId="requester",
                    requestType=self.request_type,
                    workspaceId="default",
                )
            ]

        def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None):
            del approval_id, payload, actor_id
            raise AssertionError("update_approval should not be called")

    class _RulesRepo:
        def __init__(self, rule_row: dict):
            self.rule_row = rule_row

        async def list_rule_records(self, **kwargs):
            del kwargs
            return [build_rule_record_entity(self.rule_row)]

    with pytest.raises(HTTPException) as excinfo:
        await approvals_endpoints.update_approval(
            "approval-1",
            {"status": "approved"},
            _request_with_user("approver"),
            _ApprovalsRepo("gx_suite_repair"),
            _RulesRepo({"id": "r1", "active": False, "last_approval_status": "draft"}),
            object(),
            object(),
        )

    assert excinfo.value.status_code == 409
    assert str(excinfo.value.detail) == "gx_suite_repair can only be approved while the rule is activated"


@pytest.mark.anyio
async def test_update_approval_rejects_missing_run_plan_and_version(monkeypatch):
    class _ApprovalsRepo:
        def list_approvals(self, workspace):
            del workspace
            return [
                ApprovalEntity(
                    id="approval-1",
                    ruleId="",
                    status="pending",
                    requesterId="requester",
                    requestType="activation",
                    workspaceId="default",
                    gxRunPlanId="run-plan-1",
                    gxRunPlanVersionId="version-1",
                )
            ]

        def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None):
            del approval_id, payload, actor_id
            raise AssertionError("update_approval should not be called")

    class _RunPlanRepoMissingPlan:
        async def get_plan(self, run_plan_id: str):
            del run_plan_id
            return None

    class _RunPlanRepoMissingVersion:
        async def get_plan(self, run_plan_id: str):
            del run_plan_id
            return {"versions": [{"runPlanVersionId": "other-version", "governanceState": "activation-requested"}]}

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:approve"])

    with pytest.raises(HTTPException) as missing_plan_error:
        await approvals_endpoints.update_approval(
            "approval-1",
            {"status": "approved"},
            _request_with_user("approver"),
            _ApprovalsRepo(),
            object(),
            _RunPlanRepoMissingPlan(),
            object(),
        )

    assert missing_plan_error.value.status_code == 404
    assert "GX run plan 'run-plan-1' not found" in str(missing_plan_error.value.detail)

    with pytest.raises(HTTPException) as missing_version_error:
        await approvals_endpoints.update_approval(
            "approval-1",
            {"status": "approved"},
            _request_with_user("approver"),
            _ApprovalsRepo(),
            object(),
            _RunPlanRepoMissingVersion(),
            object(),
        )

    assert missing_version_error.value.status_code == 404
    assert "GX run plan version 'version-1' not found" in str(missing_version_error.value.detail)


@pytest.mark.anyio
async def test_update_approval_repair_fails_fast_for_compilation_and_expectation_errors(approve_scopes, approvals_repo_spy, rules_repo_activated, gx_run_plan_repo_spy, gx_repo_spy, monkeypatch):
    import app.application.services as services

    monkeypatch.setattr(
        services,
        "compile_rule_to_intermediate_model",
        lambda **kwargs: {
            "compilable": False,
            "compilerVersion": "test",
            "artifactKey": "ak",
        },
        raising=True,
    )

    with pytest.raises(HTTPException) as non_compilable_error:
        await approvals_endpoints.update_approval(
            "a1",
            {"status": "approved"},
            _request_with_user("approver"),
            approvals_repo_spy,
            rules_repo_activated,
            gx_run_plan_repo_spy,
            gx_repo_spy,
        )

    assert non_compilable_error.value.status_code == 422
    assert non_compilable_error.value.detail["error"] == "rule_not_compilable"

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
        "build_gx_expectations_for_rule",
        lambda *args, **kwargs: (_ for _ in ()).throw(services.GxExpectationBuildError("boom")),
        raising=True,
    )

    with pytest.raises(HTTPException) as build_error:
        await approvals_endpoints.update_approval(
            "a1",
            {"status": "approved"},
            _request_with_user("approver"),
            approvals_repo_spy,
            rules_repo_activated,
            gx_run_plan_repo_spy,
            gx_repo_spy,
        )

    assert build_error.value.status_code == 422
    assert build_error.value.detail["error"] == "gx_expectations_build_failed"


@pytest.mark.anyio
async def test_update_approval_returns_not_found_for_missing_approval():
    class _ApprovalsRepo:
        def list_approvals(self, workspace):
            del workspace
            return [
                ApprovalEntity(
                    id="other",
                    ruleId="",
                    status="pending",
                    requesterId="requester",
                    requestType="activation",
                    workspaceId="default",
                )
            ]

        def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None):
            del approval_id, payload, actor_id
            raise AssertionError("update_approval should not be called")

    with pytest.raises(HTTPException) as excinfo:
        await approvals_endpoints.update_approval(
            "missing",
            {"status": "approved"},
            _request_with_user("approver"),
            _ApprovalsRepo(),
            object(),
            object(),
            object(),
        )

    assert excinfo.value.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("request_type", "requested_status", "current_gx_state", "expected_action", "expected_target_state"),
    [
        ("activation", "approved", "activation-requested", "transition", "approved_pending_activation"),
        ("activation", "rejected", "activation-requested", "transition", "inactive"),
        ("deactivation", "approved", "deactivation-requested", "deactivate", None),
        ("deactivation", "rejected", "deactivation-requested", "transition", "active"),
    ],
)
async def test_update_approval_applies_run_plan_state_transitions(
    approve_scopes,
    request_type: str,
    requested_status: str,
    current_gx_state: str,
    expected_action: str,
    expected_target_state: str | None,
):
    class _ApprovalsRepo:
        def __init__(self) -> None:
            self.updated_payloads: list[dict] = []

        def list_approvals(self, workspace):
            del workspace
            return [
                ApprovalEntity(
                    id="approval-1",
                    ruleId="",
                    status="pending",
                    requesterId="requester",
                    requestType=request_type,
                    workspaceId="default",
                    gxRunPlanId="run-plan-1",
                    gxRunPlanVersionId="version-1",
                )
            ]

        def update_approval(self, approval_id: str, payload: dict, actor_id: str | None = None):
            self.updated_payloads.append(dict(payload))
            return ApprovalEntity(
                id=approval_id,
                    ruleId="",
                status=str(payload.get("status") or ""),
                requesterId="requester",
                requestType=request_type,
                workspaceId="default",
                gxRunPlanId="run-plan-1",
                gxRunPlanVersionId="version-1",
            )

    class _RunPlanRepo:
        def __init__(self) -> None:
            self.transition_calls: list[tuple[str, str, str, str | None]] = []
            self.deactivate_calls: list[tuple[str, str, str]] = []

        async def get_plan(self, run_plan_id: str):
            del run_plan_id
            return {
                "versions": [
                    {
                        "runPlanVersionId": "version-1",
                        "governanceState": current_gx_state,
                    }
                ]
            }

        async def transition_plan_version(self, *, run_plan_id: str, run_plan_version_id: str, target_state: str, updated_by: str | None):
            self.transition_calls.append((run_plan_id, run_plan_version_id, target_state, updated_by))

        async def deactivate_plan(self, *, run_plan_id: str, run_plan_version_id: str, deactivated_by: str | None):
            self.deactivate_calls.append((run_plan_id, run_plan_version_id, deactivated_by))

    approvals_repo = _ApprovalsRepo()
    run_plan_repo = _RunPlanRepo()

    result = await approvals_endpoints.update_approval(
        "approval-1",
        {"status": requested_status},
        _request_with_user("approver"),
        approvals_repo,
        object(),
        run_plan_repo,
        object(),
    )

    assert result.status == requested_status
    if expected_action == "transition":
        assert run_plan_repo.transition_calls == [("run-plan-1", "version-1", expected_target_state, "approver")]
        assert run_plan_repo.deactivate_calls == []
    else:
        assert run_plan_repo.deactivate_calls == [("run-plan-1", "version-1", "approver")]
        assert run_plan_repo.transition_calls == []


@pytest.mark.anyio
async def test_create_approval_rejects_invalid_rule_transition(monkeypatch):
    approval_repo = _ApprovalRepo([])
    rules_repo = _RulesRepo({"id": "r1", "active": False, "last_approval_status": "approved"})

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:write"])
    monkeypatch.setattr(approvals_endpoints, "resolve_approval_view", lambda value: value)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-author"))

    with pytest.raises(HTTPException) as error:
        await approvals_endpoints.create_approval(
            payload={"rule_id": "r1", "workspace_id": "default"},
            request=request,
            repository=approval_repo,
            rules_repository=rules_repo,
        )

    assert error.value.status_code == 409


@pytest.mark.anyio
async def test_update_approval_rejects_invalid_approval_transition(monkeypatch):
    approval_repo = _ApprovalRepo(
        [
            SimpleNamespace(
                id="a1",
                ruleId="r1",
                status="approved",
                requesterId="user-author",
                workspaceId="default",
            )
        ]
    )
    rules_repo = _RulesRepo({"id": "r1", "active": False, "last_approval_status": "approved"})

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:approve"])
    monkeypatch.setattr(approvals_endpoints, "resolve_approval_view", lambda value: value)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-reviewer"))

    with pytest.raises(HTTPException) as error:
        await approvals_endpoints.update_approval(
            approval_id="a1",
            payload={"status": "rejected"},
            request=request,
            repository=approval_repo,
            rules_repository=rules_repo,
            validation_artifact_repository=_NoopGxRepo(),
        )

    assert error.value.status_code == 409


@pytest.mark.anyio
async def test_update_approval_allows_pending_to_approved(monkeypatch):
    approval_repo = _ApprovalRepo(
        [
            SimpleNamespace(
                id="a1",
                ruleId="r1",
                status="pending",
                requesterId="user-author",
                workspaceId="default",
            )
        ]
    )
    rules_repo = _RulesRepo({"id": "r1", "active": False, "last_approval_status": "pending"})

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:approve"])
    monkeypatch.setattr(approvals_endpoints, "resolve_approval_view", lambda value: value)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-reviewer"))

    payload = await approvals_endpoints.update_approval(
        approval_id="a1",
        payload={"status": "approved"},
        request=request,
        repository=approval_repo,
        rules_repository=rules_repo,
        validation_artifact_repository=_NoopGxRepo(),
    )

    assert payload.status == "approved"


@pytest.mark.anyio
async def test_create_approval_allows_deactivation_request_for_activated_rule(monkeypatch):
    approval_repo = _ApprovalRepo([])
    rules_repo = _RulesRepo({"id": "r1", "active": True, "last_approval_status": "approved"})

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:write"])
    monkeypatch.setattr(approvals_endpoints, "resolve_approval_view", lambda value: value)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-author"))

    payload = await approvals_endpoints.create_approval(
        payload={"rule_id": "r1", "workspace_id": "default", "request_type": "deactivation", "comments": "Retiring this rule"},
        request=request,
        repository=approval_repo,
        rules_repository=rules_repo,
    )

    assert payload.requestType == "deactivation"
    assert payload.effectiveStatus == "deactivated"


@pytest.mark.anyio
async def test_create_approval_accepts_snake_case_payload(monkeypatch):
    approval_repo = _ApprovalRepo([])
    rules_repo = _RulesRepo({"id": "r1", "active": True, "last_approval_status": "approved", "workspace": "default"})

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:write"])
    monkeypatch.setattr(approvals_endpoints, "resolve_approval_view", lambda value: value)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-author"))

    payload = await approvals_endpoints.create_approval(
        payload={"rule_id": "r1", "workspace_id": "default", "request_type": "deactivation", "comments": "Retiring this rule"},
        request=request,
        repository=approval_repo,
        rules_repository=rules_repo,
    )

    assert payload.ruleId == "r1"
    assert payload.requestType == "deactivation"
    assert payload.effectiveStatus == "deactivated"
    assert payload.workspaceId == "default"


@pytest.mark.anyio
async def test_update_approval_approved_deactivation_deactivates_rule(monkeypatch):
    approval_repo = _ApprovalRepo(
        [
            SimpleNamespace(
                id="a1",
                ruleId="r1",
                status="pending",
                requesterId="user-author",
                workspaceId="default",
                requestType="deactivation",
            )
        ]
    )
    rules_repo = _RulesRepo({"id": "r1", "active": True, "last_approval_status": "approved"})

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:approve"])
    monkeypatch.setattr(approvals_endpoints, "resolve_approval_view", lambda value: value)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-reviewer"))

    payload = await approvals_endpoints.update_approval(
        approval_id="a1",
        payload={"status": "approved"},
        request=request,
        repository=approval_repo,
        rules_repository=rules_repo,
        validation_artifact_repository=_NoopGxRepo(),
    )

    assert payload.status == "approved"
    assert rules_repo.deactivated_rule_id == "r1"

@pytest.mark.anyio
async def test_update_approval_approved_deactivation_reversions_gx_suite_to_remaining_activated_rules(monkeypatch):
    approval_repo = _ApprovalRepo(
        [
            SimpleNamespace(
                id="a1",
                ruleId="r1",
                status="pending",
                requesterId="user-author",
                workspaceId="default",
                requestType="deactivation",
            )
        ]
    )

    class _MultiRulesRepo(_RulesRepo):
        def __init__(self):
            super().__init__({"id": "r1", "active": True, "last_approval_status": "approved"})
            self._rows = [
                {"id": "r1", "active": True, "last_approval_status": "approved"},
                {"id": "r2", "active": True, "last_approval_status": "approved"},
            ]

        async def list_rule_records(self, **kwargs):
            del kwargs
            return [build_rule_record_entity(row) for row in self._rows]

        async def deactivate_rule(self, rule_id: str):
            self.deactivated_rule_id = rule_id
            for row in self._rows:
                if row.get("id") == rule_id:
                    row["active"] = False
                    row["last_approval_status"] = "deactivated"
            return next((r for r in self._rows if r.get("id") == rule_id), None)

    rules_repo = _MultiRulesRepo()

    suite = {
        "suiteId": "gx_suite_1",
        "suiteVersion": 3,
        "artifactVersion": "v1",
        "assignmentScope": {"dataObjectId": "do_1", "datasetId": None, "dataProductId": None},
        "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]},
        "gxSuite": {"expectation_suite_name": "dq_suite_v3", "expectations": [], "meta": {}},
        "compiledFrom": {"ruleIds": ["r1", "r2"], "compilerVersion": "c1", "generatedAt": "2026-04-01T00:00:00Z"},
        "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": []},
        "executionContract": {
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "traceability": {"ruleId": "r1", "ruleVersionId": "rv1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 3},
        },
    }

    gx_repo = _CapturingGxRepo(suites=[suite], history_versions=[1, 2, 3])

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:approve"]) 
    monkeypatch.setattr(approvals_endpoints, "resolve_approval_view", lambda value: value)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-reviewer"))

    payload = await approvals_endpoints.update_approval(
        approval_id="a1",
        payload={"status": "approved"},
        request=request,
        repository=approval_repo,
        rules_repository=rules_repo,
        validation_artifact_repository=gx_repo,
    )

    assert payload.status == "approved"
    assert rules_repo.deactivated_rule_id == "r1"
    assert len(gx_repo.saved_envelopes) == 1
    saved = gx_repo.saved_envelopes[0]
    assert gx_repo.saved_statuses == ["active"]
    assert saved["suiteId"] == "gx_suite_1"
    assert saved["suiteVersion"] == 4
    assert saved["compiledFrom"]["ruleIds"] == ["r2"]
    assert saved.get("executionContract") is None


@pytest.mark.anyio
async def test_update_approval_approved_deactivation_registers_disabled_empty_suite_version(monkeypatch):
    approval_repo = _ApprovalRepo(
        [
            SimpleNamespace(
                id="a1",
                ruleId="r1",
                status="pending",
                requesterId="user-author",
                workspaceId="default",
                requestType="deactivation",
            )
        ]
    )

    class _SingleRuleRepo(_RulesRepo):
        def __init__(self):
            super().__init__({"id": "r1", "active": True, "last_approval_status": "approved"})
            self._rows = [{"id": "r1", "active": True, "last_approval_status": "approved"}]

        async def list_rule_records(self, **kwargs):
            del kwargs
            return [build_rule_record_entity(row) for row in self._rows]

        async def deactivate_rule(self, rule_id: str):
            self.deactivated_rule_id = rule_id
            for row in self._rows:
                if row.get("id") == rule_id:
                    row["active"] = False
                    row["last_approval_status"] = "deactivated"
            return next((r for r in self._rows if r.get("id") == rule_id), None)

    rules_repo = _SingleRuleRepo()

    async def _get_rule_by_id(rule_id: str):
        del rule_id
        return SimpleNamespace(created_by_user_id="user-owner")

    rules_repo.get_rule_by_id = _get_rule_by_id

    suite = {
        "suiteId": "gx_suite_1",
        "suiteVersion": 3,
        "artifactVersion": "v1",
        "assignmentScope": {"dataObjectId": "do_1", "datasetId": None, "dataProductId": None},
        "resolvedExecutionScope": {"dataObjectVersionIds": ["dov_1"]},
        "gxSuite": {"expectation_suite_name": "dq_suite_v3", "expectations": [], "meta": {}},
        "compiledFrom": {"ruleIds": ["r1"], "compilerVersion": "c1", "generatedAt": "2026-04-01T00:00:00Z"},
        "executionHints": {"recommendedEngine": "pyspark", "primaryKeyFields": []},
        "executionContract": {
            "engineTarget": "pyspark",
            "executionShape": "single_object",
            "traceability": {"ruleId": "r1", "ruleVersionId": "rv1", "gxSuiteId": "gx_suite_1", "gxSuiteVersion": 3},
        },
    }

    gx_repo = _CapturingGxRepo(suites=[suite], history_versions=[1, 2, 3])

    monkeypatch.setattr(approvals_endpoints, "get_scopes", lambda: ["dq:rules:approve"]) 
    monkeypatch.setattr(approvals_endpoints, "resolve_approval_view", lambda value: value)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-reviewer"))

    payload = await approvals_endpoints.update_approval(
        approval_id="a1",
        payload={"status": "approved"},
        request=request,
        repository=approval_repo,
        rules_repository=rules_repo,
        validation_artifact_repository=gx_repo,
    )

    assert payload.status == "approved"
    assert rules_repo.deactivated_rule_id == "r1"

    assert gx_repo.patched_status_updates
    assert gx_repo.patched_status_updates[0][0] == "gx_suite_1"
    assert gx_repo.patched_status_updates[0][2] == "disabled"

    assert len(gx_repo.saved_envelopes) == 1
    assert gx_repo.saved_statuses == ["disabled"]
    saved = gx_repo.saved_envelopes[0]
    assert saved["suiteId"] == "gx_suite_1"
    assert saved["suiteVersion"] == 4
    assert saved["compiledFrom"]["ruleIds"] == []
    assert saved.get("executionContract") is None

    # Notifications are recorded as audit events for owner + requester.
    notification_rows = [
        row
        for row in approval_repo.list_approval_audit()
        if str(getattr(row, "action", "")) == "notification.gx_suite_empty"
    ]
    recipients = sorted(str(getattr(row, "actorId", "")) for row in notification_rows)
    assert recipients == ["user-author", "user-owner"]
