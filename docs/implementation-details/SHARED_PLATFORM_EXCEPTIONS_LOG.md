# Shared Platform Exceptions Log

**Status**: In progress  
**Date**: 2026-08-05  
**Work item**: SHARED-I-W6-05  
**Related**: [Shared Ingestion and SSO Platform Implementation Plan](./SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md)

---

## Purpose

Record all exceptions explicitly — code that is NOT part of the shared platform and why it stays in `dq-made-easy`. This prevents implicit boundaries and makes future extraction decisions deliberate.

---

## Shared Platform Contents (Extracted)

| Package | Contents | Tests |
|---|---|---|
| `platform-auth` | OIDC token providers, JWKS/JWT validation, auth config, scope mapping | 91 |
| `platform-ingestion` | S3 client, bucket/prefix ops, CSV→Parquet via Spark, `stage_csv_to_parquet()` | 17 |
| `platform-ingestion-cli` | Engine-agnostic `engine_type`/`runner_type` dispatch | 7 |
| `platform-testdata` | Schema-driven deterministic generation, 6 output formats, Spark column builders | 25 |
| `platform-foundation` | Config-only package (auth modules moved to `platform-auth`) | 0 |
| `platform-ingestion-runner` image | Shared runtime image for ingestion workloads | N/A |

---

## Exception 1: Ingestion — DQ-owned orchestration

**What stays in dq-made-easy**: Connector framework, connector sync orchestration, connector background worker, GX source-data resolution, profiling ETL, generated test-data materialization, database/application seeding, Kafka violation consumer.

**Why**: These contain DQ-specific business logic, domain entities, workspace semantics, retry policies, and job persistence. They are not generic enough to be shared without significant abstraction that would add complexity without clear benefit.

**Exception justification**: DQ-only. MaaS does not need these flows.

---

## Exception 2: SSO — DQ-owned authorization policy

**What stays in dq-made-easy**: Route authorization policy, auth endpoints and session lifecycle, UI permission model, direct Keycloak JS client, Keycloak realm/client generation, Kong JWKS/bootstrap, JWKS diagnostics/recovery, Airflow OAuth/FAB integration, OpenMetadata OIDC integration, Grafana/Zammad OIDC integration.

**Why**: These contain DQ-specific role mappings, workspace authorization, session persistence, user provisioning, and deployment wiring. The shared platform provides only the low-level primitives (token providers, JWKS/JWT validation, scope mapping).

**Exception justification**: DQ-only. MaaS has its own authorization policy and deployment wiring.

---

## Exception 3: SSO — Trusted-proxy JWT decoder

**What stays in dq-made-easy**: `dq-api/fastapi/app/core/auth.py` JWT payload decoding without signature verification.

**Why**: DQ relies on Kong gateway for JWT signature enforcement. The backend decoder is intentionally lightweight — it checks expiry, issuer, audience, and audience/client-id but does NOT verify the JWT signature. This is a deliberate security boundary: Kong is the trust anchor.

**Exception justification**: DQ-only. This decoder must not be promoted as a shared verifier. The shared platform's `JwtValidator` performs cryptographic JWKS verification and is fail-closed.

---

## Exception 4: Images — DQ-owned runtime images

**What stays in dq-made-easy**: API, engine, frontend, DB, profiling, base, Kong, Kafka, Kafka consumer, Trino, LLM, Zammad origin/seed, Loki wrapper, container metrics.

**Why**: These images contain DQ-specific application code, domain logic, or deployment configuration. They are not generic enough to be shared.

**Exception justification**: DQ-only. MaaS has its own runtime images.

---

## Exception 5: Platform Services — Confirmed migration targets

**What moves to platform-foundation**: Kong, Keycloak, Airflow, LLM, Trino, and the observability stack (Loki, Prometheus, Grafana, Tempo, container-metrics, OTel collector).

**Why**: These services are classified as platform services. Both `dq-made-easy` and MaaS need them, and they have generic mechanics (TLS/trust, health checks, OIDC adapters, catalog configuration) that belong in the shared platform. App-specific configuration (routes, DAGs, agents, datasets, dashboards) stays in each consuming repository.

**Exception justification**: Confirmed. Migration tracked in Workstream 7 of the implementation plan. See [SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md](./SHARED_INGESTION_AND_SSO_PLATFORM_IMPLEMENTATION_PLAN.md) §Workstream 7.

## Exception 6: Images — Remaining conditional candidates

**What may be shared in the future**: Trust-bundle utility, OpenMetadata wrappers, Edge relay, Kafka broker wrapper.

**Why**: These have generic mechanics that could be shared IF MaaS adopts the same baseline. Until a second consumer exists, they remain DQ-owned to avoid premature abstraction.

**Exception justification**: Conditional. Share only when a second consumer (MaaS) needs the same baseline.

---

## Exception 7: Logging and telemetry

**What stays in dq-made-easy**: `dq-utils/src/dq_utils/logging_utils.py` JSON logging and `log_event()` helper.

**Why**: The shared platform provides `platform-logging` and `platform-telemetry` packages, but dq-made-easy still uses the local `dq_utils.logging_utils` for historical reasons. Migration to the shared packages is tracked separately.

**Exception justification**: Temporary. Planned migration to shared platform packages.

---

## Exception 8: MaaS adoption

**What is tracked separately**: All MaaS adoption of shared platform packages.

**Why**: MaaS has its own adoption plan in `metadata-as-a-service/docs/implementation/IMPLEMENTATION_Shared_Platform_Adoption.md`. MaaS is still in draft phase and has not yet adopted any shared platform packages.

**Exception justification**: Out of scope for dq-made-easy workstream. Tracked in MaaS repository.

---

## Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-08-05 | Keep trusted-proxy JWT decoder in dq-made-easy | Kong is the trust anchor; shared verifier is fail-closed |
| 2026-08-05 | Promote Kong, Keycloak, Airflow, LLM, Trino, observability to platform services | Classified as platform services; both dq-made-easy and MaaS need them |
| 2026-08-05 | Defer trust-bundle image sharing | No second consumer yet |
| 2026-08-05 | Defer OpenMetadata wrapper sharing | No second consumer yet |
| 2026-08-05 | Defer Edge relay sharing | No second consumer yet |
| 2026-08-05 | Defer Kafka broker wrapper sharing | No second consumer yet |
| 2026-08-05 | Keep logging in dq_utils | Temporary; migration tracked separately |
| 2026-08-05 | Keep telemetry in dq_utils | Temporary; migration tracked separately |

---

## Review Cadence

This log should be reviewed:
- Before any new extraction from dq-made-easy
- When MaaS adopts a shared platform package
- Quarterly or when the shared platform boundary changes
