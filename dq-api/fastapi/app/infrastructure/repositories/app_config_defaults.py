import os
import json
from typing import Any

APP_CONFIG_DEFAULTS: dict[str, Any] = {
    "debounceMs": 300,
    "ssoProvider": "none",
    "iconProvider": "tabler",
    "stylePackage": "data-web-css",
    "ssoIssuer": None,
    "ssoClientId": None,
    "ssoEnabled": False,
    "allowLocalAuth": True,
    "apiVersion": "v1",
    "apiRetryAttempts": 3,
    "apiRetryDelay": 1000,
    "maxUsersPerWorkspace": 100,
    "maxWorkspaces": 50,
    "maxRulesPerWorkspace": 1000,
    "maxTemplatesPerWorkspace": 100,
    "maxConcurrentTests": 5,
    "allowedWorkspaceDataSourceTypes": ["adls", "s3", "oracle", "sql_server"],
    "defaultRuleThresholdPct": 0.0,
    "defaultCatalogTermMatchThresholdPct": 70.0,
    "openMetadataContractCacheTtlSeconds": 300,
    "defaultPageSize": 20,
    "maintenanceMode": False,
    "maintenanceMessage": "",
    "allowSignup": True,
    "requireEmailVerification": False,
    "defaultUserRole": "viewer",
    "assistanceRequestMode": "email",
    "assistanceRequestDestinations": ["email"],
    "assistanceRequestEmailAddress": "dq-made-easy-support@jaccloud.nl",
    "assistanceRequestItsmSystem": "Zammad",
    "assistanceRequestItsmEndpointUrl": "http://zammad-nginx:8080/api/v1/tickets",
    "assistanceRequestItsmAuthToken": "",
    "assistanceRequestTeamsWebhookUrl": "https://example.com/teams/workflow-webhook",
    "alertingSlackWebhookUrl": "",
    "alertingPagerDutyRoutingKey": "",
    "alertRoutingPolicy": {
        "deliveryTarget": "app",
        "channels": ["in_app"],
        "mandatoryCategories": [],
        "mandatoryRoles": [],
    },
    "supportEmailSmtpHost": "smtp.strato.com",
    "supportEmailSmtpPort": 465,
    "supportEmailSmtpUsername": "dq-made-easy-support@jaccloud.nl",
    "supportEmailSmtpPassword": "",
    "supportEmailSmtpUseStartTls": True,
    "supportEmailFromAddress": "dq-made-easy-support@jaccloud.nl",
    "dataProtectionMaskingMethods": ["none", "redact", "partial", "tokenize"],
    "dataProtectionEncryptionMethods": ["fernet"],
    "logLevel": "info",
    "enableAnalytics": True,
    "enableCrashReporting": True,
    "enableBulkOperations": True,
    "enableVersioning": True,
    "enableExport": True,
    "auditLogRetentionDays": 90,
    "testResultsRetentionDays": 30,
    "deletedItemsRetentionDays": 30,
    "exceptionFactRetentionDays": 30,
    "exceptionFactArchiveRetentionDays": 180,
    "exceptionAnalyticsProjectionRetentionDays": 365,
    "exceptionFactPurgeBatchSize": 5000,
    "exceptionFactJitRoleMaxDurationMinutes": 240,
    "exceptionFactJitRequestTimeoutMinutes": 30,
    "metricsForwardingEnabled": False,
    "metricsForwardUrl": None,
    "siemEnabled": False,
    "siemEndpointUrl": None,
    "siemApiToken": "",
    "featureRuleValidation": True,
    "featureRuleLifecycleManagement": True,
    "featureRuleResultAggregation": True,
    "featureRuleSuggestions": True,
    "featureExceptionRecordHandling": True,
    "featureRuleExecutionMonitoring": True,
    "featureRuleDslV2": False,
    "featureRuleValidationStage": "preview",
    "featureRuleLifecycleManagementStage": "preview",
    "featureRuleResultAggregationStage": "preview",
    "featureRuleSuggestionsStage": "live",
    "featureExceptionRecordHandlingStage": "preview",
    "featureRuleExecutionMonitoringStage": "preview",
    "featureGovernanceDrift": True,
    "featureGovernanceDriftStage": "live",
    "playgroundSourceBundlePolicy": {
        "default_allow": True,
        "allowed_bundle_ids": [],
        "blocked_bundle_ids": [],
    },
    "agentPlatformAllowlist": ["mistral_ai", "microsoft_copilot"],
    "deploymentVerificationDate": None,
    "deploymentVerifiedBy": None,
    "agentAccessPolicy": {
        "defaultAction": "deny",
        "allowedAgents": [],
    },
    "versionCatalogApi": "unknown",
    "versionCatalogUi": "unknown",
    "versionCatalogComponents": {},
    "statusGovernance": None,
    "incidentGovernance": {
        "default_assigned_to": "dq-made-easy-support@jaccloud.nl",
        "default_escalation_label": "dq-made-easy-support",
        "rules": [
            {
                "incident_kinds": ["technical_run_error"],
                "assigned_to": "dq-made-easy-support@jaccloud.nl",
                "escalation_label": "engine-on-call",
                "escalate_after_minutes": 15,
            },
            {
                "incident_kinds": ["functional_violation"],
                "assigned_to": "data-governance",
                "escalation_label": "governance-triage",
                "escalate_after_minutes": 60,
            },
        ],
    },
    "validationPolicies": [
        {"checkId": "DQ1_EMPTY_EXPRESSION", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ1_EXPRESSION_SYNTAX", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ1_UNSUPPORTED_KEYWORD", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ1_MISSING_ALIAS", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ1_JOIN_VALIDATION", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ1_DUPLICATE_EXPRESSION", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ1_DUPLICATE_NAME", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ1_CONTRADICTORY_PREDICATES", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ7_FILTER_VALIDATION", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ7_RESERVED_KEYWORD", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ7_UNSUPPORTED_AGGREGATE", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ7_JOIN_VALIDATION", "enabled": True, "severityOverride": None, "scope": "all"},
        {"checkId": "DQ7_AST_PARSE", "enabled": True, "severityOverride": None, "scope": "all"},
    ],
    "sessionTimeoutMinutes": 60,
    "sessionTimeoutWarningMinutes": 10,
    "agentSessionTimeoutMinutes": 60,
    "maxToolCallsPerSession": 100,
}

APP_CONFIG_ENCRYPTED_KEYS: tuple[str, ...] = (
    "supportEmailSmtpPassword",
    "assistanceRequestItsmAuthToken",
    "alertingSlackWebhookUrl",
    "alertingPagerDutyRoutingKey",
)

APP_CONFIG_KEY_MAP: dict[str, str] = {
    "debounce_ms": "debounceMs",
    "sso_provider": "ssoProvider",
    "icon_provider": "iconProvider",
    "style_package": "stylePackage",
    "sso_issuer": "ssoIssuer",
    "sso_client_id": "ssoClientId",
    "sso_enabled": "ssoEnabled",
    "allow_local_auth": "allowLocalAuth",
    "api_version": "apiVersion",
    "api_retry_attempts": "apiRetryAttempts",
    "api_retry_delay": "apiRetryDelay",
    "max_users_per_workspace": "maxUsersPerWorkspace",
    "max_workspaces": "maxWorkspaces",
    "max_rules_per_workspace": "maxRulesPerWorkspace",
    "max_templates_per_workspace": "maxTemplatesPerWorkspace",
    "max_concurrent_tests": "maxConcurrentTests",
    "allowed_workspace_data_source_types": "allowedWorkspaceDataSourceTypes",
    "default_rule_threshold_pct": "defaultRuleThresholdPct",
    "default_catalog_term_match_threshold_pct": "defaultCatalogTermMatchThresholdPct",
    "openmetadata_contract_cache_ttl_seconds": "openMetadataContractCacheTtlSeconds",
    "default_page_size": "defaultPageSize",
    "maintenance_mode": "maintenanceMode",
    "maintenance_message": "maintenanceMessage",
    "allow_signup": "allowSignup",
    "require_email_verification": "requireEmailVerification",
    "default_user_role": "defaultUserRole",
    "assistance_request_mode": "assistanceRequestMode",
    "assistance_request_destinations": "assistanceRequestDestinations",
    "assistance_request_email_address": "assistanceRequestEmailAddress",
    "assistance_request_itsm_system": "assistanceRequestItsmSystem",
    "assistance_request_itsm_endpoint_url": "assistanceRequestItsmEndpointUrl",
    "assistance_request_itsm_auth_token": "assistanceRequestItsmAuthToken",
    "assistance_request_teams_webhook_url": "assistanceRequestTeamsWebhookUrl",
    "alerting_slack_webhook_url": "alertingSlackWebhookUrl",
    "alerting_pagerduty_routing_key": "alertingPagerDutyRoutingKey",
    "alert_routing_policy": "alertRoutingPolicy",
    "support_email_smtp_host": "supportEmailSmtpHost",
    "support_email_smtp_port": "supportEmailSmtpPort",
    "support_email_smtp_username": "supportEmailSmtpUsername",
    "support_email_smtp_password": "supportEmailSmtpPassword",
    "support_email_smtp_use_start_tls": "supportEmailSmtpUseStartTls",
    "support_email_from_address": "supportEmailFromAddress",
    "data_protection_masking_methods": "dataProtectionMaskingMethods",
    "data_protection_encryption_methods": "dataProtectionEncryptionMethods",
    "log_level": "logLevel",
    "enable_analytics": "enableAnalytics",
    "enable_crash_reporting": "enableCrashReporting",
    "enable_bulk_operations": "enableBulkOperations",
    "enable_versioning": "enableVersioning",
    "enable_export": "enableExport",
    "audit_log_retention_days": "auditLogRetentionDays",
    "test_results_retention_days": "testResultsRetentionDays",
    "deleted_items_retention_days": "deletedItemsRetentionDays",
    "exception_fact_retention_days": "exceptionFactRetentionDays",
    "exception_fact_archive_retention_days": "exceptionFactArchiveRetentionDays",
    "exception_analytics_projection_retention_days": "exceptionAnalyticsProjectionRetentionDays",
    "exception_fact_purge_batch_size": "exceptionFactPurgeBatchSize",
    "exception_fact_jit_role_max_duration_minutes": "exceptionFactJitRoleMaxDurationMinutes",
    "exception_fact_jit_request_timeout_minutes": "exceptionFactJitRequestTimeoutMinutes",
    "metrics_forwarding_enabled": "metricsForwardingEnabled",
    "metrics_forward_url": "metricsForwardUrl",
    "siem_enabled": "siemEnabled",
    "siem_endpoint_url": "siemEndpointUrl",
    "siem_api_token": "siemApiToken",
    "feature_rule_validation": "featureRuleValidation",
    "feature_rule_lifecycle_management": "featureRuleLifecycleManagement",
    "feature_rule_result_aggregation": "featureRuleResultAggregation",
    "feature_rule_suggestions": "featureRuleSuggestions",
    "feature_exception_record_handling": "featureExceptionRecordHandling",
    "feature_rule_execution_monitoring": "featureRuleExecutionMonitoring",
    "feature_rule_dsl_v2": "featureRuleDslV2",
    "feature_rule_validation_stage": "featureRuleValidationStage",
    "feature_rule_lifecycle_management_stage": "featureRuleLifecycleManagementStage",
    "feature_rule_result_aggregation_stage": "featureRuleResultAggregationStage",
    "feature_rule_suggestions_stage": "featureRuleSuggestionsStage",
    "feature_exception_record_handling_stage": "featureExceptionRecordHandlingStage",
    "feature_rule_execution_monitoring_stage": "featureRuleExecutionMonitoringStage",
    "feature_governance_drift": "featureGovernanceDrift",
    "feature_governance_drift_stage": "featureGovernanceDriftStage",
    "playground_source_bundle_policy": "playgroundSourceBundlePolicy",
    "agent_platform_allowlist": "agentPlatformAllowlist",
    "deployment_verification_date": "deploymentVerificationDate",
    "deployment_verified_by": "deploymentVerifiedBy",
    "agent_access_policy": "agentAccessPolicy",
    "version_catalog_api": "versionCatalogApi",
    "version_catalog_ui": "versionCatalogUi",
    "version_catalog_components": "versionCatalogComponents",
    "status_governance": "statusGovernance",
    "incident_governance": "incidentGovernance",
    "validation_policies": "validationPolicies",
    "session_timeout_minutes": "sessionTimeoutMinutes",
    "session_timeout_warning_minutes": "sessionTimeoutWarningMinutes",
    "agent_session_timeout_minutes": "agentSessionTimeoutMinutes",
    "max_tool_calls_per_session": "maxToolCallsPerSession",
}

APP_CONFIG_REVERSE_KEY_MAP: dict[str, str] = {value: key for key, value in APP_CONFIG_KEY_MAP.items()}


def _get_env_string(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value is None:
            continue
        trimmed = value.strip()
        if trimmed:
            return trimmed
    return None


def _get_env_boolean_or_none(*keys: str) -> bool | None:
    value = _get_env_string(*keys)
    if value is None:
        return None
    return value.lower() in {"true", "1", "t", "yes"}


def apply_env_sso_overrides(config: dict[str, Any]) -> dict[str, Any]:
    env_sso_provider = _get_env_string("SSO_PROVIDER")
    env_sso_issuer = _get_env_string("SSO_PUBLIC_ISSUER_URL")
    env_sso_client_id = _get_env_string("SSO_CLIENT_ID", "KEYCLOAK_CLIENT_ID")
    env_sso_enabled = _get_env_boolean_or_none("SSO_ENABLED")
    env_allow_local_auth = _get_env_boolean_or_none("ALLOW_LOCAL_AUTH")

    merged = dict(config)
    if env_sso_provider is not None:
        merged["ssoProvider"] = env_sso_provider
    if env_sso_issuer is not None:
        merged["ssoIssuer"] = env_sso_issuer
    if env_sso_client_id is not None:
        merged["ssoClientId"] = env_sso_client_id
    if env_sso_enabled is not None:
        merged["ssoEnabled"] = env_sso_enabled
    if env_allow_local_auth is not None:
        merged["allowLocalAuth"] = env_allow_local_auth
    return merged


def infer_app_config_value_type(key: str) -> str:
    if key in {
        "debounceMs",
        "apiRetryAttempts",
        "apiRetryDelay",
        "maxUsersPerWorkspace",
        "maxWorkspaces",
        "maxRulesPerWorkspace",
        "maxTemplatesPerWorkspace",
        "maxConcurrentTests",
        "defaultRuleThresholdPct",
        "defaultCatalogTermMatchThresholdPct",
        "openMetadataContractCacheTtlSeconds",
        "defaultPageSize",
        "auditLogRetentionDays",
        "testResultsRetentionDays",
        "deletedItemsRetentionDays",
        "exceptionFactRetentionDays",
        "exceptionFactArchiveRetentionDays",
        "exceptionAnalyticsProjectionRetentionDays",
        "exceptionFactPurgeBatchSize",
        "exceptionFactJitRoleMaxDurationMinutes",
        "exceptionFactJitRequestTimeoutMinutes",
        "sessionTimeoutMinutes",
        "sessionTimeoutWarningMinutes",
        "agentSessionTimeoutMinutes",
        "maxToolCallsPerSession",
        "supportEmailSmtpPort",
    }:
        return "number"
    if key in {
        "ssoEnabled",
        "allowLocalAuth",
        "maintenanceMode",
        "allowSignup",
        "requireEmailVerification",
        "enableAnalytics",
        "enableCrashReporting",
        "enableBulkOperations",
        "enableVersioning",
        "enableExport",
        "metricsForwardingEnabled",
        "siemEnabled",
        "featureRuleValidation",
        "featureRuleLifecycleManagement",
        "featureRuleResultAggregation",
        "featureRuleSuggestions",
        "featureExceptionRecordHandling",
        "featureRuleExecutionMonitoring",
        "featureRuleDslV2",
        "featureGovernanceDrift",
        "supportEmailSmtpUseStartTls",
    }:
        return "boolean"

    if key in {
        "deploymentVerificationDate",
        "deploymentVerifiedBy",
        "versionCatalogApi",
        "versionCatalogUi",
        "supportEmailSmtpHost",
        "supportEmailSmtpUsername",
        "supportEmailSmtpPassword",
        "supportEmailFromAddress",
        "siemEndpointUrl",
        "siemApiToken",
    }:
        return "string"

    if key in {
        "assistanceRequestDestinations",
        "validationPolicies",
        "versionCatalogComponents",
        "statusGovernance",
        "incidentGovernance",
        "alertRoutingPolicy",
        "playgroundSourceBundlePolicy",
        "agentPlatformAllowlist",
        "agentAccessPolicy",
        "allowedWorkspaceDataSourceTypes",
        "dataProtectionMaskingMethods",
        "dataProtectionEncryptionMethods",
    }:
        return "json"

    return "string"


def normalize_app_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = apply_env_sso_overrides(dict(APP_CONFIG_DEFAULTS))

    for target_key, default_value in tuple(normalized.items()):
        raw_key = APP_CONFIG_REVERSE_KEY_MAP[target_key]
        if target_key in payload:
            raw_value = payload[target_key]
        elif raw_key in payload:
            raw_value = payload[raw_key]
        else:
            continue

        if raw_value is None:
            continue

        value_type = infer_app_config_value_type(target_key)
        if value_type == "number":
            try:
                parsed = float(raw_value)
            except (TypeError, ValueError):
                continue
            normalized[target_key] = int(parsed) if parsed.is_integer() else parsed
            continue

        if value_type == "boolean":
            if isinstance(raw_value, bool):
                normalized[target_key] = raw_value
            elif isinstance(raw_value, (int, float)):
                normalized[target_key] = bool(raw_value)
            else:
                normalized[target_key] = str(raw_value).strip().lower() in {"true", "1", "t", "yes"}
            continue

        if target_key in {"ssoProvider", "ssoIssuer", "ssoClientId"} and raw_value == "":
            normalized[target_key] = default_value
            continue

        if value_type == "json":
            normalized[target_key] = raw_value
            continue

        normalized[target_key] = str(raw_value)

    return normalized


def serialize_app_config_value(value: Any, value_type: str) -> str | None:
    if value is None:
        return None
    if value_type == "boolean":
        return "true" if bool(value) else "false"
    if value_type == "json":
        return json.dumps(value)
    return str(value)
