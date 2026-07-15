# 0.11.5 Changelog

This changelog summarizes the user-visible and infrastructure-focused changes shipped in the 0.11.5 release line.

## Summary

- Completed SEC-5 Workstreams 6 and 7: end-to-end TLS enforcement for the local development stack.
- Eliminated the double-TLS-termination path through the Zammad support stack.
- Added comprehensive TLS validation suite, cutover runbook, and observability guide.
- Bumped `Infrastructure` and `Testautomation` manifest components to 0.11.5.

## Transport and infrastructure

- The local edge now routes support traffic via SNI passthrough (`ssl_preread on`) directly to the Rails backend, with no intermediate `zammad-https` TLS-termination proxy in the path.
- Zammad Rails server and WebSocket server each own a native TLS listener; their certificates carry the user-facing edge hostname as a Subject Alternative Name so the passthrough succeeds without a hostname mismatch.
- Healthchecks for `zammad-railsserver` and `zammad-websocket` now verify the CA bundle on every probe.
- `scripts/create_certs.sh` derives the backend SAN from `EDGE_LOCAL_SUPPORT_HOST` at generation time.

## Validation and testing

- `scripts/validate_tls_backend_direct_routing.sh` (10 tests): confirms no intermediate proxy, edge SNI passthrough, backend TLS nativity, healthcheck CA verification, compose YAML validity.
- `scripts/validate_tls_service_paths.sh` (12 tests): confirms browser paths, service-to-service paths, healthchecks, no plaintext URLs, no advertised HTTP ports.
- All seven SEC-5 acceptance criteria verified and marked complete in the implementation plan.

## Operator guidance

- Cutover runbook added: per-service migration sequence, rollback procedure, incident response for certificate errors, connection refused, SNI mismatch, and HTTP regressions.
- TLS observability guide added: Prometheus alert rules, Loki query patterns, manual troubleshooting steps, dashboard design recommendations.
- Exception registry updated: ARCH-EXC-0010 (Airflow HTTP) and ARCH-EXC-0011 (zammad-https deprecation) with owners and retirement dates.
- Agent guidance file added at `.github/copilot/07-tls-transport-enforcement.md` to preserve the no-HTTP contract across future code changes.

## Architecture reference

- `TLS_EDGE_ARCHITECTURE_REFERENCE.md`: edge routing modes, before/after W6 routing diagrams, service TLS status table.
- `TLS_VALIDATION_INFRASTRUCTURE.md`: full script inventory, how to run, exception registry reference.

## Notes

- This release is focused on infrastructure and security hardening. No UI or API runtime behavior changes.
- PUBLIC mode (path-based routing with TLS termination at the edge) is documented as a Phase 2 gap in `SEC_5_W6_IMPLEMENTATION_STRATEGY.md`.
