from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

import yaml

from app.api.v1 import test_data_queue_support as _test_data_queue_support
from app.api.v1 import testing_data_requests_api as _testing_data_requests_api
from app.api.v1.schemas import CreateDataAssetRequestView
from app.api.v1.schemas import CreateDataAssetVersionRequestView
from app.api.v1.schemas import ContractImportRequestView
from app.api.v1.schemas import DataAssetGovernanceDiscoveryView
from app.api.v1.schemas import DataAssetLineageAnomalyAnnotationView
from app.api.v1.schemas import DataAssetLineageBusinessContextOverlayView
from app.api.v1.schemas import DataAssetLineageClassificationView
from app.api.v1.schemas import DataAssetLineageNodeView
from app.api.v1.schemas import DataAssetLineageView
from app.api.v1.schemas import DataAssetView
from app.api.v1.schemas import DataAssetVersionView
from app.api.v1.schemas import DataAssetValidationView
from app.api.v1.schemas import GenerateDataAssetTestDataRequestView
from app.api.v1.schemas import OkResponseView
from app.api.v1.schemas import TestDataPayloadView
from app.api.v1.schemas import UpdateDataAssetRequestView
from app.application.use_cases.testing_generated_data import GenerateTestDataForDataAssetCommand
from app.application.use_cases.testing_generated_data import GeneratedDataAssetServices
from app.application.use_cases.testing_generated_data import generate_test_data_for_data_asset as generate_test_data_for_data_asset_use_case
from app.core.dependencies import get_approvals_repository
from app.application.services.data_contract_governance import build_canonical_contract_snapshot
from app.application.services.data_contract_governance import build_observed_fields_from_data_asset_version
from app.application.services.data_contract_governance import diff_contract_snapshots
from app.application.services.data_contract_governance import validate_contract_conformance
from app.application.services.odcs_contract_text import dump_contract_text
from app.application.services.odcs_contract_text import load_contract_payload
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_incident_repository
from app.core.dependencies import get_monitor_schedule_repository
from app.core.dependencies import get_rules_repository
from app.domain.interfaces import ApprovalsRepository
from app.core.log_event import log_event
from app.domain.entities.data_asset import build_data_asset_business_context_entity
from app.domain.interfaces.v1.data_asset_repository import DataAssetRepository
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.domain.interfaces.v1.incident_repository import IncidentRepository
from app.domain.interfaces.v1.monitor_schedule_repository import MonitorScheduleRepository
from app.domain.interfaces.v1.rules_repository import RulesRepository

router = APIRouter(tags=["data-assets"])
_log = logging.getLogger(__name__)


def _contract_download_url(asset_id: str) -> str:
    normalized_asset_id = str(asset_id).strip()
    return f"/data-assets/{normalized_asset_id}/contract"


def _asset_view(entity: Any) -> DataAssetView:
    view = DataAssetView.model_validate(entity)
    return view.model_copy(update={"dataContractDownloadUrl": _contract_download_url(view.id)})


def _version_view(entity: Any) -> DataAssetVersionView:
    view = DataAssetVersionView.model_validate(entity)
    return view.model_copy(update={"dataContractDownloadUrl": _contract_download_url(view.dataAssetId or view.id)})


def _contract_logical_type(field_type: str) -> str:
    normalized = str(field_type or "").strip().lower()
    if normalized in {"string", "text", "varchar", "char", "uuid"}:
        return "string"
    if normalized in {"int", "integer", "smallint", "bigint"}:
        return "integer"
    if normalized in {"float", "double", "decimal", "number", "numeric"}:
        return "number"
    if normalized in {"bool", "boolean"}:
        return "boolean"
    if normalized in {"date"}:
        return "date"
    if normalized in {"timestamp", "datetime", "date-time", "datetimeoffset"}:
        return "date-time"
    return "string"


def _contract_physical_type(field_type: str) -> str:
    normalized = str(field_type or "").strip()
    return normalized.upper() if normalized else "STRING"


def _contract_properties(version: Any | None) -> list[dict[str, Any]]:
    properties: list[dict[str, Any]] = []
    if version is None:
        return properties

    for binding in getattr(version, "source_bindings", []) or []:
        field_name = str(getattr(binding, "source_field_name", "") or getattr(binding, "source_field_id", "") or "").strip()
        if not field_name:
            continue
        field_type = str(getattr(binding, "source_field_type", "") or "").strip()
        properties.append(
            {
                "name": field_name,
                "logicalType": _contract_logical_type(field_type),
                "description": f"Referenced field {getattr(binding, 'source_field_id', '')} from data object version {getattr(binding, 'source_data_object_version_id', '')}",
                "required": not bool(getattr(binding, "nullable", True)),
                "unique": False,
                "classification": "public",
                "physicalType": _contract_physical_type(field_type),
            }
        )

    for derived_field in getattr(version, "derived_fields", []) or []:
        field_name = str(getattr(derived_field, "name", "") or "").strip()
        if not field_name:
            continue
        field_type = str(getattr(derived_field, "data_type", "") or "").strip()
        properties.append(
            {
                "name": field_name,
                "logicalType": _contract_logical_type(field_type),
                "description": str(getattr(derived_field, "expression", "") or "").strip(),
                "required": not bool(getattr(derived_field, "nullable", True)) if getattr(derived_field, "nullable", None) is not None else False,
                "unique": False,
                "classification": "derived",
                "physicalType": _contract_physical_type(field_type or "derived"),
            }
        )

    if not properties:
        for preview_column in getattr(version, "upload_preview", None).columns if getattr(version, "upload_preview", None) is not None else []:
            field_name = str(getattr(preview_column, "name", "") or "").strip()
            if not field_name:
                continue
            field_type = str(getattr(preview_column, "data_type", "") or "").strip()
            properties.append(
                {
                    "name": field_name,
                    "logicalType": _contract_logical_type(field_type),
                    "description": "Schema preview column",
                    "required": not bool(getattr(preview_column, "nullable", True)),
                    "unique": False,
                    "classification": "public",
                    "physicalType": _contract_physical_type(field_type),
                }
            )

    return properties


