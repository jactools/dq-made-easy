# Release v0.11.5 — SEC-5 End-to-End TLS Enforcement

**Release date**: 2026-07-09  
**UI version**: `0.11.5`  
**API version**: `0.11.5`  

## Summary

This release completes the SEC-5 end-to-end no-HTTP TLS enforcement workstreams (W6 and W7) for the local development stack. All internal service communication in the supported local profile now travels over TLS with certificate verification; no proxy between the browser and an origin service terminates TLS unless it is the approved Ollama mTLS boundary.

## Included in this release

### Infrastructure (W6 — Transparent TLS Routing)

- **Edge SNI passthrough**: `dq-edge` LOCAL mode now routes by `$ssl_preread_server_name` without terminating TLS. The support browser path routes directly to `zammad-railsserver:3000` instead of through the `zammad-https` intermediate proxy.
- **Native TLS listeners**: `zammad-railsserver` binds Puma on `ssl://[::]:3000`; `zammad-websocket` uses the upstream `-s -k -c` flags. Both services own their TLS listener directly.
- **SAN expansion**: `scripts/create_certs.sh` now injects `EDGE_LOCAL_SUPPORT_HOST` into backend certificate SANs so the edge can pass through encrypted traffic without a hostname mismatch.
- **`zammad-https` deprecated for LOCAL mode**: the container is retained for PUBLIC-mode backwards compatibility but is no longer in the LOCAL SNI routing path (see ARCH-EXC-0011).

### Infrastructure (W7 — Validation and Observability)

- **TLS-verified healthchecks**: `zammad-railsserver` and `zammad-websocket` gained `healthcheck` blocks that verify the CA bundle (`--cacert` / `-CAfile`) rather than just testing connectivity.
- **Validation suite**: `scripts/validate_tls_backend_direct_routing.sh` (10 tests) and `scripts/validate_tls_service_paths.sh` (12 tests) confirm no-proxy-termination compliance and pass cleanly.
- **All seven SEC-5 acceptance criteria verified** (see [SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN.md](../implementation-details/SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN.md)).

### Documentation

- [SEC_5_W6_IMPLEMENTATION_STRATEGY.md](../implementation-details/SEC_5_W6_IMPLEMENTATION_STRATEGY.md) — phase strategy, remaining PUBLIC-mode gap
- [SEC_5_W7_CUTOVER_RUNBOOK.md](../implementation-details/SEC_5_W7_CUTOVER_RUNBOOK.md) — per-service migration sequence, rollback, incident response
- [SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md](../implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md) — Prometheus alerts, Loki query patterns, troubleshooting
- [TLS_EDGE_ARCHITECTURE_REFERENCE.md](../implementation-details/TLS_EDGE_ARCHITECTURE_REFERENCE.md) — edge routing modes, service TLS status table
- [TLS_VALIDATION_INFRASTRUCTURE.md](../implementation-details/TLS_VALIDATION_INFRASTRUCTURE.md) — validation script inventory and exception registry
- `.github/copilot/07-tls-transport-enforcement.md` — agent guidance encoding the no-HTTP rule, edge routing model, and cert conventions

### Exception registry

- **ARCH-EXC-0010** added: Airflow HTTP listener (8080), owner Platform Engineering, target closure 2026-12-31
- **ARCH-EXC-0011** added: `zammad-https` TLS-terminating proxy (deprecated for LOCAL mode), owner Platform Engineering, target closure 2026-09-30

## User-visible impact

- The ITSM support portal (Zammad) is now served over a single end-to-end TLS path with no intermediate proxy decryption in LOCAL mode.
- Operators receive a complete cert-generation workflow, TLS troubleshooting guide, and exception registry for auditing and diagnosing the transport posture.
- Automated validation prevents new HTTP regressions from being introduced silently.

## Key implementation files

- [docker-compose.yml](../../docker-compose.yml)
- [dq-edge/docker-entrypoint.d/40-render-edge-config.sh](../../dq-edge/docker-entrypoint.d/40-render-edge-config.sh)
- [scripts/create_certs.sh](../../scripts/create_certs.sh)
- [scripts/validate_tls_backend_direct_routing.sh](../../scripts/validate_tls_backend_direct_routing.sh)
- [scripts/validate_tls_service_paths.sh](../../scripts/validate_tls_service_paths.sh)
- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md](../../architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [TECHNICAL.md](../../TECHNICAL.md)
- [docs/releases/README.md](./README.md)
- [docs/releases/index.md](./index.md)
