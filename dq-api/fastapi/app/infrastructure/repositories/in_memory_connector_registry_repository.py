from __future__ import annotations

from copy import deepcopy

from app.domain.entities.connector import ConnectorRegistryEntryEntity
from app.domain.interfaces.v1.connector_registry_repository import ConnectorRegistryRepository


class InMemoryConnectorRegistryRepository(ConnectorRegistryRepository):
    def __init__(
        self,
        entries: list[ConnectorRegistryEntryEntity] | tuple[ConnectorRegistryEntryEntity, ...] | None = None,
    ) -> None:
        self._entries: dict[str, dict] = {}
        for entry in entries or ():
            self.upsert_entry(entry)

    def upsert_entry(self, entry: ConnectorRegistryEntryEntity) -> ConnectorRegistryEntryEntity:
        stored = entry.model_dump(mode="python", by_alias=False, exclude_none=True)
        provider = str(stored.get("provider") or "").strip().lower()
        if not provider:
            raise ValueError("connector registry entry requires provider")
        stored["provider"] = provider
        self._entries[provider] = deepcopy(stored)
        return ConnectorRegistryEntryEntity.model_validate(deepcopy(stored))

    def list_entries(self) -> list[ConnectorRegistryEntryEntity]:
        rows = sorted(
            self._entries.values(),
            key=lambda row: (str(row.get("display_name") or ""), str(row.get("provider") or "")),
        )
        return [ConnectorRegistryEntryEntity.model_validate(deepcopy(row)) for row in rows]

    def get_entry(self, provider: str) -> ConnectorRegistryEntryEntity | None:
        normalized_provider = str(provider or "").strip().lower()
        if not normalized_provider:
            return None
        row = self._entries.get(normalized_provider)
        if row is None:
            return None
        return ConnectorRegistryEntryEntity.model_validate(deepcopy(row))