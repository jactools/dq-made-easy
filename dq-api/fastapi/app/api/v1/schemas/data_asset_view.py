from __future__ import annotations


from typing import Any

from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import SnakeModel, to_snake_alias


class DataAssetSourceBindingView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    sourceDataObjectVersionId: str
    sourceFieldId: str
    sourceFieldName: str = ""
    sourceFieldType: str = ""
    nullable: bool = True


class DataAssetFilterView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    expression: str
    enabled: bool = True
    description: str | None = None


class DataAssetDerivedFieldView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    name: str
    expression: str
    dataType: str | None = None
    nullable: bool | None = None
    sourceFieldIds: list[str] = Field(default_factory=list)


class DataAssetUploadPreviewColumnView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    name: str
    dataType: str
    nullable: bool = True


class DataAssetUploadPreviewView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    fileName: str | None = None
    fileFormat: str | None = None
    sourceUri: str | None = None
    columns: list[DataAssetUploadPreviewColumnView] = Field(default_factory=list)


class DataAssetBusinessContextView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    datasetId: str = ""
    dataProductId: str = ""
    domain: str = ""
    owner: str = ""
    purpose: str = ""
    steward: str = ""
    criticality: str = ""
    tags: list[str] = Field(default_factory=list)
    businessDefinitions: list[str] = Field(default_factory=list)
    lineageReferences: list[str] = Field(default_factory=list)
    validationSuites: list[str] = Field(default_factory=list)
    validationPlans: list[str] = Field(default_factory=list)
    consumers: list[str] = Field(default_factory=list)


class DataAssetVersionView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    dataAssetId: str = ""
    version: int = 1
    createdAt: str = ""
    sourceBindings: list[DataAssetSourceBindingView] = Field(default_factory=list)
    filters: list[DataAssetFilterView] = Field(default_factory=list)
    derivedFields: list[DataAssetDerivedFieldView] = Field(default_factory=list)
    uploadPreview: DataAssetUploadPreviewView | None = None
    dataContractDownloadUrl: str = ""


class DataAssetView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    name: str = ""
    description: str = ""
    workspaceId: str = ""
    status: str = "draft"
    createdAt: str = ""
    currentVersionId: str | None = None
    sourceObjectVersionIds: list[str] = Field(default_factory=list)
    businessContext: DataAssetBusinessContextView | None = None
    dataContractDownloadUrl: str = ""


class CreateDataAssetRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    name: str
    description: str = ""
    workspaceId: str = ""
    status: str = "draft"
    currentVersionId: str | None = None
    sourceObjectVersionIds: list[str] = Field(default_factory=list)
    businessContext: DataAssetBusinessContextView | None = None


class UpdateDataAssetRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    name: str | None = None
    description: str | None = None
    workspaceId: str | None = None
    status: str | None = None
    currentVersionId: str | None = None
    sourceObjectVersionIds: list[str] | None = None
    businessContext: DataAssetBusinessContextView | None = None


class CreateDataAssetVersionRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    id: str
    version: int = 1
    createdAt: str = ""
    sourceBindings: list[DataAssetSourceBindingView] = Field(default_factory=list)
    filters: list[DataAssetFilterView] = Field(default_factory=list)
    derivedFields: list[DataAssetDerivedFieldView] = Field(default_factory=list)
    uploadPreview: DataAssetUploadPreviewView | None = None


class GenerateDataAssetTestDataRequestView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    sampleCount: int = Field(default=10, ge=1, le=1000)


class DataAssetValidationView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    ok: bool = True
    asset: DataAssetView
    version: DataAssetVersionView
    issues: list[str] = Field(default_factory=list)


class DataAssetLineageNodeView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    kind: str
    id: str
    name: str
    workspaceId: str | None = None
    detail: str | None = None
    navigationTarget: str | None = None


class DataAssetLineageImpactSummaryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    contractChangeCount: int = 0
    impactedRuleIds: list[str] = Field(default_factory=list)
    impactedMonitorScopeIds: list[str] = Field(default_factory=list)
    impactedIncidentIds: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

class DataAssetLineageBusinessContextOverlayView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    domain: str = ""
    purpose: str = ""
    steward: str = ""
    criticality: str = ""
    consumers: list[str] = Field(default_factory=list)
    summary: str = ""

class DataAssetLineageClassificationView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    classification: str = "public"
    rationale: str = ""
    signals: list[str] = Field(default_factory=list)

class DataAssetLineageAnomalyAnnotationView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    kind: str
    severity: str
    summary: str
    source: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class DataAssetGovernanceDiscoveryView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    assetId: str
    priority: str = "low"
    summary: str = ""
    objectStorageClassifications: list[str] = Field(default_factory=list)
    evidenceClassifications: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    latestDeliveryId: str | None = None
    latestDeliveryAt: str | None = None
    snapshotId: str | None = None
    capturedAt: str | None = None


class DataAssetLineageView(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    dataAsset: DataAssetView
    upstreamNodes: list[DataAssetLineageNodeView] = Field(default_factory=list)
    downstreamNodes: list[DataAssetLineageNodeView] = Field(default_factory=list)
    impactSummary: DataAssetLineageImpactSummaryView
    businessContextOverlay: DataAssetLineageBusinessContextOverlayView | None = None
    classificationView: DataAssetLineageClassificationView | None = None
    anomalyAnnotations: list[DataAssetLineageAnomalyAnnotationView] = Field(default_factory=list)
    snapshotId: str | None = None
    capturedAt: str | None = None
