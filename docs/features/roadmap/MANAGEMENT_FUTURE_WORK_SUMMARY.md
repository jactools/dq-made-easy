# Management Summary — Planned & Future Work (as of 2026-04-15)

This is a forward-looking snapshot of **planned** work items captured in the roadmap and feature-plan documents under `docs/`. It is intentionally grouped into **UI**, **Interfaces**, and **Background processes** only.

## UI

- DQ-10 natural-language rule drafting preview has moved to the implemented/current-state docs at [docs/features/DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW.md](../DQ-10_NATURAL_LANGUAGE_RULE_DRAFTING_PREVIEW.md) and is no longer future work.

- **Connector onboarding and health (API-1)**
  - UI flows for connector setup, validation, and discovery.
  - Connector sync status visibility (timestamps, stale indicators) and governance/audit affordances.

- **User experience enhancements (UX-*)**
  - Expand the existing dashboard into role-aware operational entry points instead of adding generic widgets.
  - Unify filtering and search semantics across rules, catalog, and selection-heavy screens.
  - Harden existing bulk-action flows with clearer eligibility and result feedback.
  - Extend the aggregate materialization-summary UX beyond the initial ad-hoc execution surface.

- **Reporting enhancements (AR-*)**
  - New chart types.
  - Export UX.
  - Custom metrics configuration.
  - Trend analysis views.

- **Onboarding**
  - Guided UX to generate standard rules for selected data objects.

## Interfaces

- **New/expanded API surfaces for integrations (API-1..API-4)**
  - Connectors: configuration CRUD, test-connection, asset discovery, and sync-job status endpoints.
  - Webhooks: subscription CRUD, test-delivery, delivery history/diagnostics endpoints, and a defined event catalog/payload contracts.
  - Rate limiting: policy schema, enforcement middleware, standardized `429` contract/headers, and operator tuning endpoints.
  - Advanced authentication: pluggable validators, hardened JWT/OIDC validation controls, service-account flows, token management endpoints, and auth diagnostics.

- **API-6 migration follow-on**
  - Split authenticated session/profile reads out of the admin namespace and reserve `/admin/v1` for admin-only operations.

- **Open Data Product Specification layer (ODP-1)**
  - Extend the now-implemented OpenMetadata-backed product-spec lookup, list, and create/update sync foundation into broader migration coverage, stewardship workflows, and downstream compatibility validation.

- **Agent-ready DQ surfaces (WS-10)**
  - Canonical REST APIs for rule execution, anomaly results, and metadata lookup with OpenAPI specs.
  - MCP server resources and tools for dashboards, rule libraries, lineage graphs, and governed actions.
  - External agent integrations for Microsoft Copilot, Slack, Airflow, and Dagster.

- **DQ-7 execution-layer follow-ons**
  - DQ-7 is complete in the current feature tracker; the compiler, activation gate, GX adapter, and traceable execution flow now live in the implemented/runtime docs instead of the future-work queue.

- **External orchestrator follow-ons**
  - Broaden the shipped Airflow validation-run-plan SDK and example DAG into additional orchestrator patterns and tighter operator packaging.
  - Optional DAG generation/export for specific suites.

## Background processes

- **Autonomous DQ agents (WS-10)**
  - Steward, lineage explorer, and remediation workflows with governed triggers and escalation rules.
  - Explainable, auditable agent actions that include lineage, business context, SLA thresholds, and remediation trail data.

- **Connector sync jobs (API-1)**
  - Background metadata discovery/sync orchestration with retry/backoff, observable job states, and governance/audit hooks.

- **Webhook delivery pipeline (API-2)**
  - Async delivery worker with retry/backoff, idempotency/dedupe, attempt persistence, and operational health indicators.

- **Test automation infrastructure (WF-4)**
  - Dedicated runner images/containers for UI/API/DB tests (separate from production images).
  - Profile-based orchestration (e.g., `docker-compose.test.yml`), unified entrypoint script, and evidence collection/retention.
  - Result ingestion and dashboards for trend/flakiness tracking plus CI release gates.
