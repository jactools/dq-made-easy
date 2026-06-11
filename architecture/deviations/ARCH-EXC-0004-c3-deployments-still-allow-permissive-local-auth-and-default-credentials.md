# ARCH-EXC-0004: C=3 Deployments Still Allow Permissive Local Auth and Default Credentials

**Status**: Approved
**Category**: security
**Owner**: Platform Security
**First recorded**: 2026-04-22
**Last reviewed**: 2026-04-22
**Next review date**: 2026-05-15
**Target closure date**: 2026-09-30
**Risk level**: critical
**Impact level**: high
**Governing baseline**: [ADR-029 EU Financial C=3 Security Baseline Mandate](../adr/ADR-029-eu-financial-c3-security-baseline-mandate.md), [DQ-SEC-EU-C3-001](../../docs/technical/EU_FINANCIAL_C3_SECURITY_REQUIREMENTS.md)

## Affected Surface

Authentication, privileged access, and deployment defaults used by repository-managed local or stack deployment paths that may be reused or copied into higher-assurance environments.

## Summary

Current repository defaults still allow local auth and include multiple default or placeholder credentials that are not acceptable as-is for a `C=3` financial-sector deployment baseline.

## Rationale

The repository has prioritized local bootstrap convenience, demo flows, and environment seeding, but the resulting defaults are too permissive for a high-criticality security baseline unless they are explicitly overridden and controlled.

## Risk Details

Permissive auth modes and default credentials raise the risk of accidental weak deployment posture, insecure copied configuration, and privileged access drift. In a `C=3` context this is incompatible with strong access-control expectations unless tightly bounded and explicitly deviated.

## Impact Details

The gap affects API auth posture, seeded identity credentials, observability admin credentials, metadata defaults, and deployment templates that contributors may treat as valid starting points.

## Compensating Controls

The new `C=3` requirement and checklist now make this gap explicit, and future `C=3` releases must review this deviation before release. Repository-managed higher-assurance deployments are expected to override these defaults rather than accept them.

## Validation and Evidence

- [docker-compose.yml](../../docker-compose.yml) currently includes `ALLOW_LOCAL_AUTH: ${ALLOW_LOCAL_AUTH:-true}` for the API service.
- [docker-compose.yml](../../docker-compose.yml) includes seeded/default credentials such as `CATALOG_OIDC_PASSWORD: ${CATALOG_OIDC_PASSWORD:-${KEYCLOAK_JACCLOUD_PASSWORD:-password}}`, `KEYCLOAK_USER_PASSWORD: ${KEYCLOAK_USER_PASSWORD:-password}`, and `GF_SECURITY_ADMIN_PASSWORD: "changeme"`; local/example environment files also include bootstrap values such as `AISTOR_ROOT_PASSWORD=aistoradmin`.
- [.env.example](../../.env.example) currently includes values such as `ALLOW_LOCAL_AUTH=true`, `KEYCLOAK_JACCLOUD_PASSWORD=password`, `KONG_ADMIN_PASSWORD=kong`, `GRAFANA_ADMIN_PASSWORD=admin`, and `OM_DB_PASSWORD=openmetadata_pass`.

## Exit Criteria

`C=3` deployment paths disable permissive local auth by default, default or placeholder privileged credentials are removed from the supported security baseline, and any remaining bootstrap-only exceptions are tightly scoped and documented.