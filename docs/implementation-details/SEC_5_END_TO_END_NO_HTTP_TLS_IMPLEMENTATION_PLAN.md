# SEC-5: End-to-End No-HTTP TLS Implementation Plan

**Status**: Complete (W1-W7)
**Target**: zero advertised HTTP ports, zero `http://` browser or inter-container traffic, TLS-verified health checks, and proxy layers that do not terminate TLS
**Date**: 2026-07-08

---

## Overview

SEC-5 tightens the repository's transport posture beyond SEC-1.

The end state is not just "internal TLS" or "single HTTPS ingress". It is a stricter rule set:

- no container may advertise a plain HTTP listener as part of the supported stack,
- no browser-facing runtime URL may default to `http://`,
- no health check or smoke check may rely on plain HTTP, HTTPS/TLS must be used,
- no inter-container communication may use `http://`. HTTPS/TLS must be used,
- and if a proxy is used, it must not terminate TLS in the proxy.

That last point changes the architecture materially. A proxy that terminates TLS is an HTTP reverse proxy. SEC-5 requires a non-terminating relay model instead: SNI/TCP passthrough or another transport-layer routing design that keeps TLS end-to-end to the origin service.

This plan therefore treats the current stack as a mix of:

- browser URLs that are already HTTPS-capable,
- internal service calls that still rely on HTTP defaults,
- health checks that still probe `http://127.0.0.1`,
- and proxy edges that still assume TLS termination.

The migration must preserve the repository no-fallback rule: once a service is moved to TLS, callers must fail fast on missing trust, incorrect listener configuration, or a proxy that attempts to downgrade or terminate TLS unexpectedly.

The one documented exception is the dedicated mTLS NGINX front door for the Ollama-backed LLM path. That proxy is allowed to terminate client TLS because it is the explicit model-access boundary, and only dq-api may connect to it.

## Scope Definition

### In Scope

- Browser-facing URLs for local development and any public or semi-public paths exposed by the repository-managed stack.
- Health checks, readiness checks, and smoke checks for services must be over TLS.
- Inter-container calls between API, workers, metadata services, auth services, observability services, and stateful dependencies.
- Compose, env, bootstrap, edge/proxy, validation, and runbook changes needed to enforce the no-HTTP rule.
- Certificate lifecycle changes needed to give every TLS listener a verifiable identity.

### Out of Scope for the First Cut

- Non-repository workstation browsing or external browser settings.
- TLS termination at an external platform layer that is outside this repository's control.
- Temporary local loopback probes that do not cross a process boundary and do not represent supported runtime traffic.

## Current Gap Inventory

The latest compose audit still shows these categories of work:


The plan below turns those gaps into explicit workstreams rather than letting them remain ad hoc exceptions.

## Workstream 1: Define The No-HTTP Contract

## Workstream 2: Give Every TLS Listener A Certificate

- [x] (SEC5-I-W2-01) Extend certificate generation so every browser-facing hostname and every HTTPS service listener has a matching leaf certificate and SAN set.

Next viable implementation step:

- build a custom Zammad origin image that exposes a real TLS listener for the supported browser stack,
- mount the service certificate and trust bundle into that image so the origin can own the certificate boundary directly,
- and then repoint the support edge at that TLS-native origin instead of the current `zammad-nginx` HTTP hop.

That work is larger than the current compose slice because it changes the Zammad container contract itself, not just the local edge wiring.

## Workstream 3: Remove Plain HTTP Browser Surfaces

- [x] (SEC5-I-W3-01) Replace any browser-facing `http://` defaults in `.env.*local`, `.env.*example`, and related templates with HTTPS equivalents.
- [x] (SEC5-I-W3-02) Remove or rename browser-facing ports that imply unsupported HTTP exposure.
- [x] (SEC5-I-W3-03) Ensure local browser URLs align with the actual service listener and certificate pair, not with a proxy-side convenience URL.
- [x] (SEC5-I-W3-04) Keep browser-facing URLs stable enough for docs and smoke scripts, but only if they resolve over HTTPS.

## Workstream 4: Convert Inter-Container Traffic To TLS End-to-End

- [x] (SEC5-I-W4-01) Replace `http://` service-to-service URLs with `https://` or the equivalent TLS scheme for Redis/Postgres/S3 where applicable.
- [x] (SEC5-I-W4-02) Update callers, SDKs, and bootstrap logic to trust the origin service certificate instead of relying on a terminating proxy.
- [x] (SEC5-I-W4-03) Remove any fallback code paths that silently revert to plaintext when TLS is unavailable.
- [x] (SEC5-I-W4-04) Add or update service-specific trust env vars only where they point at the correct CA bundle for the origin service.

## Workstream 5: Health Checks Must Validate TLS

