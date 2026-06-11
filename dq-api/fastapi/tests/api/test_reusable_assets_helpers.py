from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import reusable_assets


class _RulesRepoStub:
    def __init__(self) -> None:
        self.last_filter_kwargs: dict | None = None
        self.last_join_kwargs: dict | None = None
        self.deleted_filter_id: str | None = None
        self.deleted_join_id: str | None = None
        self.reusable_filter_row: dict | None = {
            "id": "rf-1",
            "name": "Filter A",
            "description": "desc",
            "filter_expression": "status = 'ACTIVE'",
            "active": True,
        }
        self.reusable_join_row: dict | None = {
            "id": "rj-1",
            "name": "Join A",
            "description": "desc",
            "join_definition": '{"joinType": "inner", "conditions": [{"leftDataObjectId": "orders", "leftAttributeId": "customer_id", "rightDataObjectId": "customers", "rightAttributeId": "id", "operator": "="}]}',
            "active": True,
        }

    async def list_reusable_filters(self, workspace: str | None = None, query: str | None = None) -> list[dict]:
        return [{"id": "rf-1", "workspace": workspace, "query": query}]

    async def create_reusable_filter(self, **kwargs) -> dict:
        self.last_filter_kwargs = kwargs
        return {"id": "rf-1", **kwargs}

    async def delete_reusable_filter(self, filter_id: str) -> bool:
        self.deleted_filter_id = filter_id
        return True

    async def get_reusable_filter(self, filter_id: str) -> dict | None:
        if self.reusable_filter_row is None:
            return None
        return {**self.reusable_filter_row, "id": filter_id}

    async def update_reusable_filter(self, **kwargs) -> dict | None:
        if self.reusable_filter_row is None:
            return None
        self.last_filter_kwargs = kwargs
        self.reusable_filter_row = {
            **self.reusable_filter_row,
            "id": kwargs["filter_id"],
            "name": kwargs["name"],
            "description": kwargs["description"],
            "filter_expression": kwargs["expression"],
            "active": kwargs["active"],
        }
        return dict(self.reusable_filter_row)

    async def list_reusable_joins(self, workspace: str | None = None) -> list[dict]:
        return [{"id": "rj-1", "workspace": workspace}]

    async def create_reusable_join(self, **kwargs) -> dict:
        self.last_join_kwargs = kwargs
        return {"id": "rj-1", **kwargs}

    async def delete_reusable_join(self, join_id: str) -> bool:
        self.deleted_join_id = join_id
        return True

    async def get_reusable_join(self, join_id: str) -> dict | None:
        if self.reusable_join_row is None:
            return None
        return {**self.reusable_join_row, "id": join_id}

    async def update_reusable_join(self, **kwargs) -> dict | None:
        if self.reusable_join_row is None:
            return None
        self.last_join_kwargs = kwargs
        self.reusable_join_row = {
            **self.reusable_join_row,
            "id": kwargs["join_id"],
            "name": kwargs["name"],
            "description": kwargs["description"],
            "join_definition": kwargs["join_definition"],
            "active": kwargs["active"],
        }
        return dict(self.reusable_join_row)


def test_validate_filter_expression_error_paths(
    reusable_filter_validation_cases: list[dict[str, str]],
) -> None:
    for case in reusable_filter_validation_cases:
        expression = str(case["expression"])
        expected_error = str(case["expected_error"])
        assert reusable_assets._validate_filter_expression(expression) == expected_error


def test_validate_filter_expression_allows_valid_quoted_values() -> None:
    expression = "(name = 'OReilly' OR note = \"He said yes\") AND active = true"
    assert reusable_assets._validate_filter_expression(expression) is None


def test_validate_filter_expression_allows_identifiers_starting_with_or_prefix() -> None:
    expression = "order_id = rhs.order_id AND status = rhs.status"
    assert reusable_assets._validate_filter_expression(expression) is None


@pytest.mark.anyio
async def test_list_reusable_assets_forwards_workspace() -> None:
    repo = _RulesRepoStub()

    filters = await reusable_assets.list_reusable_filters(workspace="team-a", q="active", repository=repo)
    joins = await reusable_assets.list_reusable_joins(workspace="team-a", repository=repo)

    assert filters[0]["workspace"] == "team-a"
    assert filters[0]["query"] == "active"
    assert joins[0]["workspace"] == "team-a"


