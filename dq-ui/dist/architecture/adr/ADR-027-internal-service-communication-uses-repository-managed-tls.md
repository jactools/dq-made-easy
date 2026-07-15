# ADR-027: Internal Service Communication Uses Repository-Managed TLS

**Status**: Proposed
**Date**: 2026-04-22
**Related**: [ADR-009](./ADR-009-api-gateway-technology-selection.md), [ADR-015](./ADR-015-opentelemetry-instrumentation-for-distributed-tracing.md), [ADR-016](./ADR-016-iso27001-logging-and-monitoring-policy-adoption.md), [ADR-026](./ADR-026-shell-scripts-must-run-on-macos-and-debian-linux.md)

## Context

The repository currently terminates public HTTPS at Kong and uses a mix of plain internal HTTP and plain transport connections on the private Docker network.

That model is simple to bootstrap, but it leaves several internal surfaces unencrypted even though they carry operationally sensitive traffic such as authentication callbacks, API requests, worker handoffs, telemetry exports, database connections, cache traffic, and object-storage access.

Repository inspection shows the current state clearly:

- internal service URLs are still commonly configured as `http://...` in Compose and env defaults,
- Kong upstream registration currently points to plain internal HTTP services,
- FastAPI currently serves plain HTTP internally,
- several stateful transports still use non-TLS defaults such as `redis://...` or Postgres URLs with `sslmode=disable`,
- partial TLS already exists for some public or semi-public surfaces such as Kong, Keycloak, and OpenMetadata.

Moving all internal communication to TLS is therefore not a single config change. It is a cross-stack architecture change that needs a consistent trust model, explicit service identities, phased rollout, and fail-fast behavior when required TLS configuration is missing.

## Decision

Adopt a repository direction that internal cross-process communication will use repository-managed TLS.

For this ADR, “internal communication” means any network call between containers, services, workers, or supporting infrastructure components that crosses a process boundary, whether over HTTP-based protocols or other network transports.

The decision is:

1. Internal service-to-service communication MUST migrate to TLS as a planned platform capability.
2. The rollout MUST be phased, starting with HTTP and HTTP-adjacent service calls, then expanding to stateful transports such as Postgres, Redis, object storage, search, and telemetry exporters.
3. Internal certificates and trust roots MUST be repository-managed for local and controlled deployment environments, with explicit issuance for service DNS names.
4. Once a service dependency is migrated to TLS, callers MUST use the canonical TLS endpoint and MUST NOT silently fall back to plaintext.
5. If required certificates, trust bundles, or TLS listener settings are missing, affected services and scripts MUST fail fast with clear startup or runtime errors.
6. Internal URL defaults in Compose, env files, scripts, and bootstrap tooling MUST converge on canonical TLS forms as each migration phase lands.
7. Loopback-only probes or in-process calls that do not cross a process boundary are not the primary target of this ADR; the focus is cross-service traffic.

## Consequences

### Positive

- Sensitive internal traffic gains transport confidentiality and endpoint authentication.
- Security posture becomes more consistent between edge traffic and internal platform traffic.
- Trust distribution becomes explicit instead of being an ad hoc per-service concern.
- The no-fallback policy is preserved for transport security: broken TLS wiring fails clearly instead of downgrading quietly.

### Negative

- Local stack bootstrap becomes more complex because service certificates and trust bundles must be generated, mounted, and rotated deliberately.
- More services need TLS-capable listener configuration, upstream config, and health-check changes.
- Stateful dependencies such as Postgres, Redis, AIStor, search, and telemetry collectors may require nontrivial config or image changes.
- Troubleshooting gets harder without shared validation tooling and trust-debugging guidance.

## Implementation Guidance

- Treat internal CA issuance and trust distribution as the first migration dependency.
- Prefer service-DNS certificates over host-only certificates for container-to-container traffic.
- Update Compose env defaults and bootstrap scripts in lockstep with each service migration phase.
- Keep migrations fail-fast: do not add silent plaintext fallback branches for missing TLS configuration.
- Add validation coverage for TLS readiness, certificate presence, trust propagation, and canonical internal endpoint usage.
- Sequence work so that upstream callers switch only after the target listener and trust path are ready.

## Planned Scope Boundary

The implementation track for this ADR is captured in the SEC-1 feature and implementation-plan docs.

- Feature track: [SEC-1 Internal Service-to-Service TLS](../../docs/features/SEC_1_INTERNAL_SERVICE_TLS.md)
- Security feature rollup: [SEC_FEATURES.md](../../docs/features/SEC_FEATURES.md)
- Implementation plan: [SEC-1 Internal Service TLS Implementation Plan](../../docs/implementation-details/SEC_1_INTERNAL_SERVICE_TLS_IMPLEMENTATION_PLAN.md)