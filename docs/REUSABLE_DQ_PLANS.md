# Reusable DQ Plan Templates

## Overview

This document describes the reusable DQ Plan template architecture that allows you to:

1. **Define** validation patterns once as templates
2. **Instantiate** templates with specific parameters for datasets
3. **Reuse** templates across workspaces, domains, and teams
4. **Version** templates for governance and audit

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DQ Plan Template                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Template (Reusable Definition)                      │   │
│  │  - Validation logic (rules/suites)                   │   │
│  │  - Parameterized scope                               │   │
│  │  - Configurable execution                            │   │
│  │  - Standard schedule                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                         ↓                                    │
│              ┌────────────────────────┐                      │
│              │  Instantiate           │ ← Parameters         │
│              │  with values           │                      │
│              └────────────┬───────────┘                      │
│                           ↓                                  │
│              ┌────────────────────────┐                      │
│              │  RunPlan (Instance)    │                      │
│              │  - Specific to dataset │                      │
│              │  - Ready to execute    │                      │
│              └────────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

## Key Concepts

### 1. Template (Reusable Definition)

A **DQPlanTemplate** contains:
- **Parameters**: Placeholders that get substituted during instantiation
- **Suites**: Validation rule groups
- **Scope**: Dataset filters (can be parameterized)
- **Configuration**: Engine settings
- **Schedule**: Default execution schedule

### 2. Instantiation

Creating a **RunPlan** from a template by:
- Providing parameter values
- Resolving references
- Creating a concrete execution plan

### 3. Parameter Substitution

Template references use `${param_name}` syntax:
```yaml
scope:
  dataset_ids: ["${dataset_name}"]

suites:
  - name: "freshness_check"
    config:
      max_hours: "${data_freshness_hours}"
```

## Built-in Templates

### Customer Data Quality

```yaml
template: customer-data-quality
domain: customer

parameters:
  - dataset_name: "customer_events"
  - min_pass_rate: 99.9
  - data_freshness_hours: 24

suites:
  - customer_required_fields
  - customer_format_validation
  - customer_referential_integrity
  - customer_uniqueness
  - customer_freshness
```

### Financial Transactions (BCBS 239)

```yaml
template: financial-transaction-quality
domain: financial
tags: [bcbs239, compliance]

parameters:
  - dataset_name: "transactions"
  - amount_column: "amount"
  - tolerance_percent: 0.01

suites:
  - transaction_completeness
  - transaction_accuracy
  - transaction_timeliness
  - transaction_uniqueness
  - transaction_reconciliation
```

### Data Delivery

```yaml
template: data-delivery-validation
domain: delivery

parameters:
  - pipeline_name: "etl_customers"
  - target_datasets: ["customers", "accounts"]
  - max_delay_minutes: 15

suites:
  - delivery_freshness
  - delivery_completeness
  - delivery_schema
```

## API Reference

### List Templates

```bash
GET /dq-plan-templates?workspaceId=ws-123&domain=customer&tags=pii,regulatory

Response:
[
  {
    "templateId": "tmpl-customer-dq",
    "templateName": "Customer Data Quality",
    "domain": "customer",
    "tags": ["customer", "pii", "regulatory"],
    "parameters": [
      {"name": "dataset_name", "type": "string", "required": true},
      {"name": "min_pass_rate", "type": "float", "required": false, "default": 99.9}
    ],
    "suites": ["customer_required_fields", "customer_format_validation"]
  }
]
```

### Get Template

```bash
GET /dq-plan-templates/tmpl-customer-dq?templateVersion=1.0.0

Response:
{
  "templateId": "tmpl-customer-dq",
  "templateName": "Customer Data Quality",
  "parameters": [
    {"name": "dataset_name", "type": "string", "required": true}
  ],
  "suites": [
    {
      "suiteId": "suite-123",
      "suiteName": "customer_required_fields",
      "ruleIds": ["customer_email_not_null", "customer_name_not_null"]
    }
  ],
  "scope": {
    "dataObjectIds": ["${dataset_name}"],
    "scopeSelectors": {"dataset_filter": "${dataset_name}"}
  },
  "schedule": {
    "scheduleType": "cron",
    "cronExpression": "0 2 * * *",
    "timezone": "UTC"
  }
}
```