def _build_data_asset_contract_payload(asset: Any, version: Any | None) -> dict[str, Any]:
    asset_name = str(getattr(asset, "name", "") or getattr(asset, "id", "") or "").strip()
    asset_description = str(getattr(asset, "description", "") or "").strip()
    workspace_id = str(getattr(asset, "workspace_id", "") or "").strip()
    status = str(getattr(asset, "status", "draft") or "draft").strip() or "draft"
    version_number = str(getattr(version, "version", 1) or 1).strip()
    created_at = str(getattr(version, "created_at", "") or getattr(asset, "created_at", "") or "").strip()
    properties = _contract_properties(version)
    business_context = getattr(asset, "business_context", None)
    dataset_id = str(getattr(business_context, "dataset_id", "") or "").strip()
    data_product_id = str(getattr(business_context, "data_product_id", "") or "").strip()
    domain = str(getattr(business_context, "domain", "") or "").strip()
    owner = str(getattr(business_context, "owner", "") or "").strip()
    steward = str(getattr(business_context, "steward", "") or "").strip()
    business_definitions = [str(item).strip() for item in list(getattr(business_context, "business_definitions", []) or []) if str(item).strip()]
    lineage_references = [str(item).strip() for item in list(getattr(business_context, "lineage_references", []) or []) if str(item).strip()]
    validation_suites = [str(item).strip() for item in list(getattr(business_context, "validation_suites", []) or []) if str(item).strip()]
    validation_plans = [str(item).strip() for item in list(getattr(business_context, "validation_plans", []) or []) if str(item).strip()]
    tags = list(dict.fromkeys([
        *[str(item).strip() for item in list(getattr(business_context, "tags", []) or []) if str(item).strip()],
        "dq-made-easy",
        "data-asset",
        "odcs",
    ]))

    return {
        "apiVersion": "v3.1.0",
        "kind": "DataContract",
        "id": f"urn:dq:contract:{getattr(asset, 'id', '')}",
        "name": asset_name,
        "version": f"{version_number}.0.0",
        "status": status if status in {"active", "draft", "inactive"} else "active",
        "owner": {
            "name": owner or steward or workspace_id or "DQ Data Assets",
        },
        "contact": {
            "name": steward or owner or "DQ Data Assets",
            "email": "dq-data-assets@example.com",
        },
        "domain": domain or workspace_id or "dq",
        "tags": tags,
        "description": {
            "purpose": asset_description or f"Generated contract for {asset_name}",
            "limitations": "- Source bindings remain reference-bound to the selected data object versions.\n- Derived fields are authored by the user and are part of the asset version contract.",
            "usage": f"Download and share this generated contract for {asset_name}.",
        },
        "extension": {
            "dq": {
                "dataset_id": dataset_id,
                "data_product_id": data_product_id,
                "business_definitions": business_definitions,
                "lineage_references": lineage_references,
                "validation_suites": validation_suites,
                "validation_plans": validation_plans,
                "ownership": {
                    "owner": owner,
                    "steward": steward,
                    "domain": domain,
                },
            },
        },
        "schema": [
            {
                "name": asset_name or getattr(asset, "id", ""),
                "logicalType": "object",
                "physicalType": "table",
                "description": asset_description or f"Data Asset {getattr(asset, 'id', '')}",
                "properties": properties,
            }
        ],
        "quality": {
            "type": "SodaCL",
            "specification": f"checks for {asset_name or getattr(asset, 'id', '')}:\n  # Generated contract placeholder - refine in the UI as needed.",
        },
    }


def _build_data_asset_contract_yaml(asset: Any, version: Any | None) -> str:
    return dump_contract_text(_build_data_asset_contract_payload(asset, version), contract_format="yaml")


def _build_data_asset_import_payload(contract_payload: Mapping[str, Any], existing_asset: Any) -> dict[str, Any]:
    description = contract_payload.get("description") if isinstance(contract_payload.get("description"), Mapping) else {}
    extension = contract_payload.get("extension") if isinstance(contract_payload.get("extension"), Mapping) else {}
    dq_extension = extension.get("dq") if isinstance(extension, Mapping) and isinstance(extension.get("dq"), Mapping) else {}
    owner = contract_payload.get("owner") if isinstance(contract_payload.get("owner"), Mapping) else {}
    contact = contract_payload.get("contact") if isinstance(contract_payload.get("contact"), Mapping) else {}
    ownership = dq_extension.get("ownership") if isinstance(dq_extension.get("ownership"), Mapping) else {}

    imported_name = str(contract_payload.get("name") or getattr(existing_asset, "name", "") or "").strip()
    imported_description = str(description.get("purpose") or getattr(existing_asset, "description", "") or "").strip()
    imported_workspace_id = str(contract_payload.get("domain") or getattr(existing_asset, "workspace_id", "") or "").strip()
    imported_owner = str(owner.get("name") or contact.get("name") or getattr(existing_asset, "owner", "") or "").strip()

    business_context_payload = {
        "dataset_id": str(dq_extension.get("dataset_id") or "").strip(),
        "data_product_id": str(dq_extension.get("data_product_id") or "").strip(),
        "domain": str(ownership.get("domain") or contract_payload.get("domain") or "").strip(),
        "owner": str(ownership.get("owner") or imported_owner or "").strip(),
        "purpose": str(description.get("purpose") or "").strip(),
        "steward": str(contact.get("name") or ownership.get("steward") or "").strip(),
        "criticality": str(ownership.get("criticality") or "").strip(),
        "tags": list(contract_payload.get("tags") or []),
        "business_definitions": list(dq_extension.get("business_definitions") or []),
        "lineage_references": list(dq_extension.get("lineage_references") or []),
        "validation_suites": list(dq_extension.get("validation_suites") or []),
        "validation_plans": list(dq_extension.get("validation_plans") or []),
        "consumers": list(dq_extension.get("consumers") or []),
    }

    return {
        "name": imported_name,
        "description": imported_description,
        "workspace_id": imported_workspace_id or getattr(existing_asset, "workspace_id", ""),
        "status": str(contract_payload.get("status") or getattr(existing_asset, "status", "draft") or "draft").strip() or "draft",
        "current_version_id": getattr(existing_asset, "current_version_id", None),
        "source_object_version_ids": list(getattr(existing_asset, "source_object_version_ids", []) or []),
        "business_context": build_data_asset_business_context_entity(business_context_payload),
    }


def _build_data_asset_contract_snapshot(asset_id: str, contract_yaml: str) -> dict[str, Any]:
    parsed = yaml.safe_load(contract_yaml)
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=500, detail=f"Data Asset contract '{asset_id}' has invalid structure")
    return build_canonical_contract_snapshot(parsed, data_source_id=asset_id, source_kind="data_asset")


