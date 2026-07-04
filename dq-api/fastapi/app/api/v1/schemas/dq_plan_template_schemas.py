from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict, Field

from app.schemas.pydantic_base import BaseSchema
from app.schemas.pydantic_base import to_snake_alias


class DQPlanTemplateParameterSchema(BaseSchema):
    """Schema for template parameter definition."""
    
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)
    
    name: str
    type: str = "string"
    description: str | None = None
    required: bool = True
    default: Any = None
    allowed_values: list[Any] | None = None
    validation_regex: str | None = None
    minimum: float | int | None = None
    maximum: float | int | None = None


class DQPlanTemplateSchema(BaseSchema):
    """Schema for DQ Plan template."""
    
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)
    
    template_id: str
    template_name: str
    template_description: str | None = None
    template_version: str = "1.0.0"
    template_type: str = "data_quality"
    domain: str | None = None
    tags: list[str] = Field(default_factory=list)
    workspace_id: str | None = None
    
    parameters: list[DQPlanTemplateParameterSchema] = Field(default_factory=list)
    scope: dict[str, Any] | None = None
    suites: list[dict[str, Any]] = Field(default_factory=list)
    configuration: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None
    
    owner: str | None = None
    approver: str | None = None
    approved: bool = False
    approval_date: str | None = None
    
    created_by: str | None = None
    created_at: str | None = None
    updated_by: str | None = None
    updated_at: str | None = None
    is_active: bool = True
    is_default: bool = False


class InstantiateTemplateRequestSchema(BaseSchema):
    """Schema for template instantiation request."""
    
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)
    
    plan_name: str | None = None
    plan_description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    scope_overrides: dict[str, Any] | None = None
    schedule_override: dict[str, Any] | None = None
    configuration_overrides: dict[str, Any] | None = None


class InstantiateTemplateResultSchema(BaseSchema):
    """Schema for template instantiation result."""
    
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)
    
    run_plan_id: str | None = None
    run_plan_version_id: str | None = None
    template_id: str
    validation_errors: list[dict[str, str]] = Field(default_factory=list)


class DQPlanTemplateView(BaseSchema):
    """View schema for DQ Plan template (read-only)."""
    
    model_config = ConfigDict(alias_generator=to_snake_alias, populate_by_name=True)
    
    template_id: str
    template_name: str
    template_description: str | None = None
    template_version: str
    template_type: str
    domain: str | None = None
    tags: list[str] = Field(default_factory=list)
    workspace_id: str | None = None
    
    parameters: list[DQPlanTemplateParameterSchema] = Field(default_factory=list)
    suites_count: int = 0
    created_at: str | None = None
    is_active: bool = True
    is_default: bool = False