### Create Template

```bash
POST /dq-plan-templates

Request:
{
  "templateName": "My Custom Template",
  "templateDescription": "Custom validation for my dataset",
  "templateType": "data_quality",
  "domain": "analytics",
  "parameters": [
    {
      "name": "dataset_name",
      "type": "string",
      "required": true
    },
    {
      "name": "threshold_percent",
      "type": "float",
      "required": false,
      "default": 95.0
    }
  ],
  "scope": {
    "dataObjectIds": ["${dataset_name}"]
  },
  "suites": [
    {
      "suiteName": "my_validation_suite",
      "engineType": "gx",
      "ruleIds": ["rule-123", "rule-456"]
    }
  ],
  "configuration": {
    "engineType": "gx",
    "engineTarget": "pyspark",
    "batchSize": 10000
  },
  "schedule": {
    "scheduleType": "cron",
    "cronExpression": "0 0 * * *",
    "timezone": "UTC"
  }
}
```

### Instantiate Template

```bash
POST /dq-plan-templates/tmpl-customer-dq/instantiate

Request:
{
  "planName": "Customer DQ - Production",
  "parameters": {
    "dataset_name": "customers_prod",
    "min_pass_rate": 99.5,
    "data_freshness_hours": 12,
    "enforce_pii_protection": true,
    "tags": ["production", "customer"]
  },
  "scopeOverrides": {
    "additional_filters": {"region": "US"}
  },
  "scheduleOverride": {
    "cronExpression": "0 */6 * * *"
  }
}

Response:
{
  "runPlanId": "plan-abc123",
  "runPlanVersionId": "plan-abc123-v1",
  "templateId": "tmpl-customer-dq",
  "validationErrors": []
}
```

### Preview Instantiation

```bash
GET /dq-plan-templates/tmpl-customer-dq/preview?parameters={"dataset_name": "customers_dev", "min_pass_rate": 99.0}

Response:
{
  "template_id": "tmpl-customer-dq",
  "instantiated_plan": {
    "plan_name": "Customer Data Quality (Instantiated)",
    "suites_count": 5,
    "parameters_applied": {
      "dataset_name": "customers_dev",
      "min_pass_rate": 99.0
    }
  },
  "validation_errors": [],
  "warnings": []
}
```

## CLI Usage

### List Available Templates

```bash
dq plan template list

# Output:
# ID                    NAME                          DOMAIN       STATUS
# tmpl-customer-dq      Customer Data Quality         customer     Active
# tmpl-financial-bcbs   Financial BCBS239             financial    Active
# tmpl-delivery         Data Delivery                 delivery     Active
```

### Create Plan from Template

```bash
dq plan create --template customer-data-quality \
  --parameters dataset_name=customers_prod \
               min_pass_rate=99.5 \
               data_freshness_hours=12 \
  --plan-name "Customer DQ - Production"
```

### Instantiate Template

```bash
dq plan instantiate \
  --template tmpl-customer-dq \
  --plan-name "Customer DQ - Production" \
  --parameters dataset_name=customers_prod,99.5,12
```

## Creating Custom Templates

### 1. Via API

```python
from app.domain.entities import DQPlanTemplateEntity, DQPlanTemplateParameterEntity, DQPlanTemplateSuiteEntity, DQPlanTemplateScopeEntity, DQPlanTemplateConfigurationEntity

template = DQPlanTemplateEntity(
    template_name="My Dataset Validation",
    template_description="Validation for my specific dataset",
    template_type="data_quality",
    domain="my_domain",
    tags=["custom", "myteam"],
    parameters=[
        DQPlanTemplateParameterEntity(
            name="dataset_name",
            type="string",
            required=True,
            description="Target dataset"
        ),
        DQPlanTemplateParameterEntity(
            name="custom_threshold",
            type="float",
            required=False,
            default=95.0,
            minimum=0,
            maximum=100
        )
    ],
    scope=DQPlanTemplateScopeEntity(
        data_object_ids=["${dataset_name}"],
        tag_ids=["${tags}"]
    ),
    suites=[
        DQPlanTemplateSuiteEntity(
            suite_name="custom_validation",
            engine_type="gx",
            rule_ids=["rule-123"],
            configuration={
                "threshold": "${custom_threshold}"
            }
        )
    ],
    configuration=DQPlanTemplateConfigurationEntity(
        engine_type="gx",
        engine_target="pyspark"
    ),
    schedule=None
)
```

