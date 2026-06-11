from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.presenters.workspaces import build_workspaces_page_payload
from app.api.v1.schemas import OkResponseView, WorkspaceView, WorkspacesPageView
from app.application.resolvers import resolve_workspace_view, resolve_workspaces_page_view
from app.core.dependencies import get_app_config_repository
from app.core.dependencies import get_workspaces_repository
from app.domain.interfaces import AppConfigRepository
from app.domain.interfaces import WorkspacesRepository

router = APIRouter(tags=["workspaces"])


@router.get("/workspaces", response_model=WorkspacesPageView)
async def get_workspaces(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: WorkspacesRepository = Depends(get_workspaces_repository),
) -> WorkspacesPageView:
    rows = repository.list_workspaces()
    return resolve_workspaces_page_view(build_workspaces_page_payload(rows, page, limit))


@router.post("/workspaces", response_model=OkResponseView)
async def create_workspace(
    payload: dict,
    repository: WorkspacesRepository = Depends(get_workspaces_repository),
    app_config_repository: AppConfigRepository = Depends(get_app_config_repository),
) -> OkResponseView:
    config = app_config_repository.get_app_config()
    max_workspaces = max(1, int(config.maxWorkspaces))
    try:
        repository.create_workspace(payload, max_workspaces)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return OkResponseView(ok=True)


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceView)
async def update_workspace(
    workspace_id: str,
    payload: dict,
    repository: WorkspacesRepository = Depends(get_workspaces_repository),
) -> WorkspaceView:
    updated = repository.update_workspace(workspace_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Not found")
    return resolve_workspace_view(updated)


@router.delete("/workspaces/{workspace_id}", response_model=OkResponseView)
async def delete_workspace(
    workspace_id: str,
    repository: WorkspacesRepository = Depends(get_workspaces_repository),
) -> OkResponseView:
    if str(workspace_id) == "default":
        raise HTTPException(status_code=400, detail="Cannot delete default workspace")

    deleted = repository.delete_workspace(workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Not found")
    return OkResponseView(ok=True)