def _current_asset_contract_source(asset_id: str, repository: DataAssetRepository) -> tuple[Any, Any, str]:
    asset, version = _resolve_contract_source(asset_id, repository)
    contract_yaml = _build_data_asset_contract_yaml(asset, version)
    return asset, version, contract_yaml


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _iter_text_values(value: Any) -> list[str]:
    values: list[str] = []
    if value is None:
        return values
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            values.append(normalized)
            if normalized[:1] in {"{", "["}:
                try:
                    parsed = json.loads(normalized)
                except ValueError:
                    pass
                else:
                    values.extend(_iter_text_values(parsed))
        return values
    if isinstance(value, Mapping):
        for item in value.values():
            values.extend(_iter_text_values(item))
        return values
    if isinstance(value, (list, tuple, set)):
        for item in value:
            values.extend(_iter_text_values(item))
    return values


def _value_contains_any_id(value: Any, candidate_ids: set[str]) -> bool:
    if not candidate_ids:
        return False
    for text in _iter_text_values(value):
        if any(candidate_id in text for candidate_id in candidate_ids):
            return True
    return False


def _build_lineage_node(
    *,
    kind: str,
    node_id: str,
    name: str,
    workspace_id: str | None = None,
    detail: str | None = None,
    navigation_target: str | None = None,
) -> DataAssetLineageNodeView:
    return DataAssetLineageNodeView(
        kind=kind,
        id=node_id,
        name=name,
        workspaceId=workspace_id,
        detail=detail,
        navigationTarget=navigation_target,
    )


def _upsert_lineage_node(nodes: dict[tuple[str, str], DataAssetLineageNodeView], node: DataAssetLineageNodeView) -> None:
    key = (node.kind, node.id)
    if key not in nodes:
        nodes[key] = node


def _build_lineage_business_context_overlay(asset: Any, *, contract_change_count: int, contract_notes: list[str]) -> DataAssetLineageBusinessContextOverlayView | None:
    business_context = getattr(asset, "business_context", None)
    if business_context is None:
        return None

    consumers = [str(item).strip() for item in list(getattr(business_context, "consumers", []) or []) if str(item).strip()]
    domain = str(getattr(business_context, "domain", "") or "").strip()
    purpose = str(getattr(business_context, "purpose", "") or "").strip()
    steward = str(getattr(business_context, "steward", "") or "").strip()
    criticality = str(getattr(business_context, "criticality", "") or "").strip()
    summary_parts = [part for part in [domain, purpose, steward, criticality] if part]
    if contract_change_count > 0:
        summary_parts.append(f"{contract_change_count} contract change(s)")
    if contract_notes:
        summary_parts.append(contract_notes[0])

    return DataAssetLineageBusinessContextOverlayView(
        domain=domain,
        purpose=purpose,
        steward=steward,
        criticality=criticality,
        consumers=consumers,
        summary=" · ".join(summary_parts) if summary_parts else "Business context available",
    )


def _build_lineage_classification_view(
    *,
    business_context_overlay: DataAssetLineageBusinessContextOverlayView | None,
    contract_change_count: int,
    impacted_rule_count: int,
    impacted_monitor_count: int,
    impacted_incident_count: int,
) -> DataAssetLineageClassificationView:
    criticality = str(getattr(business_context_overlay, "criticality", "") or "").strip().lower()
    if criticality in {"high", "critical"} or impacted_incident_count > 0:
        classification = "restricted"
    elif criticality in {"medium", "elevated"} or contract_change_count > 0 or impacted_monitor_count > 0:
        classification = "internal"
    else:
        classification = "public"

    signals: list[str] = []
    if business_context_overlay is not None:
        if business_context_overlay.domain:
            signals.append(f"domain:{business_context_overlay.domain}")
        if business_context_overlay.steward:
            signals.append(f"steward:{business_context_overlay.steward}")
        if business_context_overlay.consumers:
            signals.append(f"consumers:{len(business_context_overlay.consumers)}")
    if contract_change_count > 0:
        signals.append(f"contract_changes:{contract_change_count}")
    if impacted_rule_count > 0:
        signals.append(f"rules:{impacted_rule_count}")
    if impacted_monitor_count > 0:
        signals.append(f"monitors:{impacted_monitor_count}")
    if impacted_incident_count > 0:
        signals.append(f"incidents:{impacted_incident_count}")

    rationale = "Classification derived from business context and lineage impact signals."
    if criticality:
        rationale = f"Classification derived from business criticality '{criticality}'."
    if impacted_incident_count > 0:
        rationale = f"{rationale} Incidents on the lineage raise the exposure level."
    elif contract_change_count > 0:
        rationale = f"{rationale} Contract changes were detected on the latest lineage snapshot."

    return DataAssetLineageClassificationView(
        classification=classification,
        rationale=rationale,
        signals=signals,
    )


def _build_lineage_anomaly_annotations(
    *,
    contract_change_count: int,
    impacted_monitor_scope_ids: list[str],
    impacted_incident_ids: list[str],
    contract_notes: list[str],
) -> list[DataAssetLineageAnomalyAnnotationView]:
    annotations: list[DataAssetLineageAnomalyAnnotationView] = []
    if contract_change_count > 0:
        annotations.append(
            DataAssetLineageAnomalyAnnotationView(
                kind="contract_change",
                severity="medium",
                summary=f"Latest contract analysis shows {contract_change_count} changed field(s).",
                source="contract_analysis",
                details={"contract_change_count": contract_change_count, "notes": list(contract_notes)},
            )
        )
    if impacted_monitor_scope_ids:
        annotations.append(
            DataAssetLineageAnomalyAnnotationView(
                kind="monitor_scope",
                severity="medium",
                summary=f"{len(impacted_monitor_scope_ids)} monitor schedule(s) target this asset or its source datasets.",
                source="monitor_schedule_repository",
                details={"monitor_scope_ids": list(impacted_monitor_scope_ids)},
            )
        )
    if impacted_incident_ids:
        annotations.append(
            DataAssetLineageAnomalyAnnotationView(
                kind="incident_hotspot",
                severity="high",
                summary=f"{len(impacted_incident_ids)} incident(s) were raised on this lineage.",
                source="incident_repository",
                details={"incident_ids": list(impacted_incident_ids)},
            )
        )
    return annotations


_HIGH_PRIORITY_CLASSIFICATIONS = {
    "confidential",
    "high_value",
    "pii",
    "real_evidence",
    "restricted",
    "sensitive",
}


def _normalize_discovery_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "_".join(part for part in re.split(r"[^a-z0-9]+", text) if part)


