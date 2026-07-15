# Release Notes — For Users

> **For developers and admins:** See [TECHNICAL.md](./TECHNICAL.md) for API reference, architecture, and deployment details.

## v0.11.5 - TLS Security Hardening and Documentation Refresh (July 9, 2026)

### ✅ What's Updated

- UI package version bumped to `0.11.5`
- Docs-site package version bumped to `0.11.5`
- Version manifest markers updated for the changed tracked components: `Infrastructure`, `Testautomation`, `Documentation`
- Release, deployment, and versioning docs now point at the `v0.11.5` release line

### ✅ New and Improved

- The Definition Mappings user manual now explains the AI-assisted data-definition workflow end to end
- The manual covers draft generation, steward review, board approval, validation, and OpenMetadata import

### ✅ Security and Infrastructure

- Internal transport is now fully TLS end-to-end for the local development stack: no browser request passes through more than one TLS-terminating proxy
- The Zammad support stack (ITSM) now uses native TLS listeners; the support browser path is verified over HTTPS with certificate validation at each hop
- Healthchecks for all TLS-capable services now verify the certificate rather than just testing connectivity
- Automated validation suite confirms no plaintext HTTP regressions across compose, edge, and bootstrap configuration
- Operators have a documented cert-generation workflow, TLS troubleshooting guide, and exception registry to distinguish approved deviations from regressions

## v0.10.5 - Public Documentation Portal (May 22, 2026)

### ✅ What's Updated

- UI package version bumped to `0.10.5`
- Docs-site package version bumped to `0.10.5`
- Version markers in `VERSION_MANIFEST.json` were aligned for the changed tracked component: `Documentation`
- Release, deployment, and versioning docs now point at the `v0.10.5` release line

- The public documentation portal now builds as a Docusaurus site served from `/docs/`
- The public docs build now publishes one unified docs tree that includes `docs/` and `architecture/`
- Copied docs are normalized during the build so internal documentation links and MDX-sensitive Markdown render cleanly in the public portal
- Release, deployment, and versioning docs now point at the `v0.10.5` release line

## v0.10.4 — Natural-Language Rule Drafting Preview Completion (May 17, 2026)

### ✅ What's Updated

- UI package version bumped to `0.10.4`
- API package version bumped to `0.10.4`
- Version manifest markers updated for the changed tracked components: `Authentication`, `Infrastructure`, `DataCatalog`, `Documentation`, and `Testautomation`

### ✅ New and Improved

- The DQ-10 natural-language rule drafting preview is now captured in the current-state docs under `docs/features/current`
- The preview flow remains inside Suggestions, with ranked candidate attributes, explicit steward confirmation, and fail-fast ambiguity handling
- Release, deployment, and versioning docs now point at the `v0.10.4` release line

## v0.10.3 — AIStor Migration and Runtime Stability Alignment (May 13, 2026)

### ✅ What's Updated

- UI package version bumped to `0.10.3`
- API package version bumped to `0.10.3`
- Version manifest markers updated for the changed tracked components: `Authentication`, `Infrastructure`, `DataCatalog`, `Documentation`, and `Testautomation`

### ✅ New and Improved

- Local object storage now runs through AIStor free edition, with the repo-managed license file required explicitly and the app-side storage contract kept generic S3
- Delivery storage, exception storage, seeding, and observability flows now point at AIStor-compatible endpoints and terminology instead of the old MinIO-specific surface
- Keycloak reseeding now treats generated passwords as data instead of flags, so leading hyphens no longer break the login bootstrap path
- The AsyncRequestTrackerProvider mount path now resolves its API, auth, and performance context dependencies correctly, preventing the blank-page render regression in the UI
- Release, deployment, and versioning docs now point at the `v0.10.3` release line

## v0.10.2 — Natural-Language Draft Queue and Infrastructure Health Alignment (May 9, 2026)

### ✅ What's Updated

- UI package version bumped to `0.10.2`
- API package version bumped to `0.10.2`
- Version manifest markers updated for the changed tracked components: `Infrastructure` and `Documentation`

### ✅ New and Improved

