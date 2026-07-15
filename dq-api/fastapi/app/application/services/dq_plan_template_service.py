from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.application.services.dq_plan_template_validator import (
    validate_template_parameters,
    validate_template_scope,
    validate_template_suites,
)
from app.domain.entities import DQPlanTemplateEntity, InstantiateTemplateRequestEntity
from app.domain.interfaces import DQPlanTemplateRepository


class DQPlanTemplateServiceError(RuntimeError):
    """Base exception for template service errors."""
    
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class DQPlanTemplateService:
    """Service for managing DQ Plan templates."""
    
    def __init__(
        self,
        template_repository: DQPlanTemplateRepository,
        settings_provider: Callable[[], Any],
    ):
        self._template_repository = template_repository
        self._settings_provider = settings_provider
    
    async def create_template(
        self,
        template: DQPlanTemplateEntity,
    ) -> DQPlanTemplateEntity:
        """Create a new template."""
        # Validate template
        self._validate_template(template)
        
        # Set default values
        if template.is_default is None:
            template.is_default = True
        if template.is_active is None:
            template.is_active = True
        
        # Create
        return await self._template_repository.create_template(template)
    
    async def get_template(
        self,
        template_id: str,
        version: str | None = None,
    ) -> DQPlanTemplateEntity | None:
        """Get a template by ID."""
        if version:
            return await self._template_repository.get_template_by_version(template_id, version)
        return await self._template_repository.get_template(template_id)
    
    async def list_templates(
        self,
        *,
        workspace_id: str | None = None,
        domain: str | None = None,
        template_type: str | None = None,
        tags: list[str] | None = None,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DQPlanTemplateEntity]:
        """List templates with filters."""
        return await self._template_repository.list_templates(
            workspace_id=workspace_id,
            domain=domain,
            template_type=template_type,
            tags=tags,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )
    
    async def update_template(
        self,
        template_id: str,
        updates: dict[str, Any],
    ) -> DQPlanTemplateEntity:
        """Update a template."""
        existing = await self._template_repository.get_template(template_id)
        if not existing:
            raise DQPlanTemplateServiceError(f"Template '{template_id}' not found", status_code=404)
        
        # Merge updates
        merged = {**existing.model_dump(by_alias=True, exclude_none=True), **updates}
        updated = DQPlanTemplateEntity.model_validate(merged)
        
        # Validate
        self._validate_template(updated)
        
        # Update
        return await self._template_repository.update_template(updated)
    
    async def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        return await self._template_repository.delete_template(template_id)
    
    async def instantiate_template(
        self,
        request: InstantiateTemplateRequestEntity,
    ) -> Mapping[str, Any]:
        """
        Instantiate a template into a new RunPlan with parameter values.
        
        Returns:
            Mapping with:
            - run_plan_id: ID of the created plan
            - run_plan_version_id: ID of the created version
            - template_id: Original template ID
            - parameters: Applied parameter values
            - validation_errors: Any errors during instantiation
        """
        result = {
            "run_plan_id": None,
            "run_plan_version_id": None,
            "template_id": request.template_id,
            "parameters": {},
            "validation_errors": [],
        }
        
        # Get template
        template = await self._template_repository.get_template(request.template_id)
        if not template:
            raise DQPlanTemplateServiceError(f"Template '{request.template_id}' not found", status_code=404)
        
        # Validate parameters
        param_errors = validate_template_parameters(template, request.parameters)
        if param_errors:
            result["validation_errors"].extend([
                {"field": e["field"], "message": e["message"]}
                for e in param_errors
            ])
            return result
        
        # Apply parameters to template
        instantiated = await self._instantiate_template(template, request.parameters)
        
        # Validate scope
        scope_errors = validate_template_scope(instantiated)
        if scope_errors:
            result["validation_errors"].extend([
                {"field": "scope", "message": e}
                for e in scope_errors
            ])
            return result
        
        # Validate suites
        suite_errors = validate_template_suites(instantiated)
        if suite_errors:
            result["validation_errors"].extend([
                {"field": "suites", "message": e}
                for e in suite_errors
            ])
            return result
        
        # Create RunPlan from instantiated template
        run_plan_id = await self._create_run_plan_from_instantiated(instantiated, request)
        result["run_plan_id"] = run_plan_id
        result["run_plan_version_id"] = f"{run_plan_id}-v1"
        
        return result
    
    async def _instantiate_template(
        self,
        template: DQPlanTemplateEntity,
        parameters: dict[str, Any],
    ) -> DQPlanTemplateEntity:
        """Apply parameters to template and resolve references."""
        from datetime import datetime, timezone
        
        # Deep copy template
        template_dict = template.model_dump(by_alias=True, exclude_none=True)
        instantiated = DQPlanTemplateEntity.model_validate(template_dict)
        
        # Apply parameters
        for param in template.parameters:
            if param.name in parameters:
                # Type conversion
                value = self._convert_parameter_value(parameters[param.name], param.type)
                
                # Replace in template
                if hasattr(instantiated, 'scope') and instantiated.scope:
                    if hasattr(instantiated.scope, 'scope_selectors'):
                        if param.name in instantiated.scope.scope_selectors:
                            instantiated.scope.scope_selectors[param.name] = value
                
                # Check if parameter is used in suite definitions
                if instantiated.suites:
                    for suite in instantiated.suites:
                        if suite.rule_definitions:
                            suite.rule_definitions = self._substitute_parameters(
                                suite.rule_definitions, parameters
                            )
        
        # Update timestamps
        instantiated.updated_at = datetime.now(timezone.utc).isoformat()
        
        return instantiated
    
    def _convert_parameter_value(self, value: Any, param_type: str) -> Any:
        """Convert parameter value to correct type."""
        if value is None:
            return None
        
        try:
            if param_type == "int":
                return int(value)
            elif param_type == "float":
                return float(value)
            elif param_type == "bool":
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ("true", "1", "yes", "on")
            elif param_type == "list":
                if isinstance(value, list):
                    return value
                if isinstance(value, str):
                    return [v.strip() for v in value.split(",") if v.strip()]
                return [value]
            elif param_type == "object":
                if isinstance(value, dict):
                    return value
                if isinstance(value, str):
                    return json.loads(value)
                return {"value": value}
            else:  # string
                return str(value)
        except (ValueError, TypeError) as e:
            raise DQPlanTemplateServiceError(
                f"Failed to convert parameter value: {e}",
                status_code=400
            )
    
    def _substitute_parameters(self, obj: Any, parameters: dict[str, Any]) -> Any:
        """Recursively substitute parameter references in object."""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                result[key] = self._substitute_parameters(value, parameters)
            return result
        elif isinstance(obj, list):
            return [self._substitute_parameters(item, parameters) for item in obj]
        elif isinstance(obj, str):
            # Check for parameter references like ${param_name}
            pattern = r'\$\{(\w+)\}'
            matches = re.findall(pattern, obj)
            if matches:
                substituted = obj
                for match in matches:
                    if match in parameters:
                        substituted = substituted.replace(f'${{{match}}}', str(parameters[match]))
                return substituted
            return obj
        else:
            return obj
    
    async def _create_run_plan_from_instantiated(
        self,
        instantiated: DQPlanTemplateEntity,
        request: InstantiateTemplateRequestEntity,
    ) -> str:
        """Create a RunPlan from an instantiated template."""
        from app.domain.entities import (
            GxRunPlanEntity,
            GxRunPlanVersionEntity,
        )
        from app.domain.interfaces import GxRunPlanRepository
        
        # Get repository via settings
        settings = self._settings_provider()
        run_plan_repo = getattr(settings, 'run_plan_repository', None)
        
        if not run_plan_repo:
            raise DQPlanTemplateServiceError("RunPlan repository not configured")
        
        # Create RunPlan
        plan_id = f"plan-{__import__('uuid').uuid4().hex[:12]}"
        
        # Build version
        version = GxRunPlanVersionEntity(
            runPlanVersionId=f"{plan_id}-v1",
            runPlanId=plan_id,
            governanceState="active",
            gxSuiteSelection={
                "selectionMode": "direct",
                "suites": [
                    {
                        "suite_id": s.suite_id,
                        "suite_name": s.suite_name,
                        "engine_type": s.engine_type,
                        "rule_ids": s.rule_ids,
                    }
                    for s in instantiated.suites
                    if s.suite_id or s.rule_ids
                ],
            },
            suiteSnapshot={
                "suites": [
                    {
                        "suite_id": s.suite_id,
                        "name": s.suite_name,
                        "config": s.configuration,
                    }
                    for s in instantiated.suites
                ],
            },
            scheduleDefinition=dict(instantiated.schedule) if instantiated.schedule else {},
            validationStatus="pending",
            effectiveFrom=datetime.now(timezone.utc).isoformat(),
            createdBy=request.parameters.get("_created_by"),
            createdAt=datetime.now(timezone.utc).isoformat(),
        )
        
        # Create plan
        plan = GxRunPlanEntity(
            runPlanId=plan_id,
            businessKey=plan_id,
            workspaceId=instantiated.workspace_id or request.parameters.get("workspace_id"),
            scopeSelector=dict(instantiated.scope) if instantiated.scope else {},
            planningMode="direct",
            currentActiveVersionId=f"{plan_id}-v1",
            status="active",
            createdBy=request.parameters.get("_created_by"),
            createdAt=datetime.now(timezone.utc).isoformat(),
            updatedAt=datetime.now(timezone.utc).isoformat(),
            versions=[version],
        )
        
        # Save
        await run_plan_repo.create_run_plan(plan)
        
        return plan_id
    
    def _validate_template(self, template: DQPlanTemplateEntity) -> None:
        """Validate template structure."""
        if not template.template_name:
            raise DQPlanTemplateServiceError("Template name is required", status_code=400)
        
        if not template.template_type:
            raise DQPlanTemplateServiceError("Template type is required", status_code=400)
        
        # Validate parameters have unique names
        param_names = [p.name for p in template.parameters]
        if len(param_names) != len(set(param_names)):
            raise DQPlanTemplateServiceError(
                "Template has duplicate parameter names",
                status_code=400
            )
        
        # Validate parameter references
        for param in template.parameters:
            if param.name and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', param.name):
                raise DQPlanTemplateServiceError(
                    f"Invalid parameter name: {param.name}",
                    status_code=400
                )
