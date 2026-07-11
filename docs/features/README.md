# Features

**Status tracking and roadmap** for Data Quality Made Easy.

For complete feature definitions and capabilities, see [FEATURES.md](./FEATURES.md) — the authoritative reference.

This README tracks implementation status (`Status: Done` or `Status: Planned`) and split feature files. Each file carries a `Status:` header line.

## Planned features (Status: Planned)

The following workstreams are still open. See [FEATURE_ROADMAP_OVERVIEW.md](./FEATURE_ROADMAP_OVERVIEW.md) for sequencing, acceptance criteria, and backlog detail.

| Workstream | Summary |
|---|---|
| [WS-1 Observability Platform](./FEATURE_ROADMAP_OVERVIEW.md) | Alerts, anomaly detection, full rule-execution tracing |
| [WS-2 UX And Visualization](./FEATURE_ROADMAP_OVERVIEW.md) | Advanced dashboards, trend analysis, unified quality score |
| [WS-3 Governance And Lifecycle](./FEATURE_ROADMAP_OVERVIEW.md) | Policy-driven approvals, drift detection, audit workflows |
| [WS-4 Metadata And Semantic Automation](./FEATURE_ROADMAP_OVERVIEW.md) | AI-assisted definition drafting, semantic enrichment |
| [WS-5 Control, Delivery, CI/CD, Integrations](./FEATURE_ROADMAP_OVERVIEW.md) | Pipeline triggers, API connectors, webhook notifications |
| [WS-6 Scale And Advanced Validation](./FEATURE_ROADMAP_OVERVIEW.md) | Multi-runtime lowerers, partition-aware execution |
| [WS-7 Frontend Portability](./FEATURE_ROADMAP_OVERVIEW.md) | App-shell portability, theme tokens, design system |
| [WS-8 Security, Compliance, Auditability](./FEATURE_ROADMAP_OVERVIEW.md) | Post-quantum readiness, encryption-at-rest, egress control |
| [WS-9 Documentation And Onboarding](./FEATURE_ROADMAP_OVERVIEW.md) | Guided onboarding, public API docs, operator runbooks |
| [WS-10 Agentic AI Ecosystem](./FEATURE_ROADMAP_OVERVIEW.md) | Agent harness, tool-using AI for rule and definition tasks |

## Completed features (Status: Done)

The following are implemented and shipped. Each file carries `Status: Done`.

- [DQ-5 Advanced Data Profiling](./DQ-5_ADVANCED_DATA_PROFILING.md)
- [DQ-6 Batch Rule Execution](./DQ-6_BATCH_RULE_EXECUTION_IMPROVEMENTS.md)
- [DQ-7 Executable Rule Transformation](./DQ-7_EXECUTABLE_RULE_TRANSFORMATION.md)
- [DQ-10 Natural Language Rule Drafting](./DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW.md)
- [API-5 Metadata Integration](./API_5_METADATA_INTEGRATION.md)
- [API-7 Real DQ Rule Execution](./API_7_REAL_DQ_RULE_EXECUTION.md)
- [Abstraction Features](./ABSTRACTION_FEATURES.md)
- [ABS-2 Data Catalog Materialization](./ABS_2_DATA_CATALOG_MATERIALIZATION.md)
- [ABS-3 Delivery Linked Rule Execution](./ABS_3_DELIVERY_LINKED_RULE_EXECUTION.md)
- [FastAPI Migration Baseline](./FASTAPI_MIGRATION_SCOPE_BASELINE.md)
- [Internal Service TLS Migration Matrix](./INTERNAL_SERVICE_TLS_MIGRATION_MATRIX.md)
- [JWT End-to-End Test Results](./JWT_END_TO_END_TEST_RESULTS.md)
- [Management Feature Summary](./MANAGEMENT_FEATURE_SUMMARY.md)
- [Management One-Pager](./MANAGEMENT_ONE_PAGER.md)
- [Phase 7 Summary](./PHASE7_SUMMARY.md)
- [Profiling Request Generator Changelog](./PROFILING_REQUEST_GENERATOR_CHANGELOG.md)
- [Rule Status Transitions](./RULE_STATUS_TRANSITIONS.md)
- [WF-3 Comprehensive Summary](./WF3_COMPREHENSIVE_SUMMARY.md)

