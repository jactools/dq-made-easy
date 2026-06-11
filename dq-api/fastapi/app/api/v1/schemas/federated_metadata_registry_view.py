from __future__ import annotations

from pydantic import Field

from app.api.v1.schemas.data_catalog_view import AttributeCatalogView
from app.api.v1.schemas.data_catalog_view import DataObjectCatalogView
from app.api.v1.schemas.data_catalog_view import DataObjectVersionView
from app.api.v1.schemas.data_catalog_view import DataProductView
from app.api.v1.schemas.data_catalog_view import DataSetView
from app.api.v1.schemas.registry_definition_view import RegistryDefinitionView
from app.schemas.pydantic_base import SnakeModel


class FederatedMetadataRegistryManifestView(SnakeModel):
    dataProductCount: int = 0
    dataSetCount: int = 0
    dataObjectCount: int = 0
    dataObjectVersionCount: int = 0
    attributeCount: int = 0
    registryDefinitionCount: int = 0


class FederatedMetadataRegistryPushRequestView(SnakeModel):
    workspaceId: str
    dataProductId: str | None = None


class FederatedMetadataRegistryGoverningScopeView(SnakeModel):
    dataProductIds: list[str] = Field(default_factory=list)
    metadataStructureIds: list[str] = Field(default_factory=list)
    metadataItemIds: list[str] = Field(default_factory=list)


class FederatedMetadataRegistryExternalPartyRegistrationRequestView(SnakeModel):
    workspaceId: str | None = None
    tenantId: str | None = None
    displayName: str | None = None
    governingScope: FederatedMetadataRegistryGoverningScopeView = Field(default_factory=FederatedMetadataRegistryGoverningScopeView)


class FederatedMetadataRegistryExternalPartyApprovalRequestView(SnakeModel):
    approvalNotes: str | None = None


class FederatedMetadataRegistryAccessGrantRequestView(SnakeModel):
    targetKind: str
    targetId: str
    subscribed: bool = True
    canPush: bool = False
    canPull: bool = False
    notes: str | None = None


class FederatedMetadataRegistryExternalPartyView(SnakeModel):
    id: str
    workspaceId: str | None = None
    tenantId: str | None = None
    displayName: str | None = None
    governingScope: FederatedMetadataRegistryGoverningScopeView = Field(default_factory=FederatedMetadataRegistryGoverningScopeView)
    approvalStatus: str = "pending"
    approvedAt: str | None = None
    approvedBy: str | None = None
    approvalNotes: str | None = None
    registeredAt: str
    registeredBy: str | None = None
    correlationId: str | None = None


class FederatedMetadataRegistryAccessGrantView(SnakeModel):
    id: str
    externalPartyId: str
    targetKind: str
    targetId: str
    subscribed: bool = True
    canPush: bool = False
    canPull: bool = False
    notes: str | None = None
    grantedAt: str
    grantedBy: str | None = None
    correlationId: str | None = None


class FederatedMetadataRegistryPackageView(SnakeModel):
    packageId: str
    packageKind: str = "federated_metadata_package"
    workspaceId: str
    dataProductId: str | None = None
    createdAt: str
    manifest: FederatedMetadataRegistryManifestView = Field(default_factory=FederatedMetadataRegistryManifestView)
    dataProducts: list[DataProductView] = Field(default_factory=list)
    dataSets: list[DataSetView] = Field(default_factory=list)
    dataObjects: list[DataObjectCatalogView] = Field(default_factory=list)
    dataObjectVersions: list[DataObjectVersionView] = Field(default_factory=list)
    attributes: list[AttributeCatalogView] = Field(default_factory=list)
    registryDefinitions: list[RegistryDefinitionView] = Field(default_factory=list)


class FederatedMetadataRegistryPullResultView(SnakeModel):
    accepted: bool = True
    validatedAt: str
    package: FederatedMetadataRegistryPackageView


class FederatedMetadataRegistryExchangeSnapshotView(SnakeModel):
    id: str
    packageId: str
    packageKind: str = "federated_metadata_package"
    exchangeKind: str
    workspaceId: str
    dataProductId: str | None = None
    capturedAt: str
    capturedBy: str | None = None
    correlationId: str | None = None
    accepted: bool = True
    validationError: str | None = None
    manifest: FederatedMetadataRegistryManifestView = Field(default_factory=FederatedMetadataRegistryManifestView)
    package: FederatedMetadataRegistryPackageView