@pytest.mark.anyio
async def test_create_reusable_filter_uses_fallback_fields_and_defaults(
    monkeypatch,
    reusable_filter_create_payload: dict[str, object],
) -> None:
    repo = _RulesRepoStub()
    monkeypatch.setattr(reusable_assets, "get_user_id", lambda: None)

    payload_dict = reusable_filter_create_payload
    payload = reusable_assets.ReusableFilterCreateRequest(**payload_dict)

    created = await reusable_assets.create_reusable_filter(body=payload, repository=repo)

    assert created["id"] == "rf-1"
    assert repo.last_filter_kwargs is not None
    assert repo.last_filter_kwargs["name"] == "Active Users"
    assert repo.last_filter_kwargs["expression"] == "status = 'ACTIVE'"
    assert repo.last_filter_kwargs["description"] is None
    assert repo.last_filter_kwargs["workspace"] == "team-a"
    assert repo.last_filter_kwargs["created_by"] == "user-admin"
    assert repo.last_filter_kwargs["active"] is False


@pytest.mark.anyio
async def test_create_reusable_filter_rejects_missing_name() -> None:
    repo = _RulesRepoStub()

    with pytest.raises(HTTPException) as error:
        await reusable_assets.create_reusable_filter(
            body=reusable_assets.ReusableFilterCreateRequest(name="", expression="status = 'A'"),
            repository=repo,
        )

    assert error.value.status_code == 400
    assert error.value.detail == "Filter name is required"


@pytest.mark.anyio
async def test_create_reusable_filter_propagates_expression_validation_error() -> None:
    repo = _RulesRepoStub()

    with pytest.raises(HTTPException) as error:
        await reusable_assets.create_reusable_filter(
            body=reusable_assets.ReusableFilterCreateRequest(name="Broken", expression="status = 'A' OR"),
            repository=repo,
        )

    assert error.value.status_code == 400
    assert error.value.detail == "Expression cannot end with AND/OR"


@pytest.mark.anyio
async def test_create_reusable_join_handles_string_and_structured_payloads(
    monkeypatch,
    reusable_join_json_string: str,
    reusable_join_definition: dict[str, object],
) -> None:
    repo = _RulesRepoStub()
    monkeypatch.setattr(reusable_assets, "get_user_id", lambda: "user-42")

    as_string = await reusable_assets.create_reusable_join(
        body=reusable_assets.ReusableJoinCreateRequest(
            name="J1",
            joinDefinition=reusable_join_json_string,
        ),
        repository=repo,
    )
    assert as_string["id"] == "rj-1"
    assert repo.last_join_kwargs is not None
    assert json.loads(repo.last_join_kwargs["join_definition"]) == reusable_join_definition

    await reusable_assets.create_reusable_join(
        body=reusable_assets.ReusableJoinCreateRequest(
            name="J2",
            joinDefinition=reusable_join_definition,
            workspaceId="team-b",
        ),
        repository=repo,
    )

    assert repo.last_join_kwargs is not None
    assert json.loads(repo.last_join_kwargs["join_definition"]) == reusable_join_definition
    assert repo.last_join_kwargs["workspace"] == "team-b"
    assert repo.last_join_kwargs["created_by"] == "user-42"


@pytest.mark.anyio
async def test_create_reusable_join_rejects_invalid_inputs() -> None:
    repo = _RulesRepoStub()

    with pytest.raises(HTTPException) as missing_name:
        await reusable_assets.create_reusable_join(
            body=reusable_assets.ReusableJoinCreateRequest(name="", joinDefinition="x = y"),
            repository=repo,
        )
    assert missing_name.value.status_code == 400
    assert missing_name.value.detail == "Join name is required"

    with pytest.raises(HTTPException) as missing_definition:
        await reusable_assets.create_reusable_join(
            body=reusable_assets.ReusableJoinCreateRequest(name="Join", joinDefinition=None),
            repository=repo,
        )
    assert missing_definition.value.status_code == 400
    assert missing_definition.value.detail == "Join definition is required"

    with pytest.raises(HTTPException) as blank_string:
        await reusable_assets.create_reusable_join(
            body=reusable_assets.ReusableJoinCreateRequest(name="Join", joinDefinition="   "),
            repository=repo,
        )
    assert blank_string.value.status_code == 400
    assert blank_string.value.detail == "Join definition is required"

    with pytest.raises(HTTPException) as empty_conditions:
        await reusable_assets.create_reusable_join(
            body=reusable_assets.ReusableJoinCreateRequest(
                name="Join",
                joinDefinition={"joinType": "inner", "conditions": []},
            ),
            repository=repo,
        )
    assert empty_conditions.value.status_code == 400
    assert empty_conditions.value.detail == "Join definition must contain at least one condition"


