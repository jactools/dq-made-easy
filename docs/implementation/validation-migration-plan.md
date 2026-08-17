# Validation Migration: Docker Compose → Kind Cluster

**Date**: 2026-08-17
**Type**: IMPLEMENTATION_PLAN
**Project**: dq-made-easy
**Status**: In Progress

## Summary

Validation scripts migrated from Docker Compose to Kind cluster. Scripts run as K8s Jobs inside the cluster where Service FQDNs resolve correctly.

## Approach

1. **K8s Service FQDNs** — env files now include `*_K8S_URL` vars (e.g. `KEYCLOAK_K8S_URL`)
2. **Validation Jobs** — scripts run inside cluster via `scripts/run_validation_job.sh`
3. **No compose fallback** — Docker Compose support removed from validation scripts

## Completed

### Phase 1: Repo-only scripts (7 scripts)
- `validate_env_file.sh` ✅
- `validate_wf5_env_contract.sh` ✅
- `validate_container_egress_policy.sh` ✅
- `validate_time_synchronization_utc.sh` ✅
- `validate_tls_trust_bundle_conventions.sh` ✅
- `validate_internal_tls_migration.sh` ✅
- `validate_openmetadata_ingestion_tls.sh` ✅

### Phase 2: Observability scripts (4 scripts)
- `validate_dq_api_grafana_otel_smoke.sh` ✅ K8s + port-forward
- `validate_gx_compile_trend.sh` ✅ K8s + port-forward
- `validate_jit_access_requests.sh` ✅ K8s + port-forward
- `validate_natural_language_draft_queue.sh` ⏸️ Deferred (LLM disabled)

### Phase 3: End-to-end scripts (4 scripts)
- `validate_user_login_end_to_end.sh` ✅ K8s Job ready
- `validate_edge_local_ingress.sh` ✅ K8s Job ready
- `validate_edge_public_ingress.sh` ✅ K8s Job ready
- `validate_rule_lifecycle_gx_supported.sh` ✅ K8s Job ready

## Deferred (5 scripts)
- `validate_openmetadata_*.sh` — OpenMetadata not migrated
- `validate_data_definition_api_suggestions.sh` — LLM disabled
- `validate_natural_language_draft_queue.sh` — LLM disabled

## Usage

Run validations as K8s Jobs:
```bash
scripts/run_validation_job.sh validate_user_login_end_to_end.sh --env dev
```

Run repo-only validations locally:
```bash
scripts/validate.sh --env dev repo
```

## Env File Changes

Added `*_K8S_URL` vars to `.env.dev.local`:
- `DQ_API_K8S_URL`, `DQ_ENGINE_K8S_URL`, `DQ_FRONTEND_K8S_URL`
- `KONG_PROXY_K8S_URL`, `KONG_ADMIN_K8S_URL`
- `KEYCLOAK_K8S_URL`
- `GRAFANA_K8S_URL`, `PROMETHEUS_K8S_URL`, `TEMPO_K8S_URL`
- `SSO_PUBLIC_ISSUER_URL` → uses `${KEYCLOAK_K8S_URL}`
- `KONG_PUBLIC_URL` → uses `${KONG_PROXY_K8S_URL}`
