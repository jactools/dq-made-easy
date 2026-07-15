# ADR-012: Test Automation Tool Selection and Evidence Strategy

**Status**: Accepted
**Date**: 2026-03-13

### Context
The platform requires flexible test automation across UI, API, and DB layers without polluting production runtime images (`dq-ui`, `dq-api`, `dq-db`) with test-only dependencies.

Key requirements:
1. Run tests independently per layer (`ui`, `api`, `db`) and by suite level (`smoke`, `regression`, `full`).
2. Preserve high confidence in browser behavior and critical business flows.
3. Store auditable proof artifacts and machine-readable result data.
4. Support failure analysis and trend reporting for release decisions.

The UI automation choice required explicit selection between Playwright and Cypress.

### Decision

1. **UI test framework default**: Adopt **Playwright** as the default UI automation tool.
2. **Execution model**: Run UI/API/DB automation from dedicated test-runner containers/projects, never from production runtime images.
3. **Evidence model**: Use a three-tier evidence pipeline:
   - Raw run artifacts (trace/video/screenshot/log/JUnit)
   - Queryable result store for trend and flakiness analysis
   - Reporting/analysis dashboards and release-gate metrics
4. **Cypress usage**: Cypress remains an exception option when specific team constraints justify it for a bounded scope.

### Rationale

Why Playwright is the default:
- Multi-browser coverage (Chromium, Firefox, WebKit) from one framework.
- Strong debugging evidence (trace viewer, screenshots, videos, network timeline).
- Robust parallelism and isolation for CI scale.
- Native support for combining UI and API checks in the same toolchain.

Why runner separation is mandatory:
- Keeps production images lean and secure.
- Avoids coupling release artifacts to test framework churn.
- Enables independent evolution of UI/API/DB test stacks.

Why a formal evidence/analysis pipeline is required:
- Supports auditability for release readiness.
- Enables flakiness detection and failure clustering over time.
- Provides objective release gates based on quality trends.

### Consequences

**Positive**:
- Better cross-browser confidence for UI changes.
- Faster and cleaner CI through layer-specific parallel jobs.
- Improved failure diagnosis with richer artifacts.
- Data-driven release decisions from trend analysis.

**Negative**:
- Initial setup cost for dedicated runner projects and orchestration.
- Additional storage/retention costs for rich artifacts.
- Ongoing maintenance of result ingestion and dashboarding.

### Implementation Guidance

1. Build a test orchestration layer (`docker-compose.test.yml`) with profiles (`ui-tests`, `api-tests`, `db-tests`, `smoke`, `full`).
2. Provide a unified command interface (e.g., `scripts/test.sh --scope ui|api|db|all --suite smoke|regression|full`).
3. Persist proof artifacts for each run with run ID, environment, branch, and commit metadata.
4. Publish JUnit plus rich artifacts in CI; forward summarized results to a trend store/dashboard.
5. Define release gates with minimum pass thresholds and maximum tolerated flakiness.

### Scope Boundaries

- This ADR selects default UI tooling and evidence strategy.
- It does not prescribe a single API/DB test framework implementation (tooling may differ by service language and team preference).
- It does not define full CI vendor specifics; only the required quality model.
