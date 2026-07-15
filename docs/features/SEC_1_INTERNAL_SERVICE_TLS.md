# SEC-1 Internal Service-to-Service TLS

Goal: Encrypt internal cross-process platform traffic with repository-managed TLS, explicit trust distribution, and fail-fast behavior when required secure transport dependencies are unavailable.

Related architecture: [ADR-027 Internal Service Communication Uses Repository-Managed TLS](../../architecture/adr/ADR-027-internal-service-communication-uses-repository-managed-tls.md)

Implementation plan: [SEC-1 Internal Service TLS Implementation Plan](../implementation-details/SEC_1_INTERNAL_SERVICE_TLS_IMPLEMENTATION_PLAN.md)

This file defines the stable scope and acceptance contract for the security feature. Progress tracking and implementation sequencing live in the implementation-plan document.

Note: The lists below use stable IDs so tasks and acceptance criteria can be referenced unambiguously across engineering work, validation scripts, and release notes.

## Phase 1: Trust Foundation

- [ ] (SEC1-F-P1-01) Define the internal trust model for local and controlled deployment environments, including the repository-managed CA and trust-bundle distribution path.
- [ ] (SEC1-F-P1-02) Standardize the internal service names and certificate subject alternative names required for container-to-container communication.
- [ ] (SEC1-F-P1-03) Mount or inject trust material into every participating service that acts as either a TLS server or TLS client.
- [ ] (SEC1-F-P1-04) Add canonical secure internal endpoint configuration to env files, Compose surfaces, and bootstrap scripts.
- [ ] (SEC1-F-P1-05) Keep all missing-certificate or missing-trust failures explicit and fail-fast.

## Phase 2: HTTP Service Surfaces

- [ ] (SEC1-F-P2-01) Migrate the API service to an internal TLS listener or a colocated TLS termination layer.
- [ ] (SEC1-F-P2-02) Migrate Kong upstream communication to secure internal service endpoints instead of plain HTTP upstreams.
- [ ] (SEC1-F-P2-03) Migrate internal OIDC and auth-related service calls to canonical HTTPS endpoints.
- [ ] (SEC1-F-P2-04) Migrate worker-to-API, API-to-engine, and metadata-service HTTP calls to HTTPS with shared trust validation.
- [ ] (SEC1-F-P2-05) Update health, readiness, and smoke-test paths so secure transport failures are visible and diagnosable.

## Phase 3: Stateful and Platform Transports

- [ ] (SEC1-F-P3-01) Migrate Postgres connections to TLS-backed connection strings and trust configuration.
- [ ] (SEC1-F-P3-02) Migrate Redis connections to TLS-backed configuration without plaintext fallback.
- [ ] (SEC1-F-P3-03) Migrate AIStor or other S3-compatible object storage traffic to HTTPS.
- [ ] (SEC1-F-P3-04) Migrate telemetry exporter traffic and other platform control-plane calls to trusted TLS endpoints.
- [ ] (SEC1-F-P3-05) Capture any remaining internal transport exceptions explicitly and drive them to zero through tracked follow-up work.

## Phase 4: Operations and Validation

- [x] (SEC1-F-P4-01) Add validation tooling that detects plaintext internal URLs, disabled TLS flags, and missing trust mounts in supported stack profiles.
  - Delivered: `scripts/validate_tls_backend_direct_routing.sh`, `scripts/validate_tls_service_paths.sh`, `scripts/validation/validate_w6_transparent_tls_routing.sh`
- [x] (SEC1-F-P4-02) Add runbooks for certificate generation, trust debugging, and local rotation workflows.
  - Delivered: `docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK.md`, `docs/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md`
- [x] (SEC1-F-P4-03) Add smoke-test coverage for at least one secure path per migrated transport family.
  - Delivered: 22 tests across two validation scripts covering edge, backend, browser, and service paths
- [x] (SEC1-F-P4-04) Ensure observability surfaces expose clear diagnostics when TLS negotiation or trust validation fails.
  - Delivered: Prometheus alert rules and Loki queries in `SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md`
- [x] (SEC1-F-P4-05) Make rollout state visible by documenting which internal surfaces are migrated, pending, or explicitly deferred.
  - Delivered: `TLS_EDGE_ARCHITECTURE_REFERENCE.md` service TLS status table; ARCH-EXC-0010, ARCH-EXC-0011 in exception registry

## Acceptance Criteria

- [ ] (SEC1-F-AC-01) Internal HTTP service calls in the supported stack profiles use HTTPS with repository-managed trust.
- [ ] (SEC1-F-AC-02) Migrated service links fail fast when certificates, trust roots, or TLS listeners are misconfigured.
- [ ] (SEC1-F-AC-03) Kong, workers, and backend services do not silently downgrade migrated internal links to plaintext endpoints.
- [ ] (SEC1-F-AC-04) Stateful transports included in the migration scope use encrypted connections with explicit client trust configuration.
- [ ] (SEC1-F-AC-05) Validation and smoke-test tooling can detect at least one broken-trust scenario and report it clearly.
- [ ] (SEC1-F-AC-06) Operators have a documented certificate-generation and trust-debugging workflow for local stack environments.

## Delivery Milestones

- Milestone A (Trust Plane): `SEC1-F-P1-01` to `SEC1-F-P1-05`
- Milestone B (HTTP Services): `SEC1-F-P2-01` to `SEC1-F-P2-05`
- Milestone C (Stateful Transports): `SEC1-F-P3-01` to `SEC1-F-P3-05`
- Milestone D (Validation and Operations): `SEC1-F-P4-01` to `SEC1-F-P4-05`