def _build_governance_discovery_view(
    *,
    asset: Any,
    repository: DataAssetRepository,
    data_catalog_repository: DataCatalogRepository,
) -> DataAssetGovernanceDiscoveryView:
    current_version_id = _normalized_text(getattr(asset, "current_version_id", ""))
    version = repository.get_data_asset_version(str(getattr(asset, "id", "") or ""), current_version_id) if current_version_id else None
    if version is None:
        versions = repository.list_data_asset_versions(str(getattr(asset, "id", "") or ""))
        version = versions[0] if versions else None

    workspace_id = _normalized_text(getattr(asset, "workspace_id", "")) or None
    source_version_ids = [str(item).strip() for item in getattr(asset, "source_object_version_ids", []) if str(item).strip()]
    if not source_version_ids and current_version_id:
        source_version_ids = [current_version_id]

    deliveries_by_id: dict[str, Any] = {}
    for version_id in source_version_ids:
        for delivery in data_catalog_repository.list_data_deliveries(version_id=version_id, workspace=workspace_id):
            delivery_id = _normalized_text(getattr(delivery, "id", ""))
            if delivery_id and delivery_id not in deliveries_by_id:
                deliveries_by_id[delivery_id] = delivery
    deliveries = sorted(deliveries_by_id.values(), key=lambda item: _normalized_text(getattr(item, "timestamp", "")), reverse=True)

    object_storage_classifications: list[str] = []
    evidence_classifications: list[str] = []
    signals: list[str] = []
    latest_delivery_id = _normalized_text(getattr(deliveries[0], "id", "")) if deliveries else None
    latest_delivery_at = _normalized_text(getattr(deliveries[0], "timestamp", "")) if deliveries else None

    for delivery in deliveries:
        note = data_catalog_repository.get_data_delivery_note(str(getattr(delivery, "id", "") or ""))
        if note is None:
            continue
        object_storage_classification = _normalize_discovery_label(getattr(note, "object_storage_classification", ""))
        evidence_classification = _normalize_discovery_label(getattr(note, "evidence_classification", ""))
        if object_storage_classification:
            object_storage_classifications.append(object_storage_classification)
        if evidence_classification:
            evidence_classifications.append(evidence_classification)
        if object_storage_classification:
            signals.append(f"object_storage_classification:{object_storage_classification}")
        if evidence_classification:
            signals.append(f"evidence_classification:{evidence_classification}")

    business_context = getattr(asset, "business_context", None)
    criticality = _normalize_discovery_label(getattr(business_context, "criticality", ""))
    consumer_count = len([item for item in list(getattr(business_context, "consumers", []) or []) if str(item).strip()])
    if criticality:
        signals.append(f"business_criticality:{criticality}")
    if consumer_count:
        signals.append(f"consumer_count:{consumer_count}")
    if deliveries:
        signals.append(f"delivery_count:{len(deliveries)}")

    normalized_classifications = {
        *_HIGH_PRIORITY_CLASSIFICATIONS,
        *(classification for classification in object_storage_classifications if classification),
        *(classification for classification in evidence_classifications if classification),
    }
    if normalized_classifications & _HIGH_PRIORITY_CLASSIFICATIONS or criticality in {"high", "critical"}:
        priority = "high"
    elif object_storage_classifications or evidence_classifications or criticality in {"medium", "elevated"} or consumer_count > 1:
        priority = "medium"
    else:
        priority = "low"

    summary_parts = []
    if evidence_classifications:
        summary_parts.append(f"Evidence classifications: {', '.join(dict.fromkeys(evidence_classifications))}")
    if object_storage_classifications:
        summary_parts.append(f"Storage classifications: {', '.join(dict.fromkeys(object_storage_classifications))}")
    if criticality:
        summary_parts.append(f"Business criticality: {criticality}")
    if consumer_count:
        summary_parts.append(f"Consumers: {consumer_count}")
    if not summary_parts:
        summary_parts.append("No governance discovery signals were found")

    discovery_view = DataAssetGovernanceDiscoveryView(
        assetId=str(getattr(asset, "id", "") or ""),
        priority=priority,
        summary="; ".join(summary_parts),
        objectStorageClassifications=list(dict.fromkeys(object_storage_classifications)),
        evidenceClassifications=list(dict.fromkeys(evidence_classifications)),
        signals=signals,
        latestDeliveryId=latest_delivery_id,
        latestDeliveryAt=latest_delivery_at,
    )
    snapshot = repository.record_data_asset_lineage_snapshot(
        discovery_view.assetId,
        {
            "snapshot_kind": "governance_discovery",
            "captured_at": discovery_view.capturedAt or discovery_view.latestDeliveryAt or "",
            "lineage_json": discovery_view.model_dump(mode="python", by_alias=True, exclude_none=False),
            "classification_view": {
                "priority": discovery_view.priority,
                "signals": list(discovery_view.signals),
            },
            "business_context_overlay": {
                "criticality": criticality,
                "consumer_count": consumer_count,
            },
            "anomaly_annotations": [],
        },
    )
    return discovery_view.model_copy(update={"snapshotId": snapshot.id, "capturedAt": snapshot.captured_at})


def _rule_matches_asset(rule: Any, *, candidate_ids: set[str]) -> bool:
    if _normalized_text(getattr(rule, "id", "")) in candidate_ids:
        return True
    if _value_contains_any_id(getattr(rule, "check_type_params", None), candidate_ids):
        return True
    if _value_contains_any_id(getattr(rule, "dsl", None), candidate_ids):
        return True
    if _value_contains_any_id(getattr(rule, "joinConditions", None), candidate_ids):
        return True
    if _value_contains_any_id(getattr(rule, "aliasMappings", None), candidate_ids):
        return True
    return _value_contains_any_id(getattr(rule, "expression", None), candidate_ids)


