# SEC-1: Internal Service TLS Implementation Plan

**Status**: Proposed  
**Target**: Repository-managed internal TLS across service and infrastructure boundaries  
**Date**: 2026-04-22

---

## Overview

SEC-1 introduces repository-managed TLS for internal cross-process communication.

The end state is broader than edge HTTPS. It covers the internal transport paths used by API calls, worker calls, auth flows, telemetry export, data stores, caches, and object-storage access whenever those paths cross a process boundary.

This is a phased migration because the current stack still mixes:

- HTTPS on selected public-facing or semi-public surfaces,
- plain internal HTTP between several containers,
- plain transport defaults for some stateful dependencies.

The migration must preserve the repository no-fallback rule: once a dependency is moved to TLS, callers must fail fast on broken trust or listener configuration instead of silently downgrading to plaintext.

## Scope Definition

### In Scope

- Internal HTTP and HTTP-adjacent service calls between Kong, API, workers, metadata services, auth services, and observability services.
- Internal transport connections to stateful dependencies such as Postgres, Redis, AIStor, and telemetry collectors where supported by the platform.
- Compose, env, bootstrap, validation, and runbook changes required to make those secure paths usable in local and controlled deployment environments.

### Out of Scope for the First Cut

- Replacing every local loopback probe that does not cross a process boundary.
- Internet-facing certificate automation for production ingress.
- Non-repository environments that manage trust through a separate platform PKI outside repository control.

## Workstream 1: Trust Plane and Certificate Lifecycle

- [x] (SEC1-I-W1-01) Define the repository-managed internal CA layout and output paths for service certificates, keys, and trust bundles.
	- Canonical repo-managed output root: `tmp/certs/`
	- Root CA material: `tmp/certs/ca/rootCA.pem` and `tmp/certs/ca/rootCA-key.pem`
	- Shared trust bundle: `tmp/certs/trust/internal-ca-bundle.pem`
	- Per-service leaf certificates: `tmp/certs/services/<service-name>/tls.crt` and `tmp/certs/services/<service-name>/tls.key`
	- Optional service-specific SAN bundles or wildcard leaves must still be written under the per-service directory, not alongside the trust bundle.
	- Current mkcert output files already live under `tmp/certs`, but W1-01 still needs the canonical directory contract, the producer/consumer mapping, and the fail-fast checks that enforce it.

- [x] (SEC1-I-W1-02) Extend certificate-generation tooling to issue certificates for internal service DNS names used on the Docker network.
	- URL audit snapshot: most remaining `127.0.0.1` uses are intentional local-only defaults or binds, but a few host-facing defaults still deserve explicit naming or follow-up cleanup.
	- Safe local-only defaults: `DQ_API_LOCAL_URL`, `DQ_DB_LOCAL_URL`, `KONG_ADMIN_LOCAL_URL`, `KEYCLOAK_HOST`, `DQ_LLM_HOST_BIND`, `AIRFLOW_HOST_BIND`, and the local probe/bind settings in `scripts/supporting/setup_env.sh`.
	- Rename or make explicit: host-facing helper defaults that still imply `localhost` in script-level fallbacks, such as `scripts/configure_kong.sh`, `scripts/init_kong_config.sh`, and `scripts/keycloak_fetch_client_secret.sh`.
	- True regressions to fix: any public or browser-facing URL that resolves to `127.0.0.1` by default. The current sweep did not find a clear public-facing default of that kind in the env templates, but this remains the rule to enforce during future TLS/host migration work.

- [x] (SEC1-I-W1-03) Standardize mounted certificate and trust-bundle paths across containers.
	- Container trust mounts now use the canonical internal CA bundle path under `tmp/certs/trust/internal-ca-bundle.pem` and mount it at a consistent in-container path for Zammad and OpenMetadata consumers.
	- `scripts/supporting/setup_env.sh` now writes the trust bundle to the canonical trust path and keeps the root-level bundle as an alias for existing host-side tooling.

- [x] (SEC1-I-W1-04) Document client-side trust environment variables and service-specific trust configuration hooks.
	- Client-side trust variables currently used by repo tooling include `MKCERT_ROOT_CA`, `INTERNAL_ROOT_CA`, `INTERNAL_CORPORATE_ROOT_CA`, `INTERNAL_CA_BUNDLE`, and `INTERNAL_CA_BUNDLE_FILE` from `scripts/supporting/setup_env.sh`.
	- Generic client trust variables that should be documented for downstream consumers include `PIP_CERT`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, and `CURL_CA_BUNDLE`.
	- Current service-specific trust hooks that need to stay aligned with the canonical bundle path include Zammad's `SSL_CERT_FILE`/`CURL_CA_BUNDLE`, OpenMetadata's `OPENMETADATA_CA_BUNDLE`/`SSL_CERT_FILE`/`CURL_CA_BUNDLE`, and the host-side bootstrap secret files for internal CA material in `docker-compose.yml`.
	- The documented contract should make clear that service-specific hooks consume the bundle path exported by repo bootstrap, while the repo still keeps a root-level alias for older host-side consumers.
