# dq-made-easy — Executive One-Pager (Implemented + Planned)

Status: Done

_Date: 2026-04-16_

## What’s in scope

This one-pager summarizes dq-made-easy at the highest level for executives, split into three buckets only: **UI**, **Interfaces**, and **Background processes**.

For deeper detail, see:

- Implemented features (management summary): [MANAGEMENT_FEATURE_SUMMARY.md](./MANAGEMENT_FEATURE_SUMMARY.md)
- Planned & future work (management summary): [../MANAGEMENT_FUTURE_WORK_SUMMARY.md](../MANAGEMENT_FUTURE_WORK_SUMMARY.md)

## UI (What users can do)

- **Implemented:** End-to-end rule governance is usable in the UI—create and manage rules through draft → test/proof → approval → activation, with scheduling/execution management, execution-progress visibility, templates, audit trail, suggestions, reporting views, a catalog-style data browser, and admin/config screens; access is controlled by role/scope.
- **Planned:** Connector onboarding UI and expanded reporting (exports, trends, customizable metrics/dashboards).

## Interfaces (How it integrates)

- **Implemented:** A gateway-ready FastAPI backend with a broad v1 API surface for rules/approvals/testing/catalog/contracts/suggestions/governance, plus SSO/auth flows, support-requester resolution, catalog-backed business metadata integration, real-source GX execution, and operational conventions (correlation IDs, telemetry) for enterprise-grade troubleshooting.
- **Implemented:** OpenMetadata-backed product semantics are being standardized through an ISO 11179-based framework on OpenMetadata 1.12.4 over native HTTPS; Open Data Product Specification 4.1 is the product-level layer, while ODCS 3.1 remains the contract-level layer.
- **Implemented:** A first-party Airflow integration path now exists through an internal validation-run-plan SDK, fail-fast GX run polling, and a minimal compose-backed Airflow DAG example.
- **Planned:** Connector framework APIs, webhook subscriptions & delivery diagnostics, rate limiting controls, stronger enterprise auth options (service tokens + management/diagnostics), and broader orchestrator packaging/generation beyond the shipped Airflow path.

## Background processes (Automation & execution)

- **Implemented:** A profiling worker generates suggestions from queued jobs; the execution engine now supports real-source grouped execution with dispatch consumption, lifecycle completion, and delivery-linked reporting; the stack includes repeatable seeding plus operational validation/smoke scripts.
- **Planned:** Expand connector sync orchestration, add webhook delivery workers, add metadata drift detection + revalidation automation, and standardize dedicated test-runner infrastructure (UI/API/DB) with evidence capture and CI gates.
