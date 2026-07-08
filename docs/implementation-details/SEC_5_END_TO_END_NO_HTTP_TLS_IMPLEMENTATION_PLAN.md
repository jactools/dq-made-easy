# SEC-5: End-to-End No-HTTP TLS Implementation Plan

**Status**: Proposed
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

- Browser URLs: some local defaults and operator URLs still point at `http://` even though their services can already be exposed over HTTPS.
- Inter-container HTTP: a handful of service-to-service paths still use `http://` because the origin service has not yet been switched to TLS or the caller has not been updated.
- Health checks: several services still probe plain HTTP on localhost because their healthcheck command has not been migrated to the TLS endpoint.
- Proxy behavior: the edge proxy still contains HTTP proxying behavior in places where a non-terminating TLS relay is required.

The plan below turns those gaps into explicit workstreams rather than letting them remain ad hoc exceptions.

## Workstream 1: Define The No-HTTP Contract

- [x] (SEC5-I-W1-01) Define the repository-wide no-HTTP rule for browser URLs, inter-container traffic, and health checks.
- [x] (SEC5-I-W1-02) Document the exception boundary for loopback-only probes that are not supported runtime traffic.
- [x] (SEC5-I-W1-03) Classify every current `http://` occurrence into one of three buckets: must-fix, intentional local-only, or requires service redesign.
- [x] (SEC5-I-W1-04) Add the no-HTTP policy to the implementation-details index and the relevant runbooks.

## Workstream 2: Give Every TLS Listener A Certificate

- [x] (SEC5-I-W2-01) Extend certificate generation so every browser-facing hostname and every HTTPS service listener has a matching leaf certificate and SAN set.
- [x] (SEC5-I-W2-02) Standardize trust bundle mounts and env variables so callers can validate the appropriate certificate chain without custom per-service wiring.
- [x] (SEC5-I-W2-03) Ensure the certificate layout distinguishes between service leaf certs, root CA material, and any shared trust bundles.
- [x] (SEC5-I-W2-04) Add fail-fast checks for missing certs, keys, and CA bundles before startup or health probing begins.

## Workstream 3: Remove Plain HTTP Browser Surfaces

- [x] (SEC5-I-W3-01) Replace any browser-facing `http://` defaults in `.env.*local`, `.env.*example`, and related templates with HTTPS equivalents.
- [x] (SEC5-I-W3-02) Remove or rename browser-facing ports that imply unsupported HTTP exposure.
- [x] (SEC5-I-W3-03) Ensure local browser URLs align with the actual service listener and certificate pair, not with a proxy-side convenience URL.
- [x] (SEC5-I-W3-04) Keep browser-facing URLs stable enough for docs and smoke scripts, but only if they resolve over HTTPS.

## Workstream 4: Convert Inter-Container Traffic To TLS End-to-End

- [ ] (SEC5-I-W4-01) Replace `http://` service-to-service URLs with `https://` or the equivalent TLS scheme for Redis/Postgres/S3 where applicable.
- [ ] (SEC5-I-W4-02) Update callers, SDKs, and bootstrap logic to trust the origin service certificate instead of relying on a terminating proxy.
- [ ] (SEC5-I-W4-03) Remove any fallback code paths that silently revert to plaintext when TLS is unavailable.
- [ ] (SEC5-I-W4-04) Add or update service-specific trust env vars only where they point at the correct CA bundle for the origin service.

## Workstream 5: Health Checks Must Validate TLS

- [ ] (SEC5-I-W5-01) Convert every health check that can use a TLS listener to HTTPS and certificate validation.
- [ ] (SEC5-I-W5-02) Replace `http://127.0.0.1` probes with `https://127.0.0.1` or another validated TLS endpoint when the service supports it.
- [ ] (SEC5-I-W5-03) Keep HTTP loopback probes only within a container instance when the service has no TLS listener yet, and retire them as part of the service migration.
- [ ] (SEC5-I-W5-04) Align smoke tests and validation scripts with the TLS healthcheck model so regressions fail early.

## Workstream 6: Replace TLS-Terminating Proxies With Transparent TLS Routing

- [ ] (SEC5-I-W6-01) Remove TLS termination from any proxy that currently decrypts client traffic before forwarding it upstream.
- [ ] (SEC5-I-W6-02) Choose a non-terminating routing model, such as SNI passthrough or another TCP-layer relay, for browser traffic that still needs a proxy hop.
- [ ] (SEC5-I-W6-03) Drop path-based routing assumptions wherever they require the proxy to inspect HTTP requests after decryption.
- [ ] (SEC5-I-W6-04) Keep upstream services TLS-native so the proxy can forward encrypted traffic without owning the certificate boundary.
- [ ] (SEC5-I-W6-05) Document any proxy paths that cannot be made non-terminating as architecture gaps requiring a redesign.

## Workstream 7: Validation, Observability, And Cutover

- [ ] (SEC5-I-W7-01) Add a validation script that flags any remaining advertised HTTP port, browser HTTP default, healthcheck HTTP probe, or inter-container HTTP URL.
- [ ] (SEC5-I-W7-02) Add smoke coverage that proves the major browser, healthcheck, and service-to-service paths work over TLS without proxy termination.
- [ ] (SEC5-I-W7-03) Add observability for certificate verification failures, listener mismatches, and proxy-routing regressions.
- [ ] (SEC5-I-W7-04) Document the cutover sequence so HTTP is removed only after the TLS path has been verified end to end.
- [ ] (SEC5-I-W7-05) Record remaining service-level exceptions explicitly, with a retirement plan for each one.

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

- [ ] (SEC5-I-AC-01) No supported service advertises a plain HTTP host port.
- [ ] (SEC5-I-AC-02) No browser-facing runtime URL in the supported stack defaults to `http://`.
- [ ] (SEC5-I-AC-03) No health check or smoke check uses `http://` when the target service supports TLS.
- [ ] (SEC5-I-AC-04) No inter-container runtime call uses plaintext HTTP when an HTTPS/TLS equivalent exists.
- [ ] (SEC5-I-AC-05) Any proxy in the request path forwards TLS without terminating it.
- [ ] (SEC5-I-AC-06) Validation fails fast on any new HTTP regression in compose, env, bootstrap, or proxy configuration.
- [ ] (SEC5-I-AC-07) Operators have a documented way to generate certs, diagnose trust failures, and distinguish intentional exceptions from regressions.

## Related Documents

- [SEC_5_NO_HTTP_CONTRACT_AND_EXCEPTION_BOUNDARY.md](./SEC_5_NO_HTTP_CONTRACT_AND_EXCEPTION_BOUNDARY.md)
- [SEC-1 Internal Service TLS Implementation Plan](./SEC_1_INTERNAL_SERVICE_TLS_IMPLEMENTATION_PLAN.md)
- [Kong Single HTTPS Ingress - Implementation Plan](./KONG_SINGLE_HTTPS_INGRESS_IMPLEMENTATION_PLAN.md)
- [SEC-4 Container Egress Control Implementation Plan](./SEC_4_CONTAINER_EGRESS_CONTROL_IMPLEMENTATION_PLAN.md)
- [OPENTELEMETRY_IMPLEMENTATION.md](./OPENTELEMETRY_IMPLEMENTATION.md)
- [KONG_SINGLE_HTTPS_INGRESS_TARGET_ARCHITECTURE.md](./KONG_SINGLE_HTTPS_INGRESS_TARGET_ARCHITECTURE.md)
