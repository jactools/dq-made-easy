# ADR-013: FastAPI API Platform Mandate and Migration Plan

**Status**: Accepted
**Date**: 2026-03-13

### Context
The platform currently contains API capabilities that evolved over time and now require consolidation on a single API framework to improve consistency, maintainability, performance, and developer velocity.

Requirements driving this decision:
1. Standardize new API development on one backend framework.
2. Migrate existing API endpoints with controlled risk and minimal client disruption.
3. Preserve existing API contract behavior (`/v1/*`, auth, error responses, pagination) during transition.
4. Maintain operational safety with staged rollout and rollback options.

### Decision
1. **FastAPI is the mandatory framework for all new API endpoints.**
2. Existing APIs will be migrated to FastAPI through a phased migration plan.
3. Migration must preserve externally visible contract behavior until a deliberate breaking-change version is approved.
4. Cutover to FastAPI must be gated by parity, reliability, and observability criteria.

### Migration Plan

Phase 0: Contract Baseline and Inventory
- Inventory all current endpoints and dependencies.
- Capture OpenAPI contract baseline and critical behavior checks.
- Define migration waves by risk and business impact.

Phase 1: FastAPI Platform Foundation
- Build shared FastAPI foundation (middleware, auth integration, error model, pagination, correlation IDs, health/readiness).
- Add CI checks for OpenAPI drift and contract compatibility.

Phase 2: Incremental Endpoint Migration
- Migrate low-risk read endpoints first.
- Migrate core mutation and admin endpoints in successive waves.
- Run dual verification (legacy vs FastAPI behavior) during transition.

Phase 3: Controlled Cutover
- Use canary rollout and staged traffic shift.
- Monitor latency, error rates, auth failures, and endpoint-level SLOs.
- Maintain rollback path until stability window is achieved.

Phase 4: Legacy Decommission
- Decommission legacy API implementation after sustained stability.
- Remove deprecated code paths and update runbooks/documentation.

### Consequences

**Positive**:
- Unified backend development model.
- Improved consistency in API behavior and tooling.
- Cleaner long-term ownership and reduced framework fragmentation.

**Negative**:
- Migration overhead for parity testing and staged cutovers.
- Temporary complexity while dual-stack behavior is verified.

### Guardrails
1. No net-new endpoint should be introduced in legacy API stacks.
2. Contract-breaking behavior requires explicit versioning decision.
3. Migration waves must include automated contract/integration tests before cutover.
4. Observability parity is mandatory before production traffic shift.

### Implementation Notes
- This ADR is reflected in planning under `API-6` in `docs/status/roadmap/FEATURE_ROADMAP_OVERVIEW.md`.
- API automation alignment should follow FastAPI defaults (`pytest` + `httpx`) as tracked in `WF-4.10`.
