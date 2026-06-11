"""API routes for onboarding feature."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException

from app.application.services.onboarding_service import OnboardingService
from app.core.auth import has_required_scope
from app.core.dependencies import (
    get_data_asset_repository,
    get_data_catalog_repository,
    get_rules_repository,
)
from app.core.request_context import get_user_id, get_scopes
from app.core.log_event import log_event
from app.core.request_context import get_correlation_id
from app.domain.entities.onboarding_models import (
    CreateBatchRequest,
    CreateBatchResponse,
    GenerateProposalsRequest,
    GenerateProposalsResponse,
    ScopeSummaryRequest,
)
from app.domain.interfaces import DataAssetRepository, DataCatalogRepository, RulesRepository
from app.schemas.pydantic_base import SnakeModel

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _is_workspace_authorized(scopes: list[str], workspace_id: str) -> bool:
    normalized_workspace_id = str(workspace_id or "").strip()
    normalized_scopes = [str(scope).strip() for scope in scopes if str(scope).strip()]

    if normalized_workspace_id and f"workspace:{normalized_workspace_id}" in normalized_scopes:
        return True

    return has_required_scope(
        normalized_scopes,
        ["dq:workspace:read", "dq:workspace:manage", "dq:rules:read", "dq:rules:write"],
    )


class GenerateProposalsRequestSchema(SnakeModel):
    """Request schema for generate-proposals endpoint."""

    scope_type: str  # workspace | product | dataset | object
    scope_id: str
    workspace_id: str


class GenerateProposalsResponseSchema(SnakeModel):
    """Response schema for generate-proposals endpoint."""

    scope_type: str
    scope_id: str
    total_attributes: int
    total_proposals: int
    proposals: list[dict]  # Flatten to dict for JSON serialization
    generated_at: str


class CreateBatchRequestSchema(SnakeModel):
    """Request schema for create-batch endpoint."""

    workspace_id: str
    accepted_proposal_ids: list[str]


class CreateBatchResponseSchema(SnakeModel):
    """Response schema for create-batch endpoint."""

    batch_id: str
    workspace_id: str
    total_accepted: int
    created: int
    skipped: int
    failed: int
    outcomes: list[dict]
    created_at: str


class ScopeSummaryResponseSchema(SnakeModel):
    """Response schema for scope-summary endpoint."""

    scope_type: str
    scope_id: str
    workspace_id: str
    object_count: int
    attribute_count: int
    generated_at: str


@router.post("/generate-proposals")
async def generate_proposals(
    request: GenerateProposalsRequestSchema,
    user_id: str = Depends(get_user_id),
    scopes: list[str] = Depends(get_scopes),
    correlation_id: str = Depends(get_correlation_id),
    data_asset_repository: DataAssetRepository = Depends(
        get_data_asset_repository,
    ),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> GenerateProposalsResponseSchema:
    """Generate rule proposals for the given scope.
    
    - **scope_type**: One of: workspace, product, dataset, object
    - **scope_id**: The ID of the scope (workspace ID, product ID, dataset ID, or data object version ID)
    - **workspace_id**: The workspace context
    
    Returns a grouped proposal tree with proposals grouped by template type,
    then by dataset, then by data object.
    
    Fail-fast behavior:
    - 400 if scope does not exist
    - 401 if user lacks access to workspace
    - 503 if metadata or rules service is unavailable (with correlation_id)
    """
    # Validate workspace access
    if not _is_workspace_authorized(scopes, request.workspace_id):
        _log.warning(
            "User attempted to access workspace without permission",
            extra={
                "user_id": user_id,
                "workspace_id": request.workspace_id,
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(status_code=401, detail="Unauthorized for workspace")

    # Validate scope_type
    valid_scopes = {"workspace", "product", "dataset", "object"}
    if request.scope_type not in valid_scopes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scope_type: {request.scope_type}. Must be one of: {', '.join(valid_scopes)}",
        )

    try:
        # Create service and generate proposals
        service = OnboardingService(
            data_asset_repository=data_asset_repository,
            data_catalog_repository=data_catalog_repository,
            rules_repository=rules_repository,
        )

        proposal_request = GenerateProposalsRequest(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            workspace_id=request.workspace_id,
        )

        response = await service.generate_proposals(request=proposal_request)

        log_event(
            _log,
            "onboarding.proposals_generated",
            user_id=user_id,
            workspace_id=request.workspace_id,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            total_attributes=response.total_attributes,
            total_proposals=response.total_proposals,
            correlation_id=correlation_id,
        )

        # Serialize proposals to dict for JSON response
        proposals_dict = []
        for template_group in response.proposals:
            by_dataset_dict = {}
            for dataset_id, object_groups in template_group.by_dataset.items():
                by_dataset_dict[dataset_id] = [
                    {
                        "data_object_version_id": og.data_object_version_id,
                        "object_name": og.object_name,
                        "dataset_name": og.dataset_name,
                        "dataset_id": og.dataset_id,
                        "count": og.count,
                        "attributes": [
                            {
                                "attribute_id": attr.attribute_id,
                                "name": attr.name,
                                "data_type": attr.data_type,
                                "already_covered": attr.already_covered,
                            }
                            for attr in og.attributes
                        ],
                    }
                    for og in object_groups
                ]
            
            proposals_dict.append(
                {
                    "template_id": template_group.template_id,
                    "template_name": template_group.template_name,
                    "dimension": template_group.dimension,
                    "check_type": template_group.check_type,
                    "total_count": template_group.total_count,
                    "by_dataset": by_dataset_dict,
                }
            )

        return GenerateProposalsResponseSchema(
            scope_type=response.scope_type,
            scope_id=response.scope_id,
            total_attributes=response.total_attributes,
            total_proposals=response.total_proposals,
            proposals=proposals_dict,
            generated_at=response.generated_at.isoformat(),
        )

    except ValueError as e:
        # Scope does not exist or invalid
        _log.warning(
            f"Invalid onboarding scope: {e}",
            extra={
                "user_id": user_id,
                "scope_type": request.scope_type,
                "scope_id": request.scope_id,
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        # Service unavailable (e.g., metadata or rules service)
        _log.exception(
            "Onboarding proposal generation failed",
            extra={
                "user_id": user_id,
                "workspace_id": request.workspace_id,
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "proposal_generation_failed",
                "message": "Onboarding service temporarily unavailable",
                "correlation_id": correlation_id,
            },
        )


@router.post("/scope-summary", response_model=ScopeSummaryResponseSchema)
async def scope_summary(
    request: GenerateProposalsRequestSchema,
    user_id: str = Depends(get_user_id),
    scopes: list[str] = Depends(get_scopes),
    correlation_id: str = Depends(get_correlation_id),
    data_asset_repository: DataAssetRepository = Depends(
        get_data_asset_repository,
    ),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> ScopeSummaryResponseSchema:
    """Return object/attribute counts for the selected onboarding scope."""
    if not _is_workspace_authorized(scopes, request.workspace_id):
        _log.warning(
            "User attempted to access workspace summary without permission",
            extra={
                "user_id": user_id,
                "workspace_id": request.workspace_id,
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(status_code=401, detail="Unauthorized for workspace")

    valid_scopes = {"workspace", "product", "dataset", "object"}
    if request.scope_type not in valid_scopes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scope_type: {request.scope_type}. Must be one of: {', '.join(valid_scopes)}",
        )

    try:
        service = OnboardingService(
            data_asset_repository=data_asset_repository,
            data_catalog_repository=data_catalog_repository,
            rules_repository=rules_repository,
        )
        summary = await service.summarize_scope(
            request=ScopeSummaryRequest(
                scope_type=request.scope_type,
                scope_id=request.scope_id,
                workspace_id=request.workspace_id,
            )
        )

        return ScopeSummaryResponseSchema(
            scope_type=summary.scope_type,
            scope_id=summary.scope_id,
            workspace_id=summary.workspace_id,
            object_count=summary.object_count,
            attribute_count=summary.attribute_count,
            generated_at=summary.generated_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        _log.exception(
            "Onboarding scope summary failed",
            extra={
                "user_id": user_id,
                "workspace_id": request.workspace_id,
                "scope_type": request.scope_type,
                "scope_id": request.scope_id,
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "scope_summary_failed",
                "message": "Onboarding scope summary is temporarily unavailable",
                "correlation_id": correlation_id,
            },
        )


@router.post("/create-batch")
async def create_batch(
    request: CreateBatchRequestSchema,
    user_id: str = Depends(get_user_id),
    scopes: list[str] = Depends(get_scopes),
    correlation_id: str = Depends(get_correlation_id),
    data_asset_repository: DataAssetRepository = Depends(get_data_asset_repository),
    data_catalog_repository: DataCatalogRepository = Depends(get_data_catalog_repository),
    rules_repository: RulesRepository = Depends(get_rules_repository),
) -> CreateBatchResponseSchema:
    """Create onboarding draft rules for selected proposal IDs."""
    if not _is_workspace_authorized(scopes, request.workspace_id):
        _log.warning(
            "User attempted to create onboarding batch without workspace permission",
            extra={
                "user_id": user_id,
                "workspace_id": request.workspace_id,
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(status_code=401, detail="Unauthorized for workspace")

    try:
        service = OnboardingService(
            data_asset_repository=data_asset_repository,
            data_catalog_repository=data_catalog_repository,
            rules_repository=rules_repository,
        )
        response = await service.create_rule_batch(
            request=CreateBatchRequest(
                workspace_id=request.workspace_id,
                accepted_proposal_ids=request.accepted_proposal_ids,
            ),
            actor_id=user_id,
        )

        log_event(
            _log,
            "onboarding.batch_created",
            user_id=user_id,
            workspace_id=request.workspace_id,
            batch_id=response.batch_id,
            total_accepted=response.total_accepted,
            rules_created=response.created,
            rules_skipped=response.skipped,
            rules_failed=response.failed,
            correlation_id=correlation_id,
        )

        outcomes = [
            {
                "proposal_id": outcome.proposal_id,
                "status": outcome.status,
                "rule_id": outcome.rule_id,
                "reason": outcome.reason,
            }
            for outcome in response.outcomes
        ]

        return CreateBatchResponseSchema(
            batch_id=response.batch_id,
            workspace_id=response.workspace_id,
            total_accepted=response.total_accepted,
            created=response.created,
            skipped=response.skipped,
            failed=response.failed,
            outcomes=outcomes,
            created_at=response.created_at.isoformat(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception:
        _log.exception(
            "Onboarding batch creation failed",
            extra={
                "user_id": user_id,
                "workspace_id": request.workspace_id,
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "batch_creation_failed",
                "message": "Onboarding batch creation is temporarily unavailable",
                "correlation_id": correlation_id,
            },
        )
