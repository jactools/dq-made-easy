# Management Summary — Implemented Features (as of 2026-04-27)

This is a **current-state** snapshot of what is implemented in the repository (code + runtime wiring). It is intentionally grouped into **UI**, **Interfaces**, and **Background processes** only.

## UI

- **Authentication & access control**
  - Login/logout flows, session expiry handling, and workspace selection/switching.
  - Role/scope-driven navigation gating (features/pages are hidden or blocked without required scopes).
  - Maintenance-mode UI that blocks non-admin users when enabled.

- **Primary navigation areas implemented**
  - Dashboard / Welcome
  - Rules (scoped views such as “my/team/all/global”)
  - Rule Quality (validation, suggestions, drift review / revalidation)
  - Governance (approvals, lifecycle, governance-level drift overview)
  - Data Catalog
  - Operations (metrics, test results, monitoring)
  - Templates
  - Audit trail + compiler version audit
  - Notifications
  - Alert-routing policies for Teams, Slack, email, and PagerDuty are managed through application settings, with secret Slack/PagerDuty connectivity values stored encrypted and kept redacted in the admin UI.
  - Documentation
  - Settings
  - Administration (system metrics, application settings, user management, role management, GX suite admin, icon gallery)

- **Rule lifecycle and authoring UX**
  - Create/edit rules; validate rule composition; activate rules.
  - Rule versioning UX: version history, version comparison, rollback workflows, tagging/mark-for-rollback flows.
  - Approval workflows surfaced in UI (submit for approval, approve/reject).

- **Rule testing & diagnostics UX**
  - Run rule tests, store and display “proof”/test outcomes, and visualize test results in Rule Quality and Operations views.
  - Diagnostics panels for execution/validation visibility (metrics + troubleshooting views).

- **Natural-language rule drafting preview**
  - Preview-only plain-language requests inside Suggestions.
  - Ranked candidate attributes with parent context and explicit confirmation before typed draft creation.

- **Reusable assets and composition helpers**
  - Join conditions tooling.
  - Reusable joins and reusable filters management.
  - Attribute assignment workflows (including threshold overrides where applicable).

  - Theme support (light/dark/auto) and persistent UI preferences.
  - Resizable/collapsible sidebar; runtime mode indicator.
  - Health Scorecards now surface a workspace quality summary with top regressions, top failing rules, and active incidents in the Operations dashboard.
  - A scope-selectable quality history panel now lets operators inspect dataset, rule, domain, and data product drift over time, with explicit degradation and drift event details surfaced in the same observability panel.
  - Workspace health scorecards now separate current failures from worsening trends so operators can tell the active failure state apart from bucket-to-bucket regression.
  - Workspace health scorecards now include domain and data-product quality rollups based on metadata ownership and topology.
  - Incident correlation inputs now appear on incident cards and flow through the support payloads used for ITSM ticket creation.
  - Service-level evaluation now emits explicit breach events for noncompliant active definitions, and the service levels page exposes a manual evaluate action for that path.

## Interfaces

- **Backend API (FastAPI) surface area**
  - Versioned API router mounted under an `api_v1_prefix` (stack typically uses `/api/v1`).
  - Health/readiness endpoints for liveness checks.

- **Auth / SSO integration endpoints**
  - Login/logout, refresh, and OIDC redirect/callback endpoints.
  - Compatibility middleware to support gateway/JWT-based auth patterns.
  - Support-requester resolution now derives the requester email from authenticated claims, so Zammad ticket creation works even when the JWT subject is not the local admin-row id.

- **Rules API**
  - Rule CRUD, validation endpoints (including batch validation), activation.
  - Versioning endpoints: list versions, compare versions, rollback, status history, compiler artifacts.
  - Compatibility endpoints (e.g., alias resolution) to keep older rule shapes usable.
  - Git-first rule registry layout is now canonical in `dq-db/mock-data`, with per-rule and per-version JSON payloads validated by a repo-level layout check before seed/deploy workflows run.

- **Workflow and governance APIs**
  - Approvals endpoints (list/create/update/delete + audit visibility).
  - Governance endpoints including drift/impact views and revalidation job tracking.
  - Status-governance endpoints (status model retrieval by entity).

- **Catalog / metadata interfaces**
  - Data catalog endpoints for data products, data objects, datasets, object versions, attribute catalogs, and delivery views.
  - Federated metadata registry push/pull endpoints now package data products, datasets, data objects, object versions, attributes, and resolved registry definitions for exchange and validation, and exchange snapshots are persisted for audit history.
  - Data asset lineage now surfaces upstream dependency correlation and impact summaries for rules, monitor schedules, and incidents in the data-assets UI.
  - Open Data Product Specification 4.1 for product-level governed meaning, backed by OpenMetadata where applicable.
  - OpenMetadata 1.12.4 runs natively over HTTPS in the local stack, with the mkcert root CA trusted by host-side and ingestion clients.
  - ODCS 3.1 contract serving endpoints plus quality-rules extraction from contracts.

- **Suggestions & profiling interfaces**
  - Suggestions listing and lifecycle actions (accept/dismiss/apply).
  - Profiling enqueue endpoint(s) that feed the profiling worker.
  - Metrics endpoints around suggestions/profiling flows.

- **Testing interfaces**
  - Endpoints for generating test data, starting test runs, persisting test proofs, and retrieving proof history/report views.
  - Batch test request endpoints for grouped/managed test operations.
  - Incident creation and presentation endpoints carry source correlation metadata for downstream support routing and incident review.

- **Great Expectations (GX) interfaces**
  - GX endpoints under a dedicated prefix (e.g., `/gx`) for suite/execution-run related operations.
  - UI includes a GX administration area aligned to these APIs.
  - Real-source execution is live end to end: grouped planning, separate violation persistence, delivery-note enrichment, and run-plan lifecycle support are all implemented.

- **Rule validation and metadata integration**
  - DQ-1 validation logic is fully implemented in the Rule Quality area.
  - API-5 business metadata integration is fully implemented, including catalog-backed alias resolution and governance workflows.

- **Gateway / contract / telemetry conventions**
  - Kong gateway configuration and JWT/OIDC setup docs + scripts.
  - OpenAPI includes “contract metadata” links (e.g., test-proof payload contract) to keep API/contract alignment explicit.
  - Correlation ID + request timing headers, OpenTelemetry instrumentation, and API case enforcement middleware.

## Background processes

- **Profiling worker (dq-profiling)**
  - A standalone worker consuming profiling jobs from Redis, profiling data sources, writing metadata/artifacts to Postgres, and producing rule suggestions.
  - Runs as the `profiling-worker` service in stack mode; supports configurable concurrency.

- **DQ execution engine (dq-engine)**
  - A dedicated execution service that translates rules into Great Expectations expectations, executes them against configured data sources, and returns validation results.
  - The grouped real-source execution path, dispatch handoff, and delivery-linked result reporting are wired through the current API and worker flow.

- **Database lifecycle automation**
  - Database initialization and schema management via `dq-db` init assets plus API-side migrations.
  - Seeding/orchestration scripts to bootstrap demo data and bring up the full stack.

- **Operational validation & smoke checks**
  - Repository-level validation scripts (`scripts/validate_*.sh`) covering key runtime invariants (telemetry/logging contracts, trace propagation, worker lifecycle checks, etc.).
  - Smoke-test scripts to confirm Keycloak/API/UI availability in stack mode.
