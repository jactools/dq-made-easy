from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryAccessGrantRequestView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryAccessGrantView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryExternalPartyApprovalRequestView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryExternalPartyRegistrationRequestView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryExternalPartyView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryExchangeSnapshotView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryPackageView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryPullResultView
from app.api.v1.schemas.federated_metadata_registry_view import FederatedMetadataRegistryPushRequestView
from app.application.services.federated_metadata_registry import FederatedMetadataRegistryLookupError
from app.application.services.federated_metadata_registry import build_federated_metadata_registry_access_grant
from app.application.services.federated_metadata_registry import build_federated_metadata_registry_access_grant_view
from app.application.services.federated_metadata_registry import build_federated_metadata_package
from app.application.services.federated_metadata_registry import build_federated_metadata_pull_result
from app.application.services.federated_metadata_registry import build_federated_metadata_registry_external_party_approval
from app.application.services.federated_metadata_registry import build_federated_metadata_registry_external_party
from app.application.services.federated_metadata_registry import build_federated_metadata_registry_external_party_view
from app.application.services.federated_metadata_registry import build_federated_metadata_registry_exchange_snapshot
from app.application.services.registry_definition_resolver import RegistryDefinitionResolver
from app.core.dependencies import get_data_catalog_repository
from app.core.dependencies import get_federated_metadata_registry_repository
from app.core.dependencies import get_registry_definition_resolver
from app.core.request_context import get_correlation_id
from app.core.request_context import get_user_id
from app.domain.interfaces.v1.data_catalog_repository import DataCatalogRepository
from app.domain.interfaces.v1.federated_metadata_registry_repository import FederatedMetadataRegistryRepository


router = APIRouter(tags=["metadata-registry"])


def _build_lookup_http_exception(exc: FederatedMetadataRegistryLookupError, workspace_id: str, data_product_id: str | None) -> HTTPException:
    error_code_by_status = {
        404: "federated_metadata_registry_definition_not_found",
        409: "federated_metadata_registry_definition_ambiguous",
        503: "federated_metadata_registry_definition_unavailable",
    }
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error": error_code_by_status.get(exc.status_code, "federated_metadata_registry_definition_lookup_failed"),
            "message": str(exc),
            "workspace_id": workspace_id,
            "data_product_id": data_product_id,
            "definition_id": exc.definition_id,
        },
    )


def _build_invalid_package_http_exception(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": "federated_metadata_registry_invalid_package",
            "message": message,
        },
    )


def _build_invalid_external_party_http_exception(message: str, *, workspace_id: str | None, tenant_id: str | None) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": "federated_metadata_registry_invalid_external_party",
            "message": message,
            "workspace_id": workspace_id,
            "tenant_id": tenant_id,
        },
    )


def _build_external_party_approval_http_exception(message: str, *, party_id: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "error": "federated_metadata_registry_external_party_approval_failed",
            "message": message,
            "party_id": party_id,
        },
    )


def _build_invalid_access_grant_http_exception(message: str, *, party_id: str | None = None, target_kind: str | None = None, target_id: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": "federated_metadata_registry_invalid_access_grant",
            "message": message,
            "party_id": party_id,
            "target_kind": target_kind,
            "target_id": target_id,
        },
    )


@router.post(
    "/metadata-registry/push",
    response_model=FederatedMetadataRegistryPackageView,
    responses={
        200: {"description": "Build a federated metadata package from the local catalog."},
        400: {"description": "The request is invalid."},
        404: {"description": "A requested data product or registry definition was not found."},
        409: {"description": "A registry definition lookup was ambiguous."},
        503: {"description": "The registry definition resolver is unavailable."},
    },
)
async def push_metadata_registry_package(
    request: FederatedMetadataRegistryPushRequestView,
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    registry_definition_resolver: RegistryDefinitionResolver = Depends(get_registry_definition_resolver),
    federated_metadata_registry_repository: FederatedMetadataRegistryRepository = Depends(get_federated_metadata_registry_repository),
) -> FederatedMetadataRegistryPackageView:
    try:
        package = await build_federated_metadata_package(
            workspace_id=request.workspaceId,
            data_product_id=request.dataProductId,
            data_catalog_repository=data_catalog_repository,
            registry_definition_resolver=registry_definition_resolver,
        )
        snapshot = build_federated_metadata_registry_exchange_snapshot(
            package,
            exchange_kind="push",
            accepted=True,
            captured_by=get_user_id(),
            correlation_id=get_correlation_id(),
        )
        federated_metadata_registry_repository.record_federated_metadata_registry_exchange_snapshot(snapshot)
        return package
    except FederatedMetadataRegistryLookupError as exc:
        raise _build_lookup_http_exception(exc, request.workspaceId, request.dataProductId) from exc
    except ValueError as exc:
        raise _build_invalid_package_http_exception(str(exc)) from exc


