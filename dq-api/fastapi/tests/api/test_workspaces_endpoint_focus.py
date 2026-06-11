from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.workspaces import create_workspace
from app.api.v1.endpoints.workspaces import delete_workspace
from app.api.v1.endpoints.workspaces import get_workspaces
from app.api.v1.endpoints.workspaces import update_workspace


class _WorkspacesRepo:
    def __init__(self) -> None:
        self.list_called = False
        self.create_calls: list[tuple[dict, int]] = []
        self.update_calls: list[tuple[str, dict]] = []
        self.delete_calls: list[str] = []
        self.update_result = SimpleNamespace(id="ws-1", name="Workspace 1", description="Primary")
        self.delete_result = True

    def list_workspaces(self):
        self.list_called = True
        return [
            {"id": "ws-1", "name": "Workspace 1", "description": "Primary"},
            {"id": "ws-2", "name": "Workspace 2", "description": "Secondary"},
        ]

    def create_workspace(self, payload: dict, max_workspaces: int):
        self.create_calls.append((dict(payload), max_workspaces))

    def update_workspace(self, workspace_id: str, payload: dict):
        self.update_calls.append((workspace_id, dict(payload)))
        return self.update_result

    def delete_workspace(self, workspace_id: str):
        self.delete_calls.append(workspace_id)
        return self.delete_result


class _ConfigRepo:
    def __init__(self, max_workspaces: int = 5) -> None:
        self.max_workspaces = max_workspaces

    def get_app_config(self):
        return SimpleNamespace(maxWorkspaces=self.max_workspaces)


@pytest.mark.anyio
async def test_get_workspaces_returns_paginated_view() -> None:
    repo = _WorkspacesRepo()

    result = await get_workspaces(page=1, limit=1, repository=repo)

    assert repo.list_called is True
    assert result.pagination.total == 2
    assert result.pagination.limit == 1
    assert result.data[0].id == "ws-1"


@pytest.mark.anyio
async def test_create_workspace_uses_configured_limit() -> None:
    repo = _WorkspacesRepo()
    config_repo = _ConfigRepo(max_workspaces=7)

    result = await create_workspace({"id": "ws-3", "name": "Workspace 3"}, repository=repo, app_config_repository=config_repo)

    assert result.ok is True
    assert repo.create_calls == [({"id": "ws-3", "name": "Workspace 3"}, 7)]


@pytest.mark.anyio
async def test_create_workspace_maps_limit_errors_to_http_exception() -> None:
    class _RejectingRepo(_WorkspacesRepo):
        def create_workspace(self, payload: dict, max_workspaces: int):
            raise ValueError(f"workspace limit reached at {max_workspaces}")

    with pytest.raises(HTTPException) as exc_info:
        await create_workspace({"id": "ws-3", "name": "Workspace 3"}, repository=_RejectingRepo(), app_config_repository=_ConfigRepo())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "workspace limit reached at 5"


@pytest.mark.anyio
async def test_update_workspace_returns_not_found_for_missing_workspace() -> None:
    class _MissingRepo(_WorkspacesRepo):
        def update_workspace(self, workspace_id: str, payload: dict):
            self.update_calls.append((workspace_id, dict(payload)))
            return None

    with pytest.raises(HTTPException) as exc_info:
        await update_workspace("ws-missing", {"name": "Workspace X"}, repository=_MissingRepo())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Not found"


@pytest.mark.anyio
async def test_delete_workspace_rejects_default_workspace() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await delete_workspace("default", repository=_WorkspacesRepo())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cannot delete default workspace"