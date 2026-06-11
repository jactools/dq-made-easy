from collections.abc import Mapping, Sequence
from typing import Any

from app.api.v1.schemas.data_catalog_view import (
    AddRuleAttributesResultView,
    AttributeDefinitionMappingUpsertResultView,
    AttributeDefinitionMappingView,
    AttributeCatalogPageView,
    AttributeCatalogView,
    DataDeliveriesPageView,
    DataDeliveryInventoryPageView,
    DataDeliveryInventoryView,
    DataDeliveryNoteView,
    DataDeliveryView,
    DataObjectCatalogPageView,
    DataObjectCatalogView,
    DataObjectVersionView,
    DataObjectVersionsPageView,
    DataObjectView,
    DataProductView,
    DataProductsPageView,
    DataSetsPageView,
    DataSetView,
    RuleAttributeView,
)
from app.domain.entities import (
    AddRuleAttributesResultEntity,
    AttributeCatalogEntity,
    AttributeDefinitionMappingEntity,
    AttributeDefinitionMappingUpsertResultEntity,
    DataDeliveryEntity,
    DataObjectCatalogEntity,
    DataObjectEntity,
    DataObjectVersionEntity,
    DataProductEntity,
    DataSetEntity,
    RuleAttributeEntity,
)


def resolve_data_products_page_view(payload: dict[str, Any]) -> DataProductsPageView:
    return DataProductsPageView.model_validate(payload)


def resolve_data_objects_view(rows: Sequence[DataObjectEntity]) -> list[DataObjectView]:
    return [DataObjectView.model_validate(row) for row in rows]


def resolve_data_sets_page_view(payload: dict[str, Any]) -> DataSetsPageView:
    return DataSetsPageView.model_validate(payload)


def resolve_rule_attributes_view(rows: Sequence[RuleAttributeEntity]) -> list[RuleAttributeView]:
    return [RuleAttributeView.model_validate(row) for row in rows]


def resolve_add_rule_attributes_result_view(entity: AddRuleAttributesResultEntity) -> AddRuleAttributesResultView:
    return AddRuleAttributesResultView.model_validate(entity)


def resolve_attribute_definition_mappings_view(rows: Sequence[AttributeDefinitionMappingEntity]) -> list[AttributeDefinitionMappingView]:
    return [AttributeDefinitionMappingView.model_validate(row) for row in rows]


def resolve_attribute_definition_mapping_upsert_result_view(
    entity: AttributeDefinitionMappingUpsertResultEntity,
) -> AttributeDefinitionMappingUpsertResultView:
    return AttributeDefinitionMappingUpsertResultView.model_validate(entity)


def resolve_data_objects_catalog_page_view(payload: dict[str, Any]) -> DataObjectCatalogPageView:
    return DataObjectCatalogPageView.model_validate(payload)


def resolve_data_object_versions_page_view(payload: dict[str, Any]) -> DataObjectVersionsPageView:
    return DataObjectVersionsPageView.model_validate(payload)


def resolve_attributes_catalog_page_view(payload: dict[str, Any]) -> AttributeCatalogPageView:
    return AttributeCatalogPageView.model_validate(payload)


def resolve_data_deliveries_page_view(payload: dict[str, Any]) -> DataDeliveriesPageView:
    return DataDeliveriesPageView.model_validate(payload)


def resolve_data_delivery_inventory_page_view(payload: dict[str, Any]) -> DataDeliveryInventoryPageView:
    return DataDeliveryInventoryPageView.model_validate(payload)


def resolve_data_delivery_note_view(payload: dict[str, Any]) -> DataDeliveryNoteView:
    return DataDeliveryNoteView.model_validate(payload)


def resolve_attribute_rule_counts_view(payload: Mapping[str, Any]) -> dict[str, int]:
    return {str(key): int(value) for key, value in payload.items()}
