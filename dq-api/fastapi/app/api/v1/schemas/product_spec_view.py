from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import Field

from app.api.v1.schemas.common_view import PaginationView
from app.schemas.pydantic_base import SnakeModel


class ProductSpecProvenanceView(SnakeModel):
    created_by: str | None = None
    approved_by: str | None = None
    created_at: str | None = None
    approved_at: str | None = None
    change_reason: str | None = None


class ProductSpecContractReferenceView(SnakeModel):
    odcs_contract_id: str = ""
    odcs_contract_name: str = ""
    odcs_contract_version: str = ""
    openmetadata_entity_id: str = ""
    openmetadata_entity_type: str = "data_contract"
    source_system: str = "openmetadata"


class ProductSpecGlossaryView(SnakeModel):
    name: str
    display_name: str
    description: str


class ProductSpecUpsertRequestView(SnakeModel):
    glossary: ProductSpecGlossaryView
    product_spec_id: str
    product_name: str = ""
    product_version: str = ""
    product_lifecycle_state: str = ""
    product_owner: str = ""
    product_objective: str = ""
    product_scope: dict[str, Any] = Field(default_factory=dict)
    business_definition: str = ""
    registry_definition_ids: list[str] = Field(default_factory=list)
    odcs_contract_refs: list[ProductSpecContractReferenceView] = Field(default_factory=list)
    provenance: ProductSpecProvenanceView = Field(default_factory=ProductSpecProvenanceView)
    migration: dict[str, Any] = Field(default_factory=dict)


class ProductSpecImportEntryView(SnakeModel):
    product_spec_id: str
    product_name: str = ""
    product_version: str = ""
    product_lifecycle_state: str = ""
    product_owner: str = ""
    product_objective: str = ""
    product_scope: dict[str, Any] = Field(default_factory=dict)
    business_definition: str = ""
    registry_definition_ids: list[str] = Field(default_factory=list)
    odcs_contract_refs: list[ProductSpecContractReferenceView] = Field(default_factory=list)
    provenance: ProductSpecProvenanceView = Field(default_factory=ProductSpecProvenanceView)
    migration: dict[str, Any] = Field(default_factory=dict)


class ProductSpecView(SnakeModel):
    product_spec_id: str
    product_name: str = ""
    product_version: str = ""
    product_lifecycle_state: str = ""
    product_owner: str = ""
    product_objective: str = ""
    product_scope: dict[str, Any] = Field(default_factory=dict)
    business_definition: str = ""
    registry_definition_ids: list[str] = Field(default_factory=list)
    odcs_contract_refs: list[ProductSpecContractReferenceView] = Field(default_factory=list)
    openmetadata_entity_id: str = ""
    openmetadata_entity_type: str = "glossary_term"
    source_system: str = "openmetadata"
    provenance: ProductSpecProvenanceView = Field(default_factory=ProductSpecProvenanceView)
    migration: dict[str, Any] = Field(default_factory=dict)


class ProductSpecsPageView(SnakeModel):
    data: list[ProductSpecView] = Field(default_factory=list)
    pagination: PaginationView


class ProductSpecSummaryView(SnakeModel):
    total: int = 0
    by_lifecycle_state: dict[str, int] = Field(default_factory=dict)
    by_owner: dict[str, int] = Field(default_factory=dict)


class ProductSpecImportRequestView(SnakeModel):
    glossary: ProductSpecGlossaryView
    product_specs: list[ProductSpecImportEntryView] = Field(default_factory=list)


class ProductSpecImportItemView(SnakeModel):
    product_spec_id: str
    outcome: str
    product_spec: ProductSpecView | None = None


class ProductSpecImportReportView(SnakeModel):
    dry_run: bool = False
    total: int = 0
    created: int = 0
    updated: int = 0
    validated: int = 0
    items: list[ProductSpecImportItemView] = Field(default_factory=list)


class ProductSpecStewardshipActionRequestView(SnakeModel):
    glossary: ProductSpecGlossaryView
    action: Literal["submit_for_approval", "approve", "request_changes", "deprecate", "retire"]
    actor: str
    change_reason: str