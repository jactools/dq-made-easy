# EDR-029 [UI]: Frontend OpenTelemetry Instrumentation and Zone-Context Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: UI

## Context
The frontend now emits browser telemetry into the repository observability stack, but that path is constrained by browser CORS, OTLP endpoint semantics, ESNext build targets, and fetch instrumentation behavior.

## Decision
- Browser UI telemetry must use a context manager that is compatible with the repository's ESNext frontend target; do not use `ZoneContextManager` in dq-ui.
- Frontend tracing instrumentation must preserve native `Response` instances rather than wrapping them in `Proxy` objects that break browser brand checks.
- Browser OTLP export must target a collector endpoint that expects the client exporter to append `/v1/traces`; do not pre-expand the full path incorrectly in configuration.
- Collector receiver-level CORS must explicitly allow supported local UI origins before browser telemetry is considered enabled.
- UI telemetry must remain opt-in through explicit frontend environment variables so unsupported deployments fail quiet by configuration rather than by accidental browser noise.

## Rationale
- `ZoneContextManager` is incompatible with the frontend compile target used in this repository.
- Browser fetch instrumentation depends on native response behavior for cloning, `ok`, and body handling.
- OTLP HTTP endpoints are easy to misconfigure if the collector path and exporter behavior are not aligned.
- Browser telemetry is not viable if collector CORS blocks preflight requests.

## Scope Boundaries
This decision covers frontend-specific OpenTelemetry integration behavior.

It does not by itself define:
- trace naming or sampling policy
- backend instrumentation rules
- dashboard layout or alert configuration

## Consequences
**Positive**
- Browser telemetry becomes predictable across supported local/dev setups.
- Frontend tracing failures are easier to diagnose because the configuration contract is explicit.

**Negative**
- UI telemetry setup remains sensitive to collector CORS and environment configuration.
- Frontend instrumentation has less flexibility because it must preserve native response semantics.

## Implementation Guidance
- Use the stack-compatible frontend context manager.
- Patch response behavior without proxy-wrapping native response objects.
- Validate collector browser access with an `OPTIONS` request to the traces endpoint.
- Gate UI telemetry with explicit enablement env vars.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-ui-otel-zone-esnext-context-manager-note.md`
- `/memories/repo/dq-rulebuilder-ui-otel-collector-cors-note.md`
- `/memories/repo/dq-rulebuilder-ui-otel-response-proxy-brand-check-note.md`
- `/memories/repo/dq-rulebuilder-otel-collector-otlp-http-alias-and-endpoint-note.md`