async def _build_lineage_payload(
    *,
    asset: Any,
    version: Any | None,
    data_asset_repository: DataAssetRepository,
    data_catalog_repository: DataCatalogRepository,
    rules_repository: RulesRepository,
    monitor_schedule_repository: MonitorScheduleRepository,
    incident_repository: IncidentRepository,
    contract_change_count: int,
    contract_notes: list[str],
) -> DataAssetLineageView:
    upstream_nodes: dict[tuple[str, str], DataAssetLineageNodeView] = {}
    downstream_nodes: dict[tuple[str, str], DataAssetLineageNodeView] = {}

    source_version_ids = [str(item).strip() for item in getattr(asset, "source_object_version_ids", []) if str(item).strip()]
    object_by_id = {str(row.id): row for row in data_catalog_repository.list_data_objects()}
    catalog_versions = {str(row.id): row for row in data_catalog_repository.list_data_object_versions()}
    catalog_objects = {str(row.id): row for row in data_catalog_repository.list_data_objects_catalog()}
    catalog_datasets = {str(row.id): row for row in data_catalog_repository.list_data_sets()}
    catalog_products = {str(row.id): row for row in data_catalog_repository.list_data_products()}

    source_object_ids: set[str] = set()
    source_dataset_ids: set[str] = set()
    source_product_ids: set[str] = set()

    for source_version_id in source_version_ids:
        source_version = catalog_versions.get(source_version_id)
        if source_version is None:
            continue

        source_object_id = _normalized_text(getattr(source_version, "data_object_id", ""))
        source_object_ids.add(source_object_id)
        source_object = object_by_id.get(source_object_id)
        source_catalog_object = catalog_objects.get(source_object_id)
        source_dataset = catalog_datasets.get(_normalized_text(getattr(source_catalog_object, "dataset_id", ""))) if source_catalog_object is not None else None
        source_product = catalog_products.get(_normalized_text(getattr(source_dataset, "product_id", ""))) if source_dataset is not None else None

        _upsert_lineage_node(
            upstream_nodes,
            _build_lineage_node(
                kind="data_object_version",
                node_id=source_version.id,
                name=f"Version {getattr(source_version, 'version', '')}",
                workspace_id=_normalized_text(getattr(asset, "workspace_id", "")) or None,
                detail=_normalized_text(getattr(source_catalog_object, "name", "")) or source_object_id,
                navigation_target="data-browser",
            ),
        )
        if source_object is not None:
            _upsert_lineage_node(
                upstream_nodes,
                _build_lineage_node(
                    kind="data_object",
                    node_id=source_object.id,
                    name=_normalized_text(getattr(source_object, "name", "")) or source_object.id,
                    workspace_id=_normalized_text(getattr(asset, "workspace_id", "")) or None,
                    detail="Upstream catalog object",
                    navigation_target="data-browser",
                ),
            )
        if source_catalog_object is not None:
            dataset_id = _normalized_text(getattr(source_catalog_object, "dataset_id", ""))
            source_dataset_ids.add(dataset_id)
            _upsert_lineage_node(
                upstream_nodes,
                _build_lineage_node(
                    kind="data_set",
                    node_id=dataset_id,
                    name=_normalized_text(getattr(source_dataset, "name", "")) or dataset_id,
                    workspace_id=_normalized_text(getattr(source_dataset, "workspace_id", "")) or _normalized_text(getattr(asset, "workspace_id", "")) or None,
                    detail="Catalog dataset",
                    navigation_target="data-browser",
                ),
            )
        if source_dataset is not None:
            product_id = _normalized_text(getattr(source_dataset, "product_id", ""))
            source_product_ids.add(product_id)
            _upsert_lineage_node(
                upstream_nodes,
                _build_lineage_node(
                    kind="data_product",
                    node_id=product_id,
                    name=_normalized_text(getattr(source_product, "name", "")) or product_id,
                    workspace_id=_normalized_text(getattr(source_product, "workspace_id", "")) or _normalized_text(getattr(asset, "workspace_id", "")) or None,
                    detail="Business product",
                    navigation_target="data-browser",
                ),
            )

    source_ids_for_matching = {
        _normalized_text(getattr(asset, "id", "")),
        *source_version_ids,
        *source_object_ids,
        *source_dataset_ids,
        *source_product_ids,
    }

    rule_records = await rules_repository.list_rule_records()
    impacted_rule_ids: list[str] = []
    for rule in rule_records:
        if not _rule_matches_asset(rule, candidate_ids=source_ids_for_matching):
            continue
        rule_id = _normalized_text(getattr(rule, "id", ""))
        if rule_id:
            impacted_rule_ids.append(rule_id)
        _upsert_lineage_node(
            downstream_nodes,
            _build_lineage_node(
                kind="rule",
                node_id=rule_id or _normalized_text(getattr(rule, "name", "rule")) or "rule",
                name=_normalized_text(getattr(rule, "name", "Rule")) or "Rule",
                workspace_id=_normalized_text(getattr(rule, "workspace", "")) or None,
                detail=_normalized_text(getattr(rule, "dimension", "")) or _normalized_text(getattr(rule, "check_type", "")) or None,
                navigation_target="rules",
            ),
        )

    impacted_monitor_scope_ids: list[str] = []
    monitor_schedules = monitor_schedule_repository.list_monitor_schedules(workspace_id=_normalized_text(getattr(asset, "workspace_id", "")) or None)
    for schedule in monitor_schedules:
        scope_kind = _normalized_text(getattr(schedule, "scope_kind", ""))
        scope_id = _normalized_text(getattr(schedule, "scope_id", ""))
        if scope_kind == "data_asset" and scope_id == _normalized_text(getattr(asset, "id", "")):
            impacted_monitor_scope_ids.append(scope_id)
        elif scope_kind == "source_dataset" and scope_id in source_dataset_ids:
            impacted_monitor_scope_ids.append(scope_id)
        else:
            continue

        _upsert_lineage_node(
            downstream_nodes,
            _build_lineage_node(
                kind="monitor_schedule",
                node_id=_normalized_text(getattr(schedule, "id", "")) or scope_id,
                name=f"{scope_kind.replace('_', ' ').title()} monitor",
                workspace_id=_normalized_text(getattr(schedule, "workspace_id", "")) or None,
                detail=_normalized_text(getattr(schedule, "monitor_type", "")) or "scheduled monitor",
                navigation_target="reports-rule-monitoring",
            ),
        )

    impacted_incident_ids: list[str] = []
    incidents = incident_repository.list_incidents(workspace_id=_normalized_text(getattr(asset, "workspace_id", "")) or None, limit=500, offset=0)
    impacted_rule_id_set = set(impacted_rule_ids)
    for incident in incidents:
        scope_kind = _normalized_text(getattr(incident, "scope_kind", ""))
        scope_id = _normalized_text(getattr(incident, "scope_id", ""))
        violated_rule_ids = {str(item).strip() for item in (getattr(incident, "violated_rule_ids", None) or []) if str(item).strip()}
        incident_id = _normalized_text(getattr(incident, "id", ""))
        if scope_kind == "data_asset" and scope_id == _normalized_text(getattr(asset, "id", "")):
            impacted_incident_ids.append(incident_id)
        elif scope_kind == "source_dataset" and scope_id in source_dataset_ids:
            impacted_incident_ids.append(incident_id)
        elif violated_rule_ids & impacted_rule_id_set:
            impacted_incident_ids.append(incident_id)
        else:
            continue

        _upsert_lineage_node(
            downstream_nodes,
            _build_lineage_node(
                kind="incident",
                node_id=incident_id or scope_id,
                name=_normalized_text(getattr(incident, "title", "Incident")) or "Incident",
                workspace_id=_normalized_text(getattr(incident, "workspace_id", "")) or None,
                detail=_normalized_text(getattr(incident, "status", "")) or _normalized_text(getattr(incident, "incident_kind", "")) or None,
                navigation_target="reports-incidents",
            ),
        )

    notes = list(contract_notes)
    if contract_change_count > 0:
        notes.append(f"Latest contract analysis shows {contract_change_count} changed field(s).")
    if impacted_rule_ids:
        notes.append(f"{len(impacted_rule_ids)} rule(s) reference this asset lineage.")
    if impacted_monitor_scope_ids:
        notes.append(f"{len(impacted_monitor_scope_ids)} monitor schedule(s) target this asset or its source datasets.")
    if impacted_incident_ids:
        notes.append(f"{len(impacted_incident_ids)} incident(s) were raised on this lineage.")

    business_context_overlay = _build_lineage_business_context_overlay(
        asset,
        contract_change_count=contract_change_count,
        contract_notes=contract_notes,
    )
    classification_view = _build_lineage_classification_view(
        business_context_overlay=business_context_overlay,
        contract_change_count=contract_change_count,
        impacted_rule_count=len(impacted_rule_ids),
        impacted_monitor_count=len(impacted_monitor_scope_ids),
        impacted_incident_count=len(impacted_incident_ids),
    )
    anomaly_annotations = _build_lineage_anomaly_annotations(
        contract_change_count=contract_change_count,
        impacted_monitor_scope_ids=impacted_monitor_scope_ids,
        impacted_incident_ids=impacted_incident_ids,
        contract_notes=contract_notes,
    )

    lineage_payload = {
        "dataAsset": _asset_view(asset).model_dump(mode="python", by_alias=False, exclude_none=False),
        "upstreamNodes": [node.model_dump(mode="python", by_alias=False, exclude_none=False) for node in upstream_nodes.values()],
        "downstreamNodes": [node.model_dump(mode="python", by_alias=False, exclude_none=False) for node in downstream_nodes.values()],
        "impactSummary": {
            "contractChangeCount": contract_change_count,
            "impactedRuleIds": impacted_rule_ids,
            "impactedMonitorScopeIds": impacted_monitor_scope_ids,
            "impactedIncidentIds": impacted_incident_ids,
            "notes": notes,
        },
        "businessContextOverlay": business_context_overlay.model_dump(mode="python", by_alias=False, exclude_none=False) if business_context_overlay is not None else None,
        "classificationView": classification_view.model_dump(mode="python", by_alias=False, exclude_none=False),
        "anomalyAnnotations": [annotation.model_dump(mode="python", by_alias=False, exclude_none=False) for annotation in anomaly_annotations],
    }

    lineage_view = DataAssetLineageView.model_validate(lineage_payload)
    snapshot = data_asset_repository.record_data_asset_lineage_snapshot(
        str(getattr(asset, "id", "") or "").strip(),
        lineage_view.model_dump(mode="python", by_alias=True, exclude_none=False),
    )
    return lineage_view.model_copy(update={"snapshotId": snapshot.id, "capturedAt": snapshot.captured_at})


