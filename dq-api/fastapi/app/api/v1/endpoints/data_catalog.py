from collections.abc import AsyncIterator, Mapping
import json
import os
from typing import Any
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ConfigDict, Field

from dq_domain_validation import TestingOutputFormat

from app.schemas.pydantic_base import SnakeModel, to_snake_alias

from app.api.v1.schemas import (
    AddRuleAttributesResultView,
    AttributeDefinitionMappingUpsertRequestView,
    AttributeDefinitionMappingUpsertResultView,
    AttributeDefinitionMappingView,
    AttributeCatalogPageView,
    AttributeCatalogView,
    DataDeliveryExecutionReceiptView,
    DataDeliveryExecutionRequestView,
    DataDeliveriesPageView,
    DataDeliveryInventoryPageView,
    DataDeliveryNoteView,
    DataObjectCatalogPageView,
    DataObjectVersionView,
    DataObjectVersionsPageView,
    DataObjectView,
    DataProductsPageView,
    DataSetView,
    DataSetsPageView,
    ContractImportRequestView,
    GxExecutionRunView,
    RuleAttributeView,
)
from app.api.v1.schemas.data_definition_task_view import DataDefinitionTaskApprovalUpdateRequestView
from app.api.v1.schemas.data_definition_task_view import DataDefinitionTaskCreateRequestView
from app.api.v1.schemas.data_definition_task_view import DataDefinitionTaskCreateResponseView
from app.api.v1.schemas.data_definition_task_view import DataDefinitionTaskAuditEventView
from app.api.v1.schemas.data_definition_task_view import DataDefinitionTaskAuditHistoryResponseView
from app.api.v1.schemas.data_definition_task_view import DataDefinitionTaskHistoryResponseView
from app.api.v1.schemas.data_definition_task_view import DataDefinitionTaskImportResponseView
from app.api.v1.schemas.data_definition_task_view import DataDefinitionTaskStatusResponseView
from app.api.v1.schemas.data_definition_task_view import DataDefinitionTaskStatusView
from app.api.v1.schemas.test_data_materialization_view import MaterializationCompletionBatchView
from app.api.v1.schemas.test_data_materialization_view import MaterializationTargetResultRequest
from app.api.v1.schemas.test_data_materialization_view import ReportTestDataMaterializationCompletionRequest
from app.api.v1.schemas.test_data_materialization_view import TestDataMaterializationRequestView
from app.api.v1 import test_data_materialization_api as _test_data_materialization_api
from app.api.v1 import gx_runtime_api as _gx_runtime_api
from app.application.services.delivery_linked_execution_request_resolver import DeliveryLinkedExecutionRequestError
from app.application.services.delivery_linked_execution_orchestrator import DeliveryLinkedExecutionOrchestrator
from app.api.presenters.data_catalog import build_data_catalog_page_payload
from app.api.presenters.data_catalog import build_delivery_linked_execution_note_enrichment
from app.api.presenters.data_catalog import resolve_delivery_inventory_location
from app.api.presenters.data_catalog import resolve_delivery_linked_execution_delivery_id
from app.application.services.odcs_contract_text import dump_contract_text
from app.application.services.odcs_contract_text import load_contract_payload
from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError
from app.application.services.registry_definition_resolver import RegistryDefinitionResolver
from app.application.resolvers import (
    resolve_add_rule_attributes_result_view,
    resolve_attribute_definition_mapping_upsert_result_view,
    resolve_attribute_definition_mappings_view,
    resolve_attribute_rule_counts_view,
    resolve_attributes_catalog_page_view,
    resolve_data_deliveries_page_view,
    resolve_data_delivery_inventory_page_view,
    resolve_data_delivery_note_view,
    resolve_data_object_versions_page_view,
    resolve_data_objects_catalog_page_view,
    resolve_data_objects_view,
    resolve_data_products_page_view,
    resolve_data_sets_page_view,
    resolve_rule_attributes_view,
)
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_data_asset_repository
from app.core.dependencies import get_gx_execution_run_repository
from app.core.dependencies import get_admin_repository
from app.core.dependencies import get_data_protection_repository
from app.core.dependencies import get_registry_definition_resolver
from app.core.dependencies import get_validation_artifact_repository
from app.core.dependencies import get_validation_run_plan_repository
from app.application.services.delivery_inventory import DeliveryInventoryInspector
from app.application.services.data_definition_task_service import ANALYSIS_TYPE_DEFINITION_TASK
from app.application.services.data_definition_task_service import apply_board_approval_to_result
from app.application.services.data_definition_task_service import DataDefinitionTaskError
from app.application.services.data_definition_task_service import merge_import_result
from app.application.services.data_definition_task_service import require_approved_openmetadata_import_contract
from app.application.services.natural_language_draft_enqueue_service import enqueue_natural_language_draft_job
from app.application.services.natural_language_draft_enqueue_service import build_request_status_event_payload
from app.application.services.natural_language_draft_enqueue_service import load_request_record_from_settings
from app.application.services.natural_language_draft_enqueue_service import NaturalLanguageDraftEnqueueServiceError
from app.application.services.natural_language_draft_enqueue_service import open_request_event_stream_client
from app.application.services.natural_language_draft_enqueue_service import read_request_status_events
from app.application.services.natural_language_draft_enqueue_service import save_request_record_to_settings
from app.application.services.openmetadata_definition_importer import OpenMetadataDefinitionImportError
from app.application.services.openmetadata_definition_importer import OpenMetadataDefinitionImporter
from app.core.config import get_settings
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import DataAssetRepository
from app.domain.interfaces import AdminRepository
from app.domain.interfaces import DataProtectionRepository
from app.domain.interfaces import GxExecutionRunRepository
from app.domain.interfaces import ValidationArtifactRepository
from app.domain.interfaces import ValidationRunPlanRepository
from app.domain.interfaces import SuggestionsRepository
from app.core.dependencies import get_suggestions_repository

router = APIRouter(tags=["data-catalog"])


class _QueuedDataDefinitionTaskRequest(SnakeModel):
    currentWorkspaceId: str
    searchScope: str = "current"
    analysisProvider: str = "llm"
    analysisType: str = ANALYSIS_TYPE_DEFINITION_TASK
    prompt: str
    selectedAttributeIds: list[str]
    versionId: str
    taskPayload: dict[str, Any]
    autoImport: bool = False


def _has_workspace_role(current_user: object, workspace_id: str, role_name: str) -> bool:
    for workspace_role in list(getattr(current_user, "workspace_roles", []) or []):
        if str(getattr(workspace_role, "workspace_id", None) or "").strip() != workspace_id:
            continue
        if str(getattr(workspace_role, "role", None) or "").strip() == role_name:
            return True
    return False


def _has_workspace_manage_scope(current_user: object) -> bool:
    granted_scopes = [str(scope).strip() for scope in getattr(current_user, "granted_scopes", []) or [] if str(scope).strip()]
    return any(scope in {"dq:workspace:manage", "dq:*"} or scope.endswith(":*") for scope in granted_scopes)