- The Suggestions flow now uses a single Accept action that creates the rule directly, and the separate Apply-as-Rule path was removed
- Natural-language rule drafting now supports RapidFuzz vs LLM provider selection, queues LLM requests behind Redis, and tracks request progress in the UI
- dq-llm startup health now passes with the callable registry wrapper, OpenMetadata configure/sync helpers now ship the shared logging support they require, and Grafana infrastructure health now shows dq-llm container status
- Container-metrics and queue dashboards now surface natural-language draft activity end to end
- Release, deployment, and versioning docs now point at the `v0.10.2` release line

## v0.10.0 — DQ7 Migration Closure and Read-Only Reusable Assets (May 4, 2026)

### ✅ What's Updated

- UI package version bumped to `0.10.0`
- API package version bumped to `0.10.0`
- DQ-7 mock-data migration plan marked complete after the canonical `2.0.0` seed rewrite and reusable-asset promotion

### ✅ New and Improved

- Locked rules now surface reusable filter and reusable join icons in the selected rule card
- Read-only reusable modals now show only assigned asset details and hide available/edit controls
- Release, deployment, and versioning docs now point at the `0.10` release line

## v0.9.4 — DQ7 Assistant Runtime Scope (May 4, 2026)

### ✅ What's Updated

- UI package version bumped to `0.9.4`
- API package version bumped to `0.9.4`
- Version manifest markers updated for the changed tracked components: `DataCatalog`, `Templates`, `Documentation`, and `Testautomation`

### ✅ New and Improved

- The DQ7 read-only assistant now reports only actually implemented runtime support, currently GX, instead of surfacing future SodaCL, SQL, PySpark, or custom-worker capability rows
- Assistant guidance now describes GX lowerer behavior and fail-fast limits for supported DQ7 construct families
- Tests cover the implemented-runtime-only assistant response and ensure planned engines are not presented as available runtime support

## v0.9.3 — Read-Only Role Access and Header Badge Alignment (May 2, 2026)

### ✅ What's Updated

- UI package version bumped to `0.9.3`
- API package version bumped to `0.9.3`
- Version manifest markers updated for the changed tracked components: `Admin`, `UserManagement`, `RoleManagement`, `DataCatalog`, `Authentication`, `Documentation`, and `Testautomation`

### ✅ New and Improved

- Auditor and regulator users now see an explicit role badge in the header
- Delivery Inventory now opens for read-only users with data-catalog read access instead of hard-coding admin/data-steward roles
- Admin read pages now follow the same canonical read access contract as the rest of the updated role-based UI

## v0.9.2 — Validation and Docs Alignment (May 1, 2026)

### ✅ What's Updated

- UI package version bumped to `0.9.2`
- API package version bumped to `0.9.2`
- Version manifest markers updated for the changed tracked components: `Authentication`, `Infrastructure`, `Testautomation`, and `Documentation`

### ✅ New and Improved

- Public login and validation helpers now read the selected env end to end, so the Test stack uses the same SSO, Grafana, OpenMetadata, and edge settings as the running compose configuration
- Grafana smoke checks now use a browser-obtained session cookie for OAuth-backed Test deployments instead of assuming basic auth on datasource APIs
- OpenMetadata readiness and trace validation now target the mounted `/metadata/api/v1/system/version` endpoint
- The UI trace-propagation validator now uses the host-published Kong Admin API, and the edge ingress validator now matches the actual selected Test/public render shape

## v0.9.0 — Version Baseline Refresh (April 29, 2026)

### ✅ What's Updated

- UI package version bumped to `0.9.0`
- API package version bumped to `0.9.0`
- Version manifest app and component markers aligned to `0.9.0`

### ✅ New and Improved

- Release-facing docs now use the `0.9.0` release baseline consistently for package metadata and current release references
- Deployment and quick-start examples now show the `0.9-<hash>` release line for deterministic image tags
- Automatic versioning guidance now uses the `0.9.0` bump path and `0.9-<hash>` derived tag examples

## v0.8.9 — Uniform Environment Contract and URL Audience Alignment (April 28, 2026)

### ✅ What's Updated

- UI package version bumped to `0.8.9`
- API package version bumped to `0.8.7`
- Version manifest markers updated for the release and changed tracked components: `Infrastructure`, `Authentication`, and `Documentation`

### ✅ New and Improved

