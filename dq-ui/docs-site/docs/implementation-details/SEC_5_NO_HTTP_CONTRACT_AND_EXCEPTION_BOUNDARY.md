# SEC-5 No-HTTP Contract and Exception Boundary

**Status**: Active implementation note
**Scope**: repository-managed browser URLs, inter-container traffic, health checks, and proxy routing
**Date**: 2026-07-08

This note makes the SEC-5 boundary explicit so runtime changes, validation scripts, and runbooks all apply the same rule set.

## Contract

Supported stack traffic must follow these rules:

- Browser-facing runtime URLs must default to HTTPS.
- Inter-container service calls must use HTTPS or another TLS scheme for the target service.
- Health checks and smoke checks must validate TLS whenever the target service supports TLS.
- Proxies in the request path must not terminate TLS if the target service is expected to own the certificate boundary.

## Exception Boundary

The only temporary HTTP allowances are:

- local loopback probes that stay inside one container instance and do not represent supported runtime traffic,
- startup-time checks for services that still lack a TLS listener,
- the dedicated mTLS NGINX front door for the Ollama-backed LLM path, which is allowed to terminate TLS because it is the explicit model-access boundary and only dq-api may use it,
- and documented compatibility exceptions that are explicitly called out in this note and in the related runbook.

Anything else is a regression.

## Current Classification Snapshot

### Must Fix

- `http://openmetadata-ingestion:8080` in OpenMetadata ingestion wiring was converted to HTTPS and should remain so.
- Browser-facing defaults for TLS-capable services must stay HTTPS-only.
- TLS-capable health checks must not fall back to plaintext loopback probes.

### Intentional Local-Only

- Loopback probes that are only used to confirm a local process is alive inside a container.
- Host-side binds such as `127.0.0.1` for published ports, where the listener itself is HTTPS.

### Requires Service Redesign

- Any proxy path that still depends on TLS termination before forwarding upstream.
- Any service that can only be reached through plain HTTP today and has no TLS listener yet.

## Enforcement Guidance

- When a service gains a TLS listener, switch its callers and health checks in the same change set.
- When a validation script finds a plaintext URL, classify it before changing it so the exception boundary stays auditable.
- Keep the contract and the runbook in sync with compose changes so the repo does not drift back to HTTP by accident.

## Related Documents

- [SEC-5 End-to-End No-HTTP TLS Implementation Plan](/docs/implementation-details/SEC_5_END_TO_END_NO_HTTP_TLS_IMPLEMENTATION_PLAN/)
- [Internal Service TLS Runbook](/docs/technical/INTERNAL_SERVICE_TLS_RUNBOOK/)
- [Implementation Details Index](/docs/implementation-details/)