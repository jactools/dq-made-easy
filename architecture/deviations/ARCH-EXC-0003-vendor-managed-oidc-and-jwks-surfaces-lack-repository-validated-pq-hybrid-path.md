# ARCH-EXC-0003: Vendor-Managed OIDC and JWKS Surfaces Lack Repository-Validated PQ/Hybrid Path

**Status**: Approved
**Category**: vendor-dependency
**Owner**: Platform Security
**First recorded**: 2026-04-22
**Last reviewed**: 2026-04-22
**Next review date**: 2026-05-31
**Target closure date**: 2026-11-30
**Risk level**: high
**Impact level**: medium
**Governing baseline**: [ADR-028 Post-Quantum Cryptography Must Be Implemented by 2026-12-31](../adr/ADR-028-post-quantum-cryptography-must-be-implemented-by-2026-12-31.md), [SEC-2 Post-Quantum Cryptography Readiness](../../docs/features/SEC_2_POST_QUANTUM_READINESS.md), [ADR-029 EU Financial C=3 Security Baseline Mandate](../adr/ADR-029-eu-financial-c3-security-baseline-mandate.md), [DQ-SEC-EU-C3-001](../../docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md)

## Affected Surface

Keycloak-backed OIDC issuer, token, and JWKS paths consumed by API and OpenMetadata-related services.

## Summary

Repository OIDC and JWKS integration surfaces still depend on current Keycloak and OpenMetadata integration behavior, and the repo has not yet validated an approved hybrid/PQ migration path for those vendor-managed auth surfaces.

## Rationale

These auth flows are partly controlled by third-party runtime capabilities and compatibility constraints, and no repository evidence currently shows a validated PQ/hybrid issuer, JWKS, or token-signing path.

## Risk Details

Identity and metadata integrations could become the pacing item for ADR-028 because they sit at the boundary between repository-controlled configuration and vendor/runtime-controlled cryptographic behavior.

## Impact Details

API auth configuration, OpenMetadata auth configuration, JWKS retrieval, and related validation/testing paths may need different treatment from repository-managed transport-only surfaces.

## Compensating Controls

The deviation is explicit, SEC-2 includes a vendor/dependency workstream, and closure requires named evidence rather than assumptions about vendor readiness.

## Validation and Evidence

- [docker-compose.yml](../../docker-compose.yml) currently configures `CATALOG_OIDC_ISSUER` and `CATALOG_OIDC_TOKEN_URL` with `http://keycloak:8080/...`.
- [docker-compose.yml](../../docker-compose.yml) also configures OpenMetadata auth surfaces with `AUTHENTICATION_PUBLIC_KEYS` values that include `http://keycloak:8080/realms/jaccloud/protocol/openid-connect/certs`.

## Exit Criteria

The repository documents and validates an approved hybrid/PQ or otherwise compliant target pattern for these OIDC/JWKS surfaces, or replaces them with a supported alternative and closes the dependency gap.