- [x] (SEC1-I-W1-05) Add fail-fast checks in startup scripts or entrypoints for required certificate and trust artifacts.
	- `scripts/start_stack.sh` now refuses to start TLS-aware profile sets when the internal root CA or canonical internal trust bundle is missing.
	- The existing edge startup preflight still fails fast on missing edge leaf certificate material before Compose is launched.

## Workstream 2: Compose and Environment Canonicalization

- [ ] (SEC1-I-W2-01) Replace internal plaintext HTTP defaults in `.env.example` and related env surfaces with canonical HTTPS equivalents for migrated services.
- [ ] (SEC1-I-W2-02) Add explicit internal TLS configuration variables where listener ports, certificate paths, or verification modes must be configured.
- [ ] (SEC1-I-W2-03) Update `docker-compose.yml` service definitions to mount trust bundles and TLS materials consistently.
- [ ] (SEC1-I-W2-04) Update bootstrap scripts and seed tooling so internal service discovery uses canonical secure URLs.
- [ ] (SEC1-I-W2-05) Keep plaintext compatibility switches out of the default path once a service migration is complete.

## Workstream 3: HTTP Service Migration

- [ ] (SEC1-I-W3-01) Add an internal TLS serving strategy for the API service, either directly in the app runtime or via a dedicated sidecar/proxy pattern.
- [ ] (SEC1-I-W3-02) Update Kong bootstrap and service registration so internal upstreams target HTTPS endpoints with certificate validation.
- [ ] (SEC1-I-W3-03) Update API callers such as workers, metadata integrations, and internal UI config loaders to trust and use HTTPS endpoints.
- [ ] (SEC1-I-W3-04) Update internal auth issuer, token, JWKS, and admin endpoints to use canonical secure URLs where traffic crosses service boundaries.
- [ ] (SEC1-I-W3-05) Update service health checks, readiness checks, and smoke tests so TLS failures surface clearly.

## Workstream 4: Stateful Transport Migration

- [ ] (SEC1-I-W4-01) Enable and validate TLS for Postgres connections used by services and exporters.
- [ ] (SEC1-I-W4-02) Enable and validate TLS for Redis connections used by API, workers, and supporting services.
- [ ] (SEC1-I-W4-03) Enable and validate HTTPS for AIStor and any S3-compatible clients in the stack.
- [ ] (SEC1-I-W4-04) Update telemetry exporters and collectors to use trusted TLS endpoints where cross-process traffic exists.
- [ ] (SEC1-I-W4-05) Capture any service-specific transport gaps as named follow-up items instead of leaving anonymous plaintext exceptions.

## Workstream 5: Validation, Observability, and Runbooks

- [ ] (SEC1-I-W5-01) Add a validation script that flags known plaintext internal URLs, disabled TLS modes, or missing trust mounts.
- [ ] (SEC1-I-W5-02) Add smoke coverage for representative secure paths across HTTP, data, cache, and telemetry surfaces.
- [ ] (SEC1-I-W5-03) Add observability guidance and dashboards or log filters for trust and handshake failures.
- [ ] (SEC1-I-W5-04) Document certificate rotation, trust debugging, and common failure modes in runbooks.
- [ ] (SEC1-I-W5-05) Document the migration matrix that shows which services are TLS-complete, in progress, or pending.

## Sequencing

1. Complete Workstream 1 before switching any caller to a TLS-only endpoint.
2. Land Workstream 2 alongside each migrated service family so defaults and runtime wiring do not diverge.
3. Finish Workstream 3 for internal HTTP services before broadening scope to all stateful transports.
4. Use Workstream 5 to keep the migration observable and enforce the no-plaintext target over time.

## Acceptance Criteria

- [ ] (SEC1-I-AC-01) A clean local stack can generate, mount, and trust repository-managed internal certificates without manual per-service patching.
- [ ] (SEC1-I-AC-02) Kong and at least one backend caller successfully communicate with a TLS-enabled internal API endpoint using certificate validation.
- [ ] (SEC1-I-AC-03) Broken trust or missing certificate material causes a clear startup or runtime failure, not a plaintext fallback path.
- [ ] (SEC1-I-AC-04) At least one stateful transport family is migrated with encrypted connections and verification enabled.
- [ ] (SEC1-I-AC-05) Validation tooling can identify at least one plaintext internal endpoint regression before release.
- [ ] (SEC1-I-AC-06) Operators have a documented, repeatable workflow for certificate generation, trust injection, and failure diagnosis.

## Related Documents

- [SEC-1 Internal Service-to-Service TLS](../features/SEC_1_INTERNAL_SERVICE_TLS.md)
- [SEC_FEATURES.md](../features/SEC_FEATURES.md)
- [ADR-027 Internal Service Communication Uses Repository-Managed TLS](../../architecture/adr/ADR-027-internal-service-communication-uses-repository-managed-tls.md)
- [KONG Single HTTPS Ingress File Checklist](./KONG_SINGLE_HTTPS_INGRESS_FILE_CHECKLIST.md)