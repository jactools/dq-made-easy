# ADR-016: ISO 27001-Aligned Logging and Monitoring Policy Adoption

**Status**: Accepted  
**Date**: 2026-03-22  
**Related**: [ADR-015](./ADR-015-opentelemetry-instrumentation-for-distributed-tracing.md), [Policy](../../docs/technical/LOGGING_AND_MONITORING_POLICY_ISO27001.md)

## Context

dq-rulebuilder already has observability building blocks (correlation IDs, request timing, and central stack components), but lacked a single, normative policy that defines:
- mandatory logging content
- monitoring and alerting minimums
- retention and access requirements
- ISO 27001 control mapping expectations

Without a policy baseline, implementations can drift between services and environments, reducing incident response quality and audit readiness.

## Decision

Adopt [LOGGING_AND_MONITORING_POLICY_ISO27001.md](../../docs/technical/LOGGING_AND_MONITORING_POLICY_ISO27001.md) as the mandatory platform policy for all dq-rulebuilder services and environments.

The policy is aligned to ISO/IEC 27001:2022 control intent, including:
- Annex A 8.15 (Logging)
- Annex A 8.16 (Monitoring activities)
- Annex A 8.17 (Clock synchronization)
- Annex A 5.24/5.25/5.26 incident lifecycle evidence support

Mandatory baseline requirements include:
- structured JSON logging with correlation and business context fields
- centralized monitoring and alerting across compile/retrieval/execution flows
- an aggregated Execution Monitoring dashboard across all executors for shared run, status, transition, latency, results/failures, compile, throughput, and heartbeat signals
- UTC timestamping and synchronized clocks
- retention and access controls for security-relevant telemetry
- evidence collection for periodic compliance verification

## Consequences

### Positive

- Standardized telemetry across services and teams
- Improved incident triage and forensic traceability
- Better compliance posture and audit evidence quality
- Reduced ambiguity in observability implementation expectations

### Negative

- Additional implementation and governance overhead for service owners
- Need for periodic review and evidence collection process discipline
- Potential short-term refactoring where existing logs do not meet policy fields

## Implementation Notes

- Platform and service teams must map existing telemetry to policy requirements and close gaps.
- ADR-015 implementation work should be treated as the primary technical execution vehicle.
- The top-level Execution Monitoring dashboard should stay runtime-agnostic and aggregate all executors that emit the shared execution telemetry categories; runtime-specific dashboards may be added later for drilldown detail.
- Compliance checks should be integrated into release readiness and quarterly governance review.
- Execution tasks and evidence mapping are tracked in [LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md](../../docs/technical/LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md).