### 2. Via YAML

Create a `template.yaml` file:

```yaml
template:
  name: "My Dataset Validation"
  description: "Custom validation template"
  type: "data_quality"
  domain: "my_domain"
  tags:
    - custom
    - myteam
  
  parameters:
    - name: dataset_name
      type: string
      required: true
  
    - name: custom_threshold
      type: float
      required: false
      default: 95.0
      minimum: 0
      maximum: 100
  
  scope:
    data_object_ids: ["${dataset_name}"]
    tag_ids: ["${tags}"]
  
  suites:
    - name: custom_validation
      engine_type: gx
      rule_ids:
        - rule-123
      configuration:
        threshold: "${custom_threshold}"
  
  configuration:
    engine_type: gx
    engine_target: pyspark
    batch_size: 10000
  
  schedule:
    schedule_type: cron
    cron_expression: "0 0 * * *"
    timezone: UTC
```

Then upload:

```bash
curl -X POST http://api:8000/dq-plan-templates \
  -H "Content-Type: application/json" \
  --data-binary @template.yaml
```

## Use Cases

### 1. Standardize Across Teams

```yaml
# Create organization-wide templates
templates:
  - customer_data_quality
  - financial_transactions
  - data_delivery

# Each team instantiates with their dataset
team_a: instantiate customer_data_quality with dataset_name=team_a_customers
team_b: instantiate customer_data_quality with dataset_name=team_b_customers
```

### 2. Environment-Specific Execution

```yaml
# Same template, different parameters
dev: instantiate with min_pass_rate=90.0, data_freshness_hours=48
staging: instantiate with min_pass_rate=95.0, data_freshness_hours=24
prod: instantiate with min_pass_rate=99.9, data_freshness_hours=6
```

### 3. Progressive Rollout

```yaml
# Template versioning
v1.0: Basic validation
v2.0: Added PII protection (current)
v3.0: In progress - BCBS239 compliance

# Migrate plans to new version
plan-123: update_template_version from v2.0 to v3.0
```

### 4. Cross-Data-Object Validation

```yaml
scope:
  data_product_ids: ["data-product-xyz"]
  tag_ids: ["critical", "pii"]

# Instantiates for ALL datasets matching the filter
# Useful for enterprise-wide validation
```

## Best Practices

### 1. Template Design

- **Keep it focused**: One template per domain/use case
- **Use clear parameter names**: `dataset_name`, not `ds_nm`
- **Document parameters**: Add descriptions for all parameters
- **Set sensible defaults**: Provide reasonable defaults for optional parameters
- **Validate parameters**: Use regex, min/max, allowed_values

### 2. Parameter Strategy

```yaml
# REQUIRED parameters (must be provided)
- name: dataset_name
  type: string
  required: true

# OPTIONAL parameters with defaults
- name: min_pass_rate
  type: float
  required: false
  default: 95.0

# COMPLEX parameters
- name: custom_rules
  type: object
  required: false
  default: {}
```

### 3. Scope Resolution

```yaml
# Flexible scope with fallbacks
scope:
  data_object_ids: ["${dataset_name}"]
  tag_ids: ["${tags}", "pii"]  # Multiple filters
  
  # Advanced: scope selectors for dynamic filtering
  scope_selectors:
    dataset_filter: "${dataset_name}"
    tag_filter: "${tags}"
```

### 4. Suite Configuration

```yaml
suites:
  - name: required_fields
    engine_type: gx
    rule_ids: ["field_not_null_*"]
    configuration:
      severity: "error"
      fail_on_empty: true
  
  - name: format_checks
    engine_type: gx
    rule_ids: ["format_*"]
    configuration:
      severity: "warning"
      allow_non_matching: 5  # Allow some failures
```

### 5. Schedule Optimization

