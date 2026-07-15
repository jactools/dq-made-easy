from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.v1.schemas import DQPlanTemplateView
from app.api.v1.schemas import InstantiateTemplateRequestSchema as InstantiateTemplateRequestView
from app.api.v1.schemas import InstantiateTemplateResultSchema as InstantiateTemplateResultView
from app.api.v1.schemas import DQPlanTemplateSchema
from app.application.services.dq_plan_template_service import DQPlanTemplateService
from app.application.services.dq_plan_template_service import DQPlanTemplateServiceError
from app.application.services.dq_plan_templates_builtin import get_builtin_templates
from app.core.config import get_settings
from app.core.dependencies import get_dq_plan_template_repository
from app.core.request_context import get_correlation_id
from app.core.request_context import get_user_id
from app.domain.entities import DQPlanTemplateEntity
from app.domain.entities import InstantiateTemplateRequestEntity
from app.domain.interfaces import DQPlanTemplateRepository

router = APIRouter(prefix="/dq-plan-templates", tags=["dq-plan-templates"])
_log = logging.getLogger(__name__)


@router.get("", response_model=list[DQPlanTemplateView], responses={200: {"description": "List of DQ plan templates."}})
async def list_templates(
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    domain: str | None = Query(default=None),
    template_type: str | None = Query(default=None, alias="templateType"),
    tags: str | None = Query(default=None),
    is_active: bool | None = Query(default=None, alias="isActive"),
    repository: DQPlanTemplateRepository = Depends(get_dq_plan_template_repository),
) -> list[DQPlanTemplateView]:
    """
    List DQ Plan templates with optional filters.
    
    Args:
        workspace_id: Filter by workspace
        domain: Filter by business domain
        template_type: Filter by template type
        tags: Comma-separated tags to filter by
        is_active: Filter by active status
    
    Returns:
        List of DQ Plan templates
    """
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    
    templates = await repository.list_templates(
        workspace_id=workspace_id,
        domain=domain,
        template_type=template_type,
        tags=tag_list,
        is_active=is_active,
    )
    
    return [DQPlanTemplateView.model_validate(t) for t in templates]


@router.get("/builtin", response_model=list[dict[str, Any]], responses={200: {"description": "Built-in templates."}})
async def list_builtin_templates() -> list[dict[str, Any]]:
    """Get built-in templates for common use cases."""
    return get_builtin_templates()


@router.get("/{template_id}", response_model=DQPlanTemplateView, responses={
    200: {"description": "Template found."},
    404: {"description": "Template not found."},
})
async def get_template(
    template_id: str,
    version: str | None = Query(default=None, alias="templateVersion"),
    repository: DQPlanTemplateRepository = Depends(get_dq_plan_template_repository),
) -> DQPlanTemplateView:
    """
    Get a specific template by ID.
    
    Args:
        template_id: Template ID
        version: Specific version to retrieve
    
    Returns:
        Template details
    """
    template = await repository.get_template(template_id, version=version)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    
    return DQPlanTemplateView.model_validate(template)