@router.post(
    "/metadata-registry/pull",
    response_model=FederatedMetadataRegistryPullResultView,
    responses={
        200: {"description": "Validate a federated metadata package received from another party."},
        400: {"description": "The submitted package is invalid."},
    },
)
async def pull_metadata_registry_package(
    package: FederatedMetadataRegistryPackageView,
    federated_metadata_registry_repository: FederatedMetadataRegistryRepository = Depends(get_federated_metadata_registry_repository),
) -> FederatedMetadataRegistryPullResultView:
    try:
        result = build_federated_metadata_pull_result(package)
        snapshot = build_federated_metadata_registry_exchange_snapshot(
            result.package,
            exchange_kind="pull",
            accepted=result.accepted,
            captured_by=get_user_id(),
            correlation_id=get_correlation_id(),
        )
        federated_metadata_registry_repository.record_federated_metadata_registry_exchange_snapshot(snapshot)
        return result
    except ValueError as exc:
        snapshot = build_federated_metadata_registry_exchange_snapshot(
            package,
            exchange_kind="pull",
            accepted=False,
            validation_error=str(exc),
            captured_by=get_user_id(),
            correlation_id=get_correlation_id(),
        )
        federated_metadata_registry_repository.record_federated_metadata_registry_exchange_snapshot(snapshot)
        raise _build_invalid_package_http_exception(str(exc)) from exc


@router.post(
    "/metadata-registry/external-parties",
    response_model=FederatedMetadataRegistryExternalPartyView,
    responses={
        200: {"description": "Register or update an external party in the federated metadata registry."},
        400: {"description": "The request is invalid."},
    },
)
async def register_metadata_registry_external_party(
    request: FederatedMetadataRegistryExternalPartyRegistrationRequestView,
    federated_metadata_registry_repository: FederatedMetadataRegistryRepository = Depends(get_federated_metadata_registry_repository),
) -> FederatedMetadataRegistryExternalPartyView:
    try:
        party = build_federated_metadata_registry_external_party(
            request,
            registered_by=get_user_id(),
            correlation_id=get_correlation_id(),
        )
        stored_party = federated_metadata_registry_repository.record_federated_metadata_registry_external_party(party)
        return build_federated_metadata_registry_external_party_view(stored_party)
    except ValueError as exc:
        raise _build_invalid_external_party_http_exception(str(exc), workspace_id=request.workspaceId, tenant_id=request.tenantId) from exc


@router.post(
    "/metadata-registry/external-parties/{party_id}/access-grants",
    response_model=FederatedMetadataRegistryAccessGrantView,
    responses={
        200: {"description": "Grant a party access to a governed metadata target."},
        400: {"description": "The request is invalid."},
        404: {"description": "The external party was not found."},
        409: {"description": "The external party is not approved or the grant cannot be applied."},
    },
)
async def upsert_metadata_registry_access_grant(
    party_id: str,
    request: FederatedMetadataRegistryAccessGrantRequestView,
    federated_metadata_registry_repository: FederatedMetadataRegistryRepository = Depends(get_federated_metadata_registry_repository),
) -> FederatedMetadataRegistryAccessGrantView:
    parties = federated_metadata_registry_repository.list_federated_metadata_registry_external_parties(
        party_id=party_id,
        limit=1,
    )
    party = parties[0] if parties else None
    if party is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "federated_metadata_registry_external_party_not_found",
                "message": f"External party '{party_id}' was not found",
                "party_id": party_id,
            },
        )
    if str(party.approval_status or "").strip().lower() != "approved":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "federated_metadata_registry_external_party_not_approved",
                "message": f"External party '{party_id}' must be approved before access grants can be assigned",
                "party_id": party_id,
            },
        )

    try:
        grant = build_federated_metadata_registry_access_grant(
            request,
            external_party_id=party_id,
            granted_by=get_user_id(),
            correlation_id=get_correlation_id(),
        )
    except ValueError as exc:
        raise _build_invalid_access_grant_http_exception(
            str(exc),
            party_id=party_id,
            target_kind=getattr(request, "targetKind", None),
            target_id=getattr(request, "targetId", None),
        ) from exc

    stored_grant = federated_metadata_registry_repository.record_federated_metadata_registry_access_grant(grant)
    return build_federated_metadata_registry_access_grant_view(stored_grant)