def _build_definition_task_status_view(record: Mapping[str, Any]) -> DataDefinitionTaskStatusView:
    return DataDefinitionTaskStatusView.model_validate(
        {
            "requestId": str(record.get("request_id") or ""),
            "currentWorkspaceId": str(record.get("current_workspace_id") or ""),
            "versionId": record.get("version_id"),
            "selectedAttributeIds": list(record.get("selected_attribute_ids") or []),
            "prompt": str(record.get("prompt") or ""),
            "requestedByUserId": record.get("requested_by_user_id"),
            "requestedByEmail": record.get("requested_by_email"),
            "requestedAt": record.get("requested_at"),
            "startedAt": record.get("started_at"),
            "completedAt": record.get("completed_at"),
            "status": str(record.get("status") or "pending"),
            "errorMessage": record.get("error_message"),
            "analysisType": str(record.get("analysis_type") or ANALYSIS_TYPE_DEFINITION_TASK),
            "analysisProvider": str(record.get("analysis_provider") or "llm"),
            "autoImport": bool(record.get("auto_import")),
            "taskPayload": dict(record.get("task_payload") or {}),
            "result": record.get("result"),
        }
    )


def _resolve_definition_task_timeout_seconds() -> int:
    raw_value = str(os.getenv("DQ_DATA_DEFINITION_EVENT_TIMEOUT_SECONDS") or "").strip()
    if not raw_value:
        return 900

    try:
        timeout_seconds = int(float(raw_value))
    except ValueError:
        return 900

    return max(1, timeout_seconds)


def _parse_definition_task_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _reconcile_stale_definition_task_status(record: dict[str, Any]) -> dict[str, Any]:
    if str(record.get("status") or "").strip().lower() != "started":
        return record

    started_at = _parse_definition_task_timestamp(record.get("started_at"))
    if started_at is None:
        return record

    timeout_seconds = _resolve_definition_task_timeout_seconds()
    elapsed_seconds = (datetime.now(UTC) - started_at).total_seconds()
    if elapsed_seconds < timeout_seconds:
        return record

    record["status"] = "failed"
    record["completed_at"] = record.get("completed_at") or datetime.now(UTC).isoformat()
    record["error_message"] = f"Data-definition task timed out after {timeout_seconds} seconds without completing"
    return record


def _build_definition_task_audit_event_view(record: Mapping[str, Any]) -> DataDefinitionTaskAuditEventView:
    return DataDefinitionTaskAuditEventView.model_validate(
        {
            "id": str(record.get("id") or ""),
            "requestId": str(record.get("request_id") or record.get("requestId") or ""),
            "action": str(record.get("action") or ""),
            "fromStatus": record.get("from_status") or record.get("fromStatus"),
            "toStatus": record.get("to_status") or record.get("toStatus"),
            "actorId": record.get("actor_id") or record.get("actorId"),
            "changedAt": str(record.get("changed_at") or record.get("changedAt") or ""),
            "details": dict(record.get("details") or record.get("details_json") or {}),
        }
    )


def _data_definition_task_events_url(request_id: str) -> str:
    return f"/data-catalog/v1/data-definition-tasks/requests/{request_id}/events"


def _data_set_contract_download_url(data_set_id: str) -> str:
    normalized_data_set_id = str(data_set_id or "").strip()
    return f"/data-catalog/v1/data-sets/{normalized_data_set_id}/contract"


def _data_set_view(entity: Any) -> Any:
    view = DataSetView.model_validate(entity)
    return view.model_copy(update={"data_contract_download_url": _data_set_contract_download_url(view.id)})


def _build_data_set_contract_payload(data_set: Any, data_objects: list[Any]) -> dict[str, Any]:
    data_set_name = str(getattr(data_set, "name", "") or getattr(data_set, "id", "") or "").strip()
    data_set_description = str(getattr(data_set, "description", "") or "").strip()
    owner = str(getattr(data_set, "owner", "") or "").strip()
    workspace_id = str(getattr(data_set, "workspace_id", "") or "").strip()
    product_id = str(getattr(data_set, "product_id", "") or "").strip()
    business_key = str(getattr(data_set, "business_key", "") or "").strip()
    tags = [str(tag).strip() for tag in list(getattr(data_set, "tags", []) or []) if str(tag).strip()]
    return {
        "apiVersion": "v3.1.0",
        "kind": "DataContract",
        "id": f"urn:dq:dataset:{getattr(data_set, 'id', '')}",
        "name": data_set_name,
        "version": "1.0.0",
        "status": "active",
        "owner": {"name": owner or workspace_id or "DQ Data Sets"},
        "contact": {"name": owner or workspace_id or "DQ Data Sets", "email": "dq-data-sets@example.com"},
        "domain": workspace_id or "dq",
        "tags": tags,
        "description": {
            "purpose": data_set_description or f"Generated contract for {data_set_name}",
            "limitations": "- Data objects are discovered from the catalog view for this dataset.\n- Imported contracts update the dataset fields owned by the catalog service.",
            "usage": f"Download and share this generated contract for {data_set_name}.",
        },
        "extension": {
            "dq": {
                "product_id": product_id,
                "workspace_id": workspace_id,
                "business_key": business_key,
                "data_objects": [
                    {
                        "id": str(getattr(data_object, "id", "") or "").strip(),
                        "name": str(getattr(data_object, "name", "") or "").strip(),
                        "description": str(getattr(data_object, "description", "") or "").strip(),
                        "latest_version_id": str(getattr(data_object, "latest_version_id", "") or "").strip(),
                    }
                    for data_object in data_objects
                ],
            }
        },
        "schema": [
            {
                "name": data_set_name or getattr(data_set, "id", ""),
                "logicalType": "object",
                "physicalType": "dataset",
                "description": data_set_description or f"Data Set {getattr(data_set, 'id', '')}",
                "properties": [
                    {
                        "name": str(getattr(data_object, "name", "") or getattr(data_object, "id", "") or "").strip(),
                        "logicalType": "object",
                        "physicalType": "table",
                        "description": str(getattr(data_object, "description", "") or "").strip(),
                        "required": False,
                        "unique": False,
                        "classification": "public",
                    }
                    for data_object in data_objects
                ],
            }
        ],
    }


def _build_data_set_import_payload(contract_payload: Mapping[str, Any], existing_data_set: Any) -> dict[str, Any]:
    extension = contract_payload.get("extension") if isinstance(contract_payload.get("extension"), Mapping) else {}
    dq_extension = extension.get("dq") if isinstance(extension, Mapping) and isinstance(extension.get("dq"), Mapping) else {}
    owner = contract_payload.get("owner") if isinstance(contract_payload.get("owner"), Mapping) else {}
    contact = contract_payload.get("contact") if isinstance(contract_payload.get("contact"), Mapping) else {}
    contact_name = str(contact.get("name") or "").strip()
    description = contract_payload.get("description") if isinstance(contract_payload.get("description"), Mapping) else {}
    workspace_id = str(dq_extension.get("workspace_id") or contract_payload.get("domain") or getattr(existing_data_set, "workspace_id", "") or "").strip()
    product_id = str(dq_extension.get("product_id") or getattr(existing_data_set, "product_id", "") or "").strip()
    business_key = str(dq_extension.get("business_key") or getattr(existing_data_set, "business_key", "") or "").strip()
    imported_name = str(contract_payload.get("name") or getattr(existing_data_set, "name", "") or "").strip()
    imported_description = str(description.get("purpose") or getattr(existing_data_set, "description", "") or "").strip()
    imported_tags = [
        str(tag).strip()
        for tag in (
            contract_payload.get("tags")
            if isinstance(contract_payload.get("tags"), list)
            else dq_extension.get("tags")
            if isinstance(dq_extension.get("tags"), list)
            else []
        )
        if str(tag).strip()
    ]
    return {
        "product_id": product_id or getattr(existing_data_set, "product_id", ""),
        "name": imported_name,
        "description": imported_description,
        "owner": str(owner.get("name") or contact_name or getattr(existing_data_set, "owner", "") or "").strip(),
        "workspace_id": workspace_id or getattr(existing_data_set, "workspace_id", ""),
        "business_key": business_key or getattr(existing_data_set, "business_key", ""),
        "tags": imported_tags,
    }


