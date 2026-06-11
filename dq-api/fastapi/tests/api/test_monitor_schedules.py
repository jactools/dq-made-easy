"""Tests for monitor schedule endpoints (DQ-12.AC-01)."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.domain.entities.monitor_schedule import MonitorScheduleEntity
from app.infrastructure.repositories.in_memory_monitor_schedule_repository import (
    InMemoryMonitorScheduleRepository,
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
# InMemoryMonitorScheduleRepository unit tests
# ---------------------------------------------------------------------------


def test_upsert_and_get_schedule():
    repo = InMemoryMonitorScheduleRepository()
    entity = MonitorScheduleEntity(
        id="",
        scope_kind="data_asset",
        scope_id="asset-1",
        workspace_id="ws-1",
        cron_expression="0 6 * * *",
    )
    saved = repo.upsert_monitor_schedule(entity)
    assert saved.scope_kind == "data_asset"
    assert saved.scope_id == "asset-1"
    assert saved.cron_expression == "0 6 * * *"
    assert saved.id  # auto-generated

    fetched = repo.get_monitor_schedule("data_asset", "asset-1")
    assert fetched is not None
    assert fetched.id == saved.id


def test_upsert_overwrites_existing():
    repo = InMemoryMonitorScheduleRepository()
    entity = MonitorScheduleEntity(
        id="",
        scope_kind="data_asset",
        scope_id="asset-1",
        workspace_id="ws-1",
        cron_expression="0 6 * * *",
    )
    repo.upsert_monitor_schedule(entity)

    updated = MonitorScheduleEntity(
        id="",
        scope_kind="data_asset",
        scope_id="asset-1",
        workspace_id="ws-1",
        cron_expression="0 12 * * *",
    )
    saved2 = repo.upsert_monitor_schedule(updated)
    assert saved2.cron_expression == "0 12 * * *"

    all_rows = repo.list_monitor_schedules()
    assert len(all_rows) == 1


def test_list_schedules_filtered_by_workspace():
    repo = InMemoryMonitorScheduleRepository()
    for scope_id, ws in [("a1", "ws-1"), ("a2", "ws-2"), ("a3", "ws-1")]:
        repo.upsert_monitor_schedule(
            MonitorScheduleEntity(
                id="",
                scope_kind="data_asset",
                scope_id=scope_id,
                workspace_id=ws,
                cron_expression="0 6 * * *",
            )
        )
    ws1_rows = repo.list_monitor_schedules(workspace_id="ws-1")
    assert len(ws1_rows) == 2
    assert all(r.workspace_id == "ws-1" for r in ws1_rows)


def test_delete_schedule():
    repo = InMemoryMonitorScheduleRepository()
    entity = MonitorScheduleEntity(
        id="",
        scope_kind="source_dataset",
        scope_id="ds-1",
        workspace_id="ws-1",
        cron_expression="0 0 * * *",
    )
    repo.upsert_monitor_schedule(entity)
    assert repo.get_monitor_schedule("source_dataset", "ds-1") is not None

    repo.delete_monitor_schedule("source_dataset", "ds-1")
    assert repo.get_monitor_schedule("source_dataset", "ds-1") is None


def test_delete_nonexistent_is_silent():
    repo = InMemoryMonitorScheduleRepository()
    repo.delete_monitor_schedule("data_asset", "nonexistent")  # must not raise


def test_get_nonexistent_returns_none():
    repo = InMemoryMonitorScheduleRepository()
    assert repo.get_monitor_schedule("data_asset", "nonexistent") is None


# ---------------------------------------------------------------------------
# HTTP endpoint tests (with TestClient + dependency override)
# ---------------------------------------------------------------------------


@pytest.fixture()
def schedule_repo():
    return InMemoryMonitorScheduleRepository()


@pytest.fixture()
def client(schedule_repo, monkeypatch):
    from app.main import app
    from app.core.config import get_settings
    from app.core.dependencies import get_monitor_schedule_repository

    monkeypatch.setenv("SSO_ENABLED", "true")
    monkeypatch.setenv("SSO_PUBLIC_ISSUER_URL", "http://keycloak.local:8080/realms/jaccloud")
    monkeypatch.setenv("SSO_CLIENT_ID", "dq-rules-ui")
    get_settings.cache_clear()
    app.dependency_overrides[get_monitor_schedule_repository] = lambda: schedule_repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_monitor_schedule_repository, None)
    get_settings.cache_clear()


def test_list_schedules_empty(client):
    resp = client.get("/rulebuilder/v1/governance/monitor-schedules", headers=_auth_headers("dq:rules:read"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["monitor_schedules"] == []


def test_put_and_list_schedule(client):
    resp = client.put(
        "/rulebuilder/v1/governance/monitor-schedules",
        json={
            "scope_kind": "data_asset",
            "scope_id": "asset-42",
            "workspace_id": "ws-x",
            "cron_expression": "0 8 * * *",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 200
    body = resp.json()
    schedules = body["monitor_schedules"]
    assert len(schedules) == 1
    assert schedules[0]["scope_id"] == "asset-42"
    assert schedules[0]["cron_expression"] == "0 8 * * *"

    list_resp = client.get("/rulebuilder/v1/governance/monitor-schedules", headers=_auth_headers("dq:rules:read"))
    assert list_resp.status_code == 200
    assert len(list_resp.json()["monitor_schedules"]) == 1


def test_put_invalid_scope_kind(client):
    resp = client.put(
        "/rulebuilder/v1/governance/monitor-schedules",
        json={
            "scope_kind": "bad_kind",
            "scope_id": "x",
            "workspace_id": "ws-x",
            "cron_expression": "0 0 * * *",
        },
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "invalid_scope_kind"


def test_delete_schedule_endpoint(client, schedule_repo):
    schedule_repo.upsert_monitor_schedule(
        MonitorScheduleEntity(
            id="",
            scope_kind="source_dataset",
            scope_id="ds-99",
            workspace_id="ws-y",
            cron_expression="0 0 * * 0",
        )
    )
    resp = client.delete("/rulebuilder/v1/governance/monitor-schedules/source_dataset/ds-99", headers=_auth_headers("dq:rules:edit"))
    assert resp.status_code == 204

    assert schedule_repo.get_monitor_schedule("source_dataset", "ds-99") is None


def test_delete_invalid_scope_kind_endpoint(client):
    resp = client.delete("/rulebuilder/v1/governance/monitor-schedules/wrong/ds-1", headers=_auth_headers("dq:rules:edit"))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET by-scope
# ---------------------------------------------------------------------------


def test_get_by_scope_found(client, schedule_repo):
    schedule_repo.upsert_monitor_schedule(
        MonitorScheduleEntity(
            id="",
            scope_kind="data_asset",
            scope_id="asset-7",
            workspace_id="ws-a",
            cron_expression="0 3 * * 1",
        )
    )
    resp = client.get(
        "/rulebuilder/v1/governance/monitor-schedules/data_asset/asset-7",
        headers=_auth_headers("dq:rules:read"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "monitor_schedule" in body
    assert body["monitor_schedule"]["scope_id"] == "asset-7"
    assert body["monitor_schedule"]["cron_expression"] == "0 3 * * 1"


def test_get_by_scope_not_found(client):
    resp = client.get(
        "/rulebuilder/v1/governance/monitor-schedules/data_asset/nonexistent",
        headers=_auth_headers("dq:rules:read"),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "monitor_schedule_not_found"


def test_get_by_scope_invalid_scope_kind(client):
    resp = client.get(
        "/rulebuilder/v1/governance/monitor-schedules/bad_kind/some-id",
        headers=_auth_headers("dq:rules:read"),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "invalid_scope_kind"


# ---------------------------------------------------------------------------
# Cron expression validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cron", [
    "0 6 * * *",
    "*/15 * * * *",
    "0 0 1 1 *",
    "0 12 * * 1-5",
    "30 8 * * MON",
    "0 6 * JAN *",
    "0,30 * * * *",
])
def test_valid_cron_expressions(client, cron):
    resp = client.put(
        "/rulebuilder/v1/governance/monitor-schedules",
        json={"scope_kind": "data_asset", "scope_id": "x", "workspace_id": "w", "cron_expression": cron},
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 200, f"Expected 200 for cron={cron!r}, got {resp.status_code}: {resp.text}"


@pytest.mark.parametrize("cron,expected_error", [
    ("0 6 * *", "exactly 5"),
    ("0 6 * * * *", "exactly 5"),
    ("60 6 * * *", "out of range"),
    ("0 25 * * *", "out of range"),
    ("0 6 0 * *", "out of range"),
    ("0 6 * 13 *", "out of range"),
    ("0 6 * * 8", "out of range"),
    ("abc 6 * * *", "invalid syntax"),
])
def test_invalid_cron_expressions(client, cron, expected_error):
    resp = client.put(
        "/rulebuilder/v1/governance/monitor-schedules",
        json={"scope_kind": "data_asset", "scope_id": "x", "workspace_id": "w", "cron_expression": cron},
        headers=_auth_headers("dq:rules:edit"),
    )
    assert resp.status_code == 422, f"Expected 422 for cron={cron!r}, got {resp.status_code}"
    detail = resp.json()["detail"]
    assert detail["error"] == "invalid_cron_expression"
    assert expected_error in detail["message"], f"Expected {expected_error!r} in {detail['message']!r}"