@router.post("", response_model=DQPlanTemplateView, status_code=201, responses={
    201: {"description": "Template created."},
    400: {"description": "Invalid template."},
})
async def create_template(
    request: Request,
    template: DQPlanTemplateSchema,
    repository: DQPlanTemplateRepository = Depends(get_dq_plan_template_repository),
) -> DQPlanTemplateView:
    """
    Create a new DQ Plan template.

    Args:
        template: Template definition (schema)

    Returns:
        Created template
    """
    try:
        # Convert schema to entity
        template_dict = template.model_dump(by_alias=True, exclude_none=True)
        entity = DQPlanTemplateEntity.model_validate(template_dict)
        
        service = DQPlanTemplateService(
            template_repository=repository,
            settings_provider=get_settings,
        )
        created = await service.create_template(entity)
        return DQPlanTemplateView.model_validate(created)
    except DQPlanTemplateServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.put("/{template_id}", response_model=DQPlanTemplateView, responses={
    200: {"description": "Template updated."},
    404: {"description": "Template not found."},
    400: {"description": "Invalid template."},
})
async def update_template(
    template_id: str,
    template: DQPlanTemplateSchema,
    repository: DQPlanTemplateRepository = Depends(get_dq_plan_template_repository),
) -> DQPlanTemplateView:
    """
    Update an existing template.

    Args:
        template_id: Template ID to update
        template: Updated template definition (schema)

    Returns:
        Updated template
    """
    try:
        # Convert schema to entity
        template_dict = template.model_dump(by_alias=True, exclude_none=True)
        entity = DQPlanTemplateEntity.model_validate(template_dict)
        
        service = DQPlanTemplateService(
            template_repository=repository,
            settings_provider=get_settings,
        )
        updated = await service.update_template(entity)
        return DQPlanTemplateView.model_validate(updated)
    except DQPlanTemplateServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.delete("/{template_id}", status_code=204, responses={
    204: {"description": "Template deleted."},
    404: {"description": "Template not found."},
})
async def delete_template(
    template_id: str,
    repository: DQPlanTemplateRepository = Depends(get_dq_plan_template_repository),
) -> None:
    """Delete a template."""
    try:
        service = DQPlanTemplateService(
            template_repository=repository,
            settings_provider=get_settings,
        )
        await service.delete_template(template_id)
    except DQPlanTemplateServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/{template_id}/instantiate", response_model=InstantiateTemplateResultView, status_code=201, responses={
    201: {"description": "Template instantiated into RunPlan."},
    400: {"description": "Invalid instantiation request."},
    404: {"description": "Template not found."},
})
async def instantiate_template(
    request: Request,
    template_id: str,
    payload: InstantiateTemplateRequestView,
    repository: DQPlanTemplateRepository = Depends(get_dq_plan_template_repository),
) -> InstantiateTemplateResultView:
    """
    Instantiate a template into a new RunPlan with parameter values.
    
    Args:
        template_id: Template to instantiate
        payload: Instantiation request with parameters
    
    Returns:
        Instantiation result with RunPlan ID
    """
    try:
        service = DQPlanTemplateService(
            template_repository=repository,
            settings_provider=get_settings,
        )
        
        request_entity = InstantiateTemplateRequestEntity(
            template_id=template_id,
            template_version=payload.templateVersion if hasattr(payload, 'templateVersion') else None,
            plan_name=payload.planName if hasattr(payload, 'planName') else None,
            plan_description=payload.planDescription if hasattr(payload, 'planDescription') else None,
            parameters=payload.parameters or {},
            scope_overrides=payload.scopeOverrides if hasattr(payload, 'scopeOverrides') else None,
            schedule_override=payload.scheduleOverride if hasattr(payload, 'scheduleOverride') else None,
            configuration_overrides=payload.configurationOverrides if hasattr(payload, 'configurationOverrides') else None,
        )
        
        result = await service.instantiate_template(request_entity)
        
        return InstantiateTemplateResultView(
            runPlanId=result.get("run_plan_id"),
            runPlanVersionId=result.get("run_plan_version_id"),
            templateId=result.get("template_id"),
            validationErrors=[
                {"field": e["field"], "message": e["message"]}
                for e in result.get("validation_errors", [])
            ],
        )
    except DQPlanTemplateServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/{template_id}/preview", response_model=dict[str, Any], responses={
    200: {"description": "Template preview."},
    404: {"description": "Template not found."},
})
async def preview_template_instantiation(
    template_id: str,
    request: Request,
    parameters: dict[str, Any] = Query(default_factory=dict, alias="parameters"),
    repository: DQPlanTemplateRepository = Depends(get_dq_plan_template_repository),
) -> dict[str, Any]:
    """
    Preview template instantiation without creating RunPlan.
    
    Args:
        template_id: Template to preview
        parameters: Parameter values
    
    Returns:
        Preview of what would be created
    """
    try:
        template = await repository.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
        
        # Validate parameters
        from app.application.services.dq_plan_template_validator import validate_template_parameters
        errors = validate_template_parameters(template, parameters)
        
        # Return preview structure
        return {
            "template_id": template_id,
            "template_name": template.template_name,
            "instantiated_plan": {
                "plan_name": f"{template.template_name} (Instantiated)",
                "suites_count": len(template.suites),
                "parameters_applied": parameters,
                "scope": template.scope,
            },
            "validation_errors": errors,
            "warnings": [],
        }
    except DQPlanTemplateServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
