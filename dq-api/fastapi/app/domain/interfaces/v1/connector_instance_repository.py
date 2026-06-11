from typing import Protocol

from app.domain.entities.connector import ConnectorInstanceEntity


class ConnectorInstanceRepository(Protocol):
    def upsert_instance(self, instance: ConnectorInstanceEntity) -> ConnectorInstanceEntity: ...

    def list_instances(
        self,
        *,
        provider: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConnectorInstanceEntity]: ...

    def get_instance(self, instance_id: str) -> ConnectorInstanceEntity | None: ...