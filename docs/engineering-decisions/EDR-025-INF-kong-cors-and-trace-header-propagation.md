# EDR-025 [INF]: Kong CORS and Trace-Header Propagation Rules

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: INF

## Context
Browser tracing and request correlation depend on cross-origin requests carrying trace headers through Kong. This broke when CORS configuration sources drifted or when Kong plugin updates collapsed allowed-header configuration.

## Decision
- Keep Kong as the authoritative cross-origin header gate for browser-facing API traffic in this repository.
- Allow trace-context and correlation headers explicitly in all Kong CORS configuration sources.
- Configure Kong CORS plugin headers as structured arrays rather than repeated scalar arguments that can collapse or truncate in live config.
- Validate trace-header propagation through explicit browser-style preflight checks.

## Rationale
- Trace propagation fails silently if the gateway blocks required headers.
- Kong bootstrap/config scripts must stay aligned because any one of them can reintroduce a restrictive header allow-list.
- Preflight validation is the clearest way to confirm browser-visible CORS behavior.

## Scope Boundaries
This decision covers Kong CORS behavior for trace header propagation.

It does not by itself define:
- instrumentation SDK behavior
- JWT bootstrap
- server-to-server trace forwarding policies

## Consequences
**Positive**
- Browser trace headers survive gateway CORS checks more reliably.
- Kong config drift is easier to detect and validate.

**Negative**
- Multiple Kong configuration sources must remain synchronized.

## Implementation Guidance
- Keep `traceparent`, `tracestate`, `baggage`, and correlation headers in the allowed-header list.
- Post CORS config as JSON arrays.
- Verify with `OPTIONS` checks against live Kong routes.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-kong-cors-traceparent-regression-note.md`
