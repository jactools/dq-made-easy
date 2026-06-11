from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import app.infrastructure.repositories.postgres_gx_run_plan_repository as repo_module
from app.infrastructure.repositories.postgres_gx_run_plan_repository import _append_transition_event
from app.infrastructure.repositories.postgres_gx_run_plan_repository import _format_iso_datetime
from app.infrastructure.repositories.postgres_gx_run_plan_repository import _parse_iso_datetime
from app.infrastructure.repositories.postgres_gx_run_plan_repository import _select_pending_version
from app.infrastructure.repositories.postgres_gx_run_plan_repository import _serialize_transition_event
from app.infrastructure.repositories.postgres_gx_run_plan_repository import PostgresGxRunPlanRepository


class _SessionCtx:
    def __init__(self, session: object) -> None:
        self._session = session

    def __enter__(self) -> object:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False


def test_select_pending_version_returns_last_pending() -> None:
    versions = [
        {"runPlanVersionId": "v1", "governanceState": "draft"},
        {"runPlanVersionId": "v2", "governanceState": "pending_review"},
        {"runPlanVersionId": "v3", "governanceState": "pending_validation"},
    ]

    pending = _select_pending_version(versions)

    assert pending is not None
    assert pending["runPlanVersionId"] == "v3"


def test_select_pending_version_returns_none_when_absent() -> None:
    versions = [
        {"runPlanVersionId": "v1", "governanceState": "active"},
        {"runPlanVersionId": "v2", "governanceState": "deactivated"},
    ]
    assert _select_pending_version(versions) is None