```yaml
# Use appropriate schedule for data freshness needs
schedule:
  # Real-time
  schedule_type: cron
  cron_expression: "*/5 * * * *"  # Every 5 minutes
  
  # Batch
  schedule_type: cron
  cron_expression: "0 2 * * *"  # Daily at 2 AM
  
  # Event-driven
  schedule_type: interval
  interval_seconds: 3600  # Every hour
```

## Template Repository

### Create a Repository

Implement the `DQPlanTemplateRepository` interface:

```python
from app.domain.interfaces import DQPlanTemplateRepository
from app.domain.entities import DQPlanTemplateEntity

class PostgresDQPlanTemplateRepository(DQPlanTemplateRepository):
    async def create_template(self, template: DQPlanTemplateEntity) -> DQPlanTemplateEntity:
        # Save to database
        pass
    
    async def get_template(self, template_id: str, version: str | None = None) -> DQPlanTemplateEntity | None:
        # Retrieve template
        pass
    
    async def list_templates(self, **filters) -> list[DQPlanTemplateEntity]:
        # List with filters
        pass
    
    async def update_template(self, template_id: str, updates: dict) -> DQPlanTemplateEntity:
        # Update template
        pass
    
    async def delete_template(self, template_id: str) -> bool:
        # Delete template
        pass
```

### Register Repository

```python
# In app/core/config.py
settings.dq_plan_template_repository = PostgresDQPlanTemplateRepository(database_url)

# In app/core/dependencies.py
def get_dq_plan_template_repository() -> DQPlanTemplateRepository:
    return get_settings().dq_plan_template_repository
```

## Migration Guide

### From RunPlan to Template

1. **Identify common patterns** in existing RunPlans
2. **Extract parameters** that vary between instances
3. **Create template** with parameterized scope
4. **Test instantiation** with different values
5. **Update existing plans** to reference template

### Example Migration

```yaml
# Old: Separate plans for each dataset
plan-customers-prod: dataset=customers_prod
plan-customers-staging: dataset=customers_staging
plan-customers-dev: dataset=customers_dev

# New: Single template
template-customers: dataset=${env_dataset}

# Instantiations:
template-customers/instantiate(dataset=customers_prod)  # → plan-customers-prod
template-customers/instantiate(dataset=customers_staging)  # → plan-customers-staging
```

## Troubleshooting

### Issue: Parameter substitution fails

**Cause**: Parameter name mismatch or missing required parameter

**Solution**:
```bash
# Check template parameters
GET /dq-plan-templates/{id}

# Verify all required parameters are provided
POST /dq-plan-templates/{id}/instantiate \
  --parameters "dataset_name=my_dataset,min_pass_rate=99.0"
```

### Issue: Scope resolution fails

**Cause**: Scope filters don't match any datasets

**Solution**:
```bash
# Preview scope resolution
GET /dq-plan-templates/{id}/preview?parameters={"dataset_name":"my_dataset"}

# Check available datasets
GET /data-catalog/v1/data-objects?workspaceId={ws}
```

### Issue: Template validation errors

**Cause**: Invalid parameter values or configuration

**Solution**:
```bash
# Validate template structure
POST /dq-plan-templates \
  -H "Content-Type: application/json" \
  -d @template.json  # Returns validation errors
```

## Future Enhancements

1. **Template Libraries**: Share templates across organizations
2. **Template Marketplace**: Community-contributed templates
3. **Template Testing**: Test templates against sample data
4. **Template Analytics**: Track usage and performance
5. **Template Dependencies**: Templates that depend on other templates
6. **Template CI/CD**: Version-controlled template pipelines
7. **Template Approval**: Governance workflow for template changes

## References

- [API Documentation](../dq-api/fastapi/app/api/v1/endpoints/dq_plan_templates.py)
- [Service Implementation](../dq-api/fastapi/app/application/services/dq_plan_template_service.py)
- [Built-in Templates](../dq-api/fastapi/app/application/services/dq_plan_templates_builtin.py)
- [Template Repository Interface](../dq-api/fastapi/app/domain/interfaces/)

---

**Version**: 1.0.0  
**Last Updated**: 2026-07-04  
**Status**: Production Ready
