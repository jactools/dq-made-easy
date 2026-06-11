from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryAccessGrantEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryExchangeSnapshotEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryExternalPartyEntity
from app.domain.interfaces.v1.federated_metadata_registry_repository import FederatedMetadataRegistryRepository


class InMemoryFederatedMetadataRegistryRepository(FederatedMetadataRegistryRepository):
    def __init__(self) -> None:
        self._external_parties: list[dict] = []
        self._access_grants: list[dict] = []
        self._exchange_snapshots: list[dict] = []

    def record_federated_metadata_registry_external_party(
        self,
        party: FederatedMetadataRegistryExternalPartyEntity,
    ) -> FederatedMetadataRegistryExternalPartyEntity:
        stored = party.model_dump(mode="python", by_alias=True, exclude_none=True)
        if not str(stored.get("id") or "").strip():
            stored["id"] = f"federated-metadata-registry-external-party-{uuid4().hex}"
        stored["id"] = str(stored["id"]).strip()

        existing_index = next((index for index, row in enumerate(self._external_parties) if str(row.get("id") or "") == stored["id"]), None)
        if existing_index is None:
            self._external_parties.append(deepcopy(stored))
        else:
            self._external_parties[existing_index] = deepcopy(stored)
        return FederatedMetadataRegistryExternalPartyEntity.model_validate(stored)

    def list_federated_metadata_registry_external_parties(
        self,
        *,
        party_id: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        approval_status: str | None = None,
        limit: int = 20,
    ) -> list[FederatedMetadataRegistryExternalPartyEntity]:
        rows = list(self._external_parties)
        if party_id is not None:
            rows = [row for row in rows if str(row.get("id") or "") == str(party_id)]
        if workspace_id is not None:
            rows = [row for row in rows if str(row.get("workspace_id") or "") == str(workspace_id)]
        if tenant_id is not None:
            rows = [row for row in rows if str(row.get("tenant_id") or "") == str(tenant_id)]
        if approval_status is not None:
            rows = [row for row in rows if str(row.get("approval_status") or "pending") == str(approval_status)]
        rows.sort(key=lambda row: (str(row.get("registered_at") or ""), str(row.get("id") or "")), reverse=True)
        safe_limit = max(1, min(int(limit), 100))
        return [FederatedMetadataRegistryExternalPartyEntity.model_validate(deepcopy(row)) for row in rows[:safe_limit]]

    def record_federated_metadata_registry_access_grant(
        self,
        grant: FederatedMetadataRegistryAccessGrantEntity,
    ) -> FederatedMetadataRegistryAccessGrantEntity:
        stored = grant.model_dump(mode="python", by_alias=True, exclude_none=True)
        if not str(stored.get("id") or "").strip():
            stored["id"] = f"federated-metadata-registry-access-grant-{uuid4().hex}"
        stored["id"] = str(stored["id"]).strip()

        existing_index = next((index for index, row in enumerate(self._access_grants) if str(row.get("id") or "") == stored["id"]), None)
        if existing_index is None:
            self._access_grants.append(deepcopy(stored))
        else:
            self._access_grants[existing_index] = deepcopy(stored)
        return FederatedMetadataRegistryAccessGrantEntity.model_validate(stored)

    def list_federated_metadata_registry_access_grants(
        self,
        *,
        party_id: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        limit: int = 20,
    ) -> list[FederatedMetadataRegistryAccessGrantEntity]:
        rows = list(self._access_grants)
        if party_id is not None:
            rows = [row for row in rows if str(row.get("external_party_id") or "") == str(party_id)]
        if target_kind is not None:
            rows = [row for row in rows if str(row.get("target_kind") or "") == str(target_kind)]
        if target_id is not None:
            rows = [row for row in rows if str(row.get("target_id") or "") == str(target_id)]
        rows.sort(key=lambda row: (str(row.get("granted_at") or ""), str(row.get("id") or "")), reverse=True)
        safe_limit = max(1, min(int(limit), 100))
        return [FederatedMetadataRegistryAccessGrantEntity.model_validate(deepcopy(row)) for row in rows[:safe_limit]]

    def record_federated_metadata_registry_exchange_snapshot(
        self,
        snapshot: FederatedMetadataRegistryExchangeSnapshotEntity,
    ) -> FederatedMetadataRegistryExchangeSnapshotEntity:
        stored = snapshot.model_dump(mode="python", by_alias=True, exclude_none=True)
        if not str(stored.get("id") or "").strip():
            stored["id"] = f"federated-metadata-registry-exchange-snapshot-{uuid4().hex}"
        self._exchange_snapshots.append(deepcopy(stored))
        return FederatedMetadataRegistryExchangeSnapshotEntity.model_validate(stored)

    def list_federated_metadata_registry_exchange_snapshots(
        self,
        *,
        workspace_id: str | None = None,
        data_product_id: str | None = None,
        limit: int = 20,
    ) -> list[FederatedMetadataRegistryExchangeSnapshotEntity]:
        rows = list(self._exchange_snapshots)
        if workspace_id is not None:
            rows = [row for row in rows if str(row.get("workspace_id") or "") == str(workspace_id)]
        if data_product_id is not None:
            rows = [row for row in rows if str(row.get("data_product_id") or "") == str(data_product_id)]
        rows.sort(key=lambda row: (str(row.get("captured_at") or ""), str(row.get("id") or "")), reverse=True)
        safe_limit = max(1, min(int(limit), 100))
        return [FederatedMetadataRegistryExchangeSnapshotEntity.model_validate(deepcopy(row)) for row in rows[:safe_limit]]