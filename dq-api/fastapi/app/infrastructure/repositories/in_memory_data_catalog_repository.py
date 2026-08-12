from typing import Any

from uuid import uuid4

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
    delivery_note_metadata_label,
    delivery_format_warning,
    RuleAttributeEntity,
)
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.infrastructure.repositories.in_memory_test_data import data_catalog_seed_data


class InMemoryDataCatalogRepository(DataCatalogRepository):
    def __init__(self) -> None:
        seed = data_catalog_seed_data()
        self._data_products = seed["data_products"]
        self._data_sets = seed["data_sets"]
        self._data_objects = seed["data_objects"]
        self._rule_attributes = seed["rule_attributes"]
        self._data_objects_catalog = seed["data_objects_catalog"]
        self._data_object_versions = seed["data_object_versions"]
        self._attributes_catalog = seed["attributes_catalog"]
        self._attribute_definition_mappings = seed.get("attribute_definition_mappings", [])
        self._data_deliveries = seed["data_deliveries"]
        self._data_delivery_notes = seed.get("data_delivery_notes", {})
        self._attribute_rule_counts = seed["attribute_rule_counts"]

    def list_data_products(self, workspace: str | None = None) -> list[DataProductEntity]:
        rows = self._data_products
        if workspace:
            rows = [row for row in rows if row["workspace_id"] == workspace]
        sorted_rows = sorted(rows, key=lambda row: str(row["name"]))
        return [DataProductEntity(**row) for row in sorted_rows]

    def list_data_sets(
        self,
        product_id: str | None = None,
        workspace: str | None = None,
    ) -> list[DataSetEntity]:
        rows = self._data_sets
        if product_id:
            rows = [row for row in rows if row["product_id"] == product_id]
        if workspace:
            rows = [row for row in rows if row["workspace_id"] == workspace]
        sorted_rows = sorted(rows, key=lambda row: str(row["name"]))
        return [DataSetEntity(**row) for row in sorted_rows]

    def get_data_set(self, data_set_id: str) -> DataSetEntity | None:
        normalized_data_set_id = str(data_set_id or "").strip()
        if not normalized_data_set_id:
            return None
        row = next((item for item in self._data_sets if str(item.get("id") or "") == normalized_data_set_id), None)
        return DataSetEntity(**row) if row is not None else None

    def update_data_set(self, data_set_id: str, payload: dict[str, Any]) -> DataSetEntity:
        normalized_data_set_id = str(data_set_id or "").strip()
        if not normalized_data_set_id:
            raise ValueError("data_set_id is required")

        row = next((item for item in self._data_sets if str(item.get("id") or "") == normalized_data_set_id), None)
        if row is None:
            raise ValueError(f"Data set '{normalized_data_set_id}' was not found")

        for field in ("product_id", "name", "description", "owner", "workspace_id", "business_key"):
            if field in payload and payload[field] is not None:
                row[field] = str(payload[field]).strip()
        if "tags" in payload and isinstance(payload["tags"], list):
            row["tags"] = [str(tag).strip() for tag in payload["tags"] if str(tag).strip()]
        return DataSetEntity(**row)

    def list_data_objects(self) -> list[DataObjectEntity]:
        sorted_rows = sorted(self._data_objects, key=lambda row: str(row["name"]))
        return [DataObjectEntity(**row) for row in sorted_rows]

    def list_rule_attributes(self) -> list[RuleAttributeEntity]:
        return [RuleAttributeEntity(**row) for row in self._rule_attributes]

    def add_rule_attributes(self, entries: list[dict]) -> AddRuleAttributesResultEntity:
        added = 0
        existing = {(str(row["ruleId"]), str(row["attributeId"])) for row in self._rule_attributes}
        for entry in entries:
            rule_id = entry.get("ruleId")
            attribute_id = entry.get("attributeId")
            if not rule_id or not attribute_id:
                continue
            key = (str(rule_id), str(attribute_id))
            if key in existing:
                continue
            self._rule_attributes.append({"ruleId": key[0], "attributeId": key[1], "threshold_override": entry.get("thresholdOverride")})
            existing.add(key)
            added += 1
        return AddRuleAttributesResultEntity(added=added)

    def get_attribute_rule_counts(self) -> dict[str, int]:
        return dict(self._attribute_rule_counts)

    def list_data_objects_catalog(self, data_set_id: str | None = None) -> list[DataObjectCatalogEntity]:
        rows = self._data_objects_catalog
        if data_set_id:
            rows = [row for row in rows if row["dataset_id"] == data_set_id]
        sorted_rows = sorted(rows, key=lambda row: str(row["name"]))
        return [DataObjectCatalogEntity(**row) for row in sorted_rows]

    def list_data_object_versions(self, object_id: str | None = None) -> list[DataObjectVersionEntity]:
        rows = self._data_object_versions
        if object_id:
            rows = [row for row in rows if row["data_object_id"] == object_id]
        sorted_rows = sorted(rows, key=lambda row: int(row["version"]), reverse=True)
        return [DataObjectVersionEntity(**row) for row in sorted_rows]

    def get_data_object_version(self, version_id: str) -> DataObjectVersionEntity | None:
        match = next((row for row in self._data_object_versions if str(row.get("id") or "") == str(version_id)), None)
        return DataObjectVersionEntity(**match) if match is not None else None

    def get_attribute_catalog(self, attribute_id: str) -> AttributeCatalogEntity | None:
        row = next((item for item in self._attributes_catalog if str(item.get("id") or "") == str(attribute_id)), None)
        if row is None:
            return None
        return AttributeCatalogEntity(**self._attribute_row_with_mapping(row))

    def list_attributes_catalog(self, version_id: str | None = None) -> list[AttributeCatalogEntity]:
        rows = self._attributes_catalog
        if version_id:
            rows = [row for row in rows if row["version_id"] == version_id]
        sorted_rows = sorted(rows, key=lambda row: str(row["id"]))
        return [AttributeCatalogEntity(**self._attribute_row_with_mapping(row)) for row in sorted_rows]

    def upsert_attribute_protection_policy(
        self,
        *,
        attribute_id: str,
        masking_method: str,
        encryption_required: bool,
        encryption_key_id: str | None,
        configured_by: str | None,
    ) -> AttributeCatalogEntity:
        normalized_attribute_id = str(attribute_id or "").strip()
        if not normalized_attribute_id:
            raise ValueError("attribute_id is required")

        attribute_row = next((row for row in self._attributes_catalog if str(row.get("id") or "") == normalized_attribute_id), None)
        if attribute_row is None:
            raise ValueError(f"Attribute '{normalized_attribute_id}' was not found")

        normalized_masking_method = str(masking_method or "none").strip().lower() or "none"
        attribute_row["masking_method"] = normalized_masking_method
        attribute_row["encryption_required"] = bool(encryption_required)
        attribute_row["encryption_key_id"] = str(encryption_key_id or "").strip() or None
        attribute_row["protection_configured_by"] = str(configured_by or "").strip() or None
        attribute_row["protection_updated_at"] = "2026-05-25T00:00:00Z"
        return AttributeCatalogEntity(**self._attribute_row_with_mapping(attribute_row))

    def list_attribute_definition_mappings(
        self,
        version_id: str | None = None,
        attribute_id: str | None = None,
    ) -> list[AttributeDefinitionMappingEntity]:
        rows = self._attribute_definition_mappings
        if attribute_id:
            rows = [row for row in rows if str(row.get("attribute_id") or "") == str(attribute_id)]
        if version_id:
            version_attribute_ids = {
                str(row.get("id") or "")
                for row in self._attributes_catalog
                if str(row.get("version_id") or "") == str(version_id)
            }
            rows = [row for row in rows if str(row.get("attribute_id") or "") in version_attribute_ids]
        sorted_rows = sorted(rows, key=lambda row: str(row.get("attribute_id") or ""))
        return [AttributeDefinitionMappingEntity(**row) for row in sorted_rows]

    def upsert_attribute_definition_mapping(
        self,
        *,
        attribute_id: str,
        definition_id: str | None,
        mapping_state: str,
        mapped_by: str | None,
    ) -> AttributeDefinitionMappingUpsertResultEntity:
        normalized_attribute_id = str(attribute_id or "").strip()
        if not normalized_attribute_id:
            raise ValueError("attribute_id is required")

        attribute_row = next((row for row in self._attributes_catalog if str(row.get("id") or "") == normalized_attribute_id), None)
        if attribute_row is None:
            raise ValueError(f"Attribute '{normalized_attribute_id}' was not found")

        normalized_state = str(mapping_state or "mapped").strip().lower() or "mapped"
        if normalized_state not in {"mapped", "unmapped"}:
            raise ValueError("mapping_state must be 'mapped' or 'unmapped'")

        normalized_definition_id = str(definition_id or "").strip() or None
        if normalized_state == "mapped" and not normalized_definition_id:
            raise ValueError("definition_id is required when mapping_state is 'mapped'")
        if normalized_state == "unmapped":
            normalized_definition_id = None

        normalized_mapped_by = str(mapped_by or "").strip() or None
        timestamp = "2026-04-20T00:00:00Z"

        existing = next(
            (row for row in self._attribute_definition_mappings if str(row.get("attribute_id") or "") == normalized_attribute_id),
            None,
        )
        if existing is None:
            existing = {
                "id": f"adm-{uuid4().hex[:12]}",
                "attribute_id": normalized_attribute_id,
                "definition_id": normalized_definition_id,
                "mapping_state": normalized_state,
                "mapped_by": normalized_mapped_by,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            self._attribute_definition_mappings.append(existing)
        else:
            existing["definition_id"] = normalized_definition_id
            existing["mapping_state"] = normalized_state
            existing["mapped_by"] = normalized_mapped_by
            existing["updated_at"] = timestamp

        return AttributeDefinitionMappingUpsertResultEntity(
            attribute_id=normalized_attribute_id,
            definition_id=normalized_definition_id,
            mapping_state=normalized_state,
            definition_mapping_status="explicit_unmapped" if normalized_state == "unmapped" else "explicit",
            version_id=str(attribute_row.get("version_id") or ""),
            mapped_by=normalized_mapped_by,
            created_at=str(existing.get("created_at") or ""),
            updated_at=str(existing.get("updated_at") or ""),
        )

    def list_data_deliveries(self, version_id: str | None = None, workspace: str | None = None) -> list[DataDeliveryEntity]:
        rows = self._data_deliveries
        if workspace:
            workspace_lookup = {
                str(row["id"]): str(row.get("workspace_id") or "")
                for row in self._data_sets
            }
            data_object_to_dataset = {
                str(row["id"]): str(row.get("dataset_id") or "")
                for row in self._data_objects_catalog
            }
            data_object_to_dataset.update(
                {
                    str(row["name"]): str(row.get("dataset_id") or "")
                    for row in self._data_objects_catalog
                }
            )
            rows = [
                row
                for row in rows
                if workspace_lookup.get(data_object_to_dataset.get(str(row.get("data_object_id") or ""), ""), "") == workspace
            ]
        if version_id:
            version_selector = str(version_id)
            rows = [
                row
                for row in rows
                if str(row.get("data_object_version_id") or "") == version_selector
                or str(row.get("version") or "") == version_selector
            ]
        sorted_rows = sorted(rows, key=lambda row: str(row["timestamp"]), reverse=True)
        return [
            DataDeliveryEntity(
                **{
                    **row,
                    "delivered_at": str(row.get("timestamp") or ""),
                    "layer": str(row.get("layer") or "standardized").strip() or "standardized",
                    "delivery_location": row.get("delivery_location"),
                }
            )
            for row in sorted_rows
        ]

    def get_data_delivery_note(self, delivery_id: str) -> DataDeliveryNoteEntity | None:
        delivery = next((row for row in self._data_deliveries if str(row.get("id") or "") == str(delivery_id)), None)
        if delivery is None:
            return None

        note = dict(self._data_delivery_notes.get(str(delivery_id), {}))
        metadata_json = note.get("metadata_json")
        if metadata_json is None:
            metadata_json = note.get("metadataJson")

        object_storage_classification = delivery_note_metadata_label(metadata_json, "object_storage_classification")
        evidence_classification = delivery_note_metadata_label(metadata_json, "evidence_classification")

        return DataDeliveryNoteEntity(
            id=str(note.get("id") or f"note-{delivery_id}"),
            data_delivery_id=str(delivery.get("id") or ""),
            data_object_id=str(delivery.get("data_object_id") or ""),
            data_object_version_id=str(delivery.get("data_object_version_id") or "").strip() or None,
            version=int(delivery.get("version") or 0),
            delivered_at=str(delivery.get("timestamp") or ""),
            timestamp=str(delivery.get("timestamp") or ""),
            layer=str(note.get("layer") or delivery.get("layer") or "standardized").strip() or "standardized",
            storage_location=str(note.get("storage_location") or "").strip() or None,
            delivery_location=str(delivery.get("delivery_location") or "").strip() or None,
            object_storage_classification=object_storage_classification,
            evidence_classification=evidence_classification,
            delivery_status=str(delivery.get("status") or ""),
            delivery_format=str(note.get("delivery_format") or "").strip() or None,
            delivery_format_warning=delivery_format_warning(note.get("delivery_format")),
            record_count=int(delivery.get("record_count") or 0),
            size_bytes=int(delivery.get("size_bytes") or 0),
            attributes_count=int(delivery.get("attributes_count") or 0),
            file_count=note.get("file_count"),
            file_names=note.get("file_names"),
            ingestor_name=note.get("ingestor_name"),
            ingestor_run_id=note.get("ingestor_run_id"),
            source_system=note.get("source_system"),
            source_snapshot_id=note.get("source_snapshot_id"),
            checksum=note.get("checksum"),
            checksum_algorithm=note.get("checksum_algorithm"),
            metadata_json=metadata_json,
            # DPSG-compliant redelivery fields
            delivery_type=str(note.get("delivery_type") or "initial").strip() or "initial",
            predecessor_time_event=str(note.get("predecessor_time_event") or "").strip() or None,
            superseded_by_time_event=str(note.get("superseded_by_time_event") or "").strip() or None,
            correction_reason=str(note.get("correction_reason") or "").strip() or None,
            delivered_by=str(note.get("delivered_by") or "").strip() or None,
        )

    def create_materialized_delivery_note(self, payload: dict[str, Any]) -> DataDeliveryNoteEntity:
        delivery_id = str(payload.get("data_delivery_id") or f"td-del-{uuid4().hex[:12]}")
        timestamp = str(payload.get("delivered_at") or "")
        layer = str(payload.get("layer") or "standardized").strip() or "standardized"

        delivery_row = {
            "id": delivery_id,
            "data_object_id": str(payload.get("data_object_id") or ""),
            "data_object_version_id": str(payload.get("data_object_version_id") or "").strip() or None,
            "version": int(payload.get("version") or 0),
            "timestamp": timestamp,
            "layer": layer,
            "delivery_location": str(payload.get("delivery_location") or "").strip() or None,
            "record_count": int(payload.get("record_count") or 0),
            "size_bytes": int(payload.get("size_bytes") or 0),
            "status": str(payload.get("delivery_status") or "completed"),
            "attributes_count": int(payload.get("attributes_count") or 0),
        }
        self._data_deliveries.append(delivery_row)

        self._data_delivery_notes[delivery_id] = {
            "id": str(payload.get("id") or f"note-{delivery_id}"),
            "layer": layer,
            "storage_location": str(payload.get("storage_location") or "").strip() or None,
            "delivery_format": str(payload.get("delivery_format") or "").strip() or None,
            "file_count": payload.get("file_count"),
            "ingestor_name": str(payload.get("ingestor_name") or "").strip() or None,
            "ingestor_run_id": str(payload.get("ingestor_run_id") or "").strip() or None,
            "source_system": str(payload.get("source_system") or "").strip() or None,
            "source_snapshot_id": str(payload.get("source_snapshot_id") or "").strip() or None,
            "checksum": str(payload.get("checksum") or "").strip() or None,
            "checksum_algorithm": str(payload.get("checksum_algorithm") or "").strip() or None,
            "metadata_json": payload.get("metadata_json") if isinstance(payload.get("metadata_json"), dict) else None,
            # DPSG-compliant redelivery fields
            "delivery_type": str(payload.get("delivery_type") or "initial").strip() or "initial",
            "predecessor_time_event": str(payload.get("predecessor_time_event") or "").strip() or None,
            "superseded_by_time_event": str(payload.get("superseded_by_time_event") or "").strip() or None,
            "correction_reason": str(payload.get("correction_reason") or "").strip() or None,
            "delivered_by": str(payload.get("delivered_by") or "").strip() or None,
        }
        note = self.get_data_delivery_note(delivery_id)
        if note is None:
            raise RuntimeError(f"Failed to create materialized delivery note '{delivery_id}'")
        return note

    def _attribute_row_with_mapping(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = dict(row)
        payload.setdefault("workspace_id", self._workspace_id_for_attribute_row(row))
        payload.setdefault("source_kind", "data_object")
        payload.setdefault("source_name", self._source_name_for_attribute_row(row))
        payload.setdefault("source_version_label", self._source_version_label_for_attribute_row(row))
        payload.setdefault("definition_id", None)
        payload.setdefault("definition_mapping_status", "unmapped")
        payload.setdefault("definition_mapping_attribute_id", None)
        payload.setdefault("definition_mapping_version_id", None)
        payload.setdefault("definition_mapping_mapped_by", None)
        payload.setdefault("definition_mapping_created_at", None)
        payload.setdefault("masking_method", "none")
        payload.setdefault("encryption_required", False)
        payload.setdefault("encryption_key_id", None)
        payload.setdefault("protection_configured_by", None)
        payload.setdefault("protection_updated_at", None)

        direct = next(
            (mapping for mapping in self._attribute_definition_mappings if str(mapping.get("attribute_id") or "") == str(row.get("id") or "")),
            None,
        )
        if direct is not None:
            payload["definition_id"] = direct.get("definition_id")
            payload["definition_mapping_status"] = (
                "explicit_unmapped" if str(direct.get("mapping_state") or "mapped") == "unmapped" else "explicit"
            )
            payload["definition_mapping_attribute_id"] = direct.get("attribute_id")
            payload["definition_mapping_version_id"] = row.get("version_id")
            payload["definition_mapping_mapped_by"] = direct.get("mapped_by")
            payload["definition_mapping_created_at"] = direct.get("created_at")
            if payload["definition_mapping_status"] == "explicit_unmapped":
                payload["definition_id"] = None
            return payload

        object_versions = sorted(
            [
                version
                for version in self._data_object_versions
                if str(version.get("data_object_id") or "") == str(row.get("data_object_id") or "")
                and int(version.get("version") or 0) < self._version_number(str(row.get("version_id") or ""))
            ],
            key=lambda version: int(version.get("version") or 0),
            reverse=True,
        )
        for version in object_versions:
            candidate = next(
                (
                    attribute
                    for attribute in self._attributes_catalog
                    if str(attribute.get("version_id") or "") == str(version.get("id") or "")
                    and str(attribute.get("name") or "").strip().lower() == str(row.get("name") or "").strip().lower()
                ),
                None,
            )
            if candidate is None:
                continue
            candidate_mapping = next(
                (mapping for mapping in self._attribute_definition_mappings if str(mapping.get("attribute_id") or "") == str(candidate.get("id") or "")),
                None,
            )
            if candidate_mapping is None:
                continue
            payload["definition_id"] = candidate_mapping.get("definition_id")
            payload["definition_mapping_status"] = (
                "inherited_unmapped" if str(candidate_mapping.get("mapping_state") or "mapped") == "unmapped" else "inherited"
            )
            payload["definition_mapping_attribute_id"] = candidate.get("id")
            payload["definition_mapping_version_id"] = version.get("id")
            payload["definition_mapping_mapped_by"] = candidate_mapping.get("mapped_by")
            payload["definition_mapping_created_at"] = candidate_mapping.get("created_at")
            if payload["definition_mapping_status"] == "inherited_unmapped":
                payload["definition_id"] = None
            return payload
        return payload

    def _workspace_id_for_attribute_row(self, row: dict[str, Any]) -> str:
        data_object_id = str(row.get("data_object_id") or "").strip()
        object_row = next((item for item in self._data_objects_catalog if str(item.get("id") or "") == data_object_id), None)
        if object_row is None:
            return ""
        data_set_id = str(object_row.get("dataset_id") or "").strip()
        dataset_row = next((item for item in self._data_sets if str(item.get("id") or "") == data_set_id), None)
        return str(dataset_row.get("workspace_id") or "").strip() if dataset_row is not None else ""

    def _source_name_for_attribute_row(self, row: dict[str, Any]) -> str:
        data_object_id = str(row.get("data_object_id") or "").strip()
        object_row = next((item for item in self._data_objects_catalog if str(item.get("id") or "") == data_object_id), None)
        return str(object_row.get("name") or data_object_id or "").strip() if object_row is not None else data_object_id

    def _source_version_label_for_attribute_row(self, row: dict[str, Any]) -> str:
        version_id = str(row.get("version_id") or "").strip()
        version_row = next((item for item in self._data_object_versions if str(item.get("id") or "") == version_id), None)
        if version_row is None:
            return version_id
        return f"v{int(version_row.get('version') or 0)}"

    def _version_number(self, version_id: str) -> int:
        row = next((item for item in self._data_object_versions if str(item.get("id") or "") == str(version_id)), None)
        return int(row.get("version") or 0) if row is not None else 0