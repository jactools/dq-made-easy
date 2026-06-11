from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.api.v1.schemas.data_catalog_view import AttributeCatalogView
from app.api.v1.schemas.data_catalog_view import DataObjectCatalogView
from app.api.v1.schemas.data_catalog_view import DataObjectVersionView
from app.api.v1.schemas.data_catalog_view import DataProductView
from app.api.v1.schemas.data_catalog_view import DataSetView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryAccessGrantRequestView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryAccessGrantView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryExternalPartyApprovalRequestView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryExternalPartyRegistrationRequestView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryExternalPartyView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryGoverningScopeView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryManifestView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryExchangeSnapshotView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryPackageView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryPullResultView
from app.api.v1.schemas.registry_definition_view import RegistryDefinitionView
from app.application.services.registry_definition_resolver import RegistryDefinitionLookupError
from app.application.services.registry_definition_resolver import RegistryDefinitionResolver
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryExchangeSnapshotEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryAccessGrantEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryExternalPartyEntity
from app.domain.entities.federated_metadata_registry import FederatedMetadataRegistryGoverningScopeEntity
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository


_PACKAGE_KIND = "federated_metadata_package"
_ACCESS_GRANT_TARGET_KINDS = {"metadata_structure", "metadata_item"}


