# ADR-022: Domain-Driven Design Boundaries for FastAPI

**Status**: Accepted
**Date**: 2026-04-20
**Related**: [ADR-011](./ADR-011-executable-rule-transformation-strategy-dsl-first-with-great-expectations-adapter.md), [ADR-013](./ADR-013-fastapi-api-platform-mandate-and-migration-plan.md), [ADR-017](./ADR-017-canonical-snake_case-api-fields.md), [ADR-021](./ADR-021-core-package-features-first-and-custom-extension-gating.md)

## Context

The FastAPI codebase has been evolving toward clearer internal boundaries, but the migration has been uneven. Some seams already use typed domain entities, repository protocols, and application services, while other seams still let endpoint modules:

- read and shape raw persistence dictionaries directly,
- own Redis or database orchestration inline,
- mix HTTP serialization concerns with domain and infrastructure behavior.

That inconsistency makes it harder to replace persistence details, reuse application logic across entry points, and review changes for architectural drift. It also increases the chance that HTTP-facing code starts depending on infrastructure details instead of stable internal contracts.

The platform needs an explicit architectural rule for how FastAPI modules are structured while preserving the repository's fail-fast policy and canonical snake_case API contract.

## Decision

Adopt a **DDD-oriented boundary model** for FastAPI backend code.

The boundary rules are:

1. Domain entities are the canonical internal data shape.
   - Repository and application-service APIs should return typed domain entities or explicit result objects, not ad-hoc dictionaries.
   - Entities may provide lightweight mapping compatibility only to support incremental migration, not as a license to keep dict-shaped contracts indefinitely.

2. Repository interfaces define persistence-facing contracts.
   - Endpoint modules and middleware must depend on repository interfaces or application services, never directly on ORM sessions or storage tables.
   - Repository implementations live in infrastructure modules and perform the mapping between storage rows and domain entities.

3. Application services own orchestration and infrastructure-heavy workflows.
   - When a use case coordinates multiple repositories, Redis queues, trace propagation, background-worker handoff, or failure translation, that logic belongs in an application service.
   - Endpoint modules may keep thin local wrapper helpers when needed for test stability, but the underlying orchestration must live outside the endpoint module.

4. FastAPI endpoints are HTTP adapters.
   - Endpoints validate request payloads, call repositories or application services, map domain errors to HTTP errors, and serialize responses to the public API contract.
   - Public API JSON remains canonical snake_case even when internal Python models use other attribute names.

5. Fail fast remains mandatory across boundaries.
   - Required services such as PostgreSQL, Redis, worker heartbeats, or downstream APIs must surface explicit failures.
   - Repositories and application services must not silently substitute fallback data or success responses when a required dependency is unavailable.

## Consequences

### Positive

- Infrastructure seams become replaceable with smaller endpoint changes.
- The codebase gets a more consistent testing strategy: repositories can be tested against entity contracts, and services can be tested independently from HTTP transport.
- Endpoint modules become smaller and easier to review because HTTP mapping is separated from orchestration.
- Incremental refactors can converge on a stable target architecture instead of producing one-off local patterns.

### Negative

- Small features may require more files because entity, repository, and service boundaries are explicit.
- Transitional compatibility helpers may exist temporarily while older dict-based callers are being migrated.
- Teams need to decide deliberately whether logic belongs in a repository, service, or endpoint instead of taking the fastest local shortcut.

## Implementation Guidance

- For new backend work:
  - start from a typed domain entity or explicit result object,
  - define or extend a repository protocol when persistence is involved,
  - introduce an application service when orchestration spans multiple dependencies or queue interactions,
  - keep the FastAPI endpoint focused on HTTP adaptation.
- For existing dict-shaped seams, migrate incrementally:
  - add typed entities first,
  - update repository contracts,
  - move orchestration into services,
  - leave compatibility wrappers only where they reduce migration risk.
- Middleware follows the same rule as endpoints: it may enforce HTTP or auth behavior, but persistence access should still come through repository interfaces.
- Tests should validate dependency-failure behavior explicitly to preserve the repository-wide no-fallback policy.

## Related Artifacts

- [docs/features/DQ-5_ADVANCED_DATA_PROFILING.md](../../docs/features/DQ-5_ADVANCED_DATA_PROFILING.md)
- [docs/features/ABS_1_EXECUTION_ABSTRACTION.md](../../docs/features/ABS_1_EXECUTION_ABSTRACTION.md)
- [docs/engineering-decisions/EDR-009-API-api-data-contract-and-snake_case-naming.md](../../docs/engineering-decisions/EDR-009-API-api-data-contract-and-snake_case-naming.md)