- Environment variables for routable endpoints now follow one explicit audience-based contract across env files, Compose, and the main script surface: `*_INTERNAL_URL`, `*_LOCAL_URL`, and `*_PUBLIC_URL`
- Host-local startup, validation, and maintenance flows now use explicit local URLs instead of overloading public browser-facing variables for readiness probes or operator calls
- Frontend runtime API configuration now uses `KONG_PUBLIC_URL` for the browser-facing container contract, while local UI/dev flows use `KONG_LOCAL_URL`; the older `DQ_UI_API_URL` live runtime path has been removed
- Current-facing deployment, startup, and release docs now describe the canonical env contract directly, while older implementation notes that still mention superseded names are marked as historical

## v0.8.8 — Startup, Reseed, and Migration Alignment (April 27, 2026)

### ✅ What's Updated

- UI package version bumped to `0.8.8`
- API package version bumped to `0.8.6`
- Version manifest markers updated for the release and changed tracked components: `Infrastructure` and `Documentation`

### ✅ New and Improved

- Startup now runs an `api-migrate` one-shot step before the API service starts, which makes migration ownership explicit during normal stack boot
- Deployment startup and support/seed helper services now follow the selected env file end to end instead of silently reading only the repo `.env`
- Containerized Postgres reseeding now uses the current workspace seed and migration sources through the `db-seed` service, so reseeding no longer depends on a rebuilt `dq-api` image to apply current seed logic
- Startup help text and logs now state how `--no-build`, `--force-build`, the one-shot migrator, and reseed behavior interact

## v0.8.7 — Governance and Operations Navigation Alignment (April 27, 2026)

### ✅ What's Updated

- UI package version bumped to `0.8.7`
- API package version remains `0.8.5`
- Version manifest markers updated to `0.8.7` for the UI release and changed tracked components: `Approval`, `Shared`, `Documentation`, `Report`, and `Telemetry`

### ✅ New and Improved

- Rule-related navigation now exposes `Governance` and `Operations` as the visible section names instead of the older interim `Approvals` and `Reports` labels
- The governance overview now lives under Governance, while execution monitoring, aggregation, metrics, and validation results stay grouped under Operations
- UI page telemetry now normalizes approval and report routes to `governance` and `operations`, keeping product naming aligned with analytics naming
- Walkthrough and current-state docs now describe the live `Rules` / `Rule Quality` / `Governance` / `Operations` information architecture consistently

## v0.8.6 — UI Selector and Header Navigation Alignment (April 27, 2026)

### ✅ What's Updated

- UI package version bumped to `0.8.6`
- API package version remains `0.8.5`
- Version manifest markers updated to `0.8.6` for the UI release and changed tracked components: `Approval`, `Rules`, `Admin`, `Shared`, `Templates`, `Settings`, `Report`, `DataCatalog`, and `Documentation`

### ✅ New and Improved

- Workspace-scope switching now uses the same segmented pill control across the Data Catalog, Operations, Assign Attributes, Rules, Governance, and Templates screens, so scope changes look and behave consistently
- Rules now uses the same compact segmented/filter styling as the other updated screens, including a fix for the old filter-group CSS collision that wrapped the Status dropdown in the wrong pill container
- Admin Application Settings now keeps its “Jump to section” navigation attached to the header as segmented pills instead of letting that control scroll away inside the page body
- User Settings now moves the old left-side tab rail into the header as segmented pills for Profile, Notifications, Display, and Preview Features, while workspace configuration lives under Administration

## v0.8.5 — Build, Reseed, and Validation Alignment (April 26, 2026)

### ✅ What's Updated

- UI package version bumped to `0.8.5`
- API package version bumped to `0.8.5`
- Version manifest markers updated to `0.8.5` for the release and changed tracked components: `Infrastructure`, `Documentation`, and `Testautomation`

### ✅ New and Improved

- Full-stack startup with `--seed-all --init-db` now reseeds Postgres before the API is started and keeps the API and `db-seed` images on the same migration snapshot, avoiding unhealthy API startup loops during fresh-stack initialization
- The build wrapper now distinguishes the core publishable image set from the wider repo-managed image set, so operators can choose between the standard product build and the full custom-image build path explicitly
- Automatic image tags now follow the actual Docker build inputs for each image instead of a narrow `Dockerfile + src/` approximation, improving determinism for frontend assets, seed containers, and other repo-managed images
- The validation runner default `all` group now truly runs the included smoke scripts together with the included `validate_*.sh` scripts, so default validation coverage matches operator expectations