## Feature plans and scope definitions

- [DQ_FEATURES.md](./DQ_FEATURES.md)
- [UX_FEATURES.md](./UX_FEATURES.md)
- [API_FEATURES.md](./API_FEATURES.md)
- [SEC_FEATURES.md](./SEC_FEATURES.md)
- [WORKFLOW_FEATURES.md](./WORKFLOW_FEATURES.md)
- [ANALYTICS_REPORTING_FEATURES.md](./ANALYTICS_REPORTING_FEATURES.md)
- [DOCUMENTATION_FEATURES.md](./DOCUMENTATION_FEATURES.md)
- [ONBOARDING_FEATURES.md](./ONBOARDING_FEATURES.md)
- [AGENTIC_AI_ECOSYSTEM_FEATURES.md](./AGENTIC_AI_ECOSYSTEM_FEATURES.md)
- [FRONTEND_UI_PORTABILITY_FEATURES.md](./FRONTEND_UI_PORTABILITY_FEATURES.md)
- [DATA_ASSETS_FEATURES.md](./DATA_ASSETS_FEATURES.md)

## Split planning documents (feature-level detail)

- [ABS_1_EXECUTION_ABSTRACTION.md](./ABS_1_EXECUTION_ABSTRACTION.md)
- [BUSINESS_KEYS.md](./BUSINESS_KEYS.md)
- [LLM_1_AGENT_HARNESS.md](./LLM_1_AGENT_HARNESS.md)
- [CONFIG_DRIVEN_UI_REGISTRY.md](./CONFIG_DRIVEN_UI_REGISTRY.md)
- [DQ-20 Reusable DQ Engine Library](./DQ-20_REUSABLE_DQ_ENGINE_LIBRARY.md)
- [DQ_19_MULTI_RUNTIME_LOWERERS.md](./DQ_19_MULTI_RUNTIME_LOWERERS.md)
- [API_1_CONNECTORS.md](./API_1_CONNECTORS.md)
- [API_2_WEBHOOK_NOTIFICATIONS.md](./API_2_WEBHOOK_NOTIFICATIONS.md)
- [API_3_RATE_LIMITING.md](./API_3_RATE_LIMITING.md)
- [API_4_AUTHENTICATION_OPTIONS.md](./API_4_AUTHENTICATION_OPTIONS.md)
- [API_4_ENTRA_KEYCLOAK_BROKERING.md](./API_4_ENTRA_KEYCLOAK_BROKERING.md)
- [WF_5_DEDICATED_ENVIRONMENT_CONTRACT.md](./WF_5_DEDICATED_ENVIRONMENT_CONTRACT.md)
- [WF_6_KUBERNETES_IMAGE_DEPLOYMENT.md](./WF_6_KUBERNETES_IMAGE_DEPLOYMENT.md)
- [WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT.md](./WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT.md)
- [WF_8_AZURE_PIPELINE_VERIFICATION_HARNESS.md](./WF_8_AZURE_PIPELINE_VERIFICATION_HARNESS.md)
- [SEC_1_INTERNAL_SERVICE_TLS.md](./SEC_1_INTERNAL_SERVICE_TLS.md)
- [SEC_2_POST_QUANTUM_READINESS.md](./SEC_2_POST_QUANTUM_READINESS.md)
- [SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md](./SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md)
- [SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md](./SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md)
- [SEC_5_SENSITIVE_DATA_ENCRYPTION_AND_KEY_SEGREGATION.md](./SEC_5_SENSITIVE_DATA_ENCRYPTION_AND_KEY_SEGREGATION.md)

## Versioned governance references