def _resolve_contract_source(asset_id: str, repository: DataAssetRepository) -> tuple[Any, Any | None]:
    asset = repository.get_data_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Data Asset '{asset_id}' was not found")

    version = None
    current_version_id = str(getattr(asset, "current_version_id", "") or "").strip()
    if current_version_id:
        version = repository.get_data_asset_version(asset_id, current_version_id)
    if version is None:
        versions = repository.list_data_asset_versions(asset_id)
        version = versions[0] if versions else None

    return asset, version


def _resolve_data_asset_version(
    asset_id: str,
    version_id: str | None,
    repository: DataAssetRepository,
) -> tuple[Any, Any]:
    asset = repository.get_data_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Data Asset '{asset_id}' was not found")

    version = None
    normalized_version_id = str(version_id or "").strip()
    if normalized_version_id:
        version = repository.get_data_asset_version(asset_id, normalized_version_id)
    else:
        current_version_id = str(getattr(asset, "current_version_id", "") or "").strip()
        if current_version_id:
            version = repository.get_data_asset_version(asset_id, current_version_id)
        if version is None:
            versions = repository.list_data_asset_versions(asset_id)
            version = versions[0] if versions else None

    if version is None:
        raise HTTPException(status_code=400, detail=f"Data Asset '{asset_id}' has no versions to resolve")

    return asset, version


def _create_payload(body: CreateDataAssetRequestView) -> dict[str, Any]:
    return body.model_dump(mode="python", by_alias=True, exclude_none=True)


def _update_payload(body: UpdateDataAssetRequestView) -> dict[str, Any]:
    return body.model_dump(mode="python", by_alias=True, exclude_none=True)


def _version_payload(body: CreateDataAssetVersionRequestView) -> dict[str, Any]:
    return body.model_dump(mode="python", by_alias=True, exclude_none=True)


def _raise_repository_value_error(error: ValueError) -> None:
    message = str(error)
    status_code = 404 if "was not found" in message else 400
    raise HTTPException(status_code=status_code, detail=message) from error


def _build_data_asset_generation_services(
    request: Request,
    repository: DataAssetRepository,
) -> GeneratedDataAssetServices:
    def _resolve_data_asset_generation_payload(asset_id: str, sample_count: int) -> dict[str, Any]:
        return _test_data_queue_support.resolve_data_asset_generation_payload(asset_id, sample_count, repository)

    return GeneratedDataAssetServices(
        resolve_data_asset_generation_payload=_resolve_data_asset_generation_payload,
        enqueue_queued_test_data_request=_testing_data_requests_api.bind_queued_test_data_request_enqueuer(request),
        wait_for_test_data_request_result=_testing_data_requests_api.wait_for_test_data_request_result,
    )