@router.post(
    "/metadata-registry/external-parties/{party_id}/approve",
    response_model=FederatedMetadataRegistryExternalPartyView,
    responses={
        200: {"description": "Approve an external party in the federated metadata registry."},
        400: {"description": "The request is invalid."},
        404: {"description": "The external party was not found."},
        409: {"description": "The external party is not pending approval."},
    },
)
async def approve_metadata_registry_external_party(
    party_id: str,
    request: FederatedMetadataRegistryExternalPartyApprovalRequestView,
    federated_metadata_registry_repository: FederatedMetadataRegistryRepository = Depends(get_federated_metadata_registry_repository),
) -> FederatedMetadataRegistryExternalPartyView:
    parties = federated_metadata_registry_repository.list_federated_metadata_registry_external_parties(
        party_id=party_id,
        limit=1,
    )
    party = parties[0] if parties else None
    if party is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "federated_metadata_registry_external_party_not_found",
                "message": f"External party '{party_id}' was not found",
                "party_id": party_id,
            },
        )

    try:
        approved_party = build_federated_metadata_registry_external_party_approval(
            party,
            request,
            approved_by=get_user_id(),
        )
    except ValueError as exc:
        raise _build_external_party_approval_http_exception(str(exc), party_id=party_id) from exc

    stored_party = federated_metadata_registry_repository.record_federated_metadata_registry_external_party(approved_party)
    return build_federated_metadata_registry_external_party_view(stored_party)


@router.get(
    "/metadata-registry/access-grants",
    response_model=list[FederatedMetadataRegistryAccessGrantView],
    responses={
        200: {"description": "List access grants for governed metadata targets."},
        400: {"description": "The request is invalid."},
    },
)
async def list_metadata_registry_access_grants(
    party_id: str | None = Query(default=None),
    target_kind: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    federated_metadata_registry_repository: FederatedMetadataRegistryRepository = Depends(get_federated_metadata_registry_repository),
) -> list[FederatedMetadataRegistryAccessGrantView]:
    normalized_target_kind = str(target_kind or "").strip().lower() or None
    normalized_target_id = str(target_id or "").strip() or None
    if normalized_target_id is not None and normalized_target_kind is None:
        raise _build_invalid_access_grant_http_exception(
            "target_kind is required when target_id is provided",
            party_id=party_id,
            target_kind=target_kind,
            target_id=target_id,
        )
    if normalized_target_kind is not None and normalized_target_kind not in {"metadata_structure", "metadata_item"}:
        raise _build_invalid_access_grant_http_exception(
            "target_kind must be metadata_structure or metadata_item",
            party_id=party_id,
            target_kind=target_kind,
            target_id=target_id,
        )

    return [
        build_federated_metadata_registry_access_grant_view(grant)
        for grant in federated_metadata_registry_repository.list_federated_metadata_registry_access_grants(
            party_id=party_id,
            target_kind=normalized_target_kind,
            target_id=normalized_target_id,
            limit=limit,
        )
    ]


@router.get(
    "/metadata-registry/external-parties",
    response_model=list[FederatedMetadataRegistryExternalPartyView],
    responses={
        200: {"description": "List registered external parties."},
    },
)
async def list_metadata_registry_external_parties(
    party_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    approval_status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    federated_metadata_registry_repository: FederatedMetadataRegistryRepository = Depends(get_federated_metadata_registry_repository),
) -> list[FederatedMetadataRegistryExternalPartyView]:
    normalized_approval_status = str(approval_status or "").strip().lower() or None
    if normalized_approval_status is not None and normalized_approval_status not in {"pending", "approved", "rejected"}:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "federated_metadata_registry_invalid_approval_status",
                "message": "approval_status must be pending, approved, or rejected",
                "approval_status": approval_status,
            },
        )
    return [
        build_federated_metadata_registry_external_party_view(party)
        for party in federated_metadata_registry_repository.list_federated_metadata_registry_external_parties(
            party_id=party_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            approval_status=normalized_approval_status,
            limit=limit,
        )
    ]


@router.get(
    "/metadata-registry/exchanges",
    response_model=list[FederatedMetadataRegistryExchangeSnapshotView],
    responses={
        200: {"description": "List federated metadata exchange snapshots."},
    },
)
async def list_metadata_registry_exchanges(
    workspace_id: str | None = Query(default=None),
    data_product_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    federated_metadata_registry_repository: FederatedMetadataRegistryRepository = Depends(get_federated_metadata_registry_repository),
) -> list[FederatedMetadataRegistryExchangeSnapshotView]:
    return [
        FederatedMetadataRegistryExchangeSnapshotView.model_validate(snapshot)
        for snapshot in federated_metadata_registry_repository.list_federated_metadata_registry_exchange_snapshots(
            workspace_id=workspace_id,
            data_product_id=data_product_id,
            limit=limit,
        )
    ]