@pytest.mark.anyio
async def test_delete_reusable_filter_error_paths() -> None:
    class _RepoDeleteError(_RulesRepoStub):
        async def delete_reusable_filter(self, filter_id: str) -> bool:
            raise ValueError("bad filter id")

    class _RepoDeleteMissing(_RulesRepoStub):
        async def delete_reusable_filter(self, filter_id: str) -> bool:
            return False

    ok_repo = _RulesRepoStub()
    ok_payload = await reusable_assets.delete_reusable_filter(filter_id="rf-1", repository=ok_repo)
    assert ok_payload == {"ok": True}

    with pytest.raises(HTTPException) as error400:
        await reusable_assets.delete_reusable_filter(filter_id="bad", repository=_RepoDeleteError())
    assert error400.value.status_code == 400
    assert error400.value.detail == "bad filter id"

    with pytest.raises(HTTPException) as error404:
        await reusable_assets.delete_reusable_filter(filter_id="missing", repository=_RepoDeleteMissing())
    assert error404.value.status_code == 404


@pytest.mark.anyio
async def test_get_reusable_filter_returns_row_and_404_when_missing() -> None:
    repo = _RulesRepoStub()

    payload = await reusable_assets.get_reusable_filter(filter_id="rf-42", repository=repo)
    assert payload["id"] == "rf-42"

    repo.reusable_filter_row = None
    with pytest.raises(HTTPException) as missing:
        await reusable_assets.get_reusable_filter(filter_id="rf-missing", repository=repo)
    assert missing.value.status_code == 404


@pytest.mark.anyio
async def test_update_reusable_filter_merges_and_validates(
    reusable_filter_update_payload: dict[str, object],
) -> None:
    repo = _RulesRepoStub()

    updated = await reusable_assets.update_reusable_filter(
        filter_id="rf-1",
        body=reusable_assets.ReusableFilterUpdateRequest(**reusable_filter_update_payload),
        repository=repo,
    )

    assert updated["name"] == "Updated Active Users"
    assert updated["filter_expression"] == "status = 'VERIFIED'"
    assert updated["active"] is False
    assert repo.last_filter_kwargs is not None
    assert repo.last_filter_kwargs["filter_id"] == "rf-1"


@pytest.mark.anyio
async def test_update_reusable_filter_returns_404_for_missing() -> None:
    repo = _RulesRepoStub()
    repo.reusable_filter_row = None

    with pytest.raises(HTTPException) as missing:
        await reusable_assets.update_reusable_filter(
            filter_id="rf-missing",
            body=reusable_assets.ReusableFilterUpdateRequest(name="X"),
            repository=repo,
        )
    assert missing.value.status_code == 404


@pytest.mark.anyio
async def test_delete_reusable_join_error_paths() -> None:
    class _RepoDeleteError(_RulesRepoStub):
        async def delete_reusable_join(self, join_id: str) -> bool:
            raise ValueError("bad join id")

    class _RepoDeleteMissing(_RulesRepoStub):
        async def delete_reusable_join(self, join_id: str) -> bool:
            return False

    ok_repo = _RulesRepoStub()
    ok_payload = await reusable_assets.delete_reusable_join(join_id="rj-1", repository=ok_repo)
    assert ok_payload == {"ok": True}

    with pytest.raises(HTTPException) as error400:
        await reusable_assets.delete_reusable_join(join_id="bad", repository=_RepoDeleteError())
    assert error400.value.status_code == 400
    assert error400.value.detail == "bad join id"

    with pytest.raises(HTTPException) as error404:
        await reusable_assets.delete_reusable_join(join_id="missing", repository=_RepoDeleteMissing())
    assert error404.value.status_code == 404


@pytest.mark.anyio
async def test_get_reusable_join_returns_row_and_404_when_missing() -> None:
    repo = _RulesRepoStub()

    payload = await reusable_assets.get_reusable_join(join_id="rj-42", repository=repo)
    assert payload["id"] == "rj-42"

    repo.reusable_join_row = None
    with pytest.raises(HTTPException) as missing:
        await reusable_assets.get_reusable_join(join_id="rj-missing", repository=repo)
    assert missing.value.status_code == 404


@pytest.mark.anyio
async def test_update_reusable_join_merges_and_validates(
    reusable_join_update_payload: dict[str, object],
) -> None:
    repo = _RulesRepoStub()

    updated = await reusable_assets.update_reusable_join(
        join_id="rj-1",
        body=reusable_assets.ReusableJoinUpdateRequest(**reusable_join_update_payload),
        repository=repo,
    )

    assert updated["name"] == "Updated Join"
    assert updated["active"] is False
    assert repo.last_join_kwargs is not None
    assert repo.last_join_kwargs["join_id"] == "rj-1"


@pytest.mark.anyio
async def test_update_reusable_join_returns_404_for_missing() -> None:
    repo = _RulesRepoStub()
    repo.reusable_join_row = None

    with pytest.raises(HTTPException) as missing:
        await reusable_assets.update_reusable_join(
            join_id="rj-missing",
            body=reusable_assets.ReusableJoinUpdateRequest(name="X"),
            repository=repo,
        )
    assert missing.value.status_code == 404
