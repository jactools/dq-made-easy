# Workflow Enhancements

- [ ] #WF-1 Rule scheduling (depends on #DQ-7 executable transformation)
- [ ] #WF-2 Notifications for approvals
- [x] #WF-3 Rule versioning/rollback
- [ ] #WF-4 Automated testing triggers
- [~] #WF-5 Dedicated dev/test/prod environment contract

## WF-4 Automated Testing Triggers and Flexible Test Orchestration

Goal: Run UI, API, and DB test automation in a flexible manner.

Environment foundation: WF-4 should run local smoke and regression orchestration against the dedicated `test` environment defined in [WF-5 Dedicated Environment Contract and Startup Selection](/docs/features/WF_5_DEDICATED_ENVIRONMENT_CONTRACT/), rather than overloading the developer `.env` or public deployment env file.

Principles
- Support selective execution (`ui`, `api`, `db`, `all`) and suite levels (`smoke`, `regression`, `full`).
- Standardize evidence collection and analysis so failures are diagnosable and auditable.

Scope

1) UI Tool Selection and Strategy
- Default to **Playwright** for cross-browser confidence, robust traces, and combined UI/API support.
- Use **Cypress** only when team/productivity constraints clearly outweigh multi-browser and trace-depth needs.
- Maintain a small smoke suite for PR checks and a broader regression suite for nightly/release.
- Decision and rationale are captured in [ADR-012](/docs/architecture/adr/ADR-012-test-automation-tool-selection-and-evidence-strategy/).

2) API Automation
- Run API tests from a dedicated runner.
- Default to Python-based API automation (`pytest` + `httpx`) aligned with FastAPI.
- Cover both direct API and gateway paths where applicable.
- Add baseline contract checks for critical endpoints and auth flows.

3) DB Automation
- Add migration/schema validation tests and seed-data integrity assertions.
- Use SQL/pgTAP-style checks from dedicated DB test runners against ephemeral DB instances.
- Ensure test DB setup can be recreated reliably from current schema + seed assets.

4) Evidence Collection and Storage
- Collect per-run artifacts: JUnit XML, screenshots, videos, traces, and relevant logs.
- Store raw artifacts in CI artifacts and external object storage keyed by run ID, branch, and commit SHA.
- Keep a queryable test result store for trends (pass rate, duration, flaky history, owner, environment).

5) Failure Analysis and Reporting
- Add automatic failure classification (product defect, test defect, env issue, flaky/timeout).
- Use dashboards for trend analysis (failure hotspots, flaky leaderboard, slowest tests, duration drift).
- Define release gates using smoke/regression pass criteria and flakiness thresholds.

6) Execution Model
- Local: fast smoke suites by default, opt-in full suites.
- Local test: use the dedicated `test` environment as the default target for repeatable smoke/regression orchestration.
- PR: scope-aware checks (run only impacted test domains when possible).
- Main/nightly: full parallel suites across UI/API/DB plus reliability trend analysis.

Acceptance Criteria
- UI/API/DB tests can run independently from dedicated runner images.
- Test execution supports selective scope and suite level via a unified command.
- Every run produces retrievable proof artifacts and machine-readable result output.
- Analysis dashboard can identify flaky tests, recurrent failures, and performance regressions.
- Release gates can be enforced from objective test outcomes and trend thresholds.

Tracked Work Items (Proposed)
- [x] `WF-4.1` Create dedicated test-runner containers/projects (`ui`, `api`, `db`)
- [ ] `WF-4.2` Add `docker-compose.test.yml` with profile-based test orchestration
- [ ] `WF-4.3` Add unified test entrypoint (`scripts/test.sh`) with scope/suite flags
- [x] `WF-4.4` Implement UI smoke and regression suites (Playwright default)
- [ ] `WF-4.5` Implement API contract + integration suites
- [ ] `WF-4.6` Implement DB migration + integrity suites
- [ ] `WF-4.7` Standardize artifact paths and retention policy
- [ ] `WF-4.8` Add result ingestion and dashboard for trend analysis
- [ ] `WF-4.9` Configure CI matrix and release gates
- [x] `WF-4.10` Align local smoke/regression orchestration with the dedicated `test` environment from WF-5
- [ ] `WF-4.11` Define historical test-results retention policy (TTL/size/archive) for `dq-api/fastapi/test-results/history`

Delivery Milestones
- Milestone A (Foundation): `WF-4.1` to `WF-4.3`
- Milestone B (Coverage): `WF-4.4` to `WF-4.6`
- Milestone C (Evidence/Analysis): `WF-4.7` to `WF-4.8`
- Milestone D (Governance): `WF-4.9` to `WF-4.11`

## WF-5 Dedicated Environment Contract and Startup Selection

Goal: standardize dev, local test, and Debian production env files and script selectors so stack startup, seeding, validation, and deployment target explicit lifecycle stages.

Detailed plan: [WF-5 Dedicated Environment Contract and Startup Selection](/docs/features/WF_5_DEDICATED_ENVIRONMENT_CONTRACT/)

Scope
- Replace ambiguous `local` and `deployment` selectors with canonical `dev`, `test`, and `prod` environment names.
- Keep URL audience naming (`*_INTERNAL_URL`, `*_LOCAL_URL`, `*_PUBLIC_URL`) separate from lifecycle stage.
- Make the local `test` environment isolated enough to support WF-4 smoke/regression orchestration.
- Harden the `prod` environment for Debian/public-edge deployment with pinned images, loopback-bound internal services, and explicit TLS paths.

Tracked Work Items (Proposed)
- [x] `WF-5.1` Create tracked env templates for dev, test, and prod
- [x] `WF-5.2` Move legacy local defaults into `.env.dev.example`
- [x] `WF-5.3` Move legacy deployment defaults into `.env.prod.example`
- [x] `WF-5.7` Update startup/stop/seed/pull scripts to accept `--env dev\|test\|prod`
- [x] `WF-5.10` Add fail-fast env-file validation
- [x] `WF-5.13` Update README/deployment/quickstart docs and examples to canonical env names
- [x] `WF-5.14` Update repo-controlled direct Docker Compose examples to canonical local env files
- [x] `WF-5.15` Align WF-4 local smoke/regression orchestration with the dedicated `test` environment
- [x] `WF-5.19` Verify dev startup succeeds
- [x] `WF-5.20` Verify test startup succeeds without sharing dev state