def test_parse_and_format_iso_datetime_roundtrip() -> None:
    parsed = _parse_iso_datetime("2026-04-25T10:30:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert _format_iso_datetime(parsed).startswith("2026-04-25T10:30:00")
    assert _parse_iso_datetime("   ") is None
    assert _format_iso_datetime(None) is None


def test_serialize_transition_event_helpers() -> None:
    now = datetime(2026, 4, 25, 10, 30, tzinfo=UTC)
    row = SimpleNamespace(
        id="tr-1",
        run_plan_id="rp-1",
        run_plan_version_id="v-1",
        action="transitioned",
        from_state="draft",
        to_state="pending_validation",
        actor_id="user-a",
        correlation_id="corr-1",
        effective_from=now,
        details_json={"k": "v"},
        occurred_at=now,
    )

    payload_a = _serialize_transition_event(row)
    payload_b = PostgresGxRunPlanRepository._serialize_transition_event(row)

    assert payload_a["runPlanId"] == "rp-1"
    assert payload_a["details"] == {"k": "v"}
    assert payload_b["toState"] == "pending_validation"


def test_append_transition_event_adds_row() -> None:
    added: list[object] = []
    session = SimpleNamespace(add=lambda item: added.append(item))

    _append_transition_event(
        session,
        run_plan_id="rp-1",
        run_plan_version_id="v-1",
        action="activated",
        from_state="approved_pending_activation",
        to_state="active",
        actor_id="user-a",
        correlation_id="corr-1",
        details={"dispatch": "run-1"},
    )

    assert len(added) == 1
    row = added[0]
    assert row.run_plan_id == "rp-1"
    assert row.run_plan_version_id == "v-1"
    assert row.action == "activated"
    assert row.to_state == "active"
    assert row.details_json == {"dispatch": "run-1"}


def test_serialize_version_and_plan_include_pending_fields() -> None:
    repo = PostgresGxRunPlanRepository("postgresql://unused")
    now = datetime(2026, 4, 25, 10, 30, tzinfo=UTC)
    row = SimpleNamespace(
        id="rp-1",
        business_key="rk-1",
        workspace_id="ws-1",
        scope_selector_json={"scope": "all"},
        planning_mode="single_suite",
        current_active_version_id="v-active",
        status="active",
        created_by="user-a",
        created_at=now,
        updated_at=now,
        activated_by="user-a",
        activated_at=now,
        last_dispatched_run_id="run-11",
    )
    version_rows = [
        SimpleNamespace(
            id="v-1",
            run_plan_id="rp-1",
            governance_state="pending_validation",
            gx_suite_selection_json={"selector": "a"},
            suite_id="suite-a",
            suite_version=1,
            suite_snapshot_json={"snapshot": 1},
            execution_contract_snapshot_json={"engine_target": "pyspark"},
            schedule_definition_json={"cron": "* * * * *"},
            validation_status="pending",
            review_status=None,
            effective_from=now,
            supersedes_version_id=None,
            created_by="user-a",
            created_at=now,
        ),
        SimpleNamespace(
            id="v-active",
            run_plan_id="rp-1",
            governance_state="active",
            gx_suite_selection_json={"selector": "b"},
            suite_id="suite-b",
            suite_version=2,
            suite_snapshot_json=None,
            execution_contract_snapshot_json=None,
            schedule_definition_json={"cron": "*/5 * * * *"},
            validation_status="passed",
            review_status="approved",
            effective_from=now,
            supersedes_version_id="v-1",
            created_by="user-a",
            created_at=now,
        ),
    ]
    transition_rows = [
        SimpleNamespace(
            id="tr-1",
            run_plan_id="rp-1",
            run_plan_version_id="v-1",
            action="created",
            from_state=None,
            to_state="pending_validation",
            actor_id="user-a",
            correlation_id="corr-1",
            effective_from=now,
            details_json={"k": "v"},
            occurred_at=now,
        )
    ]

    payload = repo._serialize_plan(row, version_rows, transition_rows)

    assert payload["runPlanId"] == "rp-1"
    assert payload["pendingVersionId"] == "v-1"
    assert payload["pendingVersionGovernanceState"] == "pending_validation"
    assert len(payload["versions"]) == 2
    assert payload["versions"][0]["suiteSnapshot"] == {"snapshot": 1}
    assert payload["transitionEvents"][0]["action"] == "created"


@pytest.mark.anyio
async def test_create_plan_raises_when_run_plan_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = PostgresGxRunPlanRepository("postgresql://unused")
    session = SimpleNamespace(get=lambda model, obj_id: object(), add=lambda row: None, commit=lambda: None)
    monkeypatch.setattr(repo_module, "session_scope", lambda url: _SessionCtx(session))

    with pytest.raises(ValueError, match="already exists"):
        await repo.create_plan(
            run_plan_id="rp-1",
            run_plan_version_id="v-1",
            workspace_id="ws-1",
            scope_selector=SimpleNamespace(model_dump=lambda **kwargs: {"scope": "all"}),
            planning_mode="single_suite",
            status="draft",
            created_by="user-a",
            gx_suite_selection=SimpleNamespace(model_dump=lambda **kwargs: {"selector": "a"}),
            suite_id="suite-a",
            suite_version=1,
            suite_snapshot=None,
            execution_contract_snapshot=None,
            schedule_definition=SimpleNamespace(model_dump=lambda **kwargs: {"cron": "* * * * *"}),
        )


@pytest.mark.anyio
async def test_create_plan_version_raises_when_plan_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = PostgresGxRunPlanRepository("postgresql://unused")
    session = SimpleNamespace(get=lambda model, obj_id: None)
    monkeypatch.setattr(repo_module, "session_scope", lambda url: _SessionCtx(session))

    with pytest.raises(ValueError, match="not found"):
        await repo.create_plan_version(
            run_plan_id="rp-missing",
            run_plan_version_id="v-1",
            gx_suite_selection=SimpleNamespace(model_dump=lambda **kwargs: {}),
            suite_id=None,
            suite_version=None,
            suite_snapshot=None,
            execution_contract_snapshot=None,
            schedule_definition=SimpleNamespace(model_dump=lambda **kwargs: {}),
            created_by="user-a",
        )


@pytest.mark.anyio
async def test_transition_plan_version_raises_for_invalid_state_and_missing_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = PostgresGxRunPlanRepository("postgresql://unused")

    # Missing plan
    missing_plan_session = SimpleNamespace(get=lambda model, obj_id: None)
    monkeypatch.setattr(repo_module, "session_scope", lambda url: _SessionCtx(missing_plan_session))
    with pytest.raises(ValueError, match="run plan 'rp-1' not found"):
        await repo.transition_plan_version(
            run_plan_id="rp-1",
            run_plan_version_id="v-1",
            target_state="pending_review",
            updated_by="user-a",
        )

    # Missing version
    plan_row = SimpleNamespace(id="rp-1")
    missing_version_session = SimpleNamespace(get=lambda model, obj_id: plan_row if obj_id == "rp-1" else None)
    monkeypatch.setattr(repo_module, "session_scope", lambda url: _SessionCtx(missing_version_session))
    with pytest.raises(ValueError, match="version 'v-1' not found"):
        await repo.transition_plan_version(
            run_plan_id="rp-1",
            run_plan_version_id="v-1",
            target_state="pending_review",
            updated_by="user-a",
        )

    # Invalid transition
    version_row = SimpleNamespace(run_plan_id="rp-1", governance_state="draft")

    def _get_for_invalid(model, obj_id):
        if obj_id == "rp-1":
            return SimpleNamespace(id="rp-1")
        return version_row

    invalid_transition_session = SimpleNamespace(get=_get_for_invalid)
    monkeypatch.setattr(repo_module, "session_scope", lambda url: _SessionCtx(invalid_transition_session))
    monkeypatch.setattr(repo_module, "is_valid_run_plan_version_transition", lambda current, target: False)
    with pytest.raises(ValueError, match="Invalid GX run plan version transition"):
        await repo.transition_plan_version(
            run_plan_id="rp-1",
            run_plan_version_id="v-1",
            target_state="approved_pending_activation",
            updated_by="user-a",
        )


@pytest.mark.anyio
async def test_activate_and_deactivate_enforce_required_states(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = PostgresGxRunPlanRepository("postgresql://unused")

    plan_row = SimpleNamespace(id="rp-1", current_active_version_id=None)
    not_approved_version = SimpleNamespace(run_plan_id="rp-1", governance_state="draft")

    def _activate_get(model, obj_id):
        if obj_id == "rp-1":
            return plan_row
        return not_approved_version

    activate_session = SimpleNamespace(get=_activate_get)
    monkeypatch.setattr(repo_module, "session_scope", lambda url: _SessionCtx(activate_session))

    with pytest.raises(ValueError, match="not approved for activation"):
        await repo.activate_plan(
            run_plan_id="rp-1",
            run_plan_version_id="v-1",
            activated_by="user-a",
        )

    not_pending_deactivation = SimpleNamespace(run_plan_id="rp-1", governance_state="active")

    def _deactivate_get(model, obj_id):
        if obj_id == "rp-1":
            return SimpleNamespace(id="rp-1", current_active_version_id="v-1")
        return not_pending_deactivation

    deactivate_session = SimpleNamespace(get=_deactivate_get)
    monkeypatch.setattr(repo_module, "session_scope", lambda url: _SessionCtx(deactivate_session))

    with pytest.raises(ValueError, match="not pending deactivation"):
        await repo.deactivate_plan(
            run_plan_id="rp-1",
            run_plan_version_id="v-1",
            deactivated_by="user-a",
        )