def _sse_frame(*, event_name: str, payload: Mapping[str, Any], event_id: str | None = None) -> str:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_name}")
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    for line in data.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def _build_data_definition_task_event_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    event_payload = build_request_status_event_payload(record)
    event_payload["request"] = _build_definition_task_status_view(record).model_dump(by_alias=True, mode="json")
    return event_payload


async def _stream_data_definition_task_events(
    *,
    settings: Any,
    request_id: str,
    initial_record: Mapping[str, Any],
    last_event_id: str | None,
) -> AsyncIterator[str]:
    initial_status = str(initial_record.get("status") or "pending").strip().lower() or "pending"
    if initial_status in {"completed", "failed"}:
        yield _sse_frame(event_name="snapshot", payload=_build_data_definition_task_event_payload(initial_record))
        return

    client = await open_request_event_stream_client(settings)
    try:
        next_event_id = str(last_event_id or "").strip() or "0-0"
        yield _sse_frame(event_name="snapshot", payload=_build_data_definition_task_event_payload(initial_record))
        while True:
            events = await read_request_status_events(
                client,
                request_id=request_id,
                last_event_id=next_event_id,
            )
            if not events:
                yield ": keepalive\n\n"
                continue
            for event_id, fields in events:
                next_event_id = event_id
                raw_payload = str(fields.get("data") or "{}").strip() or "{}"
                event_payload = json.loads(raw_payload)
                event_name = str(fields.get("event") or "status_changed").strip() or "status_changed"
                yield _sse_frame(event_name=event_name, payload=event_payload, event_id=event_id)
                if str(event_payload.get("status") or "").strip().lower() in {"completed", "failed"}:
                    return
    finally:
        await client.aclose()


def _not_authenticated_json_response() -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": "not_authenticated", "message": "Not authenticated"})


def _openmetadata_importer_from_settings() -> OpenMetadataDefinitionImporter:
    settings = get_settings()
    return OpenMetadataDefinitionImporter(
        provider=settings.catalog_provider,
        endpoint=settings.catalog_endpoint,
        api_key=settings.catalog_api_key,
        oidc_issuer=settings.catalog_oidc_issuer,
        oidc_token_url=settings.catalog_oidc_token_url,
        oidc_client_id=settings.catalog_oidc_client_id,
        oidc_client_secret=settings.catalog_oidc_client_secret,
        oidc_scope=settings.catalog_oidc_scope,
        oidc_username=settings.catalog_oidc_username,
        oidc_password=settings.catalog_oidc_password,
        timeout_seconds=settings.catalog_timeout_seconds,
    )


def _require_protection_access(
    *,
    request: Request,
    admin_repository: AdminRepository,
    workspace_id: str,
    can_write_masking: bool = False,
    can_write_encryption: bool = False,
) -> object:
    current_user = admin_repository.get_current_user(getattr(request.state, "user_id", None), getattr(request.state, "auth_claims", None))
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if can_write_encryption:
        if _has_workspace_manage_scope(current_user) or _has_workspace_role(current_user, workspace_id, "admin"):
            return current_user
        raise HTTPException(
            status_code=403,
            detail={
                "error": "attribute_protection_access_denied",
                "message": "Workspace admin access is required to configure encryption",
                "workspace_id": workspace_id,
            },
        )

    if can_write_masking:
        if _has_workspace_manage_scope(current_user) or _has_workspace_role(current_user, workspace_id, "admin") or _has_workspace_role(current_user, workspace_id, "data-steward"):
            return current_user
        raise HTTPException(
            status_code=403,
            detail={
                "error": "attribute_protection_access_denied",
                "message": "Workspace steward access is required to configure masking",
                "workspace_id": workspace_id,
            },
        )

    if _has_workspace_manage_scope(current_user) or _has_workspace_role(current_user, workspace_id, "admin") or _has_workspace_role(current_user, workspace_id, "data-steward"):
        return current_user

    raise HTTPException(
        status_code=403,
        detail={
            "error": "attribute_protection_access_denied",
            "message": "Workspace access is required to inspect attribute protection",
            "workspace_id": workspace_id,
        },
    )


def _build_data_asset_attribute_catalog_rows(repository: DataAssetRepository) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for asset in repository.list_data_assets():
        asset_id = str(getattr(asset, "id", "") or "").strip()
        current_version_id = str(getattr(asset, "current_version_id", "") or "").strip()
        if not asset_id or not current_version_id:
            continue

        version = repository.get_data_asset_version(asset_id, current_version_id)
        if version is None:
            continue

        source_name = str(getattr(asset, "name", "") or asset_id).strip() or asset_id
        workspace_id = str(getattr(asset, "workspace_id", "") or "").strip()
        version_number = getattr(version, "version", None)
        source_version_label = f"v{int(version_number)}" if version_number is not None else current_version_id

        for binding in version.source_bindings:
            field_id = str(getattr(binding, "source_field_id", "") or "").strip()
            if not field_id:
                continue

            rows.append(
                {
                    "id": f"data-asset::{asset_id}::{version.id}::source::{field_id}",
                    "name": str(getattr(binding, "source_field_name", "") or field_id).strip() or field_id,
                    "type": str(getattr(binding, "source_field_type", "") or "").strip(),
                    "nullable": bool(getattr(binding, "nullable", True)),
                    "format": "",
                    "is_cde": False,
                    "is_primary_key": False,
                    "is_business_key": False,
                    "data_object_id": asset_id,
                    "version_id": str(version.id),
                    "workspace_id": workspace_id,
                    "source_kind": "data_asset",
                    "source_name": source_name,
                    "source_version_label": source_version_label,
                    "definition_id": None,
                    "definition_mapping_status": "data_asset",
                    "definition_mapping_attribute_id": None,
                    "definition_mapping_version_id": None,
                    "definition_mapping_mapped_by": None,
                    "definition_mapping_created_at": None,
                }
            )

        for derived_field in version.derived_fields:
            derived_name = str(getattr(derived_field, "name", "") or "").strip()
            if not derived_name:
                continue

            nullable_value = getattr(derived_field, "nullable", None)
            rows.append(
                {
                    "id": f"data-asset::{asset_id}::{version.id}::derived::{derived_name}",
                    "name": derived_name,
                    "type": str(getattr(derived_field, "data_type", "") or "").strip(),
                    "nullable": bool(nullable_value) if nullable_value is not None else True,
                    "format": "",
                    "is_cde": False,
                    "is_primary_key": False,
                    "is_business_key": False,
                    "data_object_id": asset_id,
                    "version_id": str(version.id),
                    "workspace_id": workspace_id,
                    "source_kind": "data_asset",
                    "source_name": source_name,
                    "source_version_label": source_version_label,
                    "definition_id": None,
                    "definition_mapping_status": "data_asset",
                    "definition_mapping_attribute_id": None,
                    "definition_mapping_version_id": None,
                    "definition_mapping_mapped_by": None,
                    "definition_mapping_created_at": None,
                }
            )

    rows.sort(
        key=lambda row: (
            str(row.get("source_name") or ""),
            str(row.get("source_version_label") or ""),
            str(row.get("name") or ""),
            str(row.get("id") or ""),
        )
    )
    return rows