## v0.8.4 — Edge Ingress and Startup Environment Selection (April 26, 2026)

### ✅ What's Updated

- UI package version bumped to `0.8.4`
- API package version bumped to `0.8.4`
- Version manifest markers updated to `0.8.4` for the release and changed tracked components: `Infrastructure`, `Authentication`, `Documentation`, `Telemetry`, and `Testautomation`

### ✅ New and Improved

- The stack now supports a single edge ingress layer that keeps local `*.jac.dot` host-based routing and public `jacloud.nl` / `www.jacloud.nl` path-prefix routing aligned in the same compose model
- Public routing is prepared for `/iam`, `/metadata`, `/observability`, `/support`, and `/ops/kong`, while non-edge services stay loopback-bound by default in the public deployment template and local runtime copy (`.env.deployment.example` -> `.env.deployment.local`)
- `common_startup.sh` and the downstream startup chain now support `--env local|deployment`, `--env-local`, `--env-deployment`, and `--env-file PATH`
- The selected env file now propagates through Docker Compose startup, seeding flows, and the local Vite UI helper instead of assuming a hard-coded repo `.env`
- Focused ingress validators were added for both local and public edge modes so the routing model can be checked without a full public deployment

## v0.8.3 — Version Alignment and Architecture Documentation Refresh (April 25, 2026)

### ✅ What's Updated

- UI package version bumped to `0.8.3`
- API package version bumped to `0.8.3`
- Version manifest markers updated to `0.8.3` for the release and tracked components

### ✅ New and Improved

- API layering and DDD architecture docs now reflect the current FastAPI adapter split, application use-case seams, typed repository/domain boundaries, and fail-fast runtime composition
- Standalone Mermaid source diagrams and generated SVG assets were refreshed so the published architecture visuals match the written docs
- Latest-release pointers and release-facing documentation were synchronized to the new patch version without rewriting prior release history

## v0.8.2 — Delivery Inventory, UI Alignment, and Offline Seeding Support (April 21, 2026)

### ✅ What's Updated

- UI package version bumped to `0.8.2`
- API package version bumped to `0.8.2`
- Version manifest markers updated to `0.8.2` for the release and tracked UI components

### ✅ New and Improved

- Delivery inventory can now load storage-backed file names and object counts on demand without hitting storage by default
- Delivery notes now surface explicit warnings for unsupported delivery formats
- Seed generation now supports parquet, csv, json, avro, delta, and iceberg, with Spark jars baked into the dq-engine image for offline runtime use
- Mock delivery data and OpenAPI artifacts were refreshed to keep the new delivery formats and note views aligned
- Definition Mappings now uses shared app-owned controls and shared light/dark theme tokens
- Additional pages now inherit light/dark mode through shared semantic tokens instead of page-local dark-mode branches
- UI portability and UI-consistency decisions are now documented so frontend pages stop assuming the current vendor library in feature code and styles

## v0.8.1 — Zammad Support Requester Resolution (April 15, 2026)

### ✅ What's Updated

- API package version bumped to `0.8.1`
- Version manifest API marker updated to `0.8.1`

### ✅ Fixes

- Assistance requests now resolve the requester email for Zammad tickets from the authenticated user claims when the stored user id is not the local admin-row id
- Zammad ticket creation no longer fails with "Unable to resolve the requester email for the Zammad ticket" for valid authenticated users

## v0.8.0 — Delivery Resolution, Delivery Notes, and Seeded GX Coverage (April 13, 2026)

### ✅ What's Updated

- dq-made-easy UI and API packages bumped to `0.8.0`
- Version manifest markers updated to `0.8.0` for the release and tracked components

### ✅ New and Improved

- Delivery inventory now shows workspace-scoped deliveries together with storage presence and object counts
- Delivery notes now capture extended delivery metadata and open in a dedicated detail panel
- Delivery resolution now supports latest delivery identifiers and delivery locations for data object versions
- Seed data now covers delivery notes, GX suites, run plans, execution history, and validation history through CSV-first sources
- OpenAPI documents and UI release-note assets were refreshed to reflect the new delivery and GX surfaces

## v0.7.5 — API Patch Release: SSO & Observability Reliability (April 8, 2026)

### ✅ What's Updated

- API package version bumped to `0.7.5`
- Version manifest markers updated for the API and affected platform components

