from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api.v1.endpoints.admin import _has_any_non_exception_role
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_admin_repository
from app.core.auth import get_required_scopes
from app.domain.entities.admin import AdminUserEntity
from app.domain.entities.admin import UserWorkspaceRoleEntity
from app.infrastructure.repositories import InMemoryAdminRepository
from app.infrastructure.repositories import InMemoryAppConfigRepository


def test_exception_fact_access_request_route_scopes() -> None:
    assert get_required_scopes("POST", "/admin/v1/exception-fact-access-requests") == ["dq:rules:read"]
    assert get_required_scopes("GET", "/rulebuilder/v1/exception-fact-access-requests") == ["dq:rules:read"]
    assert get_required_scopes("GET", "/rulebuilder/v1/deliveries/del-31/exception-summary") == [
        "dq:rules:read",
        "dq:exceptions:read",
    ]


def test_exception_fact_requester_must_already_have_workspace_role() -> None:
    admin_repository = InMemoryAdminRepository()
    analyst = admin_repository.get_current_user("user-analyst", {"sub": "user-analyst"})
    assert analyst is not None

    assert _has_any_non_exception_role(analyst, "retail-banking") is True
    assert _has_any_non_exception_role(analyst, "default") is False


def test_exception_fact_access_request_creation_and_approval_caps_duration() -> None:
    admin_repository = InMemoryAdminRepository()
    config_repository = InMemoryAppConfigRepository()
    config_repository.set_app_config({
        **config_repository.get_app_config().model_dump(by_alias=False),
        "exceptionFactJitRoleMaxDurationMinutes": 1,
    })

    created = admin_repository.create_exception_fact_access_request(
        {
            "workspace_id": "retail-banking",
            "role_id": "exception-fact-reader",
            "requested_duration_minutes": 999,
            "comments": "Need temporary review access",
        },
        actor_id="user-analyst",
    )

    assert created.status == "pending"
    assert created.requesterId == "user-analyst"
    assert created.workspaceId == "retail-banking"
    assert created.roleId == "exception-fact-reader"
    assert created.requestedDurationMinutes == 999
    assert created.expiresAt is None

    approved = admin_repository.update_exception_fact_access_request(
        created.id,
        {"status": "approved", "comments": "Approved for short review window"},
        actor_id="user-admin",
        max_duration_minutes=max(1, int(config_repository.get_app_config().exceptionFactJitRoleMaxDurationMinutes)),
    )

    assert approved is not None
    assert approved.status == "approved"
    assert approved.reviewedBy == "user-admin"
    assert approved.expiresAt is not None

    reviewed_at = datetime.fromisoformat(approved.reviewedAt.replace("Z", "+00:00")) if approved.reviewedAt else None
    expires_at = datetime.fromisoformat(approved.expiresAt.replace("Z", "+00:00"))
    assert reviewed_at is not None
    assert (expires_at - reviewed_at).total_seconds() <= 120


def test_exception_fact_access_request_times_out_and_blocks_review() -> None:
    admin_repository = InMemoryAdminRepository()

    created = admin_repository.create_exception_fact_access_request(
        {
            "workspace_id": "retail-banking",
            "role_id": "exception-fact-reader",
            "requested_duration_minutes": 30,
            "comments": "Need temporary review access",
        },
        actor_id="user-analyst",
    )

    admin_repository._exception_fact_access_requests[0]["requestedAt"] = (
        datetime.now(timezone.utc) - timedelta(minutes=45)
    ).isoformat().replace("+00:00", "Z")

    requests = admin_repository.list_exception_fact_access_requests(
        requester_id="user-analyst",
        request_timeout_minutes=30,
    )

    assert requests[0].id == created.id
    assert requests[0].status == "timed_out"
    assert requests[0].reviewedBy is None
    assert requests[0].reviewedAt is not None

    try:
        admin_repository.update_exception_fact_access_request(
            created.id,
            {"status": "approved"},
            actor_id="user-admin",
            max_duration_minutes=240,
            request_timeout_minutes=30,
        )
    except ValueError as error:
        assert str(error) == "Request is not pending"
    else:
        raise AssertionError("Expected timed-out request review to fail")


def test_requestor_can_list_own_exception_fact_access_requests(client, auth_headers) -> None:
    class _RequestorRepository:
        def __init__(self) -> None:
            self.repository = InMemoryAdminRepository()
            self.current_user = AdminUserEntity(
                id="user-admin",
                name="Admin User",
                email="admin@example.com",
                workspaces=["retail-banking"],
                workspace_roles=[UserWorkspaceRoleEntity(workspace_id="retail-banking", role="admin")],
            )

        def get_current_user(self, user_id: str | None, claims: dict | None = None) -> AdminUserEntity | None:
            _ = user_id
            _ = claims
            return self.current_user

        def list_exception_fact_access_requests(self, **kwargs):
            return self.repository.list_exception_fact_access_requests(**kwargs)

        def create_exception_fact_access_request(self, payload: dict, actor_id: str | None = None):
            return self.repository.create_exception_fact_access_request(payload, actor_id=actor_id)

    requester_headers = auth_headers(
        "dq:rules:read",
    )

    requestor_repository = _RequestorRepository()
    client.app.dependency_overrides[get_admin_repository] = lambda: requestor_repository

    try:
        create_response = client.post(
            "/api/rulebuilder/v1/exception-fact-access-requests",
            headers=requester_headers,
            json={
                "workspace_id": "retail-banking",
                "role_id": "exception-fact-reader",
                "requested_duration_minutes": 15,
                "comments": "Need temporary review access",
            },
        )

        assert create_response.status_code == 200
        created = create_response.json()
        assert created["status"] == "pending"

        list_response = client.get(
            "/api/rulebuilder/v1/exception-fact-access-requests",
            headers=requester_headers,
        )

        assert list_response.status_code == 200
        assert any(item["id"] == created["id"] and item["status"] == "pending" for item in list_response.json())
    finally:
        client.app.dependency_overrides.pop(get_admin_repository, None)


def test_admin_can_list_exception_fact_access_requests_without_server_error(client, auth_headers) -> None:
    class _AdminQueueRepository:
        def __init__(self) -> None:
            self.repository = InMemoryAdminRepository()
            self.current_user = AdminUserEntity(
                id="user-admin",
                name="Admin User",
                email="admin@example.com",
                workspaces=["retail-banking"],
                workspace_roles=[UserWorkspaceRoleEntity(workspace_id="retail-banking", role="admin")],
            )

        def get_current_user(self, user_id: str | None, claims: dict | None = None) -> AdminUserEntity | None:
            _ = user_id
            _ = claims
            return self.current_user

        def list_exception_fact_access_requests(self, **kwargs):
            return self.repository.list_exception_fact_access_requests(**kwargs)

    requester_headers = auth_headers("dq:admin:read", "dq:workspace:read")
    admin_repository = _AdminQueueRepository()
    app_config_repository = InMemoryAppConfigRepository()

    client.app.dependency_overrides[get_admin_repository] = lambda: admin_repository
    client.app.dependency_overrides[get_app_config_repository] = lambda: app_config_repository

    try:
        response = client.get(
            "/api/admin/v1/exception-fact-access-requests",
            headers=requester_headers,
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)
    finally:
        client.app.dependency_overrides.pop(get_admin_repository, None)
        client.app.dependency_overrides.pop(get_app_config_repository, None)
