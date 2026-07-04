from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from pydantic import ConfigDict, Field

from app.domain.entities.base import EntityModel
from app.domain.entities.gx_run_plan import GxRunPlanScopeSelectorEntity
from app.domain.entities.gx_run_plan import build_gx_run_plan_scope_selector_entity
from app.domain.entities.validation_run_plan import build_validation_run_plan_scope_selector_entity


class DQPlanTemplateParameterEntity(EntityModel):
    """A parameter that can be substituted when instantiating a template."""
    
    model_config = ConfigDict(alias_generator="snake_alias", populate_by_name=True, extra="forbid")
    
    name: str = Field(..., description="Parameter name (e.g., 'dataset_name', 'min_pass_rate')")
    type: str = Field(default="string", description="Parameter type: string, int, float, bool, list, object")
    description: str | None = Field(default=None, description="Parameter description")
    required: bool = Field(default=True, description="Whether this parameter is required")
    default: Any | None = Field(default=None, description="Default value if not provided")
    allowed_values: list[Any] | None = Field(default=None, description="Allowed values (enum)")
    validation_regex: str | None = Field(default=None, description="Regex pattern for string validation")
    minimum: float | int | None = Field(default=None, description="Minimum value for numeric types")
    maximum: float | int | None = Field(default=None, description="Maximum value for numeric types")


class DQPlanTemplateConfigurationEntity(EntityModel):
    """Engine configuration for a template."""
    
    model_config = ConfigDict(alias_generator="snake_alias", populate_by_name=True, extra="forbid")
    
    engine_type: str = Field(default="gx", description="Default engine type")
    engine_target: str | None = Field(default=None, description="Engine target (e.g., 'pyspark', 'trino')")
    execution_shape: str | None = Field(default=None, description="Execution shape")
    batch_size: int | None = Field(default=None, description="Batch size for violations")
    flush_interval_seconds: float | None = Field(default=None, description="Flush interval for streaming")
    options: dict[str, Any] = Field(default_factory=dict, description="Additional engine options")


class DQPlanTemplateScopeEntity(EntityModel):
    """Template-level scope definition (can be parameterized)."""
    
    model_config = ConfigDict(alias_generator="snake_alias", populate_by_name=True, extra="allow")
    
    data_object_ids: list[str] | None = Field(default=None, description="Template data object IDs")
    dataset_ids: list[str] | None = Field(default=None, description="Template dataset IDs")
    data_product_ids: list[str] | None = Field(default=None, description="Template data product IDs")
    tag_ids: list[str] = Field(default_factory=list, description="Template tag filters")
    scope_selectors: dict[str, Any] = Field(default_factory=dict, description="Parameterized scope selectors")


class DQPlanTemplateSuiteEntity(EntityModel):
    """A suite (validation rules) within a template."""
    
    model_config = ConfigDict(alias_generator="snake_alias", populate_by_name=True, extra="allow")
    
    suite_id: str | None = Field(default=None, description="Reference to existing suite")
    suite_name: str | None = Field(default=None, description="Name for new suite")
    engine_type: str | None = Field(default=None, description="Engine type for this suite")
    rule_ids: list[str] | None = Field(default=None, description="Reference to rule IDs")
    rule_definitions: dict[str, Any] | None = Field(default=None, description="Inline rule definitions")
    configuration: dict[str, Any] = Field(default_factory=dict, description="Suite-specific config")


class DQPlanTemplateScheduleEntity(EntityModel):
    """Template-level schedule definition."""
    
    model_config = ConfigDict(alias_generator="snake_alias", populate_by_name=True, extra="forbid")
    
    schedule_type: str = Field(default="cron", description="Schedule type: cron, interval, once")
    cron_expression: str | None = Field(default=None, description="Cron expression")
    interval_seconds: int | None = Field(default=None, description="Interval in seconds")
    timezone: str = Field(default="UTC", description="Schedule timezone")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Schedule parameters")


class DQPlanTemplateEntity(EntityModel):
    """
    A reusable DQ Plan template that can be instantiated with different parameters.
    
    Templates provide:
    - Reusable validation logic (rules, suites)
    - Parameterized scope (datasets, data products)
    - Configurable execution settings
    - Standardized scheduling
    - Governance metadata
    """
    
    model_config = ConfigDict(alias_generator="snake_alias", populate_by_name=True)
    
    # Template identity
    template_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique template ID")
    template_name: str = Field(..., description="Display name for the template")
    template_description: str | None = Field(default=None, description="Template description")
    template_version: str = Field(default="1.0.0", description="Template version")
    
    # Metadata
    template_type: str = Field(default="data_quality", description="Template type: data_quality, profiling, reconciliation")
    domain: str | None = Field(default=None, description="Business domain (e.g., 'customer', 'transactions')")
    tags: list[str] = Field(default_factory=list, description="Tags for discovery")
    workspace_id: str | None = Field(default=None, description="Workspace ID")
    
    # Parameters
    parameters: list[DQPlanTemplateParameterEntity] = Field(default_factory=list, description="Template parameters")
    
    # Scope
    scope: DQPlanTemplateScopeEntity | None = Field(default=None, description="Template scope")
    
    # Suites (validations)
    suites: list[DQPlanTemplateSuiteEntity] = Field(default_factory=list, description="Validation suites")
    
    # Configuration
    configuration: DQPlanTemplateConfigurationEntity | None = Field(default=None, description="Engine configuration")
    
    # Schedule
    schedule: DQPlanTemplateScheduleEntity | None = Field(default=None, description="Default schedule")
    
    # Governance
    owner: str | None = Field(default=None, description="Template owner")
    approver: str | None = Field(default=None, description="Template approver")
    approved: bool = Field(default=False, description="Template approval status")
    approval_date: str | None = Field(default=None, description="Template approval date")
    
    # Lifecycle
    created_by: str | None = Field(default=None, description="Creator")
    created_at: str = Field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())
    updated_by: str | None = Field(default=None, description="Last updater")
    updated_at: str = Field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())
    is_active: bool = Field(default=True, description="Whether template is active")
    is_default: bool = Field(default=False, description="Whether this is the default version")


