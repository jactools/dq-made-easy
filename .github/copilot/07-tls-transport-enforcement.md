# TLS Transport Enforcement Contract

This file captures the active TLS enforcement rules that govern how services communicate within this repository. Agents must preserve these constraints when editing compose files, bootstrap scripts, proxy configs, or service configuration.

## The No-HTTP Rule

Once a service is on a TLS listener, all callers must use TLS. There is no fallback:

- No `http://` service-to-service URLs in compose, env, or code (verified by `scripts/validate_tls_service_paths.sh`)
- No browser-facing URLs that default to `http://`
- No healthcheck that probes `http://127.0.0.1` when the service has a TLS listener
- No proxy that terminates TLS unless it is the approved Ollama mTLS front door

## Edge Routing Model

The local edge (`dq-edge`) uses **two modes**:

| Mode | Routing | TLS |
|------|---------|-----|
| LOCAL | SNI passthrough via stream module (`ssl_preread on`) | No termination at edge |
| PUBLIC | HTTP path-based (`location /path/`) | Terminates at edge, re-encrypts upstream |

**When editing `dq-edge/docker-entrypoint.d/40-render-edge-config.sh`:**
- LOCAL mode SNI map routes directly to backend service ports, not through an intermediate proxy
- Support traffic (`${support_host}`) routes to `zammad-railsserver:3000`, not to `zammad-https:443`
- Adding a new service requires updating the SNI map in `render_local()` and generating a cert with the user-facing hostname as a SAN
- See [TLS_EDGE_ARCHITECTURE_REFERENCE.md](../../docs/implementation-details/TLS_EDGE_ARCHITECTURE_REFERENCE.md)

## Certificate Generation

Run `scripts/create_certs.sh` to regenerate all service leaf certificates. Relevant rules:

- Leaf certs live under `tmp/certs/services/<service-name>/tls.{crt,key}`
- The CA bundle is at `tmp/certs/mkcert-rootCA.pem` — mount this as the trust source, not the leaf cert
- The canonical shared trust bundle is `tmp/certs/trust/internal-ca-bundle.pem`
- Backend certs for services that the LOCAL edge routes to directly must include `EDGE_LOCAL_SUPPORT_HOST` (or the relevant SNI hostname) in their SAN — this is done by passing the env var in `create_certs.sh`
- Never hardcode hostnames in cert generation; derive them from env vars

## Healthchecks

All healthchecks for TLS-native services must verify the certificate, not just the connection:

```yaml
# Correct — verifies CA
healthcheck:
  test: ["CMD-SHELL", "curl -fsS --cacert /etc/service/certs/mkcert-rootCA.pem https://127.0.0.1:3000/health"]
# Also correct for non-HTTP services
healthcheck:
  test: ["CMD-SHELL", "echo | openssl s_client -connect 127.0.0.1:6042 -CAfile /etc/service/certs/mkcert-rootCA.pem 2>/dev/null | grep -q 'Verify return code: 0'"]
```

Plain `curl http://` healthchecks are only acceptable inside a container that has no TLS listener yet, and must be documented in ARCH-EXC-0001 or a successor exception entry.

## Exception Registry

Approved deviations from the no-HTTP rule live in `architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md` under `architecture/deviations/`. Do not introduce a new HTTP surface without adding an exception entry with owner, risk, and retirement date.

Current active transport exceptions:
- **ARCH-EXC-0001** — Various plaintext defaults (Kong upstreams, API-engine traffic, Redis/Postgres); owner: Platform Engineering; target: 2026-12-31
- **ARCH-EXC-0010** — Airflow HTTP listener (8080); no TLS support upstream; target: 2026-12-31
- **ARCH-EXC-0011** — `zammad-https` TLS-terminating proxy retained for PUBLIC-mode backwards compat; target: 2026-09-30

## Validation Scripts

Run these before and after any change touching compose, edge, certs, or healthchecks:

| Script | What it validates |
|--------|------------------|
| `scripts/validate_tls_backend_direct_routing.sh` | No intermediate TLS proxy; backends TLS-native; SNI passthrough works |
| `scripts/validate_tls_service_paths.sh` | Major browser, healthcheck, and service paths work over TLS |
| `scripts/validation/validate_tls_certificate_inventory.sh` | Cert existence, SAN correctness, CA trust chain |
| `scripts/validation/validate_w6_transparent_tls_routing.sh` | Edge SNI passthrough confirmed; PUBLIC mode gap documented |

See [TLS_VALIDATION_INFRASTRUCTURE.md](../../docs/implementation-details/TLS_VALIDATION_INFRASTRUCTURE.md) for the full script inventory.
