# ADR-036: Shared Ingestion and SSO Platform Boundary and Image Ownership

**Status**: Proposed
**Date**: 2026-08-03
**Related**: [Shared Ingestion and SSO Platform Design](../../docs/design/SHARED_INGESTION_AND_SSO_PLATFORM_DESIGN.md)

## Context

`dq-made-easy` already contains real ingestion flows and an SSO integration path that are useful beyond the DQ product itself. MaaS needs both of those capabilities as well, but its implementation is still planned. Both repositories also need a consistent way to consume shared container images and local-dev/service orchestration.

Copying the same ingestion code, auth helpers, and Dockerfiles into both repositories would create avoidable drift. The resulting duplication would make it harder to evolve verification ingestions, harder to keep SSO behavior aligned, and harder to know which repository owns the reusable runtime images.

The repository therefore needs an explicit boundary for what is shared once and what remains application-specific.

## Decision

Adopt a **shared platform boundary** for real ingestion support, SSO/OIDC helpers, reusable container images, and platform services.

The decision has five parts:

1. **Reusable ingestion logic lives outside the application repos.**
   - Source connectors, generic load utilities, fixture-backed real data feeds, and shared ingestion harness code belong in a shared platform package or repository.
   - `dq-made-easy` and MaaS consume that shared code rather than duplicating it.

2. **Reusable SSO/OIDC logic lives outside the application repos.**
   - Common issuer/JWKS validation helpers, claims mapping helpers, and session/callback utilities belong in the shared platform.
   - App-specific authorization policy and route protection stay in each application repository.

3. **Shared runtime images are owned once.**
   - Reusable ingestion and auth-support images are built in the shared platform and published to a registry.
   - Application repositories reference versioned image tags instead of maintaining parallel copies of the same Dockerfile/image definition.

4. **Platform services are owned by the shared platform.**
   - Kong, Keycloak, Airflow, LLM, Trino, and the observability stack (Loki, Prometheus, Grafana, Tempo, container-metrics, OpenTelemetry collector) are classified as platform services.
   - Their Dockerfiles, runtime configuration, TLS/trust mechanics, and version pinning move to `platform-foundation`.
   - Application repositories reference platform service images through the shared image contract.
   - App-specific deployment configuration (routes, DAGs, agents, datasets) stays in each consuming repository.

5. **Application repositories keep thin adapters.**
   - `dq-made-easy` and MaaS own only the glue code needed to configure, invoke, and expose the shared capabilities in their own domain contexts.
   - If behavior differs by product, the difference belongs in the consuming application, not in the shared foundation.

## Consequences

### Positive

- One implementation of shared ingestion and SSO behavior.
- One source of truth for reusable images.
- Less drift between `dq-made-easy` and MaaS.
- Easier future adoption of MaaS SSO and verification ingestions.
- Clearer ownership boundaries for code review and maintenance.

### Negative

- A shared platform dependency introduces version management and release discipline.
- Some migration work is needed to separate reusable code from product-specific glue.
- The repository boundary must be actively maintained to avoid the shared package growing into a second monolith.

## Implementation Notes

- The shared boundary should stay narrow: only code that both repositories genuinely need should be extracted.
- Shared artifacts should be versioned so each repository can adopt changes deliberately.
- Image ownership should be centralized in the shared platform CI/CD pipeline.
- Local development may still use repo-specific overrides, but the canonical shared images should remain centrally built.

## Related Artifacts

- [Shared Ingestion and SSO Platform Design](../../docs/design/SHARED_INGESTION_AND_SSO_PLATFORM_DESIGN.md)
- [Shared Ingestion and SSO Platform Implementation Plan](../../docs/implementation-details/SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md)
