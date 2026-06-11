"""Tests for incident endpoints (DQ-13)."""
import base64
import json
from typing import Any
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import incidents as incidents_api
from app.domain.entities.incident import (
    IncidentEntity,
    IncidentRootCauseSuggestionEntity,
    INCIDENT_KIND_TECHNICAL,
    INCIDENT_KIND_FUNCTIONAL,
    INCIDENT_STATUS_OPEN,
    INCIDENT_STATUS_RESOLVED,
)
from app.infrastructure.repositories.in_memory_app_config_repository import (
    InMemoryAppConfigRepository,
)
from app.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def _jwt(payload: dict) -> str:
    def _b64(value: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    header = {"alg": "none", "typ": "JWT"}
    return f"{_b64(header)}.{_b64(payload)}.signature"


def _auth_headers(*scopes: str) -> dict[str, str]:
    token = _jwt(
        {
            "sub": "user-123",
            "preferred_username": "admin",
            "iss": "http://keycloak.local:8080/realms/jaccloud",
            "aud": ["dq-rules-ui"],
            "scope": " ".join(scopes),
        }
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# InMemoryIncidentRepository unit tests
# ---------------------------------------------------------------------------


def test_create_and_get_incident():
    repo = InMemoryIncidentRepository()
    entity = IncidentEntity(
        id="",
        incident_kind=INCIDENT_KIND_TECHNICAL,
        title="Engine crashed",
        failure_code="worker_crash",
        run_id="run-1",
        workspace_id="ws-1",
    )
    saved = repo.create_incident(entity)
    assert saved.id  # auto-generated
    assert saved.incident_kind == INCIDENT_KIND_TECHNICAL
    assert saved.status == INCIDENT_STATUS_OPEN
    assert saved.created_at
    assert saved.comments == []
    assert saved.resolution_history == []

    fetched = repo.get_incident(saved.id)
    assert fetched is not None
    assert fetched.id == saved.id


def test_get_nonexistent_incident_returns_none():
    repo = InMemoryIncidentRepository()
    assert repo.get_incident("does-not-exist") is None


def test_create_functional_incident():
    repo = InMemoryIncidentRepository()
    entity = IncidentEntity(
        id="inc-2",
        incident_kind=INCIDENT_KIND_FUNCTIONAL,
        title="Data violation in asset-A",
        violation_count=42,
        violated_rule_ids=["rule-1", "rule-2"],
        scope_kind="data_asset",
        scope_id="asset-A",
        workspace_id="ws-1",
    )
    saved = repo.create_incident(entity)
    assert saved.violation_count == 42
    assert saved.violated_rule_ids == ["rule-1", "rule-2"]


def test_update_incident_status():
    repo = InMemoryIncidentRepository()
    entity = IncidentEntity(
        id="inc-3",
        incident_kind=INCIDENT_KIND_TECHNICAL,
        title="Run failure",
        workspace_id="ws-1",
    )
    saved = repo.create_incident(entity)
    updated = repo.update_incident(
        IncidentEntity(
            **{
                **saved.model_dump(),
                "status": INCIDENT_STATUS_RESOLVED,
                "resolved_at": "2026-01-01T00:00:00",
            }
        )
    )
    assert updated.status == INCIDENT_STATUS_RESOLVED


def test_update_incident_persists_history_fields():
    repo = InMemoryIncidentRepository()
    entity = IncidentEntity(
        id="inc-3-history",
        incident_kind=INCIDENT_KIND_TECHNICAL,
        title="Run failure",
        workspace_id="ws-1",
        comments=[{"comment": "Initial note"}],
        resolution_history=[{"event_type": "created", "changes": {"status": {"from": None, "to": "open"}}}],
    )
    saved = repo.create_incident(entity)
    updated = repo.update_incident(
        IncidentEntity(
            **{
                **saved.model_dump(),
                "status": INCIDENT_STATUS_RESOLVED,
                "resolved_at": "2026-01-01T00:00:00",
                "comments": [{"comment": "Initial note"}, {"comment": "Closed"}],
                "resolution_history": saved.resolution_history
                + [{"event_type": "updated", "changes": {"status": {"from": "open", "to": "resolved"}}}],
            }
        )
    )
    assert updated.comments[-1]["comment"] == "Closed"
    assert updated.resolution_history[-1]["event_type"] == "updated"


def test_list_incidents_filters():
    repo = InMemoryIncidentRepository()
    for kind, ws in [
        (INCIDENT_KIND_TECHNICAL, "ws-1"),
        (INCIDENT_KIND_FUNCTIONAL, "ws-1"),
        (INCIDENT_KIND_TECHNICAL, "ws-2"),
    ]:
        repo.create_incident(
            IncidentEntity(
                id="",
                incident_kind=kind,
                title=f"Incident {kind} {ws}",
                workspace_id=ws,
            )
        )

    all_incidents = repo.list_incidents()
    assert len(all_incidents) == 3

    ws1 = repo.list_incidents(workspace_id="ws-1")
    assert len(ws1) == 2

    tech = repo.list_incidents(incident_kind=INCIDENT_KIND_TECHNICAL)
    assert len(tech) == 2

    ws2_func = repo.list_incidents(workspace_id="ws-2", incident_kind=INCIDENT_KIND_FUNCTIONAL)
    assert len(ws2_func) == 0


def test_list_incidents_pagination():
    repo = InMemoryIncidentRepository()
    for i in range(5):
        repo.create_incident(
            IncidentEntity(id="", incident_kind=INCIDENT_KIND_TECHNICAL, title=f"Inc {i}")
        )
    page1 = repo.list_incidents(limit=3, offset=0)
    page2 = repo.list_incidents(limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 2


def test_root_cause_suggestion_crud_in_memory():
    repo = InMemoryIncidentRepository()
    entity = IncidentRootCauseSuggestionEntity(
        id="",
        workspace_id="ws-rc",
        incident_ids=["inc-1", "inc-2"],
        incident_count=2,
        suggested_root_cause={
            "kind": "shared_source_correlation",
            "title": "Shared source correlation chain",
            "summary": "Both incidents share the same correlation id.",
        },
        events=[{"event_type": "created"}],
        created_by="user-123",
    )

    saved = repo.create_root_cause_suggestion(entity)
    assert saved.id
    assert saved.status == "pending"
    assert saved.incident_ids == ["inc-1", "inc-2"]

    fetched = repo.get_root_cause_suggestion(saved.id)
    assert fetched is not None
    assert fetched.id == saved.id

    updated = repo.update_root_cause_suggestion(
        IncidentRootCauseSuggestionEntity(
            **{
                **saved.model_dump(),
                "status": "accepted",
                "accepted_at": "2026-06-01T12:00:00+00:00",
            }
        )
    )
    assert updated.status == "accepted"

    all_suggestions = repo.list_root_cause_suggestions(workspace_id="ws-rc")
    assert len(all_suggestions) == 1
    assert all_suggestions[0].id == saved.id


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    monkeypatch.setenv("SSO_INTERNAL_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.delenv("NATURAL_LANGUAGE_DRAFT_QUEUE_KEY", raising=False)

    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.main import app
    from app.core.dependencies import get_incident_repository
    incident_repo = InMemoryIncidentRepository()
    app.dependency_overrides[get_incident_repository] = lambda: incident_repo

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, incident_repo

    app.dependency_overrides.pop(get_incident_repository, None)
    get_settings.cache_clear()


@pytest.fixture()
def app_config_repo() -> InMemoryAppConfigRepository:
    return InMemoryAppConfigRepository()


@pytest.fixture()
def client_with_incident_governance(client, app_config_repo):
    c, incident_repo = client

    from app.core.dependencies import get_app_config_repository
    from app.main import app

    app.dependency_overrides[get_app_config_repository] = lambda: app_config_repo
    try:
        yield c, incident_repo, app_config_repo
    finally:
        app.dependency_overrides.pop(get_app_config_repository, None)


def test_create_technical_incident(client):
    c, _ = client
    resp = c.post(
        "/rulebuilder/v1/incidents",
        json={
            "incident_kind": "technical_run_error",
            "title": "Engine crashed",
            "failure_code": "worker_crash",
            "failure_message": "py4j connection refused",
            "run_id": "run-42",
            "workspace_id": "ws-1",
            "source_correlation_id": "corr-source-42",
            "source_parent_correlation_id": "corr-parent-1",
            "source_request_id": "req-42",
            "source_queue_message_id": "queue-42",
            "source_trace_id": "trace-42",
            "source_system": "dq-engine",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["incident"]["incident_kind"] == "technical_run_error"
    assert body["incident"]["failure_code"] == "worker_crash"
    assert body["incident"]["failure_message"] is None
    assert body["incident"]["description"] is None
    assert body["incident"]["status"] == "open"
    assert body["incident"]["source_correlation_id"] == "corr-source-42"
    assert body["incident"]["source_parent_correlation_id"] == "corr-parent-1"
    assert body["incident"]["source_request_id"] == "req-42"
    assert body["incident"]["source_queue_message_id"] == "queue-42"
    assert body["incident"]["source_trace_id"] == "trace-42"
    assert body["incident"]["source_system"] == "dq-engine"
    assert body["incident"]["comments"] == []
    assert body["incident"]["resolution_history"]
    assert body["incident"]["resolution_history"][0]["event_type"] == "created"
    assert body["correlation_id"]


def test_create_functional_incident(client):
    c, _ = client
    resp = c.post(
        "/rulebuilder/v1/incidents",
        json={
            "incident_kind": "functional_violation",
            "title": "Data violated rule completeness-check",
            "violation_count": 17,
            "violated_rule_ids": ["rule-abc"],
            "scope_kind": "data_asset",
            "scope_id": "asset-X",
            "workspace_id": "ws-2",
            "severity": "high",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["incident"]["incident_kind"] == "functional_violation"
    assert body["incident"]["violation_count"] == 17
    assert body["incident"]["violated_rule_ids"] == ["rule-abc"]
    assert body["incident"]["severity"] == "high"


def test_incident_comment_governance_lock_and_delete(client):
    c, _ = client
    created = c.post(
        "/rulebuilder/v1/incidents",
        json={
            "incident_kind": "technical_run_error",
            "title": "Comment governance incident",
            "workspace_id": "ws-3",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert created.status_code == 201, created.text
    incident_id = created.json()["incident"]["id"]

    comment_response = c.post(
        f"/rulebuilder/v1/incidents/{incident_id}/comments",
        json={"comment": "Please investigate the root cause.", "comment_type": "question"},
        headers=_auth_headers("dq:rules:edit"),
    )
    assert comment_response.status_code == 200, comment_response.text
    comment_id = comment_response.json()["incident"]["comments"][-1]["id"]

    edited = c.patch(
        f"/rulebuilder/v1/incidents/{incident_id}/comments/{comment_id}",
        json={"comment": "Please investigate the root cause and retry."},
        headers=_auth_headers("dq:rules:edit"),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["incident"]["comments"][-1]["edited"] is True

    locked = c.patch(
        f"/rulebuilder/v1/incidents/{incident_id}/comments-lock",
        json={"locked": True},
        headers=_auth_headers("dq:rules:edit"),
    )
    assert locked.status_code == 200, locked.text
    assert locked.json()["incident"]["comments_locked"] is True

    blocked = c.post(
        f"/rulebuilder/v1/incidents/{incident_id}/comments",
        json={"comment": "This should be blocked.", "comment_type": "general"},
        headers=_auth_headers("dq:rules:edit"),
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"]["error"] == "comments_locked"

    deleted = c.delete(
        f"/rulebuilder/v1/incidents/{incident_id}/comments/{comment_id}",
        headers=_auth_headers("dq:rules:edit"),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["incident"]["removed_comment_count"] == 1


def test_create_incident_applies_governance_assignment(client_with_incident_governance):
    c, _, app_config = client_with_incident_governance
    app_config.set_app_config(
        {
            "incidentGovernance": {
                "default_assigned_to": "dq-made-easy-support@jaccloud.nl",
                "rules": [
                    {
                        "incident_kinds": ["technical_run_error"],
                        "assigned_to": "engine-on-call",
                        "escalation_label": "engine-on-call",
                        "escalate_after_minutes": 15,
                    }
                ],
            }
        }
    )

    resp = c.post(
        "/rulebuilder/v1/incidents",
        json={
            "incident_kind": "technical_run_error",
            "title": "Engine crashed",
            "run_id": "run-42",
            "workspace_id": "ws-1",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["incident"]["assigned_to"] == "engine-on-call"
    assert body["incident"]["resolution_history"][0]["changes"]["assigned_to"]["to"] == "engine-on-call"


def test_create_incident_invalid_kind(client):
    c, _ = client
    resp = c.post(
        "/rulebuilder/v1/incidents",
        json={
            "incident_kind": "not_a_valid_kind",
            "title": "Test",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "invalid_incident_kind"


def test_create_incident_invalid_severity(client):
    c, _ = client
    resp = c.post(
        "/rulebuilder/v1/incidents",
        json={
            "incident_kind": "technical_run_error",
            "title": "Test",
            "severity": "catastrophic",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "invalid_severity"


@pytest.mark.anyio
async def test_dispatch_zammad_ticket_extracts_nested_identifiers(monkeypatch):
    incident = IncidentEntity(
        id="incident-1",
        incident_kind=INCIDENT_KIND_TECHNICAL,
        title="Engine crashed",
        run_id="run-42",
    )
    config_repository = SimpleNamespace(
        get_app_config=lambda: SimpleNamespace(
            assistanceRequestItsmSystem="Zammad",
            assistanceRequestItsmEndpointUrl="http://zammad-nginx:8080/api/v1/tickets",
            assistanceRequestItsmAuthToken="token-123",
            assistanceRequestEmailAddress="dq-made-easy-support@jaccloud.nl",
        )
    )

    class _FakeResponse:
        status_code = 201

        @staticmethod
        def json() -> dict[str, Any]:
            return {"data": {"ticket_id": "123", "ticket_number": "49001"}}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]):
            assert url == "http://zammad-nginx:8080/api/v1/tickets"
            assert headers == {"Authorization": "Token token=token-123"}
            assert json["title"] == "[Technical] DQ Run Error: run-42"
            return _FakeResponse()

    monkeypatch.setattr(incidents_api.httpx, "AsyncClient", _FakeAsyncClient)

    ticket_id, ticket_number = await incidents_api._dispatch_zammad_ticket(
        incident,
        correlation_id="corr-123",
        config_repository=config_repository,
    )

    assert ticket_id == "123"
    assert ticket_number == "49001"


def test_list_incidents_empty(client):
    c, _ = client
    resp = c.get("/rulebuilder/v1/incidents", headers=_auth_headers("dq:rules:read"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["incidents"] == []
    assert body["count"] == 0


def test_list_incidents_after_create(client):
    c, _ = client
    c.post(
        "/rulebuilder/v1/incidents",
        json={"incident_kind": "technical_run_error", "title": "Crash"},
        headers=_auth_headers("dq:rules:edit"),
    )
    resp = c.get("/rulebuilder/v1/incidents", headers=_auth_headers("dq:rules:read"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 1


def test_list_incidents_filter_by_kind(client):
    c, _ = client
    c.post(
        "/rulebuilder/v1/incidents",
        json={"incident_kind": "technical_run_error", "title": "T1"},
        headers=_auth_headers("dq:rules:edit"),
    )
    c.post(
        "/rulebuilder/v1/incidents",
        json={"incident_kind": "functional_violation", "title": "F1"},
        headers=_auth_headers("dq:rules:edit"),
    )
    resp = c.get(
        "/rulebuilder/v1/incidents?incident_kind=technical_run_error",
        headers=_auth_headers("dq:rules:read"),
    )
    body = resp.json()
    assert body["count"] == 1
    assert body["incidents"][0]["incident_kind"] == "technical_run_error"
    assert body["incidents"][0]["description"] is None
    assert body["incidents"][0]["failure_message"] is None


def test_get_incident_by_id(client):
    c, _ = client
    create_resp = c.post(
        "/rulebuilder/v1/incidents",
        json={"incident_kind": "functional_violation", "title": "Violation"},
        headers=_auth_headers("dq:rules:edit"),
    )
    incident_id = create_resp.json()["incident"]["id"]

    resp = c.get(f"/rulebuilder/v1/incidents/{incident_id}", headers=_auth_headers("dq:rules:read"))
    assert resp.status_code == 200, resp.text
    incident = resp.json()["incident"]
    assert incident["id"] == incident_id
    assert incident["description"] is None
    assert incident["failure_message"] is None


def test_get_incident_not_found(client):
    c, _ = client
    resp = c.get("/rulebuilder/v1/incidents/does-not-exist", headers=_auth_headers("dq:rules:read"))
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "incident_not_found"


def test_patch_incident_status(client):
    c, _ = client
    create_resp = c.post(
        "/rulebuilder/v1/incidents",
        json={"incident_kind": "technical_run_error", "title": "Crash"},
        headers=_auth_headers("dq:rules:edit"),
    )
    incident_id = create_resp.json()["incident"]["id"]

    patch_resp = c.patch(
        f"/rulebuilder/v1/incidents/{incident_id}",
        json={
            "status": "resolved",
            "resolved_at": "2026-06-01T12:00:00",
            "comment": "Root cause fixed",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["incident"]["status"] == "resolved"
    assert patch_resp.json()["incident"]["resolved_at"] == "2026-06-01T12:00:00"
    assert patch_resp.json()["incident"]["comments"][-1]["comment"] == "Root cause fixed"
    assert patch_resp.json()["incident"]["resolution_history"][-1]["changes"]["status"] == {
        "from": "open",
        "to": "resolved",
    }

    get_resp = c.get(
        f"/rulebuilder/v1/incidents/{incident_id}",
        headers=_auth_headers("dq:rules:read"),
    )
    assert get_resp.json()["incident"]["comments"][-1]["comment"] == "Root cause fixed"


def test_patch_incident_invalid_status(client):
    c, _ = client
    create_resp = c.post(
        "/rulebuilder/v1/incidents",
        json={"incident_kind": "technical_run_error", "title": "Crash"},
        headers=_auth_headers("dq:rules:edit"),
    )
    incident_id = create_resp.json()["incident"]["id"]

    patch_resp = c.patch(
        f"/rulebuilder/v1/incidents/{incident_id}",
        json={"status": "not_valid"},
        headers=_auth_headers("dq:rules:edit"),
    )
    assert patch_resp.status_code == 422
    assert patch_resp.json()["detail"]["error"] == "invalid_status"


def test_patch_incident_not_found(client):
    c, _ = client
    resp = c.patch(
        "/rulebuilder/v1/incidents/ghost-id",
        json={"status": "resolved"},
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "incident_not_found"


def test_root_cause_suggestion_lifecycle(client):
    c, _ = client
    create_one = c.post(
        "/rulebuilder/v1/incidents",
        json={
            "incident_kind": "technical_run_error",
            "title": "Correlation incident A",
            "workspace_id": "ws-root-cause",
            "source_correlation_id": "corr-root-1",
            "source_system": "dq-engine",
            "failure_code": "worker_crash",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert create_one.status_code == 201, create_one.text
    incident_one_id = create_one.json()["incident"]["id"]

    create_two = c.post(
        "/rulebuilder/v1/incidents",
        json={
            "incident_kind": "technical_run_error",
            "title": "Correlation incident B",
            "workspace_id": "ws-root-cause",
            "source_correlation_id": "corr-root-1",
            "source_system": "dq-engine",
            "failure_code": "worker_crash",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert create_two.status_code == 201, create_two.text
    incident_two_id = create_two.json()["incident"]["id"]

    create_suggestion = c.post(
        "/rulebuilder/v1/incidents/root-cause-suggestions",
        json={"incident_ids": [incident_one_id, incident_two_id]},
        headers=_auth_headers("dq:rules:edit"),
    )
    assert create_suggestion.status_code == 201, create_suggestion.text
    suggestion = create_suggestion.json()["root_cause_suggestion"]
    assert suggestion["incident_count"] == 2
    assert suggestion["status"] == "pending"
    assert suggestion["suggested_root_cause"]["kind"] == "shared_source_correlation"
    assert suggestion["suggested_root_cause"]["summary"]

    list_response = c.get(
        "/rulebuilder/v1/incidents/root-cause-suggestions?workspace_id=ws-root-cause",
        headers=_auth_headers("dq:rules:read"),
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["count"] == 1
    assert list_response.json()["root_cause_suggestions"][0]["id"] == suggestion["id"]

    detail_response = c.get(
        f"/rulebuilder/v1/incidents/root-cause-suggestions/{suggestion['id']}",
        headers=_auth_headers("dq:rules:read"),
    )
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["root_cause_suggestion"]["id"] == suggestion["id"]

    accept_response = c.post(
        f"/rulebuilder/v1/incidents/root-cause-suggestions/{suggestion['id']}/accept",
        headers=_auth_headers("dq:rules:edit"),
    )
    assert accept_response.status_code == 200, accept_response.text
    assert accept_response.json()["root_cause_suggestion"]["status"] == "accepted"

    reject_suggestion = c.post(
        "/rulebuilder/v1/incidents/root-cause-suggestions",
        json={"incident_ids": [incident_one_id, incident_two_id]},
        headers=_auth_headers("dq:rules:edit"),
    )
    reject_suggestion_id = reject_suggestion.json()["root_cause_suggestion"]["id"]
    reject_response = c.post(
        f"/rulebuilder/v1/incidents/root-cause-suggestions/{reject_suggestion_id}/reject",
        headers=_auth_headers("dq:rules:edit"),
    )
    assert reject_response.status_code == 200, reject_response.text
    assert reject_response.json()["root_cause_suggestion"]["status"] == "rejected"


def test_root_cause_assistance_request_includes_suggestion(client, monkeypatch):
    c, _ = client
    from app.core.dependencies import get_admin_repository
    from app.core.dependencies import get_app_config_repository
    from app.main import app

    app.dependency_overrides[get_app_config_repository] = lambda: SimpleNamespace(get_app_config=lambda: SimpleNamespace())
    app.dependency_overrides[get_admin_repository] = lambda: SimpleNamespace(
        get_current_user=lambda user_id, claims: SimpleNamespace(email="ops@example.com", granted_scopes=[]) if user_id else None,
    )

    try:
        create_one = c.post(
            "/rulebuilder/v1/incidents",
            json={
                "incident_kind": "technical_run_error",
                "title": "Support incident A",
                "workspace_id": "ws-support",
                "source_correlation_id": "corr-support-1",
                "source_system": "dq-engine",
                "failure_code": "worker_crash",
            },
            headers=_auth_headers("dq:rules:edit"),
        )
        create_two = c.post(
            "/rulebuilder/v1/incidents",
            json={
                "incident_kind": "technical_run_error",
                "title": "Support incident B",
                "workspace_id": "ws-support",
                "source_correlation_id": "corr-support-1",
                "source_system": "dq-engine",
                "failure_code": "worker_crash",
            },
            headers=_auth_headers("dq:rules:edit"),
        )
        incident_one_id = create_one.json()["incident"]["id"]
        incident_two_id = create_two.json()["incident"]["id"]
        create_suggestion = c.post(
            "/rulebuilder/v1/incidents/root-cause-suggestions",
            json={"incident_ids": [incident_one_id, incident_two_id]},
            headers=_auth_headers("dq:rules:edit"),
        )
        suggestion_id = create_suggestion.json()["root_cause_suggestion"]["id"]

        from app.api.v1.endpoints import incidents as incidents_api
        from app.api.v1.endpoints.support import SupportRequestResponseView

        async def _fake_create_support_request(request, request_view, app_config_repository, admin_repository):
            assert request_view.source == "incident_root_cause_suggestion"
            assert request_view.details["incident_ids"] == [incident_one_id, incident_two_id]
            assert request_view.details["suggestion"]["title"] == "Shared source correlation chain"
            assert request_view.metadata["suggestion_id"] == suggestion_id
            return SupportRequestResponseView(
                referenceId="SUP-ROOTCAUSE01",
                correlationId="corr-support-request-1",
                deliveryModes=["itsm"],
                message="Assistance request sent to Zammad ticket ZAM-4321.",
                ticketNumber="ZAM-4321",
                ticketSystem="Zammad",
                ticketUrl="https://zammad.example/tickets/4321",
            )

        monkeypatch.setattr(incidents_api, "create_support_request", _fake_create_support_request)

        assistance_response = c.post(
            f"/rulebuilder/v1/incidents/root-cause-suggestions/{suggestion_id}/assistance-request",
            headers=_auth_headers("dq:rules:edit"),
        )
        assert assistance_response.status_code == 200, assistance_response.text
        body = assistance_response.json()
        assert body["support_request"]["ticket_number"] == "ZAM-4321"
        assert body["root_cause_suggestion"]["assistance_request_reference_id"] == "SUP-ROOTCAUSE01"
        assert body["root_cause_suggestion"]["assistance_request_ticket_number"] == "ZAM-4321"
        assert body["root_cause_suggestion"]["assistance_requested_at"]
    finally:
        app.dependency_overrides.pop(get_app_config_repository, None)
        app.dependency_overrides.pop(get_admin_repository, None)


# ---------------------------------------------------------------------------
# Presenter unit tests — Zammad ticket payload distinction
# ---------------------------------------------------------------------------


def test_technical_incident_zammad_payload_title():
    from app.api.presenters.support import build_zammad_incident_ticket_payload

    incident = IncidentEntity(
        id="inc-tech",
        incident_kind=INCIDENT_KIND_TECHNICAL,
        title="Engine crash",
        run_id="run-X",
        scope_id="asset-Y",
        source_correlation_id="corr-source-1",
        source_parent_correlation_id="corr-parent-1",
        source_request_id="req-1",
        source_queue_message_id="queue-1",
        source_trace_id="trace-1",
        source_system="dq-engine",
        failure_code="py4j_error",
        failure_message="Connection refused",
    )
    payload = build_zammad_incident_ticket_payload(
        incident, "corr-1", requester_email="ops@example.com"
    )
    assert payload["title"].startswith("[Technical]")
    assert payload["priority"] == "3 high"
    assert "py4j_error" in payload["article"]["body"]
    assert "Connection refused" in payload["article"]["body"]
    assert "Source correlation ID: corr-source-1" in payload["article"]["body"]
    assert "Parent correlation ID: corr-parent-1" in payload["article"]["body"]
    assert "Trace ID: trace-1" in payload["article"]["body"]


def test_functional_incident_zammad_payload_title():
    from app.api.presenters.support import build_zammad_incident_ticket_payload

    incident = IncidentEntity(
        id="inc-func",
        incident_kind=INCIDENT_KIND_FUNCTIONAL,
        title="Rule violation",
        scope_id="asset-Z",
        violation_count=55,
        violated_rule_ids=["rule-A"],
        severity="high",
    )
    payload = build_zammad_incident_ticket_payload(
        incident, "corr-2", requester_email="ops@example.com"
    )
    assert payload["title"].startswith("[Functional]")
    assert "55 violations" in payload["title"]
    assert payload["priority"] == "3 high"
    assert "rule-A" in payload["article"]["body"]


def test_functional_incident_low_severity_priority():
    from app.api.presenters.support import build_zammad_incident_ticket_payload

    incident = IncidentEntity(
        id="inc-low",
        incident_kind=INCIDENT_KIND_FUNCTIONAL,
        title="Minor violation",
        scope_id="asset-Q",
        violation_count=1,
        severity="low",
    )
    payload = build_zammad_incident_ticket_payload(
        incident, "corr-3", requester_email="ops@example.com"
    )
    assert payload["priority"] == "2 normal"


def test_incident_zammad_payload_includes_routing_metadata():
    from app.api.presenters.support import build_zammad_incident_ticket_payload

    incident = IncidentEntity(
        id="inc-route",
        incident_kind=INCIDENT_KIND_TECHNICAL,
        title="Engine crash",
        run_id="run-route",
        assigned_to="engine-on-call",
    )
    payload = build_zammad_incident_ticket_payload(
        incident,
        "corr-route",
        requester_email="ops@example.com",
        assigned_to="engine-on-call",
        escalation_label="engine-on-call",
        escalate_after_minutes=15,
    )
    assert payload["article"]["body"].endswith(
        "Assigned to: engine-on-call\n\nEscalation: engine-on-call, escalate after 15 minutes"
    )