### ✅ Fixes & Improvements

- Single Sign-On redirects are now reliably handled via the public auth endpoints (no more unexpected authorization failures during the SSO redirect/callback)
- SSO provider independence is strengthened with generic OIDC discovery and internal issuer fallback, improving local Keycloak/Kong login reliability
- API request metrics (throughput, error rate, and latency) are now consistently captured, including for requests that fail early during authorization checks
- Kong gateway bootstrap and validation scripts were aligned to the group-first routing scheme

### ✅ Operational Reliability

- Startup tooling supports a true fresh rebuild via `--force-build` to avoid running stale images after pulling changes

## v0.7.4 — UI Patch Release: Group-First Routing Compatibility (April 8, 2026)

### ✅ What's Updated

- UI package version bumped to `0.7.4`
- Version manifest markers updated for the UI and affected components

### ✅ Fixes

- The dq-made-easy UI no longer crashes on startup after the routing migration
- API calls throughout the UI were aligned to the group-first routing scheme (auth, admin, system, rulebuilder, and data-catalog)
- In-app release notes and documentation continue to load correctly after the migration

## v0.7.3 — Patch Release: Settings & Rule Workflow Reliability (April 3, 2026)

### ✅ What's Updated

- UI package version bumped to `0.7.1`
- API package version bumped to `0.7.3`
- Version manifest markers updated for UI/API and affected components

### ✅ Fixes

- Notifications: “Mark all as read” now correctly resets the bell counter (including system approval notifications)
- Templates: “Create from Template” no longer crashes when selecting templates
- Rules list: newly created rules (including template-based rules) reliably appear in “My Rules”
- Preview features: preview opt-in now persists across logout/login; Rule Suggestions are visible when enabled
- Settings: save failures are now surfaced instead of silently failing

### ✅ Operational Reliability

- Healthchecks can use the public `/health` endpoint (non-`/v1`) without requiring Kong routing

## v0.7.2 — Migration Closure and Contract/Auth Validation (March 29, 2026)

### ✅ What's Updated

- API package version bumped to `0.7.2`
- Version manifest API marker updated to `0.7.2`

### ✅ FastAPI Migration Checklist Closure

- Contract and auth-focused test suites were completed and validated
- Health compatibility alias parity (`ready` and `live`) remains covered and validated
- Migration baseline checklist items for contract/auth tests and docs/version updates are now closed

### ✅ Version Metadata Reliability

- Live version metadata alignment checks now validate current API version values from the manifest-backed catalog

## v0.7.1 — Rules Soft-Delete and Recovery Governance (March 29, 2026)

### ✅ What's Updated

- API package version bumped to `0.7.1`
- Version manifest API marker updated to `0.7.1`

### ✅ Rules Lifecycle Governance

- Rules are now soft-deleted only, never hard-deleted from storage
- Rule removal is only allowed after deactivation has been approved
- Admins can recover removed rules through the admin rules recovery API
- Recovered rules re-enter the approval flow before activation

### ✅ Lifecycle Guardrail

- Removed rules are blocked from approval resubmission until they are explicitly recovered by an admin

## v0.7.0 — Contract Alignment & Quality Gates (March 28, 2026)

### ✅ What's Updated

- UI package version bumped to `0.7.0`
- API package version bumped to `0.7.0`
- Version manifest app markers updated to `0.7.0`

### ✅ UX and API Behavior Improvements

- Workspace and identity handling are now strictly canonical across UI screens and hooks
- Legacy fallback chains for mixed field names were removed in favor of single-source attribute contracts
- Approval/requester ownership matching now uses exact canonical identity fields only

### ✅ Testing and Validation

- Frontend test suite passing (Vitest)
- Backend test suite passing with required coverage gate satisfied
- Fixture-usage policy enforcement now passes in the official backend unit script

## v0.6.1 — Patch Release (March 22, 2026)

### ✅ What's Updated

- UI package version bumped to `0.6.1`
- Version markers and documentation references aligned to `0.6.1`
- Release notes history corrected so the Rule Validation feature release remains tracked under `v0.6.0`
- Rule Validation documentation now reflects standard availability and the current `Rule Quality -> Rule Validation` rollout path

---

## v0.6.0 — Rule Validation (March 19, 2026)

### ✅ What's New

