# Grafana App Panel Validation Index

Last updated: 2026-05-11

This document is the current index of app-facing Grafana panels and the validation or smoke scripts that generate the data behind them.

Scope:
- App dashboards only.
- Infrastructure-only panels are excluded.
- If a panel family is marked as a gap, there is no dedicated live validation or smoke script for it yet.

## API Observability

| Panel family | Validation or smoke scripts | Status |
|---|---|---|
| Requests, Auth Failures, Error Ratio, Latency, Request Rate by Endpoint Group | [scripts/validation/validate_dq_api_grafana_otel_smoke.sh](../../scripts/validation/validate_dq_api_grafana_otel_smoke.sh), [scripts/validation/validate_ui_api_trace_propagation.sh](../../scripts/validation/validate_ui_api_trace_propagation.sh), [scripts/validation/validate_user_login_end_to_end.sh](../../scripts/validation/validate_user_login_end_to_end.sh), [scripts/validation/smoke_test_auth_kong.sh](../../scripts/validation/smoke_test_auth_kong.sh) | Covered |
| GX Operation Outcomes and Failures, GX Suite Save/Fetch Latency, GX Suite Save/Fetch Outcomes | [scripts/validation/validate_gx_compile_trend.sh](../../scripts/validation/validate_gx_compile_trend.sh), [scripts/validation/validate_rule_lifecycle_gx_supported.sh](../../scripts/validation/validate_rule_lifecycle_gx_supported.sh), [scripts/validation/validate_gx_worker_smoke.sh](../../scripts/validation/validate_gx_worker_smoke.sh), [scripts/validation/smoke_adhoc_rule_execution.sh](../../scripts/validation/smoke_adhoc_rule_execution.sh) | Covered |
| Natural Language Draft Queue Backlog, Natural Language Draft Queue Events, Async Queue Backlog, Async Queue Events | [scripts/validation/validate_natural_language_draft_queue.sh](../../scripts/validation/validate_natural_language_draft_queue.sh) | Covered |

## Execution Monitoring

| Panel family | Validation or smoke scripts | Status |
|---|---|---|
| Pending Runs, Running Runs, Entered Pending, Entered Running, Stale Running, Oldest Running Age, Current Runs by Status, Run Transitions, Executor Latency, Execution Results and Failures, Compile Success/Failure Trend, Run Throughput by Execution Shape, Executor Heartbeat Age vs Threshold | [scripts/validation/validate_rule_lifecycle_gx_supported.sh](../../scripts/validation/validate_rule_lifecycle_gx_supported.sh), [scripts/validation/validate_gx_compile_trend.sh](../../scripts/validation/validate_gx_compile_trend.sh), [scripts/validation/validate_gx_worker_smoke.sh](../../scripts/validation/validate_gx_worker_smoke.sh), [scripts/validation/smoke_adhoc_rule_execution.sh](../../scripts/validation/smoke_adhoc_rule_execution.sh), [scripts/validation/validate_profiling_worker_lifecycle.sh](../../scripts/validation/validate_profiling_worker_lifecycle.sh), [scripts/validation/validate_profiling_worker_success.sh](../../scripts/validation/validate_profiling_worker_success.sh), [scripts/validation/validate_profiling_worker_failure.sh](../../scripts/validation/validate_profiling_worker_failure.sh) | Covered |
| Non-Canonical Exception Facts, Oldest Non-Canonical Age, Latest Canonical Fact Age | [scripts/validation/validate_exception_fact_observability.sh](../../scripts/validation/validate_exception_fact_observability.sh) | Covered |

## Redis and Queues

| Panel family | Validation or smoke scripts | Status |
|---|---|---|
| Redis Operations by Source, Redis Failures by Source | [scripts/validation/validate_profiling_worker_lifecycle.sh](../../scripts/validation/validate_profiling_worker_lifecycle.sh), [scripts/validation/validate_profiling_worker_success.sh](../../scripts/validation/validate_profiling_worker_success.sh), [scripts/validation/validate_profiling_worker_failure.sh](../../scripts/validation/validate_profiling_worker_failure.sh) | Covered |
| Async Queue Backlog | [scripts/validation/validate_rule_lifecycle_gx_supported.sh](../../scripts/validation/validate_rule_lifecycle_gx_supported.sh), [scripts/validation/validate_gx_worker_smoke.sh](../../scripts/validation/validate_gx_worker_smoke.sh), [scripts/validation/smoke_adhoc_rule_execution.sh](../../scripts/validation/smoke_adhoc_rule_execution.sh), [scripts/validation/validate_natural_language_draft_queue.sh](../../scripts/validation/validate_natural_language_draft_queue.sh) | Covered |

## UI Metrics

