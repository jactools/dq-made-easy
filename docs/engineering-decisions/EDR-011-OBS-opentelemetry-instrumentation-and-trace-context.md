# EDR-011 [OBS]: OpenTelemetry Instrumentation and Trace-Context Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: OBS

## Context
The repository now emits telemetry from several layers at once: FastAPI, GX and profiling workers, the OpenTelemetry collector, and the browser UI. The failures seen in this area were not about whether instrumentation existed, but about whether instrumentation was wired in a way that remained correct and low-noise across local development, smoke tests, and prototype deployment.

Repeated issues showed a few stable rules:

- OTLP exporter protocol and endpoint selection must match the actual collector port and protocol
- local or smoke-test runs must degrade cleanly when the collector is unavailable instead of generating repeated exporter noise
- collector exporter endpoints must use the correct base URL semantics for Tempo OTLP/HTTP
- browser tracing requires collector-side CORS and browser-compatible context management
- browser telemetry patching must preserve native `Response` behavior for OpenTelemetry fetch instrumentation

These are repository-wide observability rules rather than isolated fixes.

## Decision
Adopt the following OpenTelemetry rules across the repository:

- FastAPI and worker telemetry must detect whether OTLP export is actually reachable before enabling remote exporters; when the collector is unavailable, the service should fall back to local/no-op export mode with one concise warning instead of repeated exporter stack traces.
- Worker telemetry must select OTLP exporter protocol based on the configured endpoint or protocol: gRPC exporters for port `4317` or explicit gRPC configuration, HTTP exporters only for OTLP HTTP endpoints such as `4318` or the repository's internal collector HTTP port.
- The OpenTelemetry collector must use the current OTLP HTTP exporter naming and must configure Tempo exporters with the base OTLP HTTP URL rather than appending `/v1/traces` manually.
- Browser OTLP export must rely on collector receiver CORS configuration that explicitly allows the repository's supported local dev origins.
- UI tracing must use a browser-compatible context manager; in this repository that means `StackContextManager` rather than `ZoneContextManager` because the app targets `ESNext`.
- UI telemetry response patching must preserve native `Response` instances and avoid Proxy-wrapped response objects that break OpenTelemetry fetch instrumentation and browser brand checks.
- Telemetry debug logging may be enabled with an environment flag for targeted export verification, but that diagnostic mode is supplementary and not the normal steady-state configuration.

## Rationale
- Exporter misconfiguration causes silent data loss or noisy false failures; protocol and endpoint rules need to be explicit.
- Local development and smoke tests should remain deterministic when the collector is not present.
- Tempo OTLP/HTTP endpoint behavior is strict; the collector must supply the correct base URL or traces disappear behind 404s.
- Browser telemetry has different constraints from server telemetry, especially around CORS, context propagation, and native `Response` handling.
- Environment-gated diagnostics are useful for validating end-to-end export paths without making normal logs noisy.

## Scope Boundaries
This decision applies to repository OpenTelemetry behavior in FastAPI services, workers, the OpenTelemetry collector, and browser UI tracing.

It does not by itself define:
- every metric name or span name used by the repository
- alerting thresholds or dashboard layout
- long-term production sampling policy
- non-OTel logging architecture outside telemetry integration points

## Consequences
**Positive**
- Telemetry wiring is more deterministic across local, smoke, and prototype environments.
- Collector outages do not flood logs with repeated exporter errors.
- Worker and UI telemetry use protocol- and platform-appropriate exporter behavior.
- Trace troubleshooting has a defined debug path when end-to-end export needs verification.

**Negative**
- Observability setup now depends on a few repository-specific wiring rules rather than generic defaults.
- Browser telemetry requires explicit collector CORS maintenance as local origins evolve.
- Debugging trace gaps may still require checking app, collector, and Tempo layers separately.

## Implementation Guidance
- Preflight OTLP endpoint reachability before enabling remote export in FastAPI services when the exporter would otherwise generate repeated connection errors.
- In worker telemetry, treat `4317` as gRPC-oriented and HTTP ports as OTLP HTTP; do not send HTTP exporters to a gRPC endpoint.
- Configure collector Tempo OTLP/HTTP exporters with the base URL only.
- Restart the collector after receiver or exporter configuration changes and verify browser OTLP export with an `OPTIONS` check to the trace endpoint when needed.
- In the UI, keep native `Response` objects intact and prefer instance-level method overrides over Proxy wrapping.
- Use `StackContextManager` for browser tracing in this repository's ESNext target.
- Keep telemetry debug export logging behind an env flag such as `OTEL_TRACE_EXPORT_DEBUG`.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-dq-engine-gx-worker-otel-telemetry-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-otel-exporter-unavailable-summary-note.md`
- `/memories/repo/dq-rulebuilder-otel-collector-otlp-http-alias-and-endpoint-note.md`
- `/memories/repo/dq-rulebuilder-otel-collector-tempo-otlphttp-base-endpoint-note.md`
- `/memories/repo/dq-rulebuilder-ui-otel-collector-cors-note.md`
- `/memories/repo/dq-rulebuilder-ui-otel-response-proxy-brand-check-note.md`
- `/memories/repo/dq-rulebuilder-ui-otel-zone-esnext-context-manager-note.md`
- `/memories/repo/dq-rulebuilder-fastapi-profiling-trace-exporter-success-note.md`
- `dq-engine/gx_dispatch_telemetry.py`
- `dq-api/fastapi/app/core/telemetry.py`
- `observability/otel-collector/config.yml`
- `dq-ui/src/telemetry.ts`