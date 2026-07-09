# TLS Validation Infrastructure

**Last Updated**: 2026-07-09  
**Purpose**: Reference guide for all TLS validation scripts, framework structure, and how to run checks.

---

## Validation Framework

### Structure

```
scripts/
  validate.sh                            ← top-level wrapper; auto-discovers scripts
  validate_tls_backend_direct_routing.sh ← W6: backends TLS-native, no intermediate proxy
  validate_tls_service_paths.sh          ← W7: major browser, healthcheck, service paths
  validation/
    validate_tls_certificate_inventory.sh        ← cert existence + SAN checks
    validate_tls_trust_bundle_conventions.sh      ← canonical bundle paths
    validate_internal_tls_migration.sh            ← Postgres TLS, HTTP fallback flags
    validate_w6_transparent_tls_routing.sh        ← edge SNI passthrough confirmation
    validate_internal_tls_smoke.sh                ← Kong, OpenMetadata, telemetry paths
    validate_openmetadata_ingestion_tls.sh        ← ingestion config uses HTTPS
    validate_monitoring_baseline.sh               ← Prometheus + alerting rules baseline
    validate_edge_local_ingress.sh                ← LOCAL edge ingress correctness
    ... (60+ additional validators)
```

### Execution Groups

| Group | Command | What it checks |
|-------|---------|----------------|
| `repo` | `scripts/validate.sh repo` | Repo-only, no Docker required |
| `api` | `scripts/validate.sh api` | API + observability smoke |
| `observability` | `scripts/validate.sh observability` | Monitoring/metrics checks |
| `regression` | `scripts/validate.sh regression` | End-to-end regressions |
| `governance` | `scripts/validate.sh governance` | CI gate checks |

### Running on macOS (ARM64)

```bash
# Always wrap with run_keepalive for interactive terminals
scripts/run_keepalive.sh scripts/validate.sh regression

# Check the child process exit code
cat tmp/last_terminal_command_status
```

---

## TLS-Specific Scripts

### Certificate Inventory
**File**: `scripts/validation/validate_tls_certificate_inventory.sh`  
**Checks**:
- mkcert root CA exists at `tmp/certs/mkcert-rootCA.pem`
- Every TLS listener has a matching leaf certificate
- SAN set covers all required hostnames per service

### Trust Bundle Conventions
**File**: `scripts/validation/validate_tls_trust_bundle_conventions.sh`  
**Checks**:
- Canonical bundle at `tmp/certs/trust/internal-ca-bundle.pem`
- All services mount at the documented path
- No ad hoc cert path overrides

### Internal TLS Migration
**File**: `scripts/validation/validate_internal_tls_migration.sh`  
**Checks**:
- No plaintext Postgres connection strings
- Postgres TLS cutover reflected in cert generation
- Flags HTTP service-to-service calls

### W6 Transparent TLS Routing
**File**: `scripts/validation/validate_w6_transparent_tls_routing.sh`  
**Checks**:
- LOCAL mode edge uses `ssl_preread on` (SNI passthrough)
- Support traffic routes to `zammad-railsserver:3000` (not via `zammad-https`)
- No intermediate TLS-terminating proxy in LOCAL routing table
- PUBLIC mode TLS termination documented as accepted gap

### Backend Direct Routing (W6 Smoke)
**File**: `scripts/validate_tls_backend_direct_routing.sh`  
**Checks** (10 tests):
1. Edge uses SNI passthrough (`ssl_preread on`, stream module)
2. No intermediate proxy (`zammad-railsserver:3000` in SNI map)
3. Backend certificate SAN includes edge SNI name (`EDGE_LOCAL_SUPPORT_HOST`)
4. Healthchecks use TLS verification (`--cacert` / `-CAfile`)
5. No HTTP fallback paths (no `listen 80` for backends)
6. Compose YAML valid
7. `zammad-https` marked as optional/deprecated
8. W6 strategy document exists and is complete
9. PUBLIC mode gap documented
10. Git diff clean (no whitespace issues)

```bash
# Run all W6 checks
bash scripts/validate_tls_backend_direct_routing.sh

# Run specific check
bash scripts/validate_tls_backend_direct_routing.sh test_no_intermediate_proxy verbose
```

### Service Path Validation (W7 Smoke)
**File**: `scripts/validate_tls_service_paths.sh`  
**Checks** (12 tests):
1. Browser path: frontend HTTPS
2. Browser path: support (Zammad) HTTPS
3. Service path: API → Keycloak (auth)
4. Service path: API → Kong (gateway)
5. Service path: API/services → Redis (cache)
6. Service path: API/services → Postgres (database)
7. All healthchecks use TLS verification
8. No HTTP ports advertised (no `listen 80`)
9. Browser URLs default to HTTPS
10. No plaintext inter-service URLs in config
11. Smoke coverage completeness (meta-test)
12. TLS path documentation exists

```bash
# Run all W7 checks
bash scripts/validate_tls_service_paths.sh

# Run specific check
bash scripts/validate_tls_service_paths.sh test_service_api_to_postgres verbose
```

### Internal TLS Smoke
**File**: `scripts/validation/validate_internal_tls_smoke.sh`  
**Checks**:
- Kong auth path reachable over TLS
- OpenMetadata cache over TLS
- dq-api telemetry over TLS
- OpenMetadata telemetry path

---

## Exception Registry

Tracking file: `architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md`

### Active Transport Exceptions

| ID | Service | Status | Owner | Target Closure |
|----|---------|--------|-------|----------------|
| ARCH-EXC-0001 | Various (Kong upstreams, API-engine, Redis/Postgres defaults) | approved | Platform Engineering | 2026-12-31 |
| ARCH-EXC-0010 | Airflow HTTP listener (port 8080) | approved | Platform Engineering | 2026-12-31 |
| ARCH-EXC-0011 | zammad-https TLS-terminating proxy (deprecated for LOCAL) | approved | Platform Engineering | 2026-09-30 |

### Approved Permanent Exception

The Ollama-backed LLM front door is an approved TLS termination boundary (mTLS NGINX proxy). This is not a deviation; it is the approved architecture for the LLM access boundary.

---

## Known Gaps (PUBLIC Mode)

PUBLIC mode still uses path-based HTTP routing with TLS termination at the edge. This is documented as **Phase 2** work in [SEC_5_W6_IMPLEMENTATION_STRATEGY.md](/docs/implementation-details/SEC_5_W6_IMPLEMENTATION_STRATEGY/). Options:

1. Convert all services to SNI-routable hostnames (break up `canonical_host` into per-service FQDNs)
2. Accept single TLS termination at edge with TLS re-encryption to backends
3. Use Kong's native TLS capabilities to terminate at Kong rather than at the edge

---

## Related Documents

- [SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN.md](/docs/implementation-details/SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN/)
- [SEC_5_W7_CUTOVER_RUNBOOK.md](/docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK/)
- [SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md](/docs/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE/)
- [TLS_EDGE_ARCHITECTURE_REFERENCE.md](/docs/implementation-details/TLS_EDGE_ARCHITECTURE_REFERENCE/)