#### ✔️ Validate Rules Before You Activate Them
A new **Rule Validation** panel lets you validate one rule, a filtered subset, or your entire workspace in one flow — without touching production data.

**What you should notice:**
- In the current rollout, Rule Validation is available as a standard feature under *Rule Quality -> Rule Validation*.
- Rules now include direct entry points that open the broader Rule Validation workspace with the selected rule context.
- Search and filter rules quickly (by name, ID, or version)
- Click **Validate All** to validate all currently visible (filtered) rules
- Select specific rules to validate only the chosen subset
- Each rule shows a green tick (valid) or red cross (invalid) with expandable diagnostics
- Rule versions are shown next to rule names in selection/results/history details
- Errors and warnings are explained in plain language with a short check code so you know exactly what to fix

**Checks performed:**
- Empty or blank filter expressions
- Expression syntax errors (mismatched brackets, unknown operators, etc.)
- Disallowed SQL keywords inside expressions
- Missing alias mappings referenced in an expression
- Structural issues in join definitions

#### ⚠️ Spot Duplicate and Contradictory Rules
After a batch validation, a **Cross-Rule Conflicts** section highlights problems across your workspace:

- **Duplicate expression** — two rules share exactly the same filter logic
- **Duplicate name** — two rules have the same name (case-insensitive)
- **Contradictory predicates** — the same field is constrained in two logically opposite ways (e.g. `age > 50 AND age < 10`)

#### 📋 Keep a Full Validation History
Every validation run is saved automatically. The **Validation Run History** table shows your last 10 runs. Click any run to see the per-rule breakdown, or download the results as a **CSV** for use in spreadsheets and audit reports.

#### 🧾 Business Evidence Reports for Test Results
Rule test evidence can now be exported as:

- **Markdown (.md)**
- **PDF (.pdf)**

Each report is written in business terms and includes:

- What went good
- What went wrong
- Coverage and success metrics
- Tested attributes
- Version-difference summary between rule versions (when applicable)

In the rule details panel, you can also preview the business report before downloading.

> **Full user guide:** [docs/features/DQ-1_RULE_VALIDATION_USER_GUIDE.md](docs/features/DQ-1_RULE_VALIDATION_USER_GUIDE.md)

---

## v0.5.0 — Rule Test Experience (March 16, 2026)

### ✅ What's New

#### 🎯 Target Specific Attributes When Running a Test
When a rule is assigned to more than one attribute, you can now choose exactly which attribute(s) a test run should cover — right inside the *Test Rule* dialog.

**What you should notice:**
- A checklist of assigned attributes appears in the Test Rule dialog before you run
- Use *Select all* or *Clear* to manage the selection quickly
- Tests that span attributes from different data-object versions are blocked upfront with a clear message, preventing ambiguous results
- Every saved test result now records which attributes were tested

#### 📋 See Tested Attributes in Test Results
The test-results table now includes an **Attributes** column so you can see at a glance which attributes each test run covered.

#### 💬 Plain-Language Test Explanation
After a test completes, a **"What does this mean?"** button appears in the rule-details panel.

Clicking it opens a plain-English summary that explains:
- How many records were tested and what percentage passed
- Which data source and quality dimension were used
- Which attributes were included in the test
- **Why records failed** — a short analysis listing likely causes such as blank or missing fields, with a representative example from the failing data

### ✅ Fixes Included

- **Zero-record runs no longer pass as success.** A test that generates no records is now blocked at both the API and the UI with a clear error message.
- **Test dialog now closes automatically** after a successful test run.

---

## v0.4.0 — API Platform Migration Complete (March 16, 2026)

### ⚙️ Under the Hood

This release completes a major infrastructure milestone. The backend API has been fully migrated from the legacy Node.js server to a modern Python/FastAPI platform. **You will notice no changes** to how the application works — all features, endpoints, and auth flows remain identical.

**What changed behind the scenes:**
- The backend API now runs on FastAPI (Python) instead of NestJS (Node.js)
- Faster response times and improved reliability on all API calls
- Cleaner error messages for edge cases
- No API contract changes — the same routes, auth, and response shapes you depend on

**If you are a developer or operator**, you will need to rebuild the API service after pulling this version:
```bash
docker compose up -d --build api kong
```
See [TECHNICAL.md](./TECHNICAL.md) for full details.

