import random
import time
import json
from typing import Any
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import update

from app.domain.entities.workspaces import WorkspaceEntity
from app.domain.interfaces.v1.workspaces_repository import WorkspacesRepository
from app.infrastructure.orm.models import WorkspaceRow
from app.infrastructure.orm.session import session_scope


class PostgresWorkspacesRepository(WorkspacesRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_workspaces(self) -> list[WorkspaceEntity]:
        rows = self._fetch_all()
        return [
            WorkspaceEntity(
                id=str(row.get("id") or ""),
                name=str(row.get("name") or ""),
                description=str(row.get("description") or ""),
                alertRoutingPolicy=self._parse_alert_routing_policy(row.get("alert_routing_policy")),
            )
            for row in rows
        ]

    def create_workspace(self, payload: dict, max_workspaces: int) -> WorkspaceEntity:
        count_row = self._count_workspaces()
        existing_count = int((count_row or {}).get("count") or 0)
        if existing_count >= max(1, int(max_workspaces)):
            raise ValueError("Workspace limit reached")

        workspace_id = str(payload.get("id") or "").strip() or self._generated_id()
        name = str(payload.get("name") or "").strip() or workspace_id
        description = str(payload.get("description") or "")
        alert_routing_policy = self._normalize_alert_routing_policy(payload.get("alertRoutingPolicy") or payload.get("alert_routing_policy"))

        inserted = self._insert_workspace(workspace_id, name, description, alert_routing_policy)
        if not inserted:
            raise RuntimeError("Failed to create workspace")

        return WorkspaceEntity(id=workspace_id, name=name, description=description, alertRoutingPolicy=alert_routing_policy)

    def update_workspace(self, workspace_id: str, payload: dict) -> WorkspaceEntity | None:
        existing = self._fetch_one(workspace_id)
        if existing is None:
            return None

        name = str(payload.get("name") or existing.get("name") or workspace_id).strip() or workspace_id
        description = str(payload.get("description") or existing.get("description") or "")
        alert_routing_policy = self._normalize_alert_routing_policy(
            payload.get("alertRoutingPolicy")
            if "alertRoutingPolicy" in payload
            else payload.get("alert_routing_policy")
            if "alert_routing_policy" in payload
            else existing.get("alert_routing_policy")
        )
        updated = self._update_workspace(workspace_id, name, description, alert_routing_policy)
        if not updated:
            raise RuntimeError("Failed to update workspace")
        return WorkspaceEntity(id=workspace_id, name=name, description=description, alertRoutingPolicy=alert_routing_policy)

    def delete_workspace(self, workspace_id: str) -> bool:
        deleted = self._delete_workspace(workspace_id)
        return bool(deleted)

    @staticmethod
    def _generated_id() -> str:
        return f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}"

    def _fetch_all(self) -> list[dict[str, Any]]:
        with session_scope(self.database_url) as session:
            rows = session.execute(select(WorkspaceRow)).scalars().all()
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "description": row.description,
                    "alert_routing_policy": row.alert_routing_policy,
                }
                for row in rows
            ]

    def _fetch_one(self, workspace_id: str) -> dict[str, Any] | None:
        with session_scope(self.database_url) as session:
            row = session.get(WorkspaceRow, workspace_id)
            if row is None:
                return None
            return {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "alert_routing_policy": row.alert_routing_policy,
            }

    def _count_workspaces(self) -> dict[str, int]:
        with session_scope(self.database_url) as session:
            count_value = session.execute(select(func.count(WorkspaceRow.id))).scalar_one()
            return {"count": int(count_value)}

    def _insert_workspace(self, workspace_id: str, name: str, description: str, alert_routing_policy: dict[str, Any]) -> bool:
        with session_scope(self.database_url) as session:
            session.add(
                WorkspaceRow(
                    id=workspace_id,
                    name=name,
                    description=description,
                    alert_routing_policy=json.dumps(alert_routing_policy, separators=(",", ":")),
                )
            )
            session.commit()
            return True

    def _update_workspace(self, workspace_id: str, name: str, description: str, alert_routing_policy: dict[str, Any]) -> bool:
        with session_scope(self.database_url) as session:
            result = session.execute(
                update(WorkspaceRow)
                .where(WorkspaceRow.id == workspace_id)
                .values(
                    name=name,
                    description=description,
                    alert_routing_policy=json.dumps(alert_routing_policy, separators=(",", ":")),
                )
            )
            session.commit()
            return bool(result.rowcount and result.rowcount > 0)

    def _delete_workspace(self, workspace_id: str) -> bool:
        with session_scope(self.database_url) as session:
            result = session.execute(delete(WorkspaceRow).where(WorkspaceRow.id == workspace_id))
            session.commit()
            return bool(result.rowcount and result.rowcount > 0)

    @staticmethod
    def _normalize_alert_routing_policy(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return {}
            try:
                parsed = json.loads(candidate)
            except Exception:
                return {}
            return dict(parsed) if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _parse_alert_routing_policy(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if not isinstance(value, str):
            return {}
        candidate = value.strip()
        if not candidate:
            return {}
        try:
            parsed = json.loads(candidate)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}