| Panel family | Validation or smoke scripts | Status |
|---|---|---|
| Active Logged-in Sessions, Role Logins Over Time, login-related UI metrics | [scripts/validation/smoke_test_auth_kong.sh](../../scripts/validation/smoke_test_auth_kong.sh), [scripts/validation/validate_user_login_end_to_end.sh](../../scripts/validation/validate_user_login_end_to_end.sh) | Covered |
| UI -> Gateway -> API trace propagation | [scripts/validation/validate_ui_api_trace_propagation.sh](../../scripts/validation/validate_ui_api_trace_propagation.sh) | Covered |

## OpenMetadata

| Panel family | Validation or smoke scripts | Status |
|---|---|---|
| OpenMetadata Cache Hit/Miss Trend, OpenMetadata Cache Hit Ratio, OpenMetadata Cache Events | [scripts/validation/validate_openmetadata_contract_cache.sh](../../scripts/validation/validate_openmetadata_contract_cache.sh) | Covered |
| Trace presence for `service.name=dq-openmetadata` | [scripts/validation/validate_openmetadata_otel_smoke.sh](../../scripts/validation/validate_openmetadata_otel_smoke.sh) | Covered |

## JIT Access Requests

| Panel family | Validation or smoke scripts | Status |
|---|---|---|
| Total JIT Requests, Pending Requests, Approved Requests, Declined Requests, Timed Out Requests, JIT Requests by Status | [scripts/validation/validate_jit_access_requests.sh](../../scripts/validation/validate_jit_access_requests.sh) | Covered |

## Script Index

These are the app-facing validation and smoke entrypoints referenced above:

- [scripts/validation/validate_dq_api_grafana_otel_smoke.sh](../../scripts/validation/validate_dq_api_grafana_otel_smoke.sh)
- [scripts/validation/validate_exception_fact_observability.sh](../../scripts/validation/validate_exception_fact_observability.sh)
- [scripts/validation/validate_gx_compile_trend.sh](../../scripts/validation/validate_gx_compile_trend.sh)
- [scripts/validation/validate_gx_worker_smoke.sh](../../scripts/validation/validate_gx_worker_smoke.sh)
- [scripts/validation/validate_natural_language_draft_queue.sh](../../scripts/validation/validate_natural_language_draft_queue.sh)
- [scripts/validation/validate_openmetadata_otel_smoke.sh](../../scripts/validation/validate_openmetadata_otel_smoke.sh)
- [scripts/validation/validate_openmetadata_contract_cache.sh](../../scripts/validation/validate_openmetadata_contract_cache.sh)
- [scripts/validation/validate_profiling_worker_failure.sh](../../scripts/validation/validate_profiling_worker_failure.sh)
- [scripts/validation/validate_profiling_worker_lifecycle.sh](../../scripts/validation/validate_profiling_worker_lifecycle.sh)
- [scripts/validation/validate_profiling_worker_success.sh](../../scripts/validation/validate_profiling_worker_success.sh)
- [scripts/validation/validate_jit_access_requests.sh](../../scripts/validation/validate_jit_access_requests.sh)
- [scripts/validation/validate_rule_lifecycle_gx_supported.sh](../../scripts/validation/validate_rule_lifecycle_gx_supported.sh)
- [scripts/validation/validate_ui_api_trace_propagation.sh](../../scripts/validation/validate_ui_api_trace_propagation.sh)
- [scripts/validation/validate_user_login_end_to_end.sh](../../scripts/validation/validate_user_login_end_to_end.sh)
- [scripts/validation/smoke_adhoc_rule_execution.sh](../../scripts/validation/smoke_adhoc_rule_execution.sh)
- [scripts/validation/smoke_test_auth_kong.sh](../../scripts/validation/smoke_test_auth_kong.sh)

## Notes

- The compile-trend validation was added specifically for the `Compile Success/Failure Trend` panel in Execution Monitoring.
- The Natural Language Draft Queue validation uses LLM-backed live preview and draft requests against the seeded retail-banking customer_id path.
- The JIT Access Requests validation uses live API calls through Kong, temporarily reduces the timeout window via /system/v1/app-config, and restores it after the timed_out state is observed.
- Keep this index in sync whenever a new app-facing validation or smoke script is added.

## Color Coding Matrix

Use this as the reference for Grafana tile colors when a panel family needs explicit styling. The policy is per panel family and per tile signal, not per page.

| Signal type | Intended color | Implementation pattern | Use thresholds? |
|---|---|---|---|
| Neutral total / aggregate count | Subdued gray or plain neutral | Fixed color override with a neutral hex, or no color emphasis at the panel level | No |
| Pending / in progress | Blue | Fixed color override | No |
| Success / approved / healthy | Green | Fixed color override | No |
| Failure / declined / unhealthy | Red | Fixed color override | No |
| Timed out / warning / delayed | Orange | Fixed color override | No |
| Monotonic risk or warning band | Green to orange to red | Thresholds based on numeric bands | Yes |

Guidance:

- Use fixed colors for categorical status tiles where the value already means a discrete state.
- Use thresholds only when the value represents a quantitative range that should visually escalate with risk or severity.
- If a dashboard mixes both patterns, document the tile-by-tile exception in the matching dashboard section above.