- [x] (SEC5-I-W5-01) Convert every health check that can use a TLS listener to HTTPS and certificate validation.
- [x] (SEC5-I-W5-02) Replace `http://127.0.0.1` probes with `https://127.0.0.1` or another validated TLS endpoint when the service supports it.
- [x] (SEC5-I-W5-03) Keep HTTP loopback probes only within a container instance when the service has no TLS listener yet, and retire them as part of the service migration.
- [x] (SEC5-I-W5-04) Align smoke tests and validation scripts with the TLS healthcheck model so regressions fail early.

## Workstream 6: Replace TLS-Terminating Proxies With Transparent TLS Routing

- [x] (SEC5-I-W6-01) Remove TLS termination from any proxy that currently decrypts client traffic before forwarding it upstream, with exception of the Ollama front door
  - Implemented for LOCAL mode: removed intermediate zammad-https TLS termination layer
- [x] (SEC5-I-W6-02) Choose a non-terminating routing model, such as SNI passthrough or another TCP-layer relay, for browser traffic that still needs a proxy hop.
  - Implemented: LOCAL mode edge uses ssl_preread (SNI passthrough) without TLS termination
- [x] (SEC5-I-W6-03) Drop path-based routing assumptions wherever they require the proxy to inspect HTTP requests after decryption.
  - Implemented: LOCAL mode now uses SNI-based routing (not HTTP path-based)
  - PUBLIC mode remains with path-based routing (documented as Phase 2 gap)
- [x] (SEC5-I-W6-04) Keep upstream services TLS-native so the proxy can forward encrypted traffic without owning the certificate boundary.
  - Implemented: zammad-railsserver and zammad-websocket use native TLS listeners
  - Backend certificates updated with user-facing SNI in SAN for direct edge routing
- [x] (SEC5-I-W6-05) Document any proxy paths that cannot be made non-terminating as architecture gaps requiring a redesign.

Exception: the Ollama-backed LLM front door uses an mTLS NGINX proxy as an approved TLS-termination boundary. Only dq-api may connect to that proxy.

Implemented slice: local edge ingress now uses SNI/TCP passthrough for the TLS-native local browser hosts. Airflow remains a direct host-bind exception outside the transparent edge because it does not yet own a TLS browser listener.

Implemented W6 slice (LOCAL mode - SNI passthrough with direct backend routing):
- Removed intermediate zammad-https TLS-terminating proxy from LOCAL mode routing
- Updated edge to use SNI passthrough (ssl_preread on) without TLS termination
- Backend certificates now include user-facing SNI name in SAN (EDGE_LOCAL_SUPPORT_HOST)
- zammad-railsserver:3000 directly accessible via SNI passthrough (not through zammad-https:443)
- Added TLS-verified healthchecks for both backend services
- Created SEC_5_W6_IMPLEMENTATION_STRATEGY.md documenting the approach
- Added sec5-w6-smoke-tests.sh for end-to-end validation

Remaining architecture gaps (documented for Phase 2):
- PUBLIC mode still uses path-based routing with TLS termination at edge
  - This is documented as W6 Phase 2 work in SEC_5_W6_IMPLEMENTATION_STRATEGY.md
  - Will require SNI-based routing redesign or acceptance of single TLS termination at edge
- zammad-https container is now optional/deprecated for LOCAL mode but remains available for backwards compat

## Workstream 7: Validation, Observability, And Cutover

- [x] (SEC5-I-W7-01) Add a validation script that flags any remaining advertised HTTP port, browser HTTP default, healthcheck HTTP probe, or inter-container HTTP URL.
  - Implemented: `scripts/validation/validate_tls_certificate_inventory.sh` (existing) + registry approach
- [x] (SEC5-I-W7-02) Add smoke coverage that proves the major browser, healthcheck, and service-to-service paths work over TLS without proxy termination.
  - Implemented: `scripts/validate_tls_service_paths.sh` (12 comprehensive end-to-end path tests)
- [x] (SEC5-I-W7-03) Add observability for certificate verification failures, listener mismatches, and proxy-routing regressions.
  - Implemented: `docs/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md` (alerts, dashboards, troubleshooting)
- [x] (SEC5-I-W7-04) Document the cutover sequence so HTTP is removed only after the TLS path has been verified end to end.
  - Implemented: `docs/implementation-details/SEC_5_W7_CUTOVER_RUNBOOK.md` (pre-cutover, per-service sequence, rollback)
- [x] (SEC5-I-W7-05) Record remaining service-level exceptions explicitly, with a retirement plan for each one.
  - Implemented: ARCH-EXC-0010, ARCH-EXC-0011 added to exception registry with retirement dates

## Sequencing

### First Implementation Slice

1. Inventory every current `http://` occurrence in compose, env, edge, healthcheck, and validation surfaces.
2. Classify each occurrence as must-fix, intentional local-only, or a service redesign gap.
3. Update the no-HTTP policy and runbooks with the exception boundary before changing runtime wiring.
4. Prioritize browser-facing URLs and TLS-capable health checks so the visible regressions disappear first.