---

## v0.3.3 — Development Mode Icon Fix (March 13, 2026)

### ✅ What Was Fixed

#### 🖼️ Icons Now Display Correctly in All Environments
Icons were missing in the Vite development server (port 5174) while working fine in the built/Docker frontend (port 5173). This has been resolved.

**What you should notice:**
- All icons render correctly regardless of how you access the app locally
- No broken icon placeholders or missing UI elements in dev mode

### ✅ Fixes Included

- Fixed a duplicate web-component runtime bundle import that caused a Stencil stylesheet initialization error in Vite dev mode
- Fixed icon asset path resolution so the Vite dev server correctly serves both hashed and non-hashed icon paths

---

## v0.3.2 — SSO Reliability & Auth Stabilization (March 11, 2026)

### ✅ What Was Fixed

#### 🔐 Single Sign-On Now Works End-to-End
The full Keycloak SSO login flow through Kong Gateway is now stable and reliable.

**What you should notice:**
- Logging in via SSO no longer returns a gateway error or gets stuck
- Your session is recognized correctly after the login redirect
- The app loads your profile and workspaces immediately after SSO login

#### 🏎️ No More Random "Unauthorized" Errors After Login
Under load or when multiple browser tabs were open, some requests would fail with a 401 even though you were logged in. This has been completely resolved.

**What changed behind the scenes:**
- Each request now carries its own isolated authentication context
- Concurrent requests no longer interfere with each other's login state

### ✅ Fixes Included

- Fixed SSO callback to pass the correct token type to Kong Gateway
- Fixed user profile resolution after SSO redirect
- Fixed an edge case where the wrong issuer URL was used inside the container network
- Resolved a race condition that caused intermittent 401 errors under concurrent load
- Aligned Keycloak redirect URI with the backend API path
- Improved Kong JWT credential setup to handle both internal and external hostnames

---

## v0.3.0 — Kong Gateway, Reliability & UX Fixes (March 3, 2026)

### ✨ What's New

#### 🌐 Kong Gateway as Standard API Entry Point
All frontend traffic now consistently goes through Kong Gateway, with automatic startup seeding and stable route setup.

**What changed?**
- Kong configuration now auto-seeds on stack startup
- API routing standardized on `/v1/*`
- CORS policy corrected for localhost development
- Kong Manager is now the standard admin UI (`:8002`)
- Konga removed from the stack

#### 🔐 Login & Data Loading Stability Improvements
We fixed endpoint mismatches that caused login and data screens to fail after stack restarts.

**You should notice:**
- Login succeeds without "Load failed" errors
- Settings and app config load correctly
- Rules and Data Products are visible immediately after login
- Fewer browser console errors related to CORS/404

### ✅ Fixes Included

- Fixed frontend auth/settings endpoints to use `/v1/login` and `/v1/me`
- Normalized multiple UI API calls to `/v1/*`
- Fixed Kong seed restart loop by correcting CORS schema fields
- Improved startup/shutdown scripts to handle profile-based services reliably
- Removed ARM-incompatible Konga from compose to avoid platform warnings

---

## v0.2.0 — Rule Suggestions (March 1, 2026)

### ✨ What's New

#### 🎯 AI-Powered Rule Suggestions
We've added an intelligent recommendation system that helps you discover and create data quality rules faster. The system analyzes your data and suggests validation rules based on common patterns.

**What can it do?**
- Automatically detect missing value patterns and suggest NOT_NULL rules
- Identify unique key candidates and suggest UNIQUENESS constraints
- Recognize data format patterns and suggest FORMAT_VALIDATION rules
- Provide confidence scores (High/Medium/Low) so you can prioritize recommendations
- Explain the reasoning behind each suggestion

### 📊 How to Use Rule Suggestions

#### Step 1: Access the Feature
1. Go to **Suggestions** in the sidebar menu
2. Or enable it in **Settings → Display → Preview Features** if you don't see it yet

#### Step 2: Request Data Analysis
1. Select a data source from the dropdown
2. Click **"Run Data Profiling"** to analyze your data
3. Watch the status updates as profiling runs (typically 30 seconds to a few minutes)

