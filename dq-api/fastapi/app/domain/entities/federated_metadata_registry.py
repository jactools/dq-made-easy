from __future__ import annotations

from typing import Any

from pydantic import Field

from app.domain.entities.base import EntityModel


class FederatedMetadataRegistryGoverningScopeEntity(EntityModel):
    data_product_ids: list[str] = Field(default_factory=list)
    metadata_structure_ids: list[str] = Field(default_factory=list)
    metadata_item_ids: list[str] = Field(default_factory=list)


class FederatedMetadataRegistryExternalPartyEntity(EntityModel):
    id: str
    workspace_id: str | None = None
    tenant_id: str | None = None
    display_name: str | None = None
    governing_scope: FederatedMetadataRegistryGoverningScopeEntity = Field(default_factory=FederatedMetadataRegistryGoverningScopeEntity)
    approval_status: str = "pending"
    approved_at: str | None = None
    approved_by: str | None = None
    approval_notes: str | None = None
    registered_at: str
    registered_by: str | None = None
    correlation_id: str | None = None


class FederatedMetadataRegistryAccessGrantEntity(EntityModel):
    id: str
    external_party_id: str
    target_kind: str
    target_id: str
    subscribed: bool = True
    can_push: bool = False
    can_pull: bool = False
    notes: str | None = None
    granted_at: str
    granted_by: str | None = None
    correlation_id: str | None = None


class FederatedMetadataRegistryExchangeSnapshotEntity(EntityModel):
    id: str
    package_id: str
    package_kind: str = "federated_metadata_package"
    exchange_kind: str
    workspace_id: str
    data_product_id: str | None = None
    captured_at: str
    captured_by: str | None = None
    correlation_id: str | None = None
    accepted: bool = True
    validation_error: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    package: dict[str, Any] = Field(default_factory=dict)