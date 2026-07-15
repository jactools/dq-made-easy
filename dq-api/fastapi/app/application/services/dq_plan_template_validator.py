from collections.abc import Mapping
from typing import Any

from app.domain.entities import DQPlanTemplateEntity


def validate_template_parameters(
    template: DQPlanTemplateEntity,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate that provided parameters match template requirements."""
    errors = []
    
    # Check required parameters
    for param in template.parameters:
        if param.required and param.name not in parameters:
            errors.append({
                "field": param.name,
                "message": f"Required parameter '{param.name}' is missing",
            })
            continue
        
        if param.name not in parameters:
            continue
        
        value = parameters[param.name]
        
        # Type validation
        type_error = _validate_parameter_type(param, value)
        if type_error:
            errors.append(type_error)
            continue
        
        # Enum validation
        if param.allowed_values is not None and value not in param.allowed_values:
            errors.append({
                "field": param.name,
                "message": f"Value '{value}' is not in allowed values: {param.allowed_values}",
            })
        
        # Regex validation
        if param.validation_regex is not None:
            import re
            if not re.match(param.validation_regex, str(value)):
                errors.append({
                    "field": param.name,
                    "message": f"Value '{value}' does not match pattern '{param.validation_regex}'",
                })
        
        # Numeric range validation
        if param.minimum is not None and isinstance(value, (int, float)):
            if value < param.minimum:
                errors.append({
                    "field": param.name,
                    "message": f"Value {value} is below minimum {param.minimum}",
                })
        
        if param.maximum is not None and isinstance(value, (int, float)):
            if value > param.maximum:
                errors.append({
                    "field": param.name,
                    "message": f"Value {value} is above maximum {param.maximum}",
                })
    
    return errors


def validate_template_scope(template: DQPlanTemplateEntity) -> list[str]:
    """Validate template scope configuration."""
    errors = []
    
    if not template.scope:
        return errors
    
    scope = template.scope
    
    # At least one scope selector should be defined
    has_scope = (
        scope.data_object_ids or
        scope.dataset_ids or
        scope.data_product_ids or
        scope.tag_ids or
        scope.scope_selectors
    )
    
    if not has_scope:
        errors.append("Template scope must define at least one selector")
    
    return errors


def validate_template_suites(template: DQPlanTemplateEntity) -> list[str]:
    """Validate template suite definitions."""
    errors = []
    
    if not template.suites:
        errors.append("Template must have at least one suite")
        return errors
    
    for idx, suite in enumerate(template.suites):
        suite_errors = []
        
        # Suite must have either rule_ids or rule_definitions
        if not suite.rule_ids and not suite.rule_definitions:
            suite_errors.append(f"Suite {idx}: must define rule_ids or rule_definitions")
        
        # Check for valid engine type
        if suite.engine_type and not _is_valid_engine_type(suite.engine_type):
            suite_errors.append(f"Suite {idx}: invalid engine_type '{suite.engine_type}'")
        
        if suite_errors:
            errors.extend(suite_errors)
    
    return errors


def _validate_parameter_type(param, value: Any) -> dict[str, str] | None:
    """Validate parameter value matches parameter type."""
    param_type = param.type
    
    try:
        if param_type == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                return {
                    "field": param.name,
                    "message": f"Parameter '{param.name}' must be an integer",
                }
        elif param_type == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return {
                    "field": param.name,
                    "message": f"Parameter '{param.name}' must be a number",
                }
        elif param_type == "bool":
            if not isinstance(value, bool):
                return {
                    "field": param.name,
                    "message": f"Parameter '{param.name}' must be a boolean",
                }
        elif param_type == "list":
            if not isinstance(value, list):
                return {
                    "field": param.name,
                    "message": f"Parameter '{param.name}' must be a list",
                }
        elif param_type == "object":
            if not isinstance(value, (dict, Mapping)):
                return {
                    "field": param.name,
                    "message": f"Parameter '{param.name}' must be an object",
                }
        elif param_type == "string":
            if not isinstance(value, str):
                return {
                    "field": param.name,
                    "message": f"Parameter '{param.name}' must be a string",
                }
    except Exception as e:
        return {
            "field": param.name,
            "message": f"Error validating parameter '{param.name}': {str(e)}",
        }
    
    return None


def _is_valid_engine_type(engine_type: str) -> bool:
    """Check if engine type is valid."""
    valid_types = {"gx", "soda", "spark_expectations", "trino", "sql"}
    return engine_type.lower() in valid_types
