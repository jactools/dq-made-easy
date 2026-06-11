import random
import time

from app.domain.entities.workspaces import WorkspaceEntity
from app.domain.interfaces.v1.workspaces_repository import WorkspacesRepository
from app.infrastructure.repositories.in_memory_test_data import workspaces_seed_data


class InMemoryWorkspacesRepository(WorkspacesRepository):
    def __init__(self) -> None:
        self._workspaces = workspaces_seed_data()

    def list_workspaces(self) -> list[WorkspaceEntity]:
        return [WorkspaceEntity(**item) for item in self._workspaces]

    def create_workspace(self, payload: dict, max_workspaces: int) -> WorkspaceEntity:
        if len(self._workspaces) >= max(1, int(max_workspaces)):
            raise ValueError("Workspace limit reached")

        workspace_id = str(payload.get("id") or "").strip() or self._generated_id()
        name = str(payload.get("name") or "").strip() or workspace_id
        description = str(payload.get("description") or "")
        alert_routing_policy = dict(payload.get("alertRoutingPolicy") or payload.get("alert_routing_policy") or {})

        if any(str(item.get("id") or "") == workspace_id for item in self._workspaces):
            raise ValueError("Workspace already exists")

        self._workspaces.append(
            {
                "id": workspace_id,
                "name": name,
                "description": description,
                "alert_routing_policy": alert_routing_policy,
            }
        )
        return WorkspaceEntity(id=workspace_id, name=name, description=description, alertRoutingPolicy=alert_routing_policy)

    def update_workspace(self, workspace_id: str, payload: dict) -> WorkspaceEntity | None:
        existing = next(
            (item for item in self._workspaces if str(item.get("id") or "") == str(workspace_id)),
            None,
        )
        if existing is None:
            return None

        name = str(payload.get("name") or existing.get("name") or workspace_id).strip() or workspace_id
        description = str(payload.get("description") or existing.get("description") or "")
        alert_routing_policy = dict(payload.get("alertRoutingPolicy") or payload.get("alert_routing_policy") or existing.get("alert_routing_policy") or {})

        existing["name"] = name
        existing["description"] = description
        existing["alert_routing_policy"] = alert_routing_policy
        return WorkspaceEntity(id=str(workspace_id), name=name, description=description, alertRoutingPolicy=alert_routing_policy)

    def delete_workspace(self, workspace_id: str) -> bool:
        for index, item in enumerate(self._workspaces):
            if str(item.get("id") or "") == str(workspace_id):
                del self._workspaces[index]
                return True
        return False

    @staticmethod
    def _generated_id() -> str:
        return f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}"