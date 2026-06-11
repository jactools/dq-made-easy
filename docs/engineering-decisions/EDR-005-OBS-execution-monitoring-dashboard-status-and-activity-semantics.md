# EDR-005 [OBS]: Execution Monitoring Dashboard Status and Activity Semantics

**Status**: Accepted
**Date**: 2026-04-19
**Tag**: OBS

## Context
The execution-monitoring dashboard is used to answer different operational questions that are easy to conflate:
- What is the current run state by status across all executors that participate in the shared execution model?
- Was there recent activity entering a state?
- Are there currently active pending or running runs?
- Are executor failures and validation-result failures visible at a glance?

Using Grafana's default palette-based coloring caused ambiguity because colors were determined by series ordering instead of operational meaning. This led to cases such as `failed` rendering green or `succeeded` rendering orange.

At the same time, count-based stat tiles such as `Pending Runs` and `Entered Pending (5m)` should not look like active warnings when the value is zero or absent.

## Decision
Adopt the following dashboard semantics for execution monitoring:
- The top-level Execution Monitoring dashboard is the primary aggregated runtime view and should roll up all executors that emit the shared monitoring categories for runs, statuses, transitions, latency, results/failures, compile activity, throughput, and executor heartbeat.
- Runtime-specific dashboards such as GX drilldowns may be added later, but they complement rather than replace the aggregated Execution Monitoring dashboard.
- Status-oriented charts must use deterministic, status-based colors for the canonical execution states:
  - `succeeded` = green
  - `failed` = red
  - `running` = blue
  - `pending` = orange
- Unknown or non-canonical statuses may continue to use Grafana's default palette.
- Count-based activity tiles must use numeric threshold coloring rather than fixed status coloring.
- A value of zero or `No data` on activity tiles must not be colored as active pending or running work.
- Charts that mix expectation results and worker failures must color all failure series red and success series green.

## Rationale
- Dashboard colors should communicate operational meaning directly, not reflect incidental query ordering.
- Status charts and activity tiles answer different questions and therefore need different color semantics.
- Fixed status colors improve scanability during incidents and make screenshots/readouts easier to interpret consistently.
- Threshold-based count tiles avoid false urgency when a metric is absent or zero.

## Scope Boundaries
This decision applies to the execution-monitoring dashboard under `observability/grafana/provisioning/dashboards/dq-execution-monitoring.json`.

It does not by itself define:
- a global Grafana color standard for every dashboard in the repository
- alerting thresholds or alert routes
- the full metric taxonomy of the observability stack
- branding or theme choices beyond operational chart semantics

## Consequences
**Positive**
- Dashboard color meaning becomes stable and predictable.
- Failures and successes are easier to distinguish during live investigation.
- Activity tiles no longer imply work is active when the value is zero or absent.
- Operators can reason separately about current state and recent state transitions.
- Shared execution monitoring semantics stay stable as new runtimes start emitting the same operational signals.

**Negative**
- Explicit color semantics require more dashboard maintenance than relying on Grafana defaults.
- Adding new canonical statuses later requires updating panel configuration deliberately.
- Some panel definitions become more verbose because color intent is encoded directly.

## Implementation Guidance
- Use generic panel titles on the top-level Execution Monitoring dashboard so the surface stays valid as more executors contribute telemetry.
- Prefer explicit per-status series or exact-name field overrides for canonical status charts.
- Use threshold coloring for numeric stat tiles such as pending/running counts and recent transition counts.
- Keep executor failure series red even when displayed alongside non-failure result series.
- Aggregate across executor labels when a shared metric taxonomy exists; if only one executor currently emits a given signal, keep the panel generic when the category is intended to be cross-runtime.
- Validate provisioned dashboard JSON after editing and reload Grafana so the intended semantics take effect.

## Related Artifacts
- `observability/grafana/provisioning/dashboards/dq-execution-monitoring.json`
- `observability/postgres-exporter/queries.yaml`
- `dq-engine/gx_dispatch_telemetry.py`
- `architecture/adr/ADR-016-iso27001-logging-and-monitoring-policy-adoption.md`
- `docs/technical/EXECUTION_MONITORING_METRIC_TAXONOMY.md`
