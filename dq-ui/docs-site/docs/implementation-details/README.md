# Implementation Details

Use this folder for implementation notes, phase reports, and deep-dive execution docs.

## Observability & Monitoring

- [OBSERVABILITY_SETUP.md](/docs/implementation-details/OBSERVABILITY_SETUP/) — Complete observability stack architecture and design (Loki + Prometheus + Tempo + Grafana)
- [OBSERVABILITY_QUICKSTART.md](/docs/implementation-details/OBSERVABILITY_QUICKSTART/) — Quick start guide with 5-minute setup and instrumentation examples
- [OPENTELEMETRY_IMPLEMENTATION.md](/docs/implementation-details/OPENTELEMETRY_IMPLEMENTATION/) — Detailed OpenTelemetry instrumentation patterns, span enrichment, custom metrics, and trace propagation

## Gateway & Ingress

- [KONG_SINGLE_HTTPS_INGRESS_TARGET_ARCHITECTURE.md](/docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_TARGET_ARCHITECTURE/) — Exact target-state architecture for one public HTTPS edge on port 443, with Kong retained as the API gateway behind the edge
- [KONG_SINGLE_HTTPS_INGRESS_IMPLEMENTATION_PLAN.md](/docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_IMPLEMENTATION_PLAN/) — Concrete implementation plan for docker-compose, Kong assumptions, env files, and local `*.jac.dot` execution on the single-edge model
- [KONG_SINGLE_HTTPS_INGRESS_FILE_CHECKLIST.md](/docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_FILE_CHECKLIST/) — File-by-file implementation checklist for moving public apps behind Kong and removing direct service exposure
- [KONG_SINGLE_HTTPS_INGRESS_APP_CUTOVER_MATRIX.md](/docs/implementation-details/KONG_SINGLE_HTTPS_INGRESS_APP_CUTOVER_MATRIX/) — Application-by-application cutover matrix with break risks and verification tasks

## Documentation Publishing

- [USER_MANUALS_IMPLEMENTATION_PLAN.md](/docs/implementation-details/USER_MANUALS_IMPLEMENTATION_PLAN/) — Checkable implementation plan for topic-focused user manuals, static HTML publishing, and UI navigation

## Historical / Deprecated

- [DQ_4_NEW_RULE_TYPES_PROGRESS.md](/docs/implementation-details/DQ_4_NEW_RULE_TYPES_PROGRESS/) — Historical progress log for the pre-DSL 2.0 typed check-type builder
- [DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md](/docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS/) — Historical GX orchestration note superseded by the DQ-7 DSL 2.0 contract and implementation plan

## Current implementation-detail sources

