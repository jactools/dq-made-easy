# EDR-028 [OBS]: Observability Stack and Structured Log Pipeline

**Status**: Accepted
**Date**: 2026-04-20
**Tag**: OBS

## Context
The repository’s observability deployment is not just about SDK instrumentation; it also depends on a specific lightweight stack topology and structured-log pipeline that ties traces, metrics, logs, and dashboards together in a way the local/prototype environment can sustain.

## Decision
- Use the repository’s lightweight observability stack as the reference topology: Loki for logs, Prometheus for metrics, Tempo for traces, and Grafana for visualization.
- Emit structured JSON logs suitable for Loki ingestion.
- Keep OpenTelemetry-based traces and metrics flowing into the stack through the repository’s chosen collector/export paths.
- Preserve W3C trace-context propagation across services as the common correlation mechanism.
- Treat the stack topology, exposed ports, and storage assumptions as repository deployment conventions rather than ad hoc local choices.

## Rationale
- A lightweight but complete stack keeps local/prototype observability usable without vendor lock-in.
- Structured logs are necessary for practical correlation and queryability.
- Common trace-context propagation is what ties logs, traces, and metrics together across services.

## Scope Boundaries
This decision covers stack topology and structured log pipeline conventions.

It does not by itself define:
- detailed SDK instrumentation rules, which are covered by EDR-011
- all dashboards or alert rules
- production-scale storage tuning or sampling policy

## Consequences
**Positive**
- The repository has a coherent reference observability deployment.
- Logs, traces, and metrics are easier to correlate across services.

**Negative**
- Stack components and port assumptions must stay aligned across compose/config changes.

## Implementation Guidance
- Keep logs structured and collector-friendly.
- Maintain the repository’s current stack topology and internal routing assumptions.
- Keep trace-context propagation enabled end to end.

## Related Artifacts
- `/memories/repo/dq-rulebuilder-observability-stack-note.md`