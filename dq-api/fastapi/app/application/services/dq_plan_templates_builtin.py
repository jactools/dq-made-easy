"""Built-in DQ Plan templates for common validation scenarios.

These templates provide ready-to-use validation patterns that can be
instantiated with different parameters for specific datasets.
"""

from collections.abc import Mapping
from typing import Any

from app.domain.entities import (
    DQPlanTemplateEntity,
    DQPlanTemplateParameterEntity,
    DQPlanTemplateSuiteEntity,
    DQPlanTemplateConfigurationEntity,
    DQPlanTemplateScopeEntity,
    DQPlanTemplateScheduleEntity,
)


def create_customer_data_quality_template() -> DQPlanTemplateEntity:
    """
    Customer Data Quality Template
    
    Validates customer data for:
    - Required fields
    - Format validation (email, phone, etc.)
    - Referential integrity
    - Duplicate detection
    - Data freshness
    """
    return DQPlanTemplateEntity(
        template_name="Customer Data Quality",
        template_description="Comprehensive validation for customer data including required fields, format checks, referential integrity, and freshness",
        template_version="1.0.0",
        template_type="data_quality",
        domain="customer",
        tags=["customer", "pivotal", "regulatory", "pii"],
        parameters=[
            DQPlanTemplateParameterEntity(
                name="dataset_name",
                type="string",
                description="Target dataset/table name",
                required=True,
            ),
            DQPlanTemplateParameterEntity(
                name="min_pass_rate",
                type="float",
                description="Minimum acceptable pass rate (0-100)",
                required=False,
                default=99.9,
                minimum=0,
                maximum=100,
            ),
            DQPlanTemplateParameterEntity(
                name="data_freshness_hours",
                type="int",
                description="Maximum age of data in hours",
                required=False,
                default=24,
                minimum=1,
            ),
            DQPlanTemplateParameterEntity(
                name="enforce_pii_protection",
                type="bool",
                description="Enable PII protection checks",
                required=False,
                default=True,
            ),
            DQPlanTemplateParameterEntity(
                name="tags",
                type="list",
                description="Filter by tags (comma-separated)",
                required=False,
                default=[],
            ),
        ],
        scope=DQPlanTemplateScopeEntity(
            data_object_ids=["${dataset_name}"],
            tag_ids="${tags}",
            scope_selectors={
                "dataset_filter": "${dataset_name}",
                "tag_filter": "${tags}",
            },
        ),
        suites=[
            DQPlanTemplateSuiteEntity(
                suite_name="customer_required_fields",
                engine_type="gx",
                rule_ids=["customer_email_not_null", "customer_name_not_null", "customer_account_id_not_null"],
                configuration={
                    "severity": "error",
                    "fail_on_empty": True,
                },
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="customer_format_validation",
                engine_type="gx",
                rule_ids=["customer_email_format", "customer_phone_format", "customer_zip_format"],
                configuration={
                    "severity": "warning",
                    "allow_non_matching": 5,
                },
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="customer_referential_integrity",
                engine_type="gx",
                rule_ids=["customer_account_exists", "customer_segment_exists"],
                configuration={
                    "severity": "error",
                    "on_violation": "quarantine",
                },
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="customer_uniqueness",
                engine_type="gx",
                rule_ids=["customer_email_unique", "customer_phone_unique"],
                configuration={
                    "severity": "error",
                    "duplicate_action": "flag",
                },
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="customer_freshness",
                engine_type="gx",
                rule_ids=["customer_updated_recently"],
                configuration={
                    "severity": "warning",
                    "threshold_hours": "${data_freshness_hours}",
                },
            ),
        ],
        configuration=DQPlanTemplateConfigurationEntity(
            engine_type="gx",
            engine_target="pyspark",
            execution_shape="single_object",
            batch_size=10000,
            flush_interval_seconds=30,
            options={
                "violation_storage": "s3",
                "quarantine_enabled": True,
                "diagnostic_depth": "detailed",
            },
        ),
        schedule=DQPlanTemplateScheduleEntity(
            schedule_type="cron",
            cron_expression="0 2 * * *",  # Daily at 2 AM
            timezone="UTC",
            parameters={"max_runtime_minutes": 120},
        ),
        owner="data-governance",
        approver="data-steward",
        approved=True,
        is_active=True,
        is_default=True,
    )


