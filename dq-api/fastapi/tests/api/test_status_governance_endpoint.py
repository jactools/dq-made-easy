from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import status_governance

pytestmark = pytest.mark.usefixtures("clone_payload")


@pytest.mark.anyio
async def test_status_model_for_rule_returns_values_and_transitions(monkeypatch) -> None:
    monkeypatch.setattr(status_governance, "get_scopes", lambda: ("dq:rules:activate", "dq:rules:approve"))

    payload = await status_governance.get_status_model("rule")

    assert payload.entity == "rule"
    assert any(item.value == "draft" for item in payload.statuses)
    assert any(item.toStatus == "activated" for item in payload.transitions)
    assert any(item.toStatus == "deactivated" for item in payload.transitions)
    assert any(item.toStatus == "removed" for item in payload.transitions)
    assert any(item.toStatus == "recovered" for item in payload.transitions)
    assert isinstance(payload.allowedTransitionsByStatus, dict)


@pytest.mark.anyio
async def test_status_model_filters_allowed_transitions_by_scope(monkeypatch) -> None:
    monkeypatch.setattr(status_governance, "get_scopes", lambda: ("dq:rules:read",))

    payload = await status_governance.get_status_model("rule")

    assert payload.allowedTransitionsByStatus == {}


@pytest.mark.anyio
async def test_status_model_rejects_unknown_entity() -> None:
    with pytest.raises(HTTPException) as error:
        await status_governance.get_status_model("not-supported")

    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_status_model_for_run_plan_returns_values_and_transitions(monkeypatch) -> None:
    monkeypatch.setattr(status_governance, "get_scopes", lambda: ("dq:rules:approve", "dq:rules:write"))

    payload = await status_governance.get_status_model("run_plan")

    assert payload.entity == "run_plan"
    assert any(item.value == "inactive" for item in payload.statuses)
    assert any(item.toStatus == "activation-requested" for item in payload.transitions)
    assert payload.allowedTransitionsByStatus["inactive"] == ["activation-requested"]


@pytest.mark.anyio
async def test_status_model_for_rule_lifecycle_returns_values_and_transitions(monkeypatch) -> None:
    monkeypatch.setattr(status_governance, "get_scopes", lambda: ("dq:rules:write",))

    payload = await status_governance.get_status_model("rule_lifecycle")

    assert payload.entity == "rule_lifecycle"
    assert [item.value for item in payload.statuses] == ["active", "deprecated", "superseded", "retired"]
    assert payload.allowedTransitionsByStatus["active"] == ["deprecated", "superseded", "retired"]
    assert payload.allowedTransitionsByStatus["deprecated"] == ["active", "superseded", "retired"]
    assert payload.allowedTransitionsByStatus["superseded"] == ["retired"]


@pytest.mark.anyio
async def test_status_model_for_connector_sync_job_returns_values_and_transitions(monkeypatch) -> None:
    monkeypatch.setattr(status_governance, "get_scopes", lambda: ())

    payload = await status_governance.get_status_model("connector_sync_job")

    assert payload.entity == "connector_sync_job"
    assert [item.value for item in payload.statuses] == ["queued", "running", "completed", "failed", "cancelled"]
    assert payload.allowedTransitionsByStatus["queued"] == ["running", "failed", "cancelled"]
    assert payload.allowedTransitionsByStatus["running"] == ["completed", "failed", "cancelled"]
