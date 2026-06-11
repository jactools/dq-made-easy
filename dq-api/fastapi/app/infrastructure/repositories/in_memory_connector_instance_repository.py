from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from app.domain.entities.connector import ConnectorInstanceEntity
from app.domain.interfaces.v1.connector_instance_repository import ConnectorInstanceRepository


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower()


class InMemoryConnectorInstanceRepository(ConnectorInstanceRepository):
    def __init__(self, instances: list[ConnectorInstanceEntity] | tuple[ConnectorInstanceEntity, ...] | None = None) -> None:
        self._instances: dict[str, dict] = {}
        for instance in instances or ():
            self.upsert_instance(instance)

    def _find_matching_id(self, instance: ConnectorInstanceEntity) -> str | None:
        provider = _normalize(instance.provider)
        workspace_id = _normalize(instance.workspace_id)
        tenant_id = _normalize(instance.tenant_id)
        display_name = _normalize(instance.display_name)
        for instance_id, row in self._instances.items():
            if (
                _normalize(row.get("provider")) == provider
                and _normalize(row.get("workspace_id")) == workspace_id
                and _normalize(row.get("tenant_id")) == tenant_id
                and _normalize(row.get("display_name")) == display_name
            ):
                return instance_id
        return None

    def upsert_instance(self, instance: ConnectorInstanceEntity) -> ConnectorInstanceEntity:
        stored = instance.model_dump(mode="python", by_alias=False, exclude_none=True)
        instance_id = _normalize(stored.get("id")) or self._find_matching_id(instance) or str(uuid4())
        stored["id"] = instance_id
        stored["provider"] = _normalize(stored.get("provider"))
        stored["display_name"] = str(stored.get("display_name") or "").strip()
        stored["workspace_id"] = str(stored.get("workspace_id") or "").strip() or None
        stored["tenant_id"] = str(stored.get("tenant_id") or "").strip() or None
        stored["configuration"] = deepcopy(stored.get("configuration") or {})
        self._instances[instance_id] = deepcopy(stored)
        return ConnectorInstanceEntity.model_validate(deepcopy(stored))

    def list_instances(
        self,
        *,
        provider: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorInstanceEntity]:
        safe_limit = max(0, min(int(limit), 1000))
        safe_offset = max(0, int(offset))
        rows = [
            row
            for row in self._instances.values()
            if (provider is None or _normalize(row.get("provider")) == _normalize(provider))
            and (workspace_id is None or _normalize(row.get("workspace_id")) == _normalize(workspace_id))
            and (tenant_id is None or _normalize(row.get("tenant_id")) == _normalize(tenant_id))
        ]
        rows.sort(key=lambda row: (str(row.get("updated_at") or ""), str(row.get("display_name") or ""), str(row.get("id") or "")), reverse=True)
        if safe_limit == 0:
            return []
        return [ConnectorInstanceEntity.model_validate(deepcopy(row)) for row in rows[safe_offset : safe_offset + safe_limit]]

    def get_instance(self, instance_id: str) -> ConnectorInstanceEntity | None:
        normalized_id = str(instance_id or "").strip()
        if not normalized_id:
            return None
        row = self._instances.get(normalized_id)
        if row is None:
            return None
        return ConnectorInstanceEntity.model_validate(deepcopy(row))