def create_financial_transaction_template() -> DQPlanTemplateEntity:
    """
    Financial Transaction Template
    
    Validates financial transaction data for:
    - Completeness
    - Accuracy (amount calculations)
    - Timeliness
    - Regulatory compliance (BCBS 239)
    - Duplicate detection
    """
    return DQPlanTemplateEntity(
        template_name="Financial Transaction Quality",
        template_description="BCBS 239 compliant validation for financial transactions including completeness, accuracy, and timeliness checks",
        template_version="1.0.0",
        template_type="data_quality",
        domain="financial",
        tags=["financial", "bcbs239", "compliance", "transactions"],
        parameters=[
            DQPlanTemplateParameterEntity(
                name="dataset_name",
                type="string",
                description="Transaction dataset name",
                required=True,
            ),
            DQPlanTemplateParameterEntity(
                name="date_column",
                type="string",
                description="Date column for timeliness checks",
                required=True,
                default="transaction_date",
            ),
            DQPlanTemplateParameterEntity(
                name="amount_column",
                type="string",
                description="Amount column for accuracy validation",
                required=True,
                default="transaction_amount",
            ),
            DQPlanTemplateParameterEntity(
                name="tolerance_percent",
                type="float",
                description="Tolerance for amount validation (0-100)",
                required=False,
                default=0.01,
                minimum=0,
                maximum=100,
            ),
            DQPlanTemplateParameterEntity(
                name="reconciliation_enabled",
                type="bool",
                description="Enable source-to-target reconciliation",
                required=False,
                default=True,
            ),
        ],
        scope=DQPlanTemplateScopeEntity(
            data_object_ids=["${dataset_name}"],
            tag_ids=["financial", "bcbs239"],
        ),
        suites=[
            DQPlanTemplateSuiteEntity(
                suite_name="transaction_completeness",
                engine_type="gx",
                rule_ids=[
                    "transaction_id_not_null",
                    "transaction_date_not_null",
                    "amount_not_null",
                    "account_id_not_null",
                ],
                configuration={"severity": "error"},
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="transaction_accuracy",
                engine_type="gx",
                rule_ids=[
                    "amount_positive",
                    "amount_within_tolerance",
                    "balance_reconciliation",
                ],
                configuration={
                    "severity": "error",
                    "tolerance_percent": "${tolerance_percent}",
                },
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="transaction_timeliness",
                engine_type="gx",
                rule_ids=["transaction_freshness"],
                configuration={
                    "severity": "error",
                    "date_column": "${date_column}",
                    "max_hours_ago": 6,
                },
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="transaction_uniqueness",
                engine_type="gx",
                rule_ids=["transaction_id_unique"],
                configuration={"severity": "error"},
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="transaction_reconciliation",
                engine_type="gx",
                rule_ids=["source_target_match"],
                configuration={
                    "enabled": "${reconciliation_enabled}",
                    "tolerance": 0,
                },
            ),
        ],
        configuration=DQPlanTemplateConfigurationEntity(
            engine_type="gx",
            engine_target="spark_expectations",
            execution_shape="single_object",
            batch_size=50000,
            flush_interval_seconds=60,
            options={
                "violation_storage": "s3",
                "quarantine_enabled": False,
                "reconciliation_enabled": True,
            },
        ),
        schedule=DQPlanTemplateScheduleEntity(
            schedule_type="cron",
            cron_expression="0 */4 * * *",  # Every 4 hours
            timezone="UTC",
            parameters={"max_runtime_minutes": 30},
        ),
        owner="financial-governance",
        approver="risk-compliance",
        approved=True,
        is_active=True,
        is_default=True,
    )


def create_data_delivery_template() -> DQPlanTemplateEntity:
    """
    Data Delivery Template
    
    Validates data delivery pipelines for:
    - Pipeline completeness
    - Data availability
    - Schema consistency
    - Processing delays
    """
    return DQPlanTemplateEntity(
        template_name="Data Delivery Validation",
        template_description="Validation for data delivery pipelines including availability, freshness, and schema checks",
        template_version="1.0.0",
        template_type="data_quality",
        domain="delivery",
        tags=["delivery", "pipeline", "availability"],
        parameters=[
            DQPlanTemplateParameterEntity(
                name="pipeline_name",
                type="string",
                description="Data pipeline name",
                required=True,
            ),
            DQPlanTemplateParameterEntity(
                name="target_datasets",
                type="list",
                description="Datasets in the pipeline",
                required=True,
            ),
            DQPlanTemplateParameterEntity(
                name="max_delay_minutes",
                type="int",
                description="Maximum acceptable delay in minutes",
                required=False,
                default=15,
                minimum=1,
            ),
        ],
        scope=DQPlanTemplateScopeEntity(
            data_object_ids="${target_datasets}",
        ),
        suites=[
            DQPlanTemplateSuiteEntity(
                suite_name="delivery_freshness",
                engine_type="gx",
                rule_ids=["delivery_freshness_check"],
                configuration={
                    "max_delay_minutes": "${max_delay_minutes}",
                },
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="delivery_completeness",
                engine_type="gx",
                rule_ids=["record_count_match"],
                configuration={"severity": "error"},
            ),
            DQPlanTemplateSuiteEntity(
                suite_name="delivery_schema",
                engine_type="gx",
                rule_ids=["schema_compatibility"],
                configuration={
                    "strict_mode": False,
                    "allow_additions": True,
                    "allow_removals": False,
                },
            ),
        ],
        configuration=DQPlanTemplateConfigurationEntity(
            engine_type="trino",
            execution_shape="single_object",
            batch_size=100000,
        ),
        schedule=DQPlanTemplateScheduleEntity(
            schedule_type="cron",
            cron_expression="0 * * * *",  # Every hour
            timezone="UTC",
        ),
        owner="data-platform",
        approver="data-ops",
        approved=True,
        is_active=True,
        is_default=True,
    )


def get_builtin_templates() -> list[Mapping[str, DQPlanTemplateEntity]]:
    """Get all built-in templates with their metadata."""
    templates = [
        create_customer_data_quality_template(),
        create_financial_transaction_template(),
        create_data_delivery_template(),
    ]
    
    return [
        {
            "id": t.template_id,
            "name": t.template_name,
            "description": t.template_description,
            "domain": t.domain,
            "type": t.template_type,
            "tags": t.tags,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                }
                for p in t.parameters
            ],
            "created_at": t.created_at,
            "is_active": t.is_active,
        }
        for t in templates
    ]


def get_template_by_id(template_id: str) -> DQPlanTemplateEntity | None:
    """Get a built-in template by ID."""
    for template in get_builtin_templates():
        if template["id"] == template_id:
            return None  # This is metadata, not full entity
    return None
