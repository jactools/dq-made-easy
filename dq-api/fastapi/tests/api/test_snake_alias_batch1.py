import pytest

from app.api.v1.schemas.rule_view import RuleView
from app.api.v1.schemas.testing_view import BatchTestRequestView
from app.api.v1.schemas.approvals_view import ApprovalView
from app.api.v1.schemas.auth_view import LoginResponseView


def test_rule_view_aliasing():
    rv = RuleView(
        id="r1",
        name="My rule",
        expression="x>0",
        dimension="quality",
        active=True,
        created_by_user_id="u1",
        tag_ids=[],
        checkType="THRESHOLD",
        checkTypeParams={"threshold": 10},
    )
    out = rv.model_dump(by_alias=True)
    assert "check_type" in out
    assert "checkType" not in out
    assert "created_by_user_id" in out


def test_batch_test_request_view_aliasing():
    btr = BatchTestRequestView(
        id="b1",
        ruleId="r1",
        requestedBy="tester",
        requestedAt="2020-01-01T00:00:00Z",
        testDataConfig={},
        workspace="default",
    )
    out = btr.model_dump(by_alias=True)
    assert "requested_by" in out
    assert "requestedBy" not in out


def test_approval_view_aliasing():
    av = ApprovalView(
        id="a1",
        ruleId="r1",
        status="pending",
        requesterId="u1",
        workspaceId="default",
        requestType="activation",
    )
    out = av.model_dump(by_alias=True)
    assert "requester_id" in out
    assert "requesterId" not in out
    assert "request_type" in out


def test_login_response_view_aliasing():
    lr = LoginResponseView(
        id="u1",
        first_name="User",
        last_name="One",
        email="u@example.com",
        roles=["admin"],
        granted_scopes=["dq:admin"],
        workspaces=["retail-banking", "corporate-banking"],
        workspace_roles=[
            {"workspace_id": "retail-banking", "role": "analyst"},
            {"workspace_id": "corporate-banking", "role": "data-steward"},
        ],
        workspace="retail-banking",
        preferences={},
        external_id=None,
        token="tok",
    )
    out = lr.model_dump(by_alias=True)
    assert out["first_name"] == "User"
    assert out["last_name"] == "One"
    assert "granted_scopes" in out
    assert "external_id" in out
    assert out["workspace_roles"][0]["workspace_id"] == "retail-banking"