#### Step 3: Review Generated Suggestions
Once profiling completes, you'll see a list of suggested rules with:
- **Rule name & description** — What the rule does
- **Confidence badge** — How confident we are (shown as High/Medium/Low with percentage)
- **Rule type** — The category (Uniqueness, Format Check, Required Fields, etc.)
- **Why this rule?** — The reasoning behind it
- **New badge** — Highlights recently generated suggestions

#### Step 4: Take Action
For each suggestion, you have three options:

| Action | Purpose |
|--------|---------|
| ✅ **Accept** | Mark it as useful for reference (can accept and apply later) |
| ➜ **Apply as Rule** | Create a new rule from this suggestion (ready for testing) |
| ✗ **Dismiss** | Remove if not relevant |

### 💡 Common Workflows

**Discover Rules Fast (3 minutes)**
```
1. Open Suggestions
2. Select your main data source
3. Click "Run Data Profiling"
4. Wait for completion
5. Click "Apply as Rule" on high-confidence suggestions
6. Review new rules in the Rules section
```

**Audit Patterns (10 minutes)**
```
1. Run profiling on a data source
2. Review explanations ("Why this rule?")
3. Accept suggestions that align with business rules
4. Dismiss ones that don't apply
```

**Batch Create Rules (15 minutes)**
```
1. Run profiling
2. Sort by confidence (high → low)
3. Apply all high-confidence suggestions
4. Review & test the new rules
```

### 📋 What Gets Suggested?

**Rule Types:**
- ✓ **NOT_NULL** — Fields that must have values
- ✓ **UNIQUE** — Fields that should have no duplicates
- ✓ **FORMAT_VALIDATION** — Email, phone, postal code patterns
- ✓ **RANGE_CHECK** — Number or date boundaries
- ✓ **REFERENTIAL_INTEGRITY** — Related data consistency

### ⏱️ Timing & Limits

**Profiling Duration:**
- Quick datasets: 30 seconds
- Medium datasets: 1-3 minutes
- Large datasets: 3-10 minutes
- Status updates every 5 seconds (you can watch progress!)

**Rate Limiting:**
- You can profile each data source once every 30 minutes
- This prevents excessive resource usage
- If you try too soon, you'll see how long to wait

### 🎯 Tips & Tricks

✅ **Do:**
- Start with high-confidence suggestions (80%+)
- Read the "Why" explanation to understand the pattern
- Accept first, then apply when ready
- Test suggested rules before approving
- Dismiss suggestions that don't fit your data model

❌ **Don't:**
- Profile the same source more than once per 30 minutes (cooldown enforced)
- Apply all suggestions without review
- Ignore low-confidence suggestions (they may still be useful)
- Forget that suggested rules need testing before approval

### 🐛 Known Limitations

- Works best with SQL databases (first version)
- Confidence is based on pattern heuristics (not ML yet)
- Suggestions expire after 30 days
- One profile at a time per source (rate limited)

### ❓ FAQ

**Q: How confident should I be in these suggestions?**
A: High confidence (80%+) is pretty reliable. Medium (60-80%) worth reviewing. Low (<60%) for discovery only.

**Q: What if a suggestion is wrong?**
A: Simply dismiss it. Your feedback helps us improve!

**Q: Can I profile multiple sources at once?**
A: You can request them, but they queue up one at a time to avoid overloading the system.

**Q: Will this slow down the application?**
A: No! Profiling runs in the background and doesn' impact other work.

**Q: Can I undo applying a suggestion?**
A: Yes! It creates a new rule that you can delete or modify like any other.

**Q: Do I need special permission to use this?**
A: You need "Analyst" or "Admin" role to request profiling. Anyone can review and apply suggestions.

### 🚀 What's Coming Next?

We're working on:
- Bulk actions (apply/dismiss multiple at once)
- Better filtering and search
- Custom profiling rules
- Smarter confidence scores
- Multi-source profiling in parallel
- Your feedback on what matters most!

### 📚 Need Help?

- **Can't find Suggestions?** → Check Settings → Display → Preview Features → "Participate in preview features"
- **Profiling taking too long?** → Might be a large dataset, check back in a few minutes
- **Hit cooldown limit?** → Come back in 30 minutes per data source
- **Questions?** → Check the FAQ section above or contact your administrator

---

## v0.1.0 (Initial Release)

**Core features:**
- Create, test, and manage data quality rules
- Approve and track rule changes
- View audit trail of all activities
- Configure user preferences
- Dark mode support