class DQPlanTemplateVersionEntity(EntityModel):
    """Version information for a template."""
    
    template_id: str
    template_version: str
    is_active: bool
    created_by: str | None
    created_at: str
    notes: str | None = Field(default=None, description="Version notes")


class InstantiateTemplateRequestEntity(EntityModel):
    """Request to instantiate a template into a new RunPlan."""
    
    model_config = ConfigDict(alias_generator="snake_alias", populate_by_name=True)
    
    template_id: str = Field(..., description="Template ID to instantiate")
    template_version: str | None = Field(default=None, description="Specific version to instantiate")
    plan_name: str | None = Field(default=None, description="Name for the new plan")
    plan_description: str | None = Field(default=None, description="Description for the new plan")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Parameter values for instantiation")
    scope_overrides: dict[str, Any] | None = Field(default=None, description="Override template scope")
    schedule_override: dict[str, Any] | None = Field(default=None, description="Override template schedule")
    configuration_overrides: dict[str, Any] | None = Field(default=None, description="Override engine config")


def build_dq_plan_template_parameter_entity(
    payload: Mapping[str, Any] | DQPlanTemplateParameterEntity | None,
) -> DQPlanTemplateParameterEntity | None:
    if isinstance(payload, DQPlanTemplateParameterEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    
    return DQPlanTemplateParameterEntity.model_validate(payload)


def build_dq_plan_template_configuration_entity(
    payload: Mapping[str, Any] | DQPlanTemplateConfigurationEntity | None,
) -> DQPlanTemplateConfigurationEntity | None:
    if isinstance(payload, DQPlanTemplateConfigurationEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    
    return DQPlanTemplateConfigurationEntity.model_validate(payload)


def build_dq_plan_template_scope_entity(
    payload: Mapping[str, Any] | DQPlanTemplateScopeEntity | None,
) -> DQPlanTemplateScopeEntity | None:
    if isinstance(payload, DQPlanTemplateScopeEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    
    return DQPlanTemplateScopeEntity.model_validate(payload)


def build_dq_plan_template_suite_entity(
    payload: Mapping[str, Any] | DQPlanTemplateSuiteEntity | None,
) -> DQPlanTemplateSuiteEntity | None:
    if isinstance(payload, DQPlanTemplateSuiteEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    
    return DQPlanTemplateSuiteEntity.model_validate(payload)


def build_dq_plan_template_schedule_entity(
    payload: Mapping[str, Any] | DQPlanTemplateScheduleEntity | None,
) -> DQPlanTemplateScheduleEntity | None:
    if isinstance(payload, DQPlanTemplateScheduleEntity):
        return payload
    if not isinstance(payload, Mapping):
        return None
    
    return DQPlanTemplateScheduleEntity.model_validate(payload)


def build_dq_plan_template_entity(payload: Mapping[str, Any] | DQPlanTemplateEntity) -> DQPlanTemplateEntity:
    if isinstance(payload, DQPlanTemplateEntity):
        return payload
    
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), list) else []
    suites = payload.get("suites") if isinstance(payload.get("suites"), list) else []
    
    return DQPlanTemplateEntity(
        template_id=str(payload.get("template_id") or str(uuid4())),
        template_name=str(payload.get("template_name") or ""),
        template_description=str(payload.get("template_description")) if payload.get("template_description") else None,
        template_version=str(payload.get("template_version") or "1.0.0"),
        template_type=str(payload.get("template_type") or "data_quality"),
        domain=(str(payload.get("domain")) if payload.get("domain") else None),
        tags=[str(t) for t in (payload.get("tags") or []) if str(t)],
        workspace_id=(str(payload.get("workspace_id")) if payload.get("workspace_id") else None),
        parameters=[
            build_dq_plan_template_parameter_entity(p)
            for p in parameters
            if build_dq_plan_template_parameter_entity(p)
        ],
        scope=build_dq_plan_template_scope_entity(payload.get("scope")),
        suites=[
            build_dq_plan_template_suite_entity(s)
            for s in suites
            if build_dq_plan_template_suite_entity(s)
        ],
        configuration=build_dq_plan_template_configuration_entity(payload.get("configuration")),
        schedule=build_dq_plan_template_schedule_entity(payload.get("schedule")),
        owner=(str(payload.get("owner")) if payload.get("owner") else None),
        approver=(str(payload.get("approver")) if payload.get("approver") else None),
        approved=bool(payload.get("approved")),
        approval_date=(str(payload.get("approval_date")) if payload.get("approval_date") else None),
        created_by=(str(payload.get("created_by")) if payload.get("created_by") else None),
        created_at=(str(payload.get("created_at")) if payload.get("created_at") else __import__('datetime').datetime.now().isoformat()),
        updated_by=(str(payload.get("updated_by")) if payload.get("updated_by") else None),
        updated_at=(str(payload.get("updated_at")) if payload.get("updated_at") else __import__('datetime').datetime.now().isoformat()),
        is_active=bool(payload.get("is_active", True)),
        is_default=bool(payload.get("is_default", False)),
    )


def build_instantiate_template_request_entity(
    payload: Mapping[str, Any] | InstantiateTemplateRequestEntity,
) -> InstantiateTemplateRequestEntity:
    if isinstance(payload, InstantiateTemplateRequestEntity):
        return payload
    return InstantiateTemplateRequestEntity.model_validate(payload)