- Open Data Product Specification 4.1 is the product-spec direction for data products.
- ODCS 3.1 is the contract-spec direction for data-quality and delivery contracts.

## Legacy

- [FEATURES.md](./FEATURES.md) — legacy rollup, kept for backward compatibility only.

- [DQ_FEATURES.md](./DQ_FEATURES.md)
- [UX_FEATURES.md](./UX_FEATURES.md)
- [API_FEATURES.md](./API_FEATURES.md)
- [SEC_FEATURES.md](./SEC_FEATURES.md)
- [WORKFLOW_FEATURES.md](./WORKFLOW_FEATURES.md)
- [ANALYTICS_REPORTING_FEATURES.md](./ANALYTICS_REPORTING_FEATURES.md)
- [DOCUMENTATION_FEATURES.md](./DOCUMENTATION_FEATURES.md)
- [ONBOARDING_FEATURES.md](./ONBOARDING_FEATURES.md)
- [AGENTIC_AI_ECOSYSTEM_FEATURES.md](./AGENTIC_AI_ECOSYSTEM_FEATURES.md)
- [FRONTEND_UI_PORTABILITY_FEATURES.md](./FRONTEND_UI_PORTABILITY_FEATURES.md)
- [DATA_ASSETS_FEATURES.md](./DATA_ASSETS_FEATURES.md)

## Split planning documents (feature-level detail)

- [ABS_1_EXECUTION_ABSTRACTION.md](./ABS_1_EXECUTION_ABSTRACTION.md)
- [BUSINESS_KEYS.md](./BUSINESS_KEYS.md)
- [LLM_1_AGENT_HARNESS.md](./LLM_1_AGENT_HARNESS.md)
- [CONFIG_DRIVEN_UI_REGISTRY.md](./CONFIG_DRIVEN_UI_REGISTRY.md)
- [DQ_19_MULTI_RUNTIME_LOWERERS.md](./DQ_19_MULTI_RUNTIME_LOWERERS.md)
- [API_1_CONNECTORS.md](./API_1_CONNECTORS.md)
- [API_2_WEBHOOK_NOTIFICATIONS.md](./API_2_WEBHOOK_NOTIFICATIONS.md)
- [API_3_RATE_LIMITING.md](./API_3_RATE_LIMITING.md)
- [API_4_AUTHENTICATION_OPTIONS.md](./API_4_AUTHENTICATION_OPTIONS.md)
- [API_4_ENTRA_KEYCLOAK_BROKERING.md](./API_4_ENTRA_KEYCLOAK_BROKERING.md)
- [WF_5_DEDICATED_ENVIRONMENT_CONTRACT.md](./WF_5_DEDICATED_ENVIRONMENT_CONTRACT.md)
- [WF_6_KUBERNETES_IMAGE_DEPLOYMENT.md](./WF_6_KUBERNETES_IMAGE_DEPLOYMENT.md)
- [WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT.md](./WF_7_AZURE_CONTAINER_APPS_ENVIRONMENT_DEPLOYMENT.md)
- [WF_8_AZURE_PIPELINE_VERIFICATION_HARNESS.md](./WF_8_AZURE_PIPELINE_VERIFICATION_HARNESS.md)
- [SEC_1_INTERNAL_SERVICE_TLS.md](./SEC_1_INTERNAL_SERVICE_TLS.md)
- [SEC_2_POST_QUANTUM_READINESS.md](./SEC_2_POST_QUANTUM_READINESS.md)
- [SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md](./SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md)
- [SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md](./SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md)
- [SEC_5_SENSITIVE_DATA_ENCRYPTION_AND_KEY_SEGREGATION.md](./SEC_5_SENSITIVE_DATA_ENCRYPTION_AND_KEY_SEGREGATION.md)

## Versioned governance references

- Open Data Product Specification 4.1 is the product-spec direction for data products.
- ODCS 3.1 is the contract-spec direction for data-quality and delivery contracts.

## Legacy

- [FEATURES.md](./FEATURES.md) — legacy rollup, kept for backward compatibility only.
