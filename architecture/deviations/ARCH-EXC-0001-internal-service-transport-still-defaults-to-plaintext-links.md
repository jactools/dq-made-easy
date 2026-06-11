# ARCH-EXC-0001: Internal Service Transport Still Defaults to Plaintext Links

**Status**: Approved
**Category**: transport
**Owner**: Platform Engineering
**First recorded**: 2026-04-22
**Last reviewed**: 2026-04-22
**Next review date**: 2026-05-15
**Target closure date**: 2026-12-31
**Risk level**: high
**Impact level**: high
**Governing baseline**: [ADR-027 Internal Service Communication Uses Repository-Managed TLS](../adr/ADR-027-internal-service-communication-uses-repository-managed-tls.md), [SEC-1 Internal Service-to-Service TLS](../../docs/features/SEC_1_INTERNAL_SERVICE_TLS.md), [ADR-029 EU Financial C=3 Security Baseline Mandate](../adr/ADR-029-eu-financial-c3-security-baseline-mandate.md), [DQ-SEC-EU-C3-001](../../docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md)

## Affected Surface

Internal Docker-network traffic across API, Kong, Keycloak, dq-engine, Redis, Postgres exporters, and OpenMetadata-related integration paths.

## Summary

Multiple internal service links still use plaintext defaults such as `http://...`, `redis://...`, and Postgres URLs with `sslmode=disable`.

## Rationale

The current stack was built around public-edge HTTPS with private Docker-network transport inside the stack, and the internal TLS migration has not yet been executed.

## Risk Details

Internal traffic confidentiality and endpoint-authentication guarantees are inconsistent, transport security drift is easy to miss, and the current state blocks progression toward a repository-wide secure transport baseline.

## Impact Details

Kong upstream configuration, API-to-engine traffic, API-to-Keycloak calls, OpenMetadata integration, Redis-backed workers, and Postgres-backed components all require coordinated transport changes.

## Compensating Controls

Traffic stays scoped primarily to the Docker network, public ingress is already TLS-protected on selected surfaces, and SEC-1 now defines a fail-fast migration plan instead of allowing indefinite plaintext defaults.

## Validation and Evidence

- [docker-compose.yml](../../docker-compose.yml) currently includes `KEYCLOAK_PUBLIC_URL: http://keycloak:8080`, `SSO_INTERNAL_ISSUER: http://keycloak:8080`, `DQ_ENGINE_INTERNAL_URL: http://dq-engine:8000`, `REDIS_URL: redis://redis:6379/0`, and Postgres URLs with `sslmode=disable`.
- [bootstrap_kong.sh](../../dq-kong/scripts/bootstrap_kong.sh) still registers `dq-api` with `http://api:4010`.

## Exit Criteria

Internal HTTP callers use secure endpoints, Kong upstreams validate internal TLS, Redis and Postgres surfaces stop using plaintext defaults, and SEC-1 acceptance criteria are met.