class RuleAttributesUpsertRequest(SnakeModel):
    model_config = ConfigDict(from_attributes=True, alias_generator=to_snake_alias, populate_by_name=True)

    entries: list[dict]


class CreateCatalogMaterializationRequest(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    data_product_id: str | None = None
    data_set_id: str | None = None
    data_object_id: str | None = None
    data_object_version_id: str | None = None
    sample_count: int = Field(default=1000, ge=1, le=100000)
    output_format: TestingOutputFormat = Field(default="parquet")
    output_uri: str | None = None
    selected_attribute_names: list[str] = Field(default_factory=list)
    refresh: bool = Field(default=False)


class ReportCatalogMaterializationCompletionRequest(SnakeModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", alias_generator=to_snake_alias)

    row_count: int | None = Field(default=None, ge=0)
    output_uri: str | None = None
    output_format: TestingOutputFormat | None = None
    target_results: list[MaterializationTargetResultRequest] = Field(default_factory=list)


@router.post(
    "/materialization-requests",
    response_model=TestDataMaterializationRequestView,
    status_code=202,
)
async def create_materialization_request(
    request: Request,
    payload: CreateCatalogMaterializationRequest,
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> TestDataMaterializationRequestView:
    return await _test_data_materialization_api.create_catalog_materialization_request(
        request_headers=request.headers,
        payload=payload,
        repository=repository,
    )


@router.get(
    "/materialization-requests/{request_id}",
    response_model=TestDataMaterializationRequestView,
)
async def get_materialization_request(request_id: str) -> TestDataMaterializationRequestView:
    return await _test_data_materialization_api.get_materialization_request_view(request_id)


@router.post(
    "/materialization-requests/{request_id}/complete",
    response_model=MaterializationCompletionBatchView,
)
async def report_materialization_request_completion(
    request_id: str,
    payload: ReportCatalogMaterializationCompletionRequest,
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> MaterializationCompletionBatchView:
    return await _test_data_materialization_api.report_materialization_request_completion(
        request_id=request_id,
        payload=payload,
        repository=repository,
    )


@router.get("/data-products", response_model=DataProductsPageView)
async def get_data_products(
    workspace: str | None = Query(default=None),
    businessKey: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> DataProductsPageView:
    rows = repository.list_data_products(workspace)
    if businessKey is not None:
        rows = [row for row in rows if str(getattr(row, "business_key", "") or "") == businessKey]
    return resolve_data_products_page_view(build_data_catalog_page_payload([row.model_dump() for row in rows], page, limit))


@router.get("/data-objects", response_model=list[DataObjectView])
async def get_data_objects(
    businessKey: str | None = Query(default=None),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> list[DataObjectView]:
    rows = repository.list_data_objects()
    if businessKey is not None:
        rows = [row for row in rows if str(getattr(row, "business_key", "") or "") == businessKey]
    return resolve_data_objects_view(rows)


@router.get("/data-sets", response_model=DataSetsPageView)
async def get_data_sets(
    productId: str | None = Query(default=None),
    workspace: str | None = Query(default=None),
    standalone: bool | None = Query(default=None),
    businessKey: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> DataSetsPageView:
    _ = standalone
    rows = repository.list_data_sets(productId, workspace)
    if businessKey is not None:
        rows = [row for row in rows if str(getattr(row, "business_key", "") or "") == businessKey]
    payload = resolve_data_sets_page_view(build_data_catalog_page_payload([row.model_dump() for row in rows], page, limit))
    return payload.model_copy(
        update={
            "data": [
                row.model_copy(update={"data_contract_download_url": _data_set_contract_download_url(row.id)})
                for row in payload.data
            ]
        }
    )


@router.get("/data-sets/{data_set_id}/contract", response_model=None)
async def download_data_set_contract(
    data_set_id: str,
    format: str | None = Query(default="yaml"),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> Response:
    data_set = repository.get_data_set(data_set_id)
    if data_set is None:
        raise HTTPException(status_code=404, detail=f"Data set '{data_set_id}' was not found")
    data_objects = repository.list_data_objects_catalog(data_set_id)
    contract_payload = _build_data_set_contract_payload(data_set, data_objects)
    contract_format = str(format or "yaml").strip().lower() or "yaml"
    if contract_format not in {"yaml", "yml", "json"}:
        raise HTTPException(status_code=400, detail="format must be 'yaml' or 'json'")
    rendered_contract = dump_contract_text(contract_payload, contract_format=contract_format)
    media_type = "text/plain; charset=utf-8" if contract_format == "json" else "application/x-yaml"
    filename = f"{data_set_id}.odcs.json" if contract_format == "json" else f"{data_set_id}.odcs.yaml"
    return Response(
        content=rendered_contract,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/data-sets/{data_set_id}/contract/import", response_model=DataSetView)
async def import_data_set_contract(
    data_set_id: str,
    payload: ContractImportRequestView,
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> DataSetView:
    data_set = repository.get_data_set(data_set_id)
    if data_set is None:
        raise HTTPException(status_code=404, detail=f"Data set '{data_set_id}' was not found")

    try:
        contract_payload = load_contract_payload(payload.contractText)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    contract_id = str(contract_payload.get("id") or "").strip()
    if contract_id and contract_id != f"urn:dq:dataset:{data_set_id}":
        raise HTTPException(status_code=400, detail="contract id does not match the selected data set")

    update_payload = _build_data_set_import_payload(contract_payload, data_set)
    updated_data_set = repository.update_data_set(data_set_id, update_payload)
    return _data_set_view(updated_data_set)


@router.get("/rule-attributes", response_model=list[RuleAttributeView])
async def get_rule_attributes(
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> list[RuleAttributeView]:
    return resolve_rule_attributes_view(repository.list_rule_attributes())


@router.post("/rule-attributes", response_model=AddRuleAttributesResultView)
async def post_rule_attributes(
    payload: RuleAttributesUpsertRequest,
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> AddRuleAttributesResultView:
    return resolve_add_rule_attributes_result_view(repository.add_rule_attributes(payload.entries))


@router.get("/data-objects-catalog", response_model=DataObjectCatalogPageView)
async def get_data_objects_catalog(
    dataSetId: str | None = Query(default=None),
    businessKey: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> DataObjectCatalogPageView:
    rows = repository.list_data_objects_catalog(dataSetId)
    if businessKey is not None:
        rows = [row for row in rows if str(getattr(row, "business_key", "") or "") == businessKey]
    return resolve_data_objects_catalog_page_view(build_data_catalog_page_payload([row.model_dump() for row in rows], page, limit))


@router.get("/data-object-versions", response_model=DataObjectVersionsPageView)
async def get_data_object_versions(
    objectId: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> DataObjectVersionsPageView:
    rows = repository.list_data_object_versions(objectId)
    return resolve_data_object_versions_page_view(build_data_catalog_page_payload([row.model_dump() for row in rows], page, limit))


@router.get("/data-object-versions/{version_id}", response_model=DataObjectVersionView)
async def get_data_object_version(
    version_id: str,
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> DataObjectVersionView:
    row = repository.get_data_object_version(version_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Data object version '{version_id}' not found")
    return DataObjectVersionView.model_validate(row.model_dump())


@router.get("/attributes-catalog", response_model=AttributeCatalogPageView)
async def get_attributes_catalog(
    versionId: str | None = Query(default=None),
    businessKeyOnly: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    data_asset_repository: DataAssetRepository = Depends(get_data_asset_repository),
) -> AttributeCatalogPageView:
    rows = list(repository.list_attributes_catalog(versionId))
    if versionId is None:
        rows.extend(_build_data_asset_attribute_catalog_rows(data_asset_repository))
    if businessKeyOnly is not None:
        rows = [row for row in rows if bool(getattr(row, "is_business_key", False)) == businessKeyOnly]
    payload_rows = [row.model_dump() if hasattr(row, "model_dump") else dict(row) for row in rows]
    return resolve_attributes_catalog_page_view(build_data_catalog_page_payload(payload_rows, page, limit))


@router.get("/attributes-catalog/{attribute_id}/protection", response_model=AttributeCatalogView)
async def get_attribute_protection(
    request: Request,
    attribute_id: str,
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> AttributeCatalogView:
    attribute = repository.get_attribute_catalog(attribute_id)
    if attribute is None:
        raise HTTPException(status_code=404, detail=f"Attribute '{attribute_id}' not found")
    _require_protection_access(request=request, admin_repository=admin_repository, workspace_id=str(getattr(attribute, "workspace_id", "") or ""))
    return AttributeCatalogView.model_validate(attribute)


@router.put("/attributes-catalog/{attribute_id}/protection", response_model=AttributeCatalogView)
async def put_attribute_protection(
    request: Request,
    attribute_id: str,
    payload: dict[str, Any],
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    protection_repository: DataProtectionRepository = Depends(get_data_protection_repository),
    admin_repository: AdminRepository = Depends(get_admin_repository),
) -> AttributeCatalogView:
    attribute = repository.get_attribute_catalog(attribute_id)
    if attribute is None:
        raise HTTPException(status_code=404, detail=f"Attribute '{attribute_id}' not found")

    workspace_id = str(getattr(attribute, "workspace_id", "") or "")
    masking_method = str(payload.get("masking_method") or payload.get("maskingMethod") or "none").strip().lower() or "none"
    encryption_required = bool(payload.get("encryption_required") if "encryption_required" in payload else payload.get("encryptionRequired"))
    encryption_key_id = str(payload.get("encryption_key_id") or payload.get("encryptionKeyId") or "").strip() or None

    if encryption_key_id is not None and not encryption_required:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_attribute_protection",
                "message": "encryption_required must be true when an encryption_key_id is provided",
                "attribute_id": attribute_id,
            },
        )

    configured_by = str(getattr(request.state, "user_id", None) or "").strip() or None

    if encryption_required or encryption_key_id is not None:
        _require_protection_access(request=request, admin_repository=admin_repository, workspace_id=workspace_id, can_write_encryption=True)
    else:
        _require_protection_access(request=request, admin_repository=admin_repository, workspace_id=workspace_id, can_write_masking=True)

    if encryption_key_id is not None:
        key = protection_repository.get_encryption_key(encryption_key_id)
        if key is None:
            raise HTTPException(status_code=404, detail=f"Encryption key '{encryption_key_id}' not found")
        key_scope = str(getattr(key, "keyScope", "app") or "app").strip().lower() or "app"
        key_workspace_id = str(getattr(key, "workspaceId", "") or "").strip() or None
        if key_scope == "workspace" and key_workspace_id != workspace_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_encryption_key_scope",
                    "message": "Workspace-scoped encryption key does not belong to this workspace",
                    "attribute_id": attribute_id,
                    "workspace_id": workspace_id,
                    "encryption_key_id": encryption_key_id,
                },
            )

    try:
        updated = repository.upsert_attribute_protection_policy(
            attribute_id=attribute_id,
            masking_method=masking_method,
            encryption_required=encryption_required,
            encryption_key_id=encryption_key_id,
            configured_by=configured_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return AttributeCatalogView.model_validate(updated)


@router.get("/attribute-definition-mappings", response_model=list[AttributeDefinitionMappingView])
async def get_attribute_definition_mappings(
    versionId: str | None = Query(default=None),
    attributeId: str | None = Query(default=None),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> list[AttributeDefinitionMappingView]:
    return resolve_attribute_definition_mappings_view(
        repository.list_attribute_definition_mappings(version_id=versionId, attribute_id=attributeId)
    )


@router.post("/attribute-definition-mappings", response_model=AttributeDefinitionMappingUpsertResultView)
async def post_attribute_definition_mapping(
    payload: AttributeDefinitionMappingUpsertRequestView,
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    resolver: RegistryDefinitionResolver = Depends(get_registry_definition_resolver),
) -> AttributeDefinitionMappingUpsertResultView:
    if payload.mapping_state == "mapped":
        try:
            await resolver.resolve_definition(str(payload.definition_id or ""))
        except RegistryDefinitionLookupError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "error": "registry_definition_lookup_failed",
                    "message": str(exc),
                    "definition_id": payload.definition_id,
                    "attribute_id": payload.attribute_id,
                },
            ) from exc

    try:
        result = repository.upsert_attribute_definition_mapping(
            attribute_id=payload.attribute_id,
            definition_id=payload.definition_id,
            mapping_state=payload.mapping_state,
            mapped_by=payload.mapped_by,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_attribute_definition_mapping",
                "message": str(exc),
                "attribute_id": payload.attribute_id,
            },
        ) from exc
    return resolve_attribute_definition_mapping_upsert_result_view(result)


@router.post(
    "/data-definition-tasks",
    response_model=DataDefinitionTaskCreateResponseView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_data_definition_task(
    payload: DataDefinitionTaskCreateRequestView,
    request: Request,
    suggestions_repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> JSONResponse:
    user_id = str(getattr(request.state, "user_id", None) or "").strip()
    if not user_id:
        return _not_authenticated_json_response()

    board_approval = payload.boardApproval.model_dump(mode="json", by_alias=True) if payload.boardApproval is not None else None
    if payload.autoImport and str((board_approval or {}).get("status") or "").strip().lower() != "approved":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "board_approval_required",
                "message": "Automatic OpenMetadata import requires board approval status 'approved'",
            },
        )

    queued_request = _QueuedDataDefinitionTaskRequest(
        currentWorkspaceId=payload.currentWorkspaceId,
        prompt=str(payload.userInput or f"Generate data definitions for {len(payload.selectedAttributeIds)} attribute(s)").strip(),
        selectedAttributeIds=payload.selectedAttributeIds,
        versionId=payload.versionId,
        taskPayload={
            "task_id": str(getattr(request.state, "correlation_id", None) or user_id),
            "current_workspace_id": payload.currentWorkspaceId,
            "version_id": payload.versionId,
            "selected_attribute_ids": payload.selectedAttributeIds,
            "user_input": payload.userInput,
            "policies": payload.policies,
            "context_documents": [item.model_dump(mode="json", by_alias=True) for item in payload.contextDocuments],
            "feedback_items": [item.model_dump(mode="json", by_alias=True) for item in payload.feedbackItems],
            "board_approval": board_approval,
            "steward_name": payload.stewardName,
            "board_name": payload.boardName,
            "glossary_name": payload.glossaryName,
            "glossary_display_name": payload.glossaryDisplayName,
            "domain_name": payload.domainName,
            "source_system": payload.sourceSystem,
        },
        autoImport=payload.autoImport,
    )

    try:
        queue_result = await enqueue_natural_language_draft_job(
            request_body=queued_request,
            settings=get_settings(),
            suggestions_repository=suggestions_repository,
            correlation_id=str(getattr(request.state, "correlation_id", None) or user_id),
            requested_by_user_id=user_id,
            accessible_workspace_ids={payload.currentWorkspaceId},
            selected_attribute_ids=payload.selectedAttributeIds,
        )
    except NaturalLanguageDraftEnqueueServiceError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "data_definition_task_enqueue_failed",
                "message": exc.public_detail,
                "status": exc.status_code,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=DataDefinitionTaskCreateResponseView(
            requestId=queue_result.request_id,
            eventsUrl=_data_definition_task_events_url(queue_result.request_id),
            message="Data-definition task accepted. Subscribe to task events for draft generation progress.",
        ).model_dump(by_alias=True, mode="json"),
    )


@router.get("/data-definition-tasks/requests/{request_id}/status", response_model=DataDefinitionTaskStatusResponseView)
async def get_data_definition_task_status(request_id: str) -> JSONResponse:
    try:
        record = load_request_record_from_settings(get_settings(), request_id)
    except NaturalLanguageDraftEnqueueServiceError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "data_definition_task_store_unavailable",
                "message": exc.public_detail,
                "status": exc.status_code,
            },
        )

    if record is None or str(record.get("analysis_type") or "").strip().lower() != ANALYSIS_TYPE_DEFINITION_TASK:
        return JSONResponse(
            status_code=404,
            content={"error": "data_definition_task_not_found", "message": "Data-definition task was not found", "status": 404},
        )

    reconciled_record = _reconcile_stale_definition_task_status(dict(record))
    if reconciled_record != record:
        try:
            save_request_record_to_settings(get_settings(), reconciled_record)
        except Exception:
            pass

    return JSONResponse(
        status_code=200,
        content=DataDefinitionTaskStatusResponseView(
            request=_build_definition_task_status_view(reconciled_record),
        ).model_dump(by_alias=True, mode="json"),
    )


@router.get("/data-definition-tasks/requests/{request_id}/events", response_model=None)
async def stream_data_definition_task_events(request_id: str, request: Request):
    settings = get_settings()
    try:
        record = load_request_record_from_settings(settings, request_id)
    except NaturalLanguageDraftEnqueueServiceError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "data_definition_task_store_unavailable",
                "message": exc.public_detail,
                "status": exc.status_code,
            },
        )

    if record is None or str(record.get("analysis_type") or "").strip().lower() != ANALYSIS_TYPE_DEFINITION_TASK:
        return JSONResponse(
            status_code=404,
            content={"error": "data_definition_task_not_found", "message": "Data-definition task was not found", "status": 404},
        )

    if str(record.get("status") or "").strip().lower() in {"completed", "failed"}:
        return Response(
            content=_sse_frame(event_name="snapshot", payload=_build_data_definition_task_event_payload(record)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    last_event_id = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
    return StreamingResponse(
        _stream_data_definition_task_events(
            settings=settings,
            request_id=request_id,
            initial_record=record,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/data-definition-tasks/requests", response_model=DataDefinitionTaskHistoryResponseView)
async def list_data_definition_tasks(
    request: Request,
    workspace_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    suggestions_repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> JSONResponse:
    user_id = str(getattr(request.state, "user_id", None) or "").strip()
    if not user_id:
        return _not_authenticated_json_response()

    requests = suggestions_repository.list_natural_language_requests(
        user_id=user_id,
        workspace_id=workspace_id,
        limit=limit,
    )
    filtered = [
        request_entity
        for request_entity in requests
        if str(getattr(request_entity, "analysis_type", "") or "").strip().lower() == ANALYSIS_TYPE_DEFINITION_TASK
    ]
    payload = DataDefinitionTaskHistoryResponseView(
        requests=[
            _build_definition_task_status_view(
                {
                    "request_id": request_entity.request_id,
                    "current_workspace_id": request_entity.current_workspace_id,
                    "version_id": None,
                    "selected_attribute_ids": request_entity.selected_attribute_ids,
                    "prompt": request_entity.prompt,
                    "requested_by_user_id": request_entity.requested_by_user_id,
                    "requested_by_email": request_entity.requested_by_email,
                    "requested_at": request_entity.requested_at,
                    "started_at": request_entity.started_at,
                    "completed_at": request_entity.completed_at,
                    "status": request_entity.status,
                    "error_message": request_entity.error_message,
                    "analysis_type": request_entity.analysis_type,
                    "analysis_provider": request_entity.analysis_provider,
                    "result": request_entity.result,
                }
            )
            for request_entity in filtered
        ],
        count=len(filtered),
    )
    return JSONResponse(status_code=200, content=payload.model_dump(by_alias=True, mode="json"))


@router.get("/data-definition-tasks/requests/{request_id}/history", response_model=DataDefinitionTaskAuditHistoryResponseView)
async def list_data_definition_task_history(
    request_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    suggestions_repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> JSONResponse:
    user_id = str(getattr(request.state, "user_id", None) or "").strip()
    if not user_id:
        return _not_authenticated_json_response()

    history = suggestions_repository.list_natural_language_request_history(
        request_id=request_id,
        limit=limit,
        offset=offset,
    )
    if history is None:
        raise HTTPException(status_code=404, detail={"error": "data_definition_task_not_found", "message": "Data-definition task was not found"})

    payload = DataDefinitionTaskAuditHistoryResponseView(
        requestId=request_id,
        events=[
            _build_definition_task_audit_event_view(
                {
                    "id": event.id,
                    "request_id": event.request_id,
                    "action": event.action,
                    "from_status": event.from_status,
                    "to_status": event.to_status,
                    "actor_id": event.actor_id,
                    "changed_at": event.changed_at,
                    "details": event.details,
                }
            )
            for event in history
        ],
        count=len(history),
    )
    return JSONResponse(status_code=200, content=payload.model_dump(by_alias=True, mode="json"))


@router.post("/data-definition-tasks/requests/{request_id}/approval", response_model=DataDefinitionTaskStatusResponseView)
async def update_data_definition_task_approval(
    request_id: str,
    payload: DataDefinitionTaskApprovalUpdateRequestView,
    request: Request,
    suggestions_repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> JSONResponse:
    user_id = str(getattr(request.state, "user_id", None) or "").strip()
    if not user_id:
        return _not_authenticated_json_response()

    record = load_request_record_from_settings(get_settings(), request_id)
    if record is None or str(record.get("analysis_type") or "").strip().lower() != ANALYSIS_TYPE_DEFINITION_TASK:
        raise HTTPException(status_code=404, detail={"error": "data_definition_task_not_found", "message": "Data-definition task was not found"})

    result = record.get("result") if isinstance(record.get("result"), dict) else None
    if result is None:
        raise HTTPException(status_code=409, detail={"error": "task_result_not_available", "message": "Task result is not available yet"})

    approval_payload = payload.boardApproval.model_dump(mode="json", by_alias=False)
    try:
        updated_result = apply_board_approval_to_result(result=result, approval_payload=approval_payload)
    except DataDefinitionTaskError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": "data_definition_guideline_violation", "message": str(exc)},
        ) from exc

    if payload.autoImport and str(approval_payload.get("status") or "").strip().lower() != "approved":
        raise HTTPException(status_code=422, detail={"error": "board_approval_required", "message": "Only approved tasks can be imported to OpenMetadata"})

    if str(updated_result.get("review_status") or "").strip().lower() == "approved":
        importer = _openmetadata_importer_from_settings()
        try:
            import_contract = require_approved_openmetadata_import_contract(result=updated_result)
        except DataDefinitionTaskError as exc:
            error_code = "missing_import_contract" if exc.status_code == 502 else "board_approval_required"
            raise HTTPException(status_code=exc.status_code, detail={"error": error_code, "message": str(exc)}) from exc
        try:
            import_report = importer.import_contract(import_contract)
        except OpenMetadataDefinitionImportError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"error": "openmetadata_import_failed", "message": str(exc)}) from exc
        updated_result = merge_import_result(result=updated_result, import_report=import_report)
        record["auto_import"] = True

    record["result"] = updated_result
    task_payload = record.get("task_payload") if isinstance(record.get("task_payload"), dict) else {}
    task_payload["board_approval"] = approval_payload
    record["task_payload"] = task_payload
    save_request_record_to_settings(get_settings(), record)
    suggestions_repository.update_natural_language_request(
        request_id=request_id,
        status=str(record.get("status") or "completed"),
        job_id=str(record.get("job_id") or ""),
        started_at=record.get("started_at"),
        completed_at=record.get("completed_at"),
        error_message=record.get("error_message"),
        result=updated_result,
    )

    return JSONResponse(
        status_code=200,
        content=DataDefinitionTaskStatusResponseView(
            request=_build_definition_task_status_view(record),
        ).model_dump(by_alias=True, mode="json"),
    )


@router.post("/data-definition-tasks/requests/{request_id}/openmetadata-sync", response_model=DataDefinitionTaskImportResponseView)
async def import_data_definition_task_to_openmetadata(
    request_id: str,
    request: Request,
    suggestions_repository: SuggestionsRepository = Depends(get_suggestions_repository),
) -> JSONResponse:
    user_id = str(getattr(request.state, "user_id", None) or "").strip()
    if not user_id:
        return _not_authenticated_json_response()

    record = load_request_record_from_settings(get_settings(), request_id)
    if record is None or str(record.get("analysis_type") or "").strip().lower() != ANALYSIS_TYPE_DEFINITION_TASK:
        raise HTTPException(status_code=404, detail={"error": "data_definition_task_not_found", "message": "Data-definition task was not found"})

    result = record.get("result") if isinstance(record.get("result"), dict) else None
    if result is None:
        raise HTTPException(status_code=409, detail={"error": "task_result_not_available", "message": "Task result is not available yet"})
    try:
        import_contract = require_approved_openmetadata_import_contract(result=result)
    except DataDefinitionTaskError as exc:
        if exc.status_code == 422 and str(exc) == "Only approved tasks can be imported to OpenMetadata":
            raise HTTPException(status_code=422, detail={"error": "board_approval_required", "message": str(exc)}) from exc
        if exc.status_code == 502:
            raise HTTPException(status_code=502, detail={"error": "missing_import_contract", "message": str(exc)}) from exc
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": "data_definition_guideline_violation", "message": str(exc)},
        ) from exc

    importer = _openmetadata_importer_from_settings()
    try:
        import_report = importer.import_contract(import_contract)
    except OpenMetadataDefinitionImportError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": "openmetadata_import_failed", "message": str(exc)}) from exc

    updated_result = merge_import_result(result=result, import_report=import_report)
    record["result"] = updated_result
    record["auto_import"] = True
    save_request_record_to_settings(get_settings(), record)
    suggestions_repository.update_natural_language_request(
        request_id=request_id,
        status=str(record.get("status") or "completed"),
        job_id=str(record.get("job_id") or ""),
        started_at=record.get("started_at"),
        completed_at=record.get("completed_at"),
        error_message=record.get("error_message"),
        result=updated_result,
    )

    return JSONResponse(
        status_code=200,
        content=DataDefinitionTaskImportResponseView(
            requestId=request_id,
            message="Imported generated data definitions into OpenMetadata.",
            importReport=import_report,
        ).model_dump(by_alias=True, mode="json"),
    )


@router.get("/data-deliveries", response_model=DataDeliveriesPageView)
async def get_data_deliveries(
    dataObjectVersionId: str | None = Query(default=None),
    versionId: str | None = Query(default=None),
    workspace: str | None = Query(default=None),
    businessKey: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> DataDeliveriesPageView:
    if dataObjectVersionId and versionId and dataObjectVersionId != versionId:
        raise HTTPException(
            status_code=422,
            detail="Provide only one of dataObjectVersionId or versionId",
        )
    rows = repository.list_data_deliveries(dataObjectVersionId or versionId, workspace)
    if businessKey is not None:
        rows = [row for row in rows if str(getattr(row, "delivery_location", "") or "") == businessKey]
    return resolve_data_deliveries_page_view(build_data_catalog_page_payload([row.model_dump() for row in rows], page, limit))


@router.get("/data-deliveries/{delivery_id}/note", response_model=DataDeliveryNoteView)
async def get_data_delivery_note(
    delivery_id: str,
    include_storage_details: bool = Query(default=False),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> DataDeliveryNoteView:
    note = repository.get_data_delivery_note(delivery_id)
    if note is None:
        raise HTTPException(status_code=404, detail=f"Data delivery '{delivery_id}' not found")

    payload = note.model_dump()
    execution_runs = await execution_run_repository.list_runs({})
    payload.update(build_delivery_linked_execution_note_enrichment(delivery_id=delivery_id, runs=execution_runs))
    if include_storage_details:
        metadata_json = payload.get("metadata_json")
        workspace_id = ""
        if isinstance(metadata_json, Mapping):
            workspace_id = str(metadata_json.get("workspace_id") or "").strip()

        if workspace_id and str(payload.get("delivery_location") or "").strip():
            data_objects_catalog = repository.list_data_objects_catalog()
            object_name_lookup = {
                **{str(obj.id or ""): str(obj.name or "") for obj in data_objects_catalog},
                **{str(obj.name or ""): str(obj.name or "") for obj in data_objects_catalog},
            }
            inspector = DeliveryInventoryInspector()
            resolved_delivery_location = resolve_delivery_inventory_location(
                delivery_location=str(payload.get("delivery_location") or ""),
                layer=str(payload.get("layer") or ""),
                workspace=workspace_id,
                data_object_id=str(payload.get("data_object_id") or ""),
                data_object_name=object_name_lookup.get(str(payload.get("data_object_id") or ""), ""),
            )
            storage_status = inspector.inspect(resolved_delivery_location)
            storage_file_names = storage_status.get("file_names")
            storage_exists = storage_status.get("storage_exists")
            storage_object_count = storage_status.get("storage_object_count")
            if payload.get("file_count") is None:
                if storage_object_count is not None:
                    payload["file_count"] = storage_object_count
                elif isinstance(storage_file_names, list):
                    payload["file_count"] = len(storage_file_names)
            if payload.get("file_names") is None and storage_file_names is not None:
                payload["file_names"] = list(storage_file_names)
            payload["storage_exists"] = storage_exists
            payload["storage_object_count"] = storage_object_count

    return resolve_data_delivery_note_view(payload)


@router.get(
    "/data-deliveries/{data_delivery_id}/executions/{execution_id}",
    response_model=GxExecutionRunView,
    responses={
        200: {
            "description": "Delivery-linked GX execution run metadata and lifecycle state.",
        },
        404: {
            "description": "Delivery or execution run not found.",
        },
        409: {
            "description": "Execution run does not belong to the requested delivery.",
        },
    },
)
async def get_data_delivery_execution_status(
    data_delivery_id: str,
    execution_id: str,
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> GxExecutionRunView:
    if catalog_repository.get_data_delivery_note(data_delivery_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "data_delivery_not_found",
                "message": f"Data delivery '{data_delivery_id}' not found",
                "data_delivery_id": data_delivery_id,
            },
        )

    run = await execution_run_repository.get_run(execution_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "execution_run_not_found",
                "message": f"GX execution run '{execution_id}' not found",
                "data_delivery_id": data_delivery_id,
                "execution_run_id": execution_id,
            },
        )

    linked_data_delivery_id = resolve_delivery_linked_execution_delivery_id(run)
    if not linked_data_delivery_id:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "execution_run_not_linked_to_delivery",
                "message": "GX execution run is not linked to a delivery",
                "data_delivery_id": data_delivery_id,
                "execution_run_id": execution_id,
            },
        )

    if linked_data_delivery_id != data_delivery_id:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "execution_delivery_mismatch",
                "message": "GX execution run does not belong to the requested delivery",
                "data_delivery_id": data_delivery_id,
                "execution_run_id": execution_id,
                "resolved_data_delivery_id": linked_data_delivery_id,
            },
        )

    return GxExecutionRunView.model_validate(run.model_dump(mode="python", by_alias=False, exclude_none=True))


@router.post(
    "/data-deliveries/{data_delivery_id}/executions",
    response_model=DataDeliveryExecutionReceiptView,
    status_code=202,
)
async def post_data_delivery_execution_request(
    request: Request,
    data_delivery_id: str,
    payload: DataDeliveryExecutionRequestView | None = None,
    catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    validation_artifact_repository: ValidationArtifactRepository = Depends(get_validation_artifact_repository),
    validation_run_plan_repository: ValidationRunPlanRepository = Depends(get_validation_run_plan_repository),
    execution_run_repository: GxExecutionRunRepository = Depends(get_gx_execution_run_repository),
) -> DataDeliveryExecutionReceiptView:
    orchestrator = DeliveryLinkedExecutionOrchestrator(
        catalog_repository=catalog_repository,
        validation_artifact_repository=validation_artifact_repository,
        validation_run_plan_repository=validation_run_plan_repository,
        execution_run_repository=execution_run_repository,
        runtime_api=_gx_runtime_api,
    )
    try:
        result = await orchestrator.execute_submission(
            request=request,
            data_delivery_id=data_delivery_id,
            execution_selector=(payload.execution_selector.model_dump(exclude_none=True) if payload and payload.execution_selector else None),
        )
    except DeliveryLinkedExecutionRequestError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": exc.reason,
                "message": str(exc),
                "data_delivery_id": data_delivery_id,
            },
        ) from exc

    return DataDeliveryExecutionReceiptView.model_validate(result)


@router.get("/delivery-inventory", response_model=DataDeliveryInventoryPageView)
async def get_delivery_inventory(
    dataObjectVersionId: str | None = Query(default=None),
    versionId: str | None = Query(default=None),
    workspace: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> DataDeliveryInventoryPageView:
    if dataObjectVersionId and versionId and dataObjectVersionId != versionId:
        raise HTTPException(
            status_code=422,
            detail="Provide only one of dataObjectVersionId or versionId",
        )
    rows = repository.list_data_deliveries(dataObjectVersionId or versionId, workspace)
    data_objects_catalog = repository.list_data_objects_catalog()
    object_name_lookup = {
        **{str(obj.id or ""): str(obj.name or "") for obj in data_objects_catalog},
        **{str(obj.name or ""): str(obj.name or "") for obj in data_objects_catalog},
    }
    inspector = DeliveryInventoryInspector()
    payload = []
    for row in rows:
        resolved_delivery_location = resolve_delivery_inventory_location(
            delivery_location=str(getattr(row, "delivery_location", None) or ""),
            layer=str(getattr(row, "layer", None) or ""),
            workspace=workspace,
            data_object_id=str(getattr(row, "data_object_id", None) or ""),
            data_object_name=object_name_lookup.get(str(getattr(row, "data_object_id", None) or ""), ""),
        )
        status = inspector.inspect(resolved_delivery_location)
        row_payload = row.model_dump()
        payload.append({
            "id": row_payload.get("id"),
            "data_object_version_id": row_payload.get("data_object_version_id"),
            "version": row_payload.get("version"),
            "delivered_at": row_payload.get("delivered_at"),
            "layer": row_payload.get("layer"),
            "delivery_location": row_payload.get("delivery_location"),
            **status,
        })
    return resolve_data_delivery_inventory_page_view(build_data_catalog_page_payload(payload, page, limit))


@router.get("/attribute-rule-counts")
async def get_attribute_rule_counts(
    repository: DataCatalogRepository = Depends(get_data_catalog_repository),
) -> dict[str, int]:
    return resolve_attribute_rule_counts_view(repository.get_attribute_rule_counts())