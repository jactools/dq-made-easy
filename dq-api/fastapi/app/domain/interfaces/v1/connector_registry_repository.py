from typing import Protocol

from app.domain.entities.connector import ConnectorRegistryEntryEntity


class ConnectorRegistryRepository(Protocol):
    def upsert_entry(self, entry: ConnectorRegistryEntryEntity) -> ConnectorRegistryEntryEntity: ...

    def list_entries(self) -> list[ConnectorRegistryEntryEntity]: ...

    def get_entry(self, provider: str) -> ConnectorRegistryEntryEntity | None: ...