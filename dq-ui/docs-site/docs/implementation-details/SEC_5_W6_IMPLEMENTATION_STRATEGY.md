# SEC-5 Workstream 6 Implementation Strategy

## Problem Statement

Currently, the Zammad support stack has **double TLS termination**:
```
Browser → EDGE:443 (terminates TLS with support.jac.dot cert)
       → EDGE routes by path to zammad-https:443
       → zammad-https:443 (terminates TLS with support.jac.dot cert)  
       → zammad-https proxies HTTPS to zammad-railsserver:3000 & zammad-websocket:6042
```

This violates SEC-5 W6-01: "Remove TLS termination from any proxy that currently decrypts client traffic before forwarding it upstream."

## Root Cause

- The edge (dq-edge) uses HTTP path-based routing in PUBLIC mode, which requires TLS termination
- The edge uses SNI passthrough in LOCAL mode but routes to zammad-https:443 which then terminates TLS again
- The zammad-https container terminates TLS and proxies HTTPS to backends, creating the double hop

## SEC-5 W6 Compliance Goal

A non-terminating relay model where:
- TLS is established between client and the final backend service (zammad-railsserver or zammad-websocket)
- No intermediate proxy terminates and re-wraps TLS
- The edge/routing layer uses SNI passthrough or TCP passthrough

## Implementation Strategy

### Phase 1: Local Mode (SNI Passthrough - Immediate Fix)

**Current**: Edge → zammad-https:443 (terminates) → backends

**Target**: Edge → backends directly (SNI passthrough, no intermediate proxy)

**Changes**:
1. Update backend certificates to include the user-facing SNI name (e.g., `itsm.jac.dot`) in the Subject Alternative Names (SAN)
2. Update LOCAL edge mode to route directly to `zammad-railsserver:3000` (not zammad-https)
3. Remove zammad-https from compose when not needed for PUBLIC mode
4. Ensure edge does SNI passthrough (which it already does)

**Technical Details**:
- LOCAL mode already uses `ssl_preread on` and stream module - pure SNI passthrough
- Just need to update the mapping and backend cert configuration
- Browser connects with SNI=`itsm.jac.dot`, edge passes through, backend presents cert with that SAN

**Result**: 
```
Browser → EDGE:443 (SNI passthrough, no termination)
       → zammad-railsserver:3000 (TLS with itsm.jac.dot cert)
```

### Phase 2: Public Mode (SNI-Based Routing - Future Work)

**Current**: Edge → HTTPS proxy routes by `/support/` path

**Target**: Edge → SNI-based routing (requires TLS termination at edge only)

**Challenge**: Path-based routing (`/support/`, `/metadata/`, `/observability/`) requires decrypting HTTP requests, which means TLS termination.

**Options**:
- Option A: Convert all services to support SNI-based routing (e.g., support.example.com, metadata.example.com)
- Option B: Accept that PUBLIC mode edge does TLS termination but backends use native TLS (single termination)
- Option C: Use a different routing model at the application level (Kong routes internally)

**Recommended**: Option B for now - PUBLIC mode edge terminates once, backends are TLS-native.

## Files Affected

| File | Change | Reason |
|------|--------|--------|
| `scripts/create_certs.sh` | Add SAN for user-facing SNI names to backend certs | Backends present correct cert for edge passthrough |
| `dq-edge/docker-entrypoint.d/40-render-edge-config.sh` | Update LOCAL mode to route to backends directly | Remove intermediate zammad-https hop |
| `docker-compose.yml` | Make zammad-https optional or remove from LOCAL profile | Direct routing eliminates need for it |
| `docker/zammad/origin-nginx.conf` | Simplify or remove (if zammad-https is removed) | Not needed in direct routing model |
| `docker/Dockerfile.zammad-origin` | Simplify or remove | Docker image no longer needed |
| `scripts/validate_tls_backend_direct_routing.sh` | NEW: Smoke test for W6 compliance | Validates backends are TLS-native and directly routable |

## Acceptance Criteria for W6 Completion

- [ ] W6-01: No proxy between client and zammad backends (in LOCAL mode)
- [ ] W6-02: LOCAL mode uses SNI passthrough confirmed via validation
- [ ] W6-03: Path-based routing removed from LOCAL (SNI-based now)
- [ ] W6-04: zammad-railsserver and zammad-websocket remain TLS-native
- [ ] W6-05: Architecture gaps documented (PUBLIC mode still uses edge termination)

## Implementation Order

1. Update backend certificates with SAN for user-facing SNI
2. Update LOCAL edge routing
3. Test LOCAL mode end-to-end
4. Make zammad-https optional or remove
5. Document PUBLIC mode strategy
