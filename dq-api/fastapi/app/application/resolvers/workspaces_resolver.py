from typing import Any

from app.api.v1.schemas.workspaces_view import WorkspaceView, WorkspacesPageView
from app.domain.entities import WorkspaceEntity


def resolve_workspaces_page_view(payload: dict[str, Any]) -> WorkspacesPageView:
    return WorkspacesPageView.model_validate(payload)


def resolve_workspace_view(entity: WorkspaceEntity) -> WorkspaceView:
    return WorkspaceView.model_validate(entity)