@router.get("/data-assets", response_model=list[DataAssetView])
async def list_data_assets(
    workspace_id: str | None = None,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> list[DataAssetView]:
    return [_asset_view(entity) for entity in repository.list_data_assets(workspace_id=workspace_id)]


@router.get("/data-assets/{asset_id}", response_model=DataAssetView)
async def get_data_asset(
    asset_id: str,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> DataAssetView:
    entity = repository.get_data_asset(asset_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Data Asset '{asset_id}' was not found")
    return _asset_view(entity)


@router.post("/data-assets", response_model=DataAssetView)
async def create_data_asset(
    body: CreateDataAssetRequestView,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> DataAssetView:
    try:
        entity = repository.create_data_asset(_create_payload(body))
    except ValueError as error:
        _raise_repository_value_error(error)
    return _asset_view(entity)


@router.put("/data-assets/{asset_id}", response_model=DataAssetView)
async def update_data_asset(
    asset_id: str,
    body: UpdateDataAssetRequestView,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> DataAssetView:
    try:
        entity = repository.update_data_asset(asset_id, _update_payload(body))
    except ValueError as error:
        _raise_repository_value_error(error)
    return _asset_view(entity)


@router.get("/data-assets/{asset_id}/versions", response_model=list[DataAssetVersionView])
async def list_data_asset_versions(
    asset_id: str,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> list[DataAssetVersionView]:
    if repository.get_data_asset(asset_id) is None:
        raise HTTPException(status_code=404, detail=f"Data Asset '{asset_id}' was not found")
    return [_version_view(entity) for entity in repository.list_data_asset_versions(asset_id)]


@router.get("/data-assets/{asset_id}/versions/{version_id}", response_model=DataAssetVersionView)
async def get_data_asset_version(
    asset_id: str,
    version_id: str,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> DataAssetVersionView:
    entity = repository.get_data_asset_version(asset_id, version_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Data Asset version '{version_id}' was not found")
    return _version_view(entity)


@router.post("/data-assets/{asset_id}/versions", response_model=DataAssetVersionView)
async def create_data_asset_version(
    asset_id: str,
    body: CreateDataAssetVersionRequestView,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> DataAssetVersionView:
    try:
        entity = repository.create_data_asset_version(asset_id, _version_payload(body))
    except ValueError as error:
        _raise_repository_value_error(error)
    return _version_view(entity)


@router.post("/data-assets/{asset_id}/generate-test-data", response_model=TestDataPayloadView)
async def generate_test_data_for_data_asset(
    asset_id: str,
    body: GenerateDataAssetTestDataRequestView,
    request: Request,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> TestDataPayloadView:
    result_payload = await generate_test_data_for_data_asset_use_case(
        command=GenerateTestDataForDataAssetCommand(asset_id=asset_id, sample_count=body.sampleCount),
        services=_build_data_asset_generation_services(request, repository),
    )
    return TestDataPayloadView.model_validate(
        _test_data_queue_support.queued_test_data_result_entity(result_payload).model_dump(mode="python")
    )


@router.get("/data-assets/{asset_id}/contract/analysis")
async def analyze_data_asset_contract(
    asset_id: str,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> dict[str, Any]:
    asset, version, contract_yaml = _current_asset_contract_source(asset_id, repository)
    current_snapshot = _build_data_asset_contract_snapshot(asset_id, contract_yaml)
    contract_versions = repository.list_data_asset_contract_versions(asset_id)
    previous_snapshot = None
    diff = None
    if len(contract_versions) > 1:
        previous_snapshot = _build_data_asset_contract_snapshot(asset_id, contract_versions[1].contract_yaml)
        diff = diff_contract_snapshots(previous_snapshot, current_snapshot)

    conformance = validate_contract_conformance(current_snapshot, build_observed_fields_from_data_asset_version(version))

    return {
        "success": True,
        "data_asset_id": asset_id,
        "contract": current_snapshot,
        "comparison": diff,
        "conformance": conformance,
        "latest_contract_version": contract_versions[0].model_dump(mode="python", by_alias=True, exclude_none=False) if contract_versions else None,
    }


@router.get("/data-assets/{asset_id}/lineage", response_model=DataAssetLineageView)
async def get_data_asset_lineage(
    asset_id: str,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
    monitor_schedule_repository: MonitorScheduleRepository = Depends(get_monitor_schedule_repository),
    incident_repository: IncidentRepository = Depends(get_incident_repository),
) -> DataAssetLineageView:
    asset, version = _resolve_contract_source(asset_id, repository)

    contract_change_count = 0
    contract_notes: list[str] = []
    contract_versions = repository.list_data_asset_contract_versions(asset_id)
    if contract_versions:
        contract_notes.append(f"Latest contract version: {contract_versions[0].version}.")
        if version is None:
            contract_notes.append("No asset version is available for contract comparison.")
        elif len(contract_versions) > 1:
            previous_snapshot = _build_data_asset_contract_snapshot(asset_id, contract_versions[1].contract_yaml)
            current_snapshot = _build_data_asset_contract_snapshot(asset_id, contract_versions[0].contract_yaml)
            diff = diff_contract_snapshots(previous_snapshot, current_snapshot)
            contract_change_count = int(diff.get("summary", {}).get("total_changes", 0)) if isinstance(diff, Mapping) else 0
            if contract_change_count > 0:
                contract_notes.append(str(diff.get("change_classification") or "Contract changes detected"))
    else:
        contract_notes.append("No contract has been generated yet.")

    return await _build_lineage_payload(
        asset=asset,
        version=version,
        data_asset_repository=repository,
        data_catalog_repository=data_catalog_repository,
        rules_repository=rules_repository,
        monitor_schedule_repository=monitor_schedule_repository,
        incident_repository=incident_repository,
        contract_change_count=contract_change_count,
        contract_notes=contract_notes,
    )


@router.get("/data-assets/{asset_id}/governance-discovery", response_model=DataAssetGovernanceDiscoveryView)
async def get_data_asset_governance_discovery(
    asset_id: str,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> DataAssetGovernanceDiscoveryView:
    asset = repository.get_data_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Data Asset '{asset_id}' was not found")

    return _build_governance_discovery_view(
        asset=asset,
        repository=repository,
        data_catalog_repository=data_catalog_repository,
    )


@router.post("/data-assets/{asset_id}/contract/conformance")
async def validate_data_asset_contract_conformance(
    asset_id: str,
    validation_payload: dict[str, Any] | None = None,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> dict[str, Any]:
    asset, version, contract_yaml = _current_asset_contract_source(asset_id, repository)
    candidate_contract_yaml = str((validation_payload or {}).get("contract_yaml") or "").strip() or contract_yaml
    candidate_snapshot = _build_data_asset_contract_snapshot(asset_id, candidate_contract_yaml)
    conformance = validate_contract_conformance(candidate_snapshot, build_observed_fields_from_data_asset_version(version))

    return {
        "success": True,
        "data_asset_id": asset_id,
        "contract": candidate_snapshot,
        "conformance": conformance,
    }


@router.post("/data-assets/{asset_id}/contract/review")
async def review_data_asset_contract(
    asset_id: str,
    review_payload: dict[str, Any],
    request: Request,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
    approvals_repository: ApprovalsRepository = Depends(get_approvals_repository),
) -> dict[str, Any]:
    review_status = str(review_payload.get("review_status") or review_payload.get("status") or "").strip().lower()
    if review_status not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="review_status must be 'approved' or 'rejected'")

    review_comments = str(review_payload.get("review_comments") or review_payload.get("comments") or "").strip() or None
    reviewer_id = str(getattr(request.state, "user_id", None) or "system").strip() or "system"

    asset, version, contract_yaml = _current_asset_contract_source(asset_id, repository)
    workspace_id = str(getattr(asset, "workspace_id", "") or "").strip()
    stored_contract = repository.save_data_asset_contract_version(
        asset_id,
        {
            "contract_yaml": contract_yaml,
            "generated_at": getattr(request.state, "generated_at", None) or "",
            "generated_by": reviewer_id,
            "generated_where": str(request.url.path),
            "generated_what": f"Generated ODCS contract for Data Asset '{asset_id}'",
            "source_data_asset_version_id": getattr(version, "id", None) if version is not None else None,
        },
    )
    reviewed_contract = repository.update_data_asset_contract_version_review(
        asset_id,
        stored_contract.id,
        {
            "review_status": review_status,
            "reviewed_by": reviewer_id,
            "reviewed_at": getattr(request.state, "generated_at", None) or "",
            "review_comments": review_comments,
        },
    )

    contract_versions = repository.list_data_asset_contract_versions(asset_id)
    previous_snapshot = None
    comparison = None
    if len(contract_versions) > 1:
        previous_snapshot = _build_data_asset_contract_snapshot(asset_id, contract_versions[1].contract_yaml)
        comparison = diff_contract_snapshots(previous_snapshot, _build_data_asset_contract_snapshot(asset_id, contract_yaml))

    review_summary = f"Contract {review_status} for Data Asset '{asset_id}'"
    if comparison is not None:
        review_summary = f"{review_summary}; {comparison['change_classification']} change"

    approvals_repository.append_audit_event(
        approval_id=f"contract-review:{asset_id}:{reviewed_contract.id}",
        action="notification.contract_change",
        actor_id=reviewer_id,
        details={
            "message": review_summary,
            "asset_id": asset_id,
            "workspace_id": workspace_id,
            "contract_version_id": reviewed_contract.id,
            "review_status": review_status,
            "review_comments": review_comments,
            "comparison": comparison,
            "reviewed_by": reviewer_id,
            "reviewed_at": getattr(request.state, "generated_at", None) or "",
        },
    )

    log_event(
        _log,
        "data_assets.contract.review.complete",
        component="data-assets-api",
        assetId=asset_id,
        reviewStatus=review_status,
    )

    return {
        "success": True,
        "data_asset_id": asset_id,
        "contract_version": reviewed_contract.model_dump(mode="python", by_alias=True, exclude_none=False),
        "comparison": comparison,
        "notification_status": "queued",
    }


@router.post("/data-assets/{asset_id}/validate", response_model=DataAssetValidationView)
async def validate_data_asset(
    asset_id: str,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> DataAssetValidationView:
    asset, version = _resolve_data_asset_version(asset_id, None, repository)
    return DataAssetValidationView(
        ok=True,
        asset=_asset_view(asset),
        version=_version_view(version),
        issues=[],
    )


@router.delete("/data-assets/{asset_id}", response_model=OkResponseView)
async def delete_data_asset(
    asset_id: str,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> OkResponseView:
    deleted = repository.delete_data_asset(asset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Data Asset '{asset_id}' was not found")
    return OkResponseView(ok=True)


@router.get("/data-assets/{asset_id}/contract")
async def download_data_asset_contract(
    asset_id: str,
    request: Request,
    format: str | None = Query(default="yaml"),
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> PlainTextResponse:
    asset, version = _resolve_contract_source(asset_id, repository)
    contract_yaml = _build_data_asset_contract_yaml(asset, version)
    stored_contract = repository.save_data_asset_contract_version(
        asset_id,
        {
            "contract_yaml": contract_yaml,
            "generated_at": getattr(request.state, "generated_at", None) or "",
            "generated_by": getattr(request.state, "user_id", None) or "system",
            "generated_where": str(request.url.path),
            "generated_what": f"Generated ODCS contract for Data Asset '{asset_id}'",
            "source_data_asset_version_id": getattr(version, "id", None) if version is not None else None,
        },
    )
    contract_format = str(format or "yaml").strip().lower() or "yaml"
    if contract_format not in {"yaml", "yml", "json"}:
        raise HTTPException(status_code=400, detail="format must be 'yaml' or 'json'")
    rendered_contract = dump_contract_text(_build_data_asset_contract_payload(asset, version), contract_format=contract_format)
    media_type = "text/plain; charset=utf-8" if contract_format == "json" else "application/x-yaml"
    filename = f"{asset_id}.odcs.json" if contract_format == "json" else f"{asset_id}.odcs.yaml"
    return PlainTextResponse(
        content=rendered_contract,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/data-assets/{asset_id}/contract/import", response_model=DataAssetView)
async def import_data_asset_contract(
    asset_id: str,
    payload: ContractImportRequestView,
    repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> DataAssetView:
    asset = repository.get_data_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Data Asset '{asset_id}' was not found")

    try:
        contract_payload = load_contract_payload(payload.contractText)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    contract_id = str(contract_payload.get("id") or "").strip()
    if contract_id and contract_id != f"urn:dq:contract:{asset_id}":
        raise HTTPException(status_code=400, detail="contract id does not match the selected data asset")

    updated_asset = repository.update_data_asset(asset_id, _build_data_asset_import_payload(contract_payload, asset))
    return _asset_view(updated_asset)