- [DQ_RULE_TO_RUN_PLAN_FLOW.md](/docs/implementation-details/DQ_RULE_TO_RUN_PLAN_FLOW/)
- [DQ_19_MULTI_RUNTIME_LOWERERS_IMPLEMENTATION_PLAN.md](/docs/implementation-details/DQ_19_MULTI_RUNTIME_LOWERERS_IMPLEMENTATION_PLAN/)
- [DQ_20_EXECUTION_DISPATCH_AND_LOWERER_MODULE_SPLIT_PLAN.md](/docs/implementation-details/DQ_20_EXECUTION_DISPATCH_AND_LOWERER_MODULE_SPLIT_PLAN/) — Actionable split plan for making `execution_dispatch` the shared abstraction layer and keeping GX/lowerer modules separate
- [SPARK_EXPECTATIONS_ENGINE_PLAN.md](/docs/implementation-details/SPARK_EXPECTATIONS_ENGINE_PLAN/)
- [ABS_1_EXECUTION_ABSTRACTION_IMPLEMENTATION_DETAILS.md](/docs/implementation-details/ABS_1_EXECUTION_ABSTRACTION_IMPLEMENTATION_DETAILS/)
- [ABS_2_DATA_CATALOG_MATERIALIZATION_IMPLEMENTATION_DETAILS.md](/docs/implementation-details/ABS_2_DATA_CATALOG_MATERIALIZATION_IMPLEMENTATION_DETAILS/)
- [ABS_3_DELIVERY_LINKED_RULE_EXECUTION_IMPLEMENTATION_DETAILS.md](/docs/implementation-details/ABS_3_DELIVERY_LINKED_RULE_EXECUTION_IMPLEMENTATION_DETAILS/)
- [BUSINESS_KEY_IMPLEMENTATION_DETAILS.md](/docs/implementation-details/BUSINESS_KEY_IMPLEMENTATION_DETAILS/)
- [API_7_DATA_DELIVERY_RESOLUTION.md](/docs/implementation-details/API_7_DATA_DELIVERY_RESOLUTION/)
- [API_5_IMPLEMENTATION_PLAN.md](/docs/implementation-details/API_5_IMPLEMENTATION_PLAN/)
- [API_5_PHASE_2_COMPLETE.md](/docs/implementation-details/API_5_PHASE_2_COMPLETE/)
- [API_5_PHASE_4_COMPLETE.md](/docs/implementation-details/API_5_PHASE_4_COMPLETE/)
- [API_5_PHASE_5_UI_INTEGRATION.md](/docs/implementation-details/API_5_PHASE_5_UI_INTEGRATION/)
- [API_6_FASTAPI_MIGRATION.md](/docs/implementation-details/API_6_FASTAPI_MIGRATION/)
- [DQ_1_RULE_VALIDATION_STANDARD_FEATURE_IMPLEMENTATION_PLAN.md](/docs/implementation-details/DQ_1_RULE_VALIDATION_STANDARD_FEATURE_IMPLEMENTATION_PLAN/)
- [DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN.md](/docs/implementation-details/DQ_7_ENGINE_INDEPENDENT_DSL_IMPLEMENTATION_PLAN/)
- [DQ_7_3_RULE_COMPILER_IMPLEMENTATION_PROGRESS.md](/docs/implementation-details/DQ_7_3_RULE_COMPILER_IMPLEMENTATION_PROGRESS/)
- [FRONTEND_UI_LIBRARY_ABSTRACTION_IMPLEMENTATION_APPROACH.md](https://github.com/jactools/dq-rulebuilder/blob/main/FRONTEND_UI_LIBRARY_ABSTRACTION_IMPLEMENTATION_APPROACH.md)
- [FRONTEND_UI_PORTABILITY_ACTION_PLAN.md](https://github.com/jactools/dq-rulebuilder/blob/main/FRONTEND_UI_PORTABILITY_ACTION_PLAN.md)
- [UI_PORTABILITY_RDS_REMOVAL_RESPONSE_PLAN.md](https://github.com/jactools/dq-rulebuilder/blob/main/UI_PORTABILITY_RDS_REMOVAL_RESPONSE_PLAN.md)
- [docs/technical/API_6_FASTAPI_MIGRATION_GUIDE.md](/docs/technical/API_6_FASTAPI_MIGRATION_GUIDE/)
- [PROFILING_IMPLEMENTATION.md](/docs/implementation-details/PROFILING_IMPLEMENTATION/)
- [SEC_1_INTERNAL_SERVICE_TLS_IMPLEMENTATION_PLAN.md](/docs/implementation-details/SEC_1_INTERNAL_SERVICE_TLS_IMPLEMENTATION_PLAN/)
- [SEC_2_POST_QUANTUM_IMPLEMENTATION_PLAN.md](/docs/implementation-details/SEC_2_POST_QUANTUM_IMPLEMENTATION_PLAN/)
- [WF-3_IMPLEMENTATION_PHASE_1.md](/docs/implementation-details/WF-3_IMPLEMENTATION_PHASE_1/)
- [WF-3_IMPLEMENTATION_COMPLETE.md](/docs/implementation-details/WF-3_IMPLEMENTATION_COMPLETE/)
