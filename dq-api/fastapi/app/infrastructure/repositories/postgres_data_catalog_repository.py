from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select

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
from app.infrastructure.orm.models import AttributeCatalogRow
from app.infrastructure.orm.models import AttributeDefinitionMappingRow
from app.infrastructure.orm.models import DataDeliveryRow
from app.infrastructure.orm.models import DataDeliveryNoteRow
from app.infrastructure.orm.models import DataObjectCatalogRow
from app.infrastructure.orm.models import DataObjectRow
from app.infrastructure.orm.models import DataObjectVersionRow
from app.infrastructure.orm.models import DataProductRow
from app.infrastructure.orm.models import DataSetRow
from app.infrastructure.orm.models import RuleAttributeRow
from app.infrastructure.orm.models import RuleRow
from app.infrastructure.orm.session import session_scope


class PostgresDataCatalogRepository(DataCatalogRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_data_products(self, workspace: str | None = None) -> list[DataProductEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(DataProductRow)
            if workspace:
                stmt = stmt.where(DataProductRow.workspace_id == workspace)
            stmt = stmt.order_by(DataProductRow.name)
            rows = session.execute(stmt).scalars().all()
            return [
                DataProductEntity(
                    id=str(row.id or ""),
                    name=str(row.name or ""),
                    description=str(row.description or ""),
                    owner=str(row.owner or ""),
                    created_at=self._to_text(row.created_at),
                    icon=str(row.icon or ""),
                    workspace_id=str(row.workspace_id).strip() if row.workspace_id else "default",
                    odcs_data_product_id=str(getattr(row, "odcs_data_product_id", None) or "").strip() or None,
                    business_key=str(getattr(row, "business_key", "") or ""),
                )
                for row in rows
            ]

    def list_data_objects(self) -> list[DataObjectEntity]:
        with session_scope(self.database_url) as session:
            rows = session.execute(select(DataObjectRow).order_by(DataObjectRow.name)).scalars().all()
            return [
                DataObjectEntity(
                    id=str(row.id or ""),
                    name=str(row.name or ""),
                    description=str(row.description or ""),
                    business_key=str(getattr(row, "business_key", "") or ""),
                )
                for row in rows
            ]

    def list_data_sets(
        self,
        product_id: str | None = None,
        workspace: str | None = None,
    ) -> list[DataSetEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(DataSetRow)
            filters = []
            if product_id:
                filters.append(DataSetRow.product_id == product_id)
            if workspace:
                filters.append(DataSetRow.workspace_id == workspace)
            if filters:
                stmt = stmt.where(and_(*filters))
            stmt = stmt.order_by(DataSetRow.name)
            rows = session.execute(stmt).scalars().all()
            return [
                DataSetEntity(
                    id=str(row.id or ""),
                    product_id=str(row.product_id or ""),
                    name=str(row.name or ""),
                    description=str(row.description or ""),
                    owner=str(row.owner or ""),
                    created_at=self._to_text(row.created_at),
                    workspace_id=str(row.workspace_id).strip() if row.workspace_id else "default",
                    business_key=str(getattr(row, "business_key", "") or ""),
                )
                for row in rows
            ]

    def list_rule_attributes(self) -> list[RuleAttributeEntity]:
        with session_scope(self.database_url) as session:
            stmt = (
                select(RuleAttributeRow)
                .join(RuleRow, RuleAttributeRow.rule_id == RuleRow.id)
                .where(RuleRow.deleted_on.is_(None))
            )
            rows = session.execute(stmt).scalars().all()
            return [
                RuleAttributeEntity(
                    ruleId=str(row.rule_id or ""),
                    attributeId=str(row.attribute_id or ""),
                    threshold_override=float(row.threshold_override) if row.threshold_override is not None else None,
                )
                for row in rows
            ]

    def add_rule_attributes(self, entries: list[dict]) -> AddRuleAttributesResultEntity:
        added = 0
        seen_payload_keys: set[tuple[str, str]] = set()
        for entry in entries:
            rule_id = entry.get("ruleId")
            attribute_id = entry.get("attributeId")
            if not rule_id or not attribute_id:
                continue
            key = (str(rule_id), str(attribute_id))
            if key in seen_payload_keys:
                continue
            try:
                with session_scope(self.database_url) as session:
                    existing_rows = session.execute(
                        select(RuleAttributeRow)
                        .where(RuleAttributeRow.rule_id == key[0])
                        .where(RuleAttributeRow.attribute_id == key[1])
                    ).scalars().all()
                    if existing_rows:
                        seen_payload_keys.add(key)
                        continue

                    session.add(
                        RuleAttributeRow(
                            id=str(uuid4()),
                            rule_id=key[0],
                            attribute_id=key[1],
                            threshold_override=entry.get("thresholdOverride"),
                        )
                    )
                    session.commit()
                seen_payload_keys.add(key)
                added += 1
            except Exception:
                continue
        return AddRuleAttributesResultEntity(added=added)

    def list_data_objects_catalog(self, data_set_id: str | None = None) -> list[DataObjectCatalogEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(DataObjectCatalogRow)
            if data_set_id:
                stmt = stmt.where(DataObjectCatalogRow.dataset_id == data_set_id)
            stmt = stmt.order_by(DataObjectCatalogRow.name)
            rows = session.execute(stmt).scalars().all()
            return [
                DataObjectCatalogEntity(
                    id=str(row.id or ""),
                    dataset_id=str(row.dataset_id or ""),
                    name=str(row.name or ""),
                    description=str(row.description or ""),
                    icon=str(row.icon or ""),
                    created_at=self._to_text(row.created_at),
                    latest_version_id=row.latest_version_id,
                    business_key=str(getattr(row, "business_key", "") or ""),
                )
                for row in rows
            ]

    def list_data_object_versions(self, object_id: str | None = None) -> list[DataObjectVersionEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(DataObjectVersionRow)
            if object_id:
                stmt = stmt.where(DataObjectVersionRow.data_object_id == object_id)
            stmt = stmt.order_by(DataObjectVersionRow.version.desc())
            rows = session.execute(stmt).scalars().all()
            return [
                DataObjectVersionEntity(
                    id=str(row.id or ""),
                    data_object_id=str(row.data_object_id or ""),
                    version=int(row.version or 0),
                    created_at=self._to_text(row.created_at),
                    schema_hash=str(row.schema_hash or ""),
                    attribute_count=int(row.attribute_count or 0),
                    storage_uri=str(row.storage_uri) if row.storage_uri else None,
                    storage_format=str(row.storage_format) if row.storage_format else None,
                    storage_options_json=dict(row.storage_options_json) if row.storage_options_json else None,
                )
                for row in rows
            ]

    def get_data_object_version(self, version_id: str) -> DataObjectVersionEntity | None:
        with session_scope(self.database_url) as session:
            row = session.get(DataObjectVersionRow, version_id)
            if row is None:
                return None
            return DataObjectVersionEntity(
                id=str(row.id or ""),
                data_object_id=str(row.data_object_id or ""),
                version=int(row.version or 0),
                created_at=self._to_text(row.created_at),
                schema_hash=str(row.schema_hash or ""),
                attribute_count=int(row.attribute_count or 0),
                storage_uri=str(row.storage_uri) if row.storage_uri else None,
                storage_format=str(row.storage_format) if row.storage_format else None,
                storage_options_json=dict(row.storage_options_json) if row.storage_options_json else None,
            )

    def list_attributes_catalog(self, version_id: str | None = None) -> list[AttributeCatalogEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(AttributeCatalogRow)
            if version_id:
                stmt = stmt.where(AttributeCatalogRow.version_id == version_id)
            stmt = stmt.order_by(AttributeCatalogRow.id)
            rows = session.execute(stmt).scalars().all()
            all_attribute_rows = session.execute(select(AttributeCatalogRow)).scalars().all()
            mapping_rows = session.execute(select(AttributeDefinitionMappingRow)).scalars().all()
            direct_mappings = {
                str(row.attribute_id or ""): row
                for row in mapping_rows
            }
            versions_by_object: dict[str, list[DataObjectVersionRow]] = {}
            for version_row in session.execute(select(DataObjectVersionRow)).scalars().all():
                versions_by_object.setdefault(str(version_row.data_object_id or ""), []).append(version_row)
            for object_versions in versions_by_object.values():
                object_versions.sort(key=lambda row: int(row.version or 0), reverse=True)

            attributes_by_version: dict[str, list[AttributeCatalogRow]] = {}
            for attribute_row in all_attribute_rows:
                attributes_by_version.setdefault(str(attribute_row.version_id or ""), []).append(attribute_row)

            data_objects_by_id = {
                str(row.id or ""): row
                for row in session.execute(select(DataObjectCatalogRow)).scalars().all()
            }
            data_sets_by_id = {
                str(row.id or ""): row
                for row in session.execute(select(DataSetRow)).scalars().all()
            }

            return [
                self._attribute_catalog_entity_with_mapping(
                    row=row,
                    direct_mappings=direct_mappings,
                    versions_by_object=versions_by_object,
                    attributes_by_version=attributes_by_version,
                    data_objects_by_id=data_objects_by_id,
                    data_sets_by_id=data_sets_by_id,
                )
                for row in rows
            ]

    def get_attribute_catalog(self, attribute_id: str) -> AttributeCatalogEntity | None:
        normalized_attribute_id = str(attribute_id or "").strip()
        if not normalized_attribute_id:
            return None
        with session_scope(self.database_url) as session:
            row = session.get(AttributeCatalogRow, normalized_attribute_id)
            if row is None:
                return None
            direct_mappings = {
                str(mapping.attribute_id or ""): mapping
                for mapping in session.execute(select(AttributeDefinitionMappingRow)).scalars().all()
            }
            versions_by_object: dict[str, list[DataObjectVersionRow]] = {}
            for version_row in session.execute(select(DataObjectVersionRow)).scalars().all():
                versions_by_object.setdefault(str(version_row.data_object_id or ""), []).append(version_row)
            for object_versions in versions_by_object.values():
                object_versions.sort(key=lambda item: int(item.version or 0), reverse=True)
            attributes_by_version: dict[str, list[AttributeCatalogRow]] = {}
            for attribute_row in session.execute(select(AttributeCatalogRow)).scalars().all():
                attributes_by_version.setdefault(str(attribute_row.version_id or ""), []).append(attribute_row)
            data_objects_by_id = {
                str(item.id or ""): item
                for item in session.execute(select(DataObjectCatalogRow)).scalars().all()
            }
            data_sets_by_id = {
                str(item.id or ""): item
                for item in session.execute(select(DataSetRow)).scalars().all()
            }
            return self._attribute_catalog_entity_with_mapping(
                row=row,
                direct_mappings=direct_mappings,
                versions_by_object=versions_by_object,
                attributes_by_version=attributes_by_version,
                data_objects_by_id=data_objects_by_id,
                data_sets_by_id=data_sets_by_id,
            )

    def list_attribute_definition_mappings(
        self,
        version_id: str | None = None,
        attribute_id: str | None = None,
    ) -> list[AttributeDefinitionMappingEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(AttributeDefinitionMappingRow)
            if attribute_id:
                stmt = stmt.where(AttributeDefinitionMappingRow.attribute_id == attribute_id)
            if version_id:
                stmt = stmt.join(AttributeCatalogRow, AttributeDefinitionMappingRow.attribute_id == AttributeCatalogRow.id)
                stmt = stmt.where(AttributeCatalogRow.version_id == version_id)
            stmt = stmt.order_by(AttributeDefinitionMappingRow.attribute_id)
            rows = session.execute(stmt).scalars().all()
            return [
                AttributeDefinitionMappingEntity(
                    id=str(row.id or ""),
                    attribute_id=str(row.attribute_id or ""),
                    definition_id=str(row.definition_id or "").strip() or None,
                    mapping_state=str(row.mapping_state or "mapped"),
                    mapped_by=str(row.mapped_by or "").strip() or None,
                    created_at=self._to_text(row.created_at),
                    updated_at=self._to_text(row.updated_at),
                )
                for row in rows
            ]

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

        normalized_state = str(mapping_state or "mapped").strip().lower() or "mapped"
        if normalized_state not in {"mapped", "unmapped"}:
            raise ValueError("mapping_state must be 'mapped' or 'unmapped'")

        normalized_definition_id = str(definition_id or "").strip() or None
        if normalized_state == "mapped" and not normalized_definition_id:
            raise ValueError("definition_id is required when mapping_state is 'mapped'")
        if normalized_state == "unmapped":
            normalized_definition_id = None

        normalized_mapped_by = str(mapped_by or "").strip() or None

        with session_scope(self.database_url) as session:
            attribute_row = session.get(AttributeCatalogRow, normalized_attribute_id)
            if attribute_row is None:
                raise ValueError(f"Attribute '{normalized_attribute_id}' was not found")

            mapping_row = session.execute(
                select(AttributeDefinitionMappingRow)
                .where(AttributeDefinitionMappingRow.attribute_id == normalized_attribute_id)
            ).scalars().first()
            now = datetime.now(UTC)
            if mapping_row is None:
                mapping_row = AttributeDefinitionMappingRow(
                    id=str(uuid4()),
                    attribute_id=normalized_attribute_id,
                    definition_id=normalized_definition_id,
                    mapping_state=normalized_state,
                    mapped_by=normalized_mapped_by,
                    created_at=now,
                    updated_at=now,
                )
                session.add(mapping_row)
            else:
                mapping_row.definition_id = normalized_definition_id
                mapping_row.mapping_state = normalized_state
                mapping_row.mapped_by = normalized_mapped_by
                mapping_row.updated_at = now
            session.commit()

            return AttributeDefinitionMappingUpsertResultEntity(
                attribute_id=normalized_attribute_id,
                definition_id=normalized_definition_id,
                mapping_state=normalized_state,
                definition_mapping_status="explicit_unmapped" if normalized_state == "unmapped" else "explicit",
                version_id=str(attribute_row.version_id or ""),
                mapped_by=normalized_mapped_by,
                created_at=self._to_text(mapping_row.created_at),
                updated_at=self._to_text(mapping_row.updated_at),
            )

    def get_data_set(self, data_set_id: str) -> DataSetEntity | None:
        normalized_data_set_id = str(data_set_id or "").strip()
        if not normalized_data_set_id:
            return None

        with session_scope(self.database_url) as session:
            row = session.get(DataSetRow, normalized_data_set_id)
            if row is None:
                return None
            return DataSetEntity(
                id=str(row.id or ""),
                product_id=str(row.product_id or ""),
                name=str(row.name or ""),
                description=str(row.description or ""),
                owner=str(row.owner or ""),
                created_at=self._to_text(row.created_at),
                workspace_id=str(row.workspace_id or ""),
                business_key=str(getattr(row, "business_key", "") or ""),
            )

    def update_data_set(self, data_set_id: str, payload: dict[str, Any]) -> DataSetEntity:
        normalized_data_set_id = str(data_set_id or "").strip()
        if not normalized_data_set_id:
            raise ValueError("data_set_id is required")

        with session_scope(self.database_url) as session:
            row = session.get(DataSetRow, normalized_data_set_id)
            if row is None:
                raise ValueError(f"Data set '{normalized_data_set_id}' was not found")

            for field in ("product_id", "name", "description", "owner", "workspace_id", "business_key"):
                if field in payload and payload[field] is not None:
                    setattr(row, field, str(payload[field]).strip())
            session.commit()

            return DataSetEntity(
                id=str(row.id or ""),
                product_id=str(row.product_id or ""),
                name=str(row.name or ""),
                description=str(row.description or ""),
                owner=str(row.owner or ""),
                created_at=self._to_text(row.created_at),
                workspace_id=str(row.workspace_id or ""),
                business_key=str(getattr(row, "business_key", "") or ""),
            )

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

        with session_scope(self.database_url) as session:
            attribute_row = session.get(AttributeCatalogRow, normalized_attribute_id)
            if attribute_row is None:
                raise ValueError(f"Attribute '{normalized_attribute_id}' was not found")

            attribute_row.masking_method = str(masking_method or "none").strip().lower() or "none"
            attribute_row.encryption_required = bool(encryption_required)
            attribute_row.encryption_key_id = str(encryption_key_id or "").strip() or None
            attribute_row.protection_configured_by = str(configured_by or "").strip() or None
            attribute_row.protection_updated_at = datetime.now(UTC)
            session.commit()

            direct_mappings = {
                str(mapping.attribute_id or ""): mapping
                for mapping in session.execute(select(AttributeDefinitionMappingRow)).scalars().all()
            }
            versions_by_object: dict[str, list[DataObjectVersionRow]] = {}
            for version_row in session.execute(select(DataObjectVersionRow)).scalars().all():
                versions_by_object.setdefault(str(version_row.data_object_id or ""), []).append(version_row)
            for object_versions in versions_by_object.values():
                object_versions.sort(key=lambda item: int(item.version or 0), reverse=True)
            attributes_by_version: dict[str, list[AttributeCatalogRow]] = {}
            for candidate in session.execute(select(AttributeCatalogRow)).scalars().all():
                attributes_by_version.setdefault(str(candidate.version_id or ""), []).append(candidate)
            data_objects_by_id = {
                str(item.id or ""): item
                for item in session.execute(select(DataObjectCatalogRow)).scalars().all()
            }
            data_sets_by_id = {
                str(item.id or ""): item
                for item in session.execute(select(DataSetRow)).scalars().all()
            }
            return self._attribute_catalog_entity_with_mapping(
                row=attribute_row,
                direct_mappings=direct_mappings,
                versions_by_object=versions_by_object,
                attributes_by_version=attributes_by_version,
                data_objects_by_id=data_objects_by_id,
                data_sets_by_id=data_sets_by_id,
            )

    def list_data_deliveries(self, version_id: str | None = None, workspace: str | None = None) -> list[DataDeliveryEntity]:
        with session_scope(self.database_url) as session:
            stmt = select(DataDeliveryRow)
            if workspace is not None:
                stmt = (
                    stmt.join(
                        DataObjectCatalogRow,
                        or_(
                            DataDeliveryRow.data_object_id == DataObjectCatalogRow.id,
                            DataDeliveryRow.data_object_id == DataObjectCatalogRow.name,
                        ),
                    )
                    .join(DataSetRow, DataObjectCatalogRow.dataset_id == DataSetRow.id)
                    .where(DataSetRow.workspace_id == workspace)
                )
            if version_id:
                version_selector = str(version_id)
                predicates = [DataDeliveryRow.data_object_version_id == version_selector]
                try:
                    predicates.append(DataDeliveryRow.version == int(version_selector))
                except (TypeError, ValueError):
                    pass
                stmt = stmt.where(or_(*predicates))
            stmt = stmt.order_by(DataDeliveryRow.timestamp.desc())
            rows = session.execute(stmt).scalars().all()
            return [
                DataDeliveryEntity(
                    id=str(row.id or ""),
                    data_object_id=str(row.data_object_id or ""),
                    data_object_version_id=str(getattr(row, "data_object_version_id", None) or "").strip() or None,
                    version=int(row.version or 0),
                    delivered_at=self._to_text(row.timestamp),
                    timestamp=self._to_text(row.timestamp),
                    layer=str(getattr(row, "layer", None) or "standardized").strip() or "standardized",
                    delivery_location=str(getattr(row, "delivery_location", None) or "").strip() or None,
                    record_count=int(row.record_count or 0),
                    size_bytes=int(row.size_bytes or 0),
                    status=str(row.status or ""),
                    attributes_count=int(row.attributes_count or 0),
                )
                for row in rows
            ]

    def get_data_delivery_note(self, delivery_id: str) -> DataDeliveryNoteEntity | None:
        with session_scope(self.database_url) as session:
            delivery_rows = session.execute(
                select(DataDeliveryRow).where(DataDeliveryRow.id == delivery_id)
            ).scalars().all()
            note_rows = session.execute(
                select(DataDeliveryNoteRow).where(DataDeliveryNoteRow.data_delivery_id == delivery_id)
            ).scalars().all()
            if not delivery_rows or not note_rows:
                return None
            delivery_row = delivery_rows[0]
            note_row = note_rows[0]
            metadata_json = getattr(note_row, "metadata_json", None)
            object_storage_classification = delivery_note_metadata_label(
                metadata_json, "object_storage_classification"
            )
            evidence_classification = delivery_note_metadata_label(metadata_json, "evidence_classification")

            delivery_id_text = str(delivery_row.id or "").strip()
            return DataDeliveryNoteEntity(
                id=f"note-{delivery_id_text}" if delivery_id_text else "",
                data_delivery_id=delivery_id_text,
                data_object_id=str(delivery_row.data_object_id or ""),
                data_object_version_id=str(getattr(delivery_row, "data_object_version_id", None) or "").strip() or None,
                version=int(delivery_row.version or 0),
                delivered_at=self._to_text(delivery_row.timestamp),
                timestamp=self._to_text(delivery_row.timestamp),
                layer=str(getattr(note_row, "layer", None) or getattr(delivery_row, "layer", None) or "standardized").strip() or "standardized",
                storage_location=str(getattr(note_row, "storage_location", None) or "").strip() or None,
                delivery_location=str(getattr(delivery_row, "delivery_location", None) or "").strip() or None,
                object_storage_classification=object_storage_classification,
                evidence_classification=evidence_classification,
                delivery_status=str(delivery_row.status or ""),
                delivery_format=str(getattr(note_row, "delivery_format", None) or "").strip() or None,
                delivery_format_warning=delivery_format_warning(getattr(note_row, "delivery_format", None)),
                record_count=int(delivery_row.record_count or 0),
                size_bytes=int(delivery_row.size_bytes or 0),
                attributes_count=int(delivery_row.attributes_count or 0),
                file_count=getattr(note_row, "file_count", None),
                file_names=getattr(note_row, "file_names", None),
                ingestor_name=getattr(note_row, "ingestor_name", None),
                ingestor_run_id=getattr(note_row, "ingestor_run_id", None),
                source_system=getattr(note_row, "source_system", None),
                source_snapshot_id=getattr(note_row, "source_snapshot_id", None),
                checksum=getattr(note_row, "checksum", None),
                checksum_algorithm=getattr(note_row, "checksum_algorithm", None),
                metadata_json=metadata_json,
                # DPSG-compliant redelivery fields
                delivery_type=str(getattr(note_row, "delivery_type", None) or "initial").strip() or "initial",
                predecessor_time_event=str(getattr(note_row, "predecessor_time_event", None) or "").strip() or None,
                superseded_by_time_event=str(getattr(note_row, "superseded_by_time_event", None) or "").strip() or None,
                correction_reason=str(getattr(note_row, "correction_reason", None) or "").strip() or None,
                delivered_by=str(getattr(note_row, "delivered_by", None) or "").strip() or None,
            )

    def create_materialized_delivery_note(self, payload: dict[str, Any]) -> DataDeliveryNoteEntity:
        delivery_id = str(payload.get("data_delivery_id") or f"td-del-{uuid4().hex[:12]}")
        delivered_at = self._parse_datetime(str(payload.get("delivered_at") or ""))
        layer = str(payload.get("layer") or "standardized").strip() or "standardized"

        with session_scope(self.database_url) as session:
            session.add(
                DataDeliveryRow(
                    id=delivery_id,
                    data_object_id=str(payload.get("data_object_id") or ""),
                    data_object_version_id=str(payload.get("data_object_version_id") or "").strip() or None,
                    version=int(payload.get("version") or 0),
                    timestamp=delivered_at,
                    layer=layer,
                    delivery_location=str(payload.get("delivery_location") or "").strip() or None,
                    record_count=int(payload.get("record_count") or 0),
                    size_bytes=int(payload.get("size_bytes") or 0),
                    status=str(payload.get("delivery_status") or "completed"),
                    attributes_count=int(payload.get("attributes_count") or 0),
                )
            )
            session.flush()
            session.add(
                DataDeliveryNoteRow(
                    data_delivery_id=delivery_id,
                    layer=layer,
                    storage_location=str(payload.get("storage_location") or "").strip() or None,
                    delivery_format=str(payload.get("delivery_format") or "").strip() or None,
                    file_count=payload.get("file_count"),
                    ingestor_name=str(payload.get("ingestor_name") or "").strip() or None,
                    ingestor_run_id=str(payload.get("ingestor_run_id") or "").strip() or None,
                    source_system=str(payload.get("source_system") or "").strip() or None,
                    source_snapshot_id=str(payload.get("source_snapshot_id") or "").strip() or None,
                    checksum=str(payload.get("checksum") or "").strip() or None,
                    checksum_algorithm=str(payload.get("checksum_algorithm") or "").strip() or None,
                    metadata_json=payload.get("metadata_json") if isinstance(payload.get("metadata_json"), dict) else None,
                    # DPSG-compliant redelivery fields
                    delivery_type=str(payload.get("delivery_type") or "initial").strip() or "initial",
                    predecessor_time_event=str(payload.get("predecessor_time_event") or "").strip() or None,
                    superseded_by_time_event=str(payload.get("superseded_by_time_event") or "").strip() or None,
                    correction_reason=str(payload.get("correction_reason") or "").strip() or None,
                    delivered_by=str(payload.get("delivered_by") or "").strip() or None,
                )
            )
            session.commit()

        note = self.get_data_delivery_note(delivery_id)
        if note is None:
            raise RuntimeError(f"Failed to create materialized delivery note '{delivery_id}'")
        return note

    def get_attribute_rule_counts(self) -> dict[str, int]:
        with session_scope(self.database_url) as session:
            rows = session.execute(
                select(RuleAttributeRow.attribute_id, func.count())
                .where(RuleAttributeRow.attribute_id.is_not(None))
                .group_by(RuleAttributeRow.attribute_id)
            ).all()
            return {
                str(attribute_id): int(count_value)
                for attribute_id, count_value in rows
                if attribute_id is not None
            }

    def _attribute_catalog_entity_with_mapping(
        self,
        *,
        row: AttributeCatalogRow,
        direct_mappings: dict[str, AttributeDefinitionMappingRow],
        versions_by_object: dict[str, list[DataObjectVersionRow]],
        attributes_by_version: dict[str, list[AttributeCatalogRow]],
        data_objects_by_id: dict[str, DataObjectCatalogRow],
        data_sets_by_id: dict[str, DataSetRow],
    ) -> AttributeCatalogEntity:
        workspace_id = self._workspace_id_for_attribute_row(row=row, data_objects_by_id=data_objects_by_id, data_sets_by_id=data_sets_by_id)
        source_name = self._source_name_for_attribute_row(row=row, data_objects_by_id=data_objects_by_id)
        source_version_label = self._source_version_label_for_attribute_row(row=row)
        direct_mapping = direct_mappings.get(str(row.id or ""))
        definition_id: str | None = None
        mapping_status = "unmapped"
        mapping_attribute_id: str | None = None
        mapping_version_id: str | None = None
        mapping_mapped_by: str | None = None
        mapping_created_at: str | None = None

        if direct_mapping is not None:
            mapping_attribute_id = str(direct_mapping.attribute_id or "") or None
            mapping_version_id = str(row.version_id or "") or None
            mapping_mapped_by = str(direct_mapping.mapped_by or "").strip() or None
            mapping_created_at = self._to_text(direct_mapping.created_at) or None
            if str(direct_mapping.mapping_state or "mapped") == "unmapped":
                mapping_status = "explicit_unmapped"
            else:
                mapping_status = "explicit"
                definition_id = str(direct_mapping.definition_id or "").strip() or None
        else:
            inherited = self._resolve_inherited_attribute_definition_mapping(
                attribute_row=row,
                direct_mappings=direct_mappings,
                versions_by_object=versions_by_object,
                attributes_by_version=attributes_by_version,
            )
            if inherited is not None:
                definition_id = inherited["definition_id"]
                mapping_status = str(inherited["status"] or "unmapped")
                mapping_attribute_id = inherited["attribute_id"]
                mapping_version_id = inherited["version_id"]
                mapping_mapped_by = inherited["mapped_by"]
                mapping_created_at = inherited["created_at"]

        return AttributeCatalogEntity(
            id=str(row.id or ""),
            name=str(row.name or ""),
            type=str(row.type or ""),
            nullable=bool(row.nullable),
            format=str(row.format or ""),
            is_cde=bool(row.is_cde),
            is_primary_key=bool(row.is_primary_key),
            is_business_key=bool(getattr(row, "is_business_key", False)),
            data_object_id=str(row.data_object_id or ""),
            version_id=str(row.version_id or ""),
            workspace_id=workspace_id,
            source_kind="data_object",
            source_name=source_name,
            source_version_label=source_version_label,
            definition_id=definition_id,
            definition_mapping_status=mapping_status,
            definition_mapping_attribute_id=mapping_attribute_id,
            definition_mapping_version_id=mapping_version_id,
            definition_mapping_mapped_by=mapping_mapped_by,
            definition_mapping_created_at=mapping_created_at,
            masking_method=str(getattr(row, "masking_method", None) or "none").strip() or "none",
            encryption_required=bool(getattr(row, "encryption_required", False)),
            encryption_key_id=str(getattr(row, "encryption_key_id", None) or "").strip() or None,
            protection_configured_by=str(getattr(row, "protection_configured_by", None) or "").strip() or None,
            protection_updated_at=self._to_text(getattr(row, "protection_updated_at", None)) or None,
        )

    def _resolve_inherited_attribute_definition_mapping(
        self,
        *,
        attribute_row: AttributeCatalogRow,
        direct_mappings: dict[str, AttributeDefinitionMappingRow],
        versions_by_object: dict[str, list[DataObjectVersionRow]],
        attributes_by_version: dict[str, list[AttributeCatalogRow]],
    ) -> dict[str, str | None] | None:
        version_id = str(attribute_row.version_id or "")
        data_object_id = str(attribute_row.data_object_id or "")
        current_versions = versions_by_object.get(data_object_id, [])
        current_version_number = None
        for version_row in current_versions:
            if str(version_row.id or "") == version_id:
                current_version_number = int(version_row.version or 0)
                break
        if current_version_number is None:
            return None

        candidate_versions = [
            version_row
            for version_row in current_versions
            if int(version_row.version or 0) < current_version_number
        ]
        candidate_versions.sort(key=lambda row: int(row.version or 0), reverse=True)
        attribute_name = str(attribute_row.name or "").strip().lower()
        for version_row in candidate_versions:
            for candidate_attribute in attributes_by_version.get(str(version_row.id or ""), []):
                if str(candidate_attribute.name or "").strip().lower() != attribute_name:
                    continue
                mapping_row = direct_mappings.get(str(candidate_attribute.id or ""))
                if mapping_row is None:
                    continue
                if str(mapping_row.mapping_state or "mapped") == "unmapped":
                    return {
                        "definition_id": None,
                        "status": "inherited_unmapped",
                        "attribute_id": str(candidate_attribute.id or "") or None,
                        "version_id": str(version_row.id or "") or None,
                        "mapped_by": str(mapping_row.mapped_by or "").strip() or None,
                        "created_at": self._to_text(mapping_row.created_at) or None,
                    }
                return {
                    "definition_id": str(mapping_row.definition_id or "").strip() or None,
                    "status": "inherited",
                    "attribute_id": str(candidate_attribute.id or "") or None,
                    "version_id": str(version_row.id or "") or None,
                    "mapped_by": str(mapping_row.mapped_by or "").strip() or None,
                    "created_at": self._to_text(mapping_row.created_at) or None,
                }
        return None

    @staticmethod
    def _workspace_id_for_attribute_row(
        *,
        row: AttributeCatalogRow,
        data_objects_by_id: dict[str, DataObjectCatalogRow],
        data_sets_by_id: dict[str, DataSetRow],
    ) -> str:
        data_object_row = data_objects_by_id.get(str(row.data_object_id or ""))
        if data_object_row is None:
            return ""
        data_set_row = data_sets_by_id.get(str(data_object_row.dataset_id or ""))
        if data_set_row is None:
            return ""
        return str(data_set_row.workspace_id or "")

    @staticmethod
    def _source_name_for_attribute_row(
        *,
        row: AttributeCatalogRow,
        data_objects_by_id: dict[str, DataObjectCatalogRow],
    ) -> str:
        data_object_row = data_objects_by_id.get(str(row.data_object_id or ""))
        if data_object_row is None:
            return str(row.data_object_id or "")
        return str(data_object_row.name or row.data_object_id or "")

    def _source_version_label_for_attribute_row(self, *, row: AttributeCatalogRow) -> str:
        return str(row.version_id or "")

    @staticmethod
    def _to_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        return str(value)

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        raw = str(value or "").strip()
        if not raw:
            return datetime.now(UTC)
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
