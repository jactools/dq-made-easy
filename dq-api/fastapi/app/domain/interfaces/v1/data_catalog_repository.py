from typing import Any, Protocol

from app.domain.entities.data_catalog import (
    AddRuleAttributesResultEntity,
    AttributeCatalogEntity,
    AttributeDefinitionMappingEntity,
    AttributeDefinitionMappingUpsertResultEntity,
    DataDeliveryEntity,
    DataDeliveryNoteEntity,
    DataObjectCatalogEntity,
    DataObjectEntity,
    DataObjectVersionEntity,
    DataProductEntity,
    DataSetEntity,
    RuleAttributeEntity,
)


class DataCatalogRepository(Protocol):
    def list_data_products(self, workspace: str | None = None) -> list[DataProductEntity]: ...

    def list_data_objects(self) -> list[DataObjectEntity]: ...

    def get_data_set(self, data_set_id: str) -> DataSetEntity | None: ...

    def list_data_sets(
        self,
        product_id: str | None = None,
        workspace: str | None = None,
    ) -> list[DataSetEntity]: ...

    def update_data_set(self, data_set_id: str, payload: dict[str, Any]) -> DataSetEntity: ...

    def list_rule_attributes(self) -> list[RuleAttributeEntity]: ...

    def add_rule_attributes(self, entries: list[dict]) -> AddRuleAttributesResultEntity: ...

    def get_attribute_rule_counts(self) -> dict[str, int]: ...

    def list_data_objects_catalog(self, data_set_id: str | None = None) -> list[DataObjectCatalogEntity]: ...

    def get_attribute_catalog(self, attribute_id: str) -> AttributeCatalogEntity | None: ...

    def list_data_object_versions(self, object_id: str | None = None) -> list[DataObjectVersionEntity]: ...

    def get_data_object_version(self, version_id: str) -> DataObjectVersionEntity | None: ...

    def list_attributes_catalog(self, version_id: str | None = None) -> list[AttributeCatalogEntity]: ...

    def list_attribute_definition_mappings(
        self,
        version_id: str | None = None,
        attribute_id: str | None = None,
    ) -> list[AttributeDefinitionMappingEntity]: ...

    def upsert_attribute_definition_mapping(
        self,
        *,
        attribute_id: str,
        definition_id: str | None,
        mapping_state: str,
        mapped_by: str | None,
    ) -> AttributeDefinitionMappingUpsertResultEntity: ...

    def upsert_attribute_protection_policy(
        self,
        *,
        attribute_id: str,
        masking_method: str,
        encryption_required: bool,
        encryption_key_id: str | None,
        configured_by: str | None,
    ) -> AttributeCatalogEntity: ...

    def list_data_deliveries(self, version_id: str | None = None, workspace: str | None = None) -> list[DataDeliveryEntity]: ...

    def get_data_delivery_note(self, delivery_id: str) -> DataDeliveryNoteEntity | None: ...

    def create_materialized_delivery_note(self, payload: dict[str, Any]) -> DataDeliveryNoteEntity: ...