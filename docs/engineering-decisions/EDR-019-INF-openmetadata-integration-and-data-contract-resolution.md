# EDR-019 [INF]: OpenMetadata Integration and Data-Contract Resolution Patterns

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: INF

## Context
OpenMetadata-backed contract lookup is now part of repository behavior for dataset and delivery-contract resolution. This path spans API container runtime, service-to-service auth, TLS trust, cached lookups, and dataset-level scope checks.

## Decision
- Resolve data contracts from OpenMetadata through the supported service API rather than local contract files when the feature depends on catalog-owned contract metadata.
- Allow Redis-backed caching for resolved contract metadata, but keep cache availability non-blocking; cache is optional, OpenMetadata is not.
- Enforce dataset-level scope when resolving contract-linked behavior so both sides of a dataset-scoped check resolve within the same dataset boundary.
- Use the repository's OpenMetadata service auth and TLS trust wiring as part of the runtime contract, not as per-feature custom setup.
- Treat OpenMetadata as MySQL-backed in this repository's stack assumptions unless the platform changes explicitly.

## Rationale
- Contract resolution belongs to the metadata system of record.
- Optional cache improves performance without turning Redis into a hard dependency for metadata correctness.
- Dataset-level enforcement avoids cross-dataset ambiguity in contract lookup.
- Shared auth and TLS setup reduces integration drift across API features that call OpenMetadata.

## Scope Boundaries
This decision covers OpenMetadata integration for contract resolution and runtime access patterns.

It does not by itself define:
- full OpenMetadata seeding strategy
- search/indexing behavior
- generic Redis caching conventions for all services

## Consequences
**Positive**
- Contract resolution stays aligned with the metadata system of record.
- Redis cache failure does not block metadata-driven API behavior.
- Service auth and trust configuration are consistent across OpenMetadata-backed flows.

**Negative**
- API features remain dependent on OpenMetadata availability for uncached lookups.
- Integration assumptions must stay aligned with the actual OpenMetadata backend/runtime.

## Implementation Guidance
- Use the shared resolver path for OpenMetadata contract lookups.
- Keep Redis cache TTL explicit and disableable.
- Reuse the repository's Keycloak-authenticated OpenMetadata service access path.
- Keep dataset scoping checks explicit before contract fetch.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-fastapi-openmetadata-data-contract-resolver-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-openmetadata-container-runtime-note.md`
- `/memories/repo/dq-rulebuilder-openmetadata-oidc-auth-note.md`
- `/memories/repo/dq-rulebuilder-openmetadata-mysql-not-postgres-note.md`
