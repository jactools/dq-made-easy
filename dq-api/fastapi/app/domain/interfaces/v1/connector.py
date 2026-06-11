from __future__ import annotations

from typing import Protocol
from typing import runtime_checkable

from app.domain.entities.connector import ConnectorCapabilityEntity
from app.domain.entities.connector import ConnectorConfigurationEntity
from app.domain.entities.connector import ConnectorDiscoveryResultEntity
from app.domain.entities.connector import ConnectorHealthResultEntity
from app.domain.entities.connector import ConnectorSyncResultEntity
from app.domain.entities.connector import ConnectorValidationResultEntity


@runtime_checkable
class Connector(Protocol):
    provider: str
    capabilities: ConnectorCapabilityEntity

    def configure(self, configuration: ConnectorConfigurationEntity) -> ConnectorConfigurationEntity: ...

    def validate(self, configuration: ConnectorConfigurationEntity) -> ConnectorValidationResultEntity: ...

    def discover(self, configuration: ConnectorConfigurationEntity) -> ConnectorDiscoveryResultEntity: ...

    def sync(self, configuration: ConnectorConfigurationEntity) -> ConnectorSyncResultEntity: ...

    def health(self, configuration: ConnectorConfigurationEntity) -> ConnectorHealthResultEntity: ...