class FederatedMetadataRegistryLookupError(RuntimeError):
    def __init__(self, message: str, *, definition_id: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.definition_id = definition_id
        self.status_code = status_code


def _now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _snapshot_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_target_kind(value: Any) -> str:
    normalized = _normalize_text(value)
    if normalized not in _ACCESS_GRANT_TARGET_KINDS:
        raise ValueError("target_kind must be metadata_structure or metadata_item")
    return normalized


def _unique_strings(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        normalized = _normalize_text(value)
        if normalized and normalized not in unique_values:
            unique_values.append(normalized)
    return unique_values


def _normalize_governing_scope(
    governing_scope: FederatedMetadataRegistryGoverningScopeView | dict[str, Any] | None,
) -> FederatedMetadataRegistryGoverningScopeEntity:
    normalized_scope = FederatedMetadataRegistryGoverningScopeView.model_validate(governing_scope or {})
    normalized_entity = FederatedMetadataRegistryGoverningScopeEntity(
        data_product_ids=_unique_strings(normalized_scope.dataProductIds),
        metadata_structure_ids=_unique_strings(normalized_scope.metadataStructureIds),
        metadata_item_ids=_unique_strings(normalized_scope.metadataItemIds),
    )
    if not normalized_entity.data_product_ids and not normalized_entity.metadata_structure_ids and not normalized_entity.metadata_item_ids:
        raise ValueError(
            "governing_scope must include at least one data_product_id, metadata_structure_id, or metadata_item_id"
        )
    return normalized_entity


def build_federated_metadata_registry_external_party(
    request: FederatedMetadataRegistryExternalPartyRegistrationRequestView,
    *,
    registered_by: str | None = None,
    correlation_id: str | None = None,
    registered_at: str | None = None,
) -> FederatedMetadataRegistryExternalPartyEntity:
    normalized_request = FederatedMetadataRegistryExternalPartyRegistrationRequestView.model_validate(request)
    normalized_workspace_id = _normalize_text(normalized_request.workspaceId)
    normalized_tenant_id = _normalize_text(normalized_request.tenantId)

    if bool(normalized_workspace_id) == bool(normalized_tenant_id):
        raise ValueError("exactly one of workspace_id or tenant_id is required")

    governing_scope = _normalize_governing_scope(normalized_request.governingScope)
    party_id = f"workspace:{normalized_workspace_id}" if normalized_workspace_id else f"tenant:{normalized_tenant_id}"

    return FederatedMetadataRegistryExternalPartyEntity(
        id=party_id,
        workspace_id=normalized_workspace_id or None,
        tenant_id=normalized_tenant_id or None,
        display_name=_normalize_text(normalized_request.displayName) or None,
        governing_scope=governing_scope,
        approval_status="pending",
        approved_at=None,
        approved_by=None,
        approval_notes=None,
        registered_at=str(registered_at or _snapshot_now_text()).strip(),
        registered_by=_normalize_text(registered_by) or None,
        correlation_id=_normalize_text(correlation_id) or None,
    )


def build_federated_metadata_registry_external_party_approval(
    party: FederatedMetadataRegistryExternalPartyEntity,
    request: FederatedMetadataRegistryExternalPartyApprovalRequestView | dict[str, Any] | None = None,
    *,
    approved_by: str | None = None,
    approved_at: str | None = None,
) -> FederatedMetadataRegistryExternalPartyEntity:
    normalized_party = FederatedMetadataRegistryExternalPartyEntity.model_validate(party)
    normalized_status = _normalize_text(normalized_party.approval_status) or "pending"
    if normalized_status != "pending":
        raise ValueError("external party is not pending approval")

    normalized_request = FederatedMetadataRegistryExternalPartyApprovalRequestView.model_validate(request or {})
    return FederatedMetadataRegistryExternalPartyEntity(
        id=normalized_party.id,
        workspace_id=normalized_party.workspace_id,
        tenant_id=normalized_party.tenant_id,
        display_name=normalized_party.display_name,
        governing_scope=normalized_party.governing_scope,
        approval_status="approved",
        approved_at=str(approved_at or _snapshot_now_text()).strip(),
        approved_by=_normalize_text(approved_by) or None,
        approval_notes=_normalize_text(normalized_request.approvalNotes) or None,
        registered_at=normalized_party.registered_at,
        registered_by=normalized_party.registered_by,
        correlation_id=normalized_party.correlation_id,
    )


def build_federated_metadata_registry_access_grant(
    request: FederatedMetadataRegistryAccessGrantRequestView,
    *,
    external_party_id: str,
    granted_by: str | None = None,
    correlation_id: str | None = None,
    granted_at: str | None = None,
) -> FederatedMetadataRegistryAccessGrantEntity:
    normalized_request = FederatedMetadataRegistryAccessGrantRequestView.model_validate(request)
    normalized_external_party_id = _normalize_text(external_party_id)
    if not normalized_external_party_id:
        raise ValueError("external_party_id is required")

    target_kind = _normalize_target_kind(normalized_request.targetKind)
    target_id = _normalize_text(normalized_request.targetId)
    if not target_id:
        raise ValueError("target_id is required")

    subscribed = bool(normalized_request.subscribed)
    can_push = bool(normalized_request.canPush)
    can_pull = bool(normalized_request.canPull)
    if not (subscribed or can_push or can_pull):
        raise ValueError("at least one of subscribed, can_push, or can_pull is required")

    grant_id = f"{normalized_external_party_id}|{target_kind}|{target_id}"
    return FederatedMetadataRegistryAccessGrantEntity(
        id=grant_id,
        external_party_id=normalized_external_party_id,
        target_kind=target_kind,
        target_id=target_id,
        subscribed=subscribed,
        can_push=can_push,
        can_pull=can_pull,
        notes=_normalize_text(normalized_request.notes) or None,
        granted_at=str(granted_at or _snapshot_now_text()).strip(),
        granted_by=_normalize_text(granted_by) or None,
        correlation_id=_normalize_text(correlation_id) or None,
    )


async def _resolve_registry_definitions(
    definition_ids: list[str],
    resolver: RegistryDefinitionResolver,
) -> list[RegistryDefinitionView]:
    if not definition_ids:
        return []

    resolved_views: list[RegistryDefinitionView] = []
    for definition_id in definition_ids:
        try:
            payload = await resolver.resolve_definition(definition_id)
        except RegistryDefinitionLookupError as exc:
            raise FederatedMetadataRegistryLookupError(
                str(exc),
                definition_id=definition_id,
                status_code=exc.status_code,
            ) from exc
        resolved_views.append(RegistryDefinitionView.model_validate(payload))
    return resolved_views


def _build_manifest(
    *,
    data_products: list[DataProductView],
    data_sets: list[DataSetView],
    data_objects: list[DataObjectCatalogView],
    data_object_versions: list[DataObjectVersionView],
    attributes: list[AttributeCatalogView],
    registry_definitions: list[RegistryDefinitionView],
) -> FederatedMetadataRegistryManifestView:
    return FederatedMetadataRegistryManifestView(
        dataProductCount=len(data_products),
        dataSetCount=len(data_sets),
        dataObjectCount=len(data_objects),
        dataObjectVersionCount=len(data_object_versions),
        attributeCount=len(attributes),
        registryDefinitionCount=len(registry_definitions),
    )


async def build_federated_metadata_package(
    *,
    workspace_id: str,
    data_catalog_repository: DataCatalogRepository,
    registry_definition_resolver: RegistryDefinitionResolver,
    data_product_id: str | None = None,
) -> FederatedMetadataRegistryPackageView:
    normalized_workspace_id = _normalize_text(workspace_id)
    if not normalized_workspace_id:
        raise ValueError("workspace_id is required")

    normalized_data_product_id = _normalize_text(data_product_id) or None

    data_products_entities = data_catalog_repository.list_data_products(workspace=normalized_workspace_id)
    if normalized_data_product_id:
        data_products_entities = [
            data_product
            for data_product in data_products_entities
            if _normalize_text(data_product.id) == normalized_data_product_id
        ]
        if not data_products_entities:
            raise ValueError(
                f"Data product '{normalized_data_product_id}' was not found in workspace '{normalized_workspace_id}'"
            )
    if not data_products_entities:
        raise ValueError(f"No data products were found in workspace '{normalized_workspace_id}'")

    data_products = [DataProductView.model_validate(data_product) for data_product in data_products_entities]
    data_sets: list[DataSetView] = []
    data_objects: list[DataObjectCatalogView] = []
    data_object_versions: list[DataObjectVersionView] = []
    attributes: list[AttributeCatalogView] = []

    for data_product in data_products_entities:
        for data_set in data_catalog_repository.list_data_sets(product_id=_normalize_text(data_product.id), workspace=normalized_workspace_id):
            data_set_view = DataSetView.model_validate(data_set)
            data_sets.append(data_set_view)
            for data_object in data_catalog_repository.list_data_objects_catalog(data_set_id=_normalize_text(data_set.id)):
                data_object_view = DataObjectCatalogView.model_validate(data_object)
                data_objects.append(data_object_view)
                for data_object_version in data_catalog_repository.list_data_object_versions(object_id=_normalize_text(data_object.id)):
                    data_object_version_view = DataObjectVersionView.model_validate(data_object_version)
                    data_object_versions.append(data_object_version_view)
                    attributes.extend(
                        AttributeCatalogView.model_validate(attribute)
                        for attribute in data_catalog_repository.list_attributes_catalog(version_id=_normalize_text(data_object_version.id))
                    )

    definition_ids = _unique_strings([attribute.definition_id for attribute in attributes if attribute.definition_id is not None])
    registry_definitions = await _resolve_registry_definitions(definition_ids, registry_definition_resolver)

    return FederatedMetadataRegistryPackageView(
        packageId=f"fmp-{uuid4().hex[:12]}",
        packageKind=_PACKAGE_KIND,
        workspaceId=normalized_workspace_id,
        dataProductId=normalized_data_product_id,
        createdAt=_now_text(),
        manifest=_build_manifest(
            data_products=data_products,
            data_sets=data_sets,
            data_objects=data_objects,
            data_object_versions=data_object_versions,
            attributes=attributes,
            registry_definitions=registry_definitions,
        ),
        dataProducts=data_products,
        dataSets=data_sets,
        dataObjects=data_objects,
        dataObjectVersions=data_object_versions,
        attributes=attributes,
        registryDefinitions=registry_definitions,
    )


def validate_federated_metadata_package(package: FederatedMetadataRegistryPackageView) -> FederatedMetadataRegistryPackageView:
    normalized_package = FederatedMetadataRegistryPackageView.model_validate(package)

    if _normalize_text(normalized_package.packageKind) != _PACKAGE_KIND:
        raise ValueError(f"package_kind must be '{_PACKAGE_KIND}'")

    normalized_workspace_id = _normalize_text(normalized_package.workspaceId)
    if not normalized_workspace_id:
        raise ValueError("workspace_id is required")

    if not normalized_package.dataProducts:
        raise ValueError("at least one data product is required")

    if normalized_package.dataProductId:
        if len(normalized_package.dataProducts) != 1:
            raise ValueError("data_product_id packages must contain exactly one data product")
        if _normalize_text(normalized_package.dataProducts[0].id) != normalized_package.dataProductId:
            raise ValueError("data_product_id must match the exported data product")

    data_product_ids = _unique_strings([data_product.id for data_product in normalized_package.dataProducts])
    data_set_ids = _unique_strings([data_set.id for data_set in normalized_package.dataSets])
    data_object_ids = _unique_strings([data_object.id for data_object in normalized_package.dataObjects])
    version_ids = _unique_strings([version.id for version in normalized_package.dataObjectVersions])
    definition_ids = _unique_strings([definition.definition_id for definition in normalized_package.registryDefinitions])

    if len(data_product_ids) != len(normalized_package.dataProducts):
        raise ValueError("data_products contains duplicate identifiers")
    if len(data_set_ids) != len(normalized_package.dataSets):
        raise ValueError("data_sets contains duplicate identifiers")
    if len(data_object_ids) != len(normalized_package.dataObjects):
        raise ValueError("data_objects contains duplicate identifiers")
    if len(version_ids) != len(normalized_package.dataObjectVersions):
        raise ValueError("data_object_versions contains duplicate identifiers")
    if len(definition_ids) != len(normalized_package.registryDefinitions):
        raise ValueError("registry_definitions contains duplicate identifiers")

    if len(data_product_ids) != normalized_package.manifest.dataProductCount:
        raise ValueError("data_product_count does not match the exported data_products list")
    if len(data_set_ids) != normalized_package.manifest.dataSetCount:
        raise ValueError("data_set_count does not match the exported data_sets list")
    if len(data_object_ids) != normalized_package.manifest.dataObjectCount:
        raise ValueError("data_object_count does not match the exported data_objects list")
    if len(version_ids) != normalized_package.manifest.dataObjectVersionCount:
        raise ValueError("data_object_version_count does not match the exported data_object_versions list")
    if len(_unique_strings([attribute.id for attribute in normalized_package.attributes])) != normalized_package.manifest.attributeCount:
        raise ValueError("attribute_count does not match the exported attributes list")
    if len(definition_ids) != normalized_package.manifest.registryDefinitionCount:
        raise ValueError("registry_definition_count does not match the exported registry_definitions list")

    data_product_id_set = set(data_product_ids)
    data_set_id_set = set(data_set_ids)
    data_object_id_set = set(data_object_ids)
    version_id_set = set(version_ids)
    definition_id_set = set(definition_ids)

    for data_product in normalized_package.dataProducts:
        if _normalize_text(data_product.workspace_id) != normalized_workspace_id:
            raise ValueError("all data_products must belong to the package workspace")

    for data_set in normalized_package.dataSets:
        if _normalize_text(data_set.workspace_id) != normalized_workspace_id:
            raise ValueError("all data_sets must belong to the package workspace")
        if _normalize_text(data_set.product_id) not in data_product_id_set:
            raise ValueError(f"data_set '{data_set.id}' references an unknown data_product_id")

    for data_object in normalized_package.dataObjects:
        if _normalize_text(data_object.dataset_id) not in data_set_id_set:
            raise ValueError(f"data_object '{data_object.id}' references an unknown dataset_id")

    for version in normalized_package.dataObjectVersions:
        if _normalize_text(version.data_object_id) not in data_object_id_set:
            raise ValueError(f"data_object_version '{version.id}' references an unknown data_object_id")

    for attribute in normalized_package.attributes:
        if _normalize_text(attribute.data_object_id) not in data_object_id_set:
            raise ValueError(f"attribute '{attribute.id}' references an unknown data_object_id")
        if _normalize_text(attribute.version_id) not in version_id_set:
            raise ValueError(f"attribute '{attribute.id}' references an unknown version_id")
        if attribute.definition_id is not None and _normalize_text(attribute.definition_id) not in definition_id_set:
            raise ValueError(f"attribute '{attribute.id}' references an unknown definition_id")

    return normalized_package


def build_federated_metadata_pull_result(package: FederatedMetadataRegistryPackageView) -> FederatedMetadataRegistryPullResultView:
    validated_package = validate_federated_metadata_package(package)
    return FederatedMetadataRegistryPullResultView(
        accepted=True,
        validatedAt=_now_text(),
        package=validated_package,
    )


def build_federated_metadata_registry_exchange_snapshot(
    package: FederatedMetadataRegistryPackageView,
    *,
    exchange_kind: str,
    accepted: bool,
    validation_error: str | None = None,
    captured_by: str | None = None,
    correlation_id: str | None = None,
    snapshot_id: str | None = None,
    captured_at: str | None = None,
) -> FederatedMetadataRegistryExchangeSnapshotEntity:
    normalized_package = FederatedMetadataRegistryPackageView.model_validate(package)
    normalized_exchange_kind = str(exchange_kind or "").strip()
    if normalized_exchange_kind not in {"push", "pull"}:
        raise ValueError("exchange_kind must be 'push' or 'pull'")

    return FederatedMetadataRegistryExchangeSnapshotEntity(
        id=str(snapshot_id or f"federated-metadata-registry-exchange-{uuid4().hex}").strip(),
        package_id=str(normalized_package.packageId).strip(),
        package_kind=str(normalized_package.packageKind or _PACKAGE_KIND).strip() or _PACKAGE_KIND,
        exchange_kind=normalized_exchange_kind,
        workspace_id=str(normalized_package.workspaceId).strip(),
        data_product_id=str(normalized_package.dataProductId or "").strip() or None,
        captured_at=str(captured_at or _snapshot_now_text()).strip(),
        captured_by=str(captured_by or "").strip() or None,
        correlation_id=str(correlation_id or "").strip() or None,
        accepted=bool(accepted),
        validation_error=str(validation_error or "").strip() or None,
        manifest=normalized_package.manifest.model_dump(mode="python", by_alias=False, exclude_none=False),
        package=normalized_package.model_dump(mode="python", by_alias=False, exclude_none=False),
    )


def build_federated_metadata_registry_external_party_view(
    party: FederatedMetadataRegistryExternalPartyEntity,
) -> FederatedMetadataRegistryExternalPartyView:
    return FederatedMetadataRegistryExternalPartyView.model_validate(party)


def build_federated_metadata_registry_access_grant_view(
    grant: FederatedMetadataRegistryAccessGrantEntity,
) -> FederatedMetadataRegistryAccessGrantView:
    return FederatedMetadataRegistryAccessGrantView.model_validate(grant)