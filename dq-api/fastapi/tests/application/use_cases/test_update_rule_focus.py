from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.use_cases.rule_mutation import RuleMutationCommand
from app.application.use_cases.update_rule import update_rule

update_rule_module = importlib.import_module("app.application.use_cases.update_rule")


class _FakeRulesRepository:
    def __init__(self, rows: list[object], updated_payload: object | None = None, update_error: Exception | None = None) -> None:
        self.rows = rows
        self.updated_payload = updated_payload
        self.update_error = update_error
        self.list_calls: list[dict[str, object]] = []
        self.update_calls: list[dict[str, object]] = []

    async def list_rule_records(self, **kwargs: object) -> list[object]:
        self.list_calls.append(dict(kwargs))
        return self.rows

    async def update_rule_record(self, **kwargs: object) -> object | None:
        self.update_calls.append(dict(kwargs))
        if self.update_error is not None:
            raise self.update_error
        return self.updated_payload


def _command() -> RuleMutationCommand:
    return RuleMutationCommand(
        name="Rule name",
        description="Rule description",
        dimension="completeness",
        workspace=None,
        workspace_id=None,
        dsl={},
    )


def _patch_resolver(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]) -> None:
    async def _resolve_rule_mutation_payload(**kwargs: object) -> dict[str, object]:
        return dict(payload)

    monkeypatch.setattr(update_rule_module, "resolve_rule_mutation_payload", _resolve_rule_mutation_payload)


@pytest.mark.anyio
async def test_update_rule_raises_not_found_for_missing_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _FakeRulesRepository(rows=[])

    with pytest.raises(HTTPException) as exc_info:
        await update_rule(
            "rule-1",
            _command(),
            repository,
            config_repository=object(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
        )

    assert exc_info.value.status_code == 404
    assert "Rule 'rule-1' not found" in str(exc_info.value.detail)
    assert repository.update_calls == []


@pytest.mark.anyio
async def test_update_rule_rejects_approved_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _FakeRulesRepository(rows=[SimpleNamespace(id="rule-1", workspace="default", last_approval_status="approved", active=False)])

    with pytest.raises(HTTPException) as exc_info:
        await update_rule(
            "rule-1",
            _command(),
            repository,
            config_repository=object(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
        )

    assert exc_info.value.status_code == 409
    assert "can no longer be changed" in str(exc_info.value.detail)
    assert repository.update_calls == []


@pytest.mark.anyio
async def test_update_rule_rejects_active_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _FakeRulesRepository(rows=[SimpleNamespace(id="rule-1", workspace="default", last_approval_status=None, active=True)])

    with pytest.raises(HTTPException) as exc_info:
        await update_rule(
            "rule-1",
            _command(),
            repository,
            config_repository=object(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
        )

    assert exc_info.value.status_code == 409
    assert repository.update_calls == []


@pytest.mark.anyio
async def test_update_rule_uses_existing_workspace_and_updates_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _FakeRulesRepository(
        rows=[SimpleNamespace(id="rule-1", workspace="default", last_approval_status=None, active=False)],
        updated_payload=SimpleNamespace(to_payload=lambda: {"id": "rule-1", "status": "updated"}),
    )
    seen: dict[str, object] = {}

    async def _resolve_rule_mutation_payload(**kwargs: object) -> dict[str, object]:
        seen.update(
            {
                "workspace_id": kwargs["workspace_id"],
                "exclude_rule_id": kwargs["exclude_rule_id"],
                "actor_id": kwargs["actor_id"],
            }
        )
        return {
            "name": kwargs["command"].name,
            "description": kwargs["command"].description,
            "expression": "compiled expression",
            "dimension": kwargs["command"].dimension,
            "active": False,
            "dsl": {},
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "manual_override_by": None,
            "manual_override_at": None,
            "check_type": None,
            "check_type_params": None,
        }

    monkeypatch.setattr(update_rule_module, "resolve_rule_mutation_payload", _resolve_rule_mutation_payload)

    payload = await update_rule(
        "rule-1",
        _command(),
        repository,
        config_repository=object(),
        catalog_repository=object(),
        contract_resolver=object(),
        actor_id="user-1",
    )

    assert payload == {"id": "rule-1", "status": "updated"}
    assert seen == {
        "workspace_id": "default",
        "exclude_rule_id": "rule-1",
        "actor_id": "user-1",
    }
    assert repository.update_calls == [
        {
            "rule_id": "rule-1",
            "name": "Rule name",
            "description": "Rule description",
            "expression": "compiled expression",
            "dimension": "completeness",
            "active": False,
            "dsl": {},
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "manual_override_by": None,
            "manual_override_at": None,
            "check_type": None,
            "check_type_params": None,
        }
    ]


@pytest.mark.anyio
async def test_update_rule_raises_not_found_when_repository_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _FakeRulesRepository(
        rows=[SimpleNamespace(id="rule-1", workspace="default", last_approval_status=None, active=False)],
        updated_payload=None,
    )
    _patch_resolver(
        monkeypatch,
        {
            "name": "Rule name",
            "description": "Rule description",
            "expression": "compiled expression",
            "dimension": "completeness",
            "active": False,
            "dsl": {},
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "manual_override_by": None,
            "manual_override_at": None,
            "check_type": None,
            "check_type_params": None,
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_rule(
            "rule-1",
            _command(),
            repository,
            config_repository=object(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
        )

    assert exc_info.value.status_code == 404
    assert "Rule 'rule-1' not found" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_update_rule_maps_value_error_to_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = _FakeRulesRepository(
        rows=[SimpleNamespace(id="rule-1", workspace="default", last_approval_status=None, active=False)],
        update_error=ValueError("duplicate rule name"),
    )
    _patch_resolver(
        monkeypatch,
        {
            "name": "Rule name",
            "description": "Rule description",
            "expression": "compiled expression",
            "dimension": "completeness",
            "active": False,
            "dsl": {},
            "join_conditions": [],
            "alias_mappings": {},
            "reusable_join_id": None,
            "reusable_filter_ids": [],
            "manual_override_by": None,
            "manual_override_at": None,
            "check_type": None,
            "check_type_params": None,
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_rule(
            "rule-1",
            _command(),
            repository,
            config_repository=object(),
            catalog_repository=object(),
            contract_resolver=object(),
            actor_id="user-1",
        )

    assert exc_info.value.status_code == 409
    assert "duplicate rule name" in str(exc_info.value.detail)