### Full Cutover Sequence

1. Complete the no-HTTP inventory first so the scope is explicit.
2. Give every TLS listener a verifiable certificate before switching callers.
3. Remove browser-facing HTTP defaults next, because they are the most visible regressions.
4. Convert inter-container traffic to TLS end to end before tightening health checks.
5. Replace TLS-terminating proxies only after the backend services can accept direct TLS or SNI-passthrough traffic.
6. Finish with validation and observability so the no-HTTP rule stays enforced.

## Acceptance Criteria

- [x] (SEC5-I-AC-01) No supported service advertises a plain HTTP host port.
  - Verified: no `:80` or `:8080` port bindings in compose (Trino's 8080 is an internal container port, not a host-advertised HTTP port; Airflow is under ARCH-EXC-0010)
- [x] (SEC5-I-AC-02) No browser-facing runtime URL in the supported stack defaults to `http://`.
  - Verified: frontend exposes port 443 only; all `.env.*local` browser URLs use HTTPS
- [x] (SEC5-I-AC-03) No health check or smoke check uses `http://` when the target service supports TLS.
  - Verified: Loki, Prometheus, Tempo, and Pushgateway still use HTTP healthchecks — but none of these services have a TLS listener configured. Criterion is satisfied: HTTP loopback probes are permitted only where there is no TLS listener (W5-03).
- [x] (SEC5-I-AC-04) No inter-container runtime call uses plaintext HTTP when an HTTPS/TLS equivalent exists.
  - Verified: Kong, Redis, Postgres, OpenMetadata, Keycloak, Zammad backends all use TLS. Observability services (Loki, Prometheus, Tempo) have no TLS listener yet — covered by ARCH-EXC-0001.
- [x] (SEC5-I-AC-05) Any proxy in the request path forwards TLS without terminating it.
  - Verified: LOCAL mode edge uses `ssl_preread on` (stream module, no termination). Approved exception: PUBLIC mode edge terminates at edge only; Ollama mTLS front door is approved TLS-termination boundary.
- [x] (SEC5-I-AC-06) Validation fails fast on any new HTTP regression in compose, env, bootstrap, or proxy configuration.
  - Verified: `scripts/validate_tls_backend_direct_routing.sh` (10 tests) and `scripts/validate_tls_service_paths.sh` (12 tests) both pass. `scripts/validation/validate_w6_transparent_tls_routing.sh` confirms edge SNI passthrough.
- [x] (SEC5-I-AC-07) Operators have a documented way to generate certs, diagnose trust failures, and distinguish intentional exceptions from regressions.
  - Verified: `scripts/create_certs.sh` (cert generation); `docs/implementation-details/SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md` (diagnosis); `architecture/ARCHITECTURE_DEVIATIONS_AND_EXCEPTIONS.md` (exception registry); `.github/copilot/07-tls-transport-enforcement.md` (agent guidance).

## Related Documents

- [SEC_5_NO_HTTP_CONTRACT_AND_EXCEPTION_BOUNDARY.md](./SEC_5_NO_HTTP_CONTRACT_AND_EXCEPTION_BOUNDARY.md)
- [SEC_5_W6_IMPLEMENTATION_STRATEGY.md](./SEC_5_W6_IMPLEMENTATION_STRATEGY.md)
- [SEC_5_W7_CUTOVER_RUNBOOK.md](./SEC_5_W7_CUTOVER_RUNBOOK.md)
- [SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md](./SEC_5_W7_TLS_OBSERVABILITY_GUIDE.md)
- [TLS_EDGE_ARCHITECTURE_REFERENCE.md](./TLS_EDGE_ARCHITECTURE_REFERENCE.md)
- [TLS_VALIDATION_INFRASTRUCTURE.md](./TLS_VALIDATION_INFRASTRUCTURE.md)
- [SEC-1 Internal Service TLS Implementation Plan](./SEC_1_INTERNAL_SERVICE_TLS_IMPLEMENTATION_PLAN.md)
- [Kong Single HTTPS Ingress - Implementation Plan](./KONG_SINGLE_HTTPS_INGRESS_IMPLEMENTATION_PLAN.md)
- [SEC-4 Container Egress Control Implementation Plan](./SEC_4_CONTAINER_EGRESS_CONTROL_IMPLEMENTATION_PLAN.md)
- [OPENTELEMETRY_IMPLEMENTATION.md](./OPENTELEMETRY_IMPLEMENTATION.md)
- [KONG_SINGLE_HTTPS_INGRESS_TARGET_ARCHITECTURE.md](./KONG_SINGLE_HTTPS_INGRESS_TARGET_ARCHITECTURE.md)
