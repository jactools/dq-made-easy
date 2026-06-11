from typing import Protocol

from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryAccessGrantEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryExchangeSnapshotEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryExternalPartyEntity


class FederatedMetadataRegistryRepository(Protocol):
    def record_federated_metadata_registry_external_party(
        self,
        party: FederatedMetadataRegistryExternalPartyEntity,
    ) -> FederatedMetadataRegistryExternalPartyEntity: ...

    def list_federated_metadata_registry_external_parties(
        self,
        *,
        party_id: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        approval_status: str | None = None,
        limit: int = 20,
    ) -> list[FederatedMetadataRegistryExternalPartyEntity]: ...

    def record_federated_metadata_registry_access_grant(
        self,
        grant: FederatedMetadataRegistryAccessGrantEntity,
    ) -> FederatedMetadataRegistryAccessGrantEntity: ...

    def list_federated_metadata_registry_access_grants(
        self,
        *,
        party_id: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        limit: int = 20,
    ) -> list[FederatedMetadataRegistryAccessGrantEntity]: ...

    def record_federated_metadata_registry_exchange_snapshot(
        self,
        snapshot: FederatedMetadataRegistryExchangeSnapshotEntity,
    ) -> FederatedMetadataRegistryExchangeSnapshotEntity: ...

    def list_federated_metadata_registry_exchange_snapshots(
        self,
        *,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
        limit: int = 20,
    ) -> list[FederatedMetadataRegistryExchangeSnapshotEntity]: ...