# Logging and Monitoring Policy (ISO 27001 Aligned)

**Policy ID**: DQ-SEC-LOGMON-001  
**Version**: 1.0  
**Effective Date**: 2026-03-22  
**Owner**: Engineering + Security  
**Review Cycle**: Quarterly (minimum) and after major incidents

## 1. Purpose

Define mandatory controls for security logging, operational monitoring, alerting, and evidence retention across the dq-made-easy platform, aligned with ISO/IEC 27001:2022 control intent.

## 2. Scope

This policy applies to:
- All services in the dq-made-easy platform (API, engine, workers, gateway, data stores, observability stack)
- All environments (local, test, staging, production)
- All execution paths (synchronous HTTP, asynchronous jobs, pipelines, batch runs)

## 3. ISO 27001 Alignment

This policy implements and operationalizes the following control intent:
- ISO/IEC 27001:2022 Annex A 8.15 (Logging)
- ISO/IEC 27001:2022 Annex A 8.16 (Monitoring activities)
- ISO/IEC 27001:2022 Annex A 8.17 (Clock synchronization)
- ISO/IEC 27001:2022 Annex A 5.24 / 5.25 / 5.26 (Incident management lifecycle support via evidence)

Note: This policy provides implementation requirements for dq-made-easy and does not replace organization-wide ISMS governance documents.

## 4. Policy Statements

### 4.1 Structured Logging Requirement

All in-scope services MUST emit structured JSON logs.

Each log event MUST include, where applicable:
- event
- component
- correlationId
- ts (UTC timestamp)
- level
- runId
- suiteId
- ruleId
- dataObjectId
- dataObjectVersionId
- datasetId
- dataProductId

Logs MUST NOT contain:
- passwords, secrets, private keys, or bearer tokens
- full PII payloads unless explicitly approved and documented
- full data row bodies for rule exceptions (store only minimum required identifiers)

### 4.2 Correlation and Traceability

- Each inbound request MUST have a correlation ID; if absent, one MUST be generated.
- Correlation ID MUST be propagated across service boundaries.
- Where distributed tracing is enabled, trace/span context MUST be linked to correlationId.

### 4.3 Monitoring and Alerting

The platform MUST monitor, at minimum:
- authentication/authorization failures
- API error rates and latency SLOs
- execution run counts and current status
- execution run transitions
- rule compile failures
- rule execution latency, results/failures, and timeouts
- rule execution throughput
- executor heartbeat gaps
- exception-store write failures
- service health/readiness and heartbeat gaps

The primary Execution Monitoring dashboard MUST provide an aggregated view across all executors for the shared execution categories above. Executor-specific dashboards MAY be added for engine-native detail, but they MUST not replace the aggregated operational view.

Shared Prometheus metric families and labels for that dashboard MUST follow [EXECUTION_MONITORING_METRIC_TAXONOMY.md](./EXECUTION_MONITORING_METRIC_TAXONOMY.md).

Alerts MUST be configured with documented severity levels:
- Critical: immediate operational impact or security event
- Warning: elevated risk requiring investigation

### 4.4 Time Synchronization

- All service hosts and containers MUST use synchronized UTC time.
- Logs and metrics timestamps MUST be generated and stored in UTC.

### 4.5 Log Integrity and Access Control

- Access to logs/monitoring data MUST follow least privilege and role-based access.
- Administrative actions in observability tooling MUST be auditable.
- Log transport and storage SHOULD be protected against tampering and unauthorized modification.

### 4.6 Retention and Disposal

Retention baselines:
- Security and audit-relevant logs: minimum 90 days online
- Operational metrics and traces: retention per environment profile (documented per stack)
- Incident-related evidence: retained per incident and compliance process

Disposal MUST follow defined data lifecycle controls and avoid unauthorized recovery.

## 5. Roles and Responsibilities

- Engineering Teams:
  - implement required structured logging fields
  - instrument monitored events and metrics
  - maintain dashboards and runbooks for owned services
- Security / Governance:
  - review policy adherence and exceptions
  - map evidence to ISO control objectives
- Platform / SRE:
  - operate logging/monitoring stack availability and retention settings
  - maintain alert routing and on-call integrations

## 6. Minimum Technical Implementation Baseline

For dq-made-easy, the following baseline is required:
- Structured JSON logging enabled in API and execution services
- Correlation ID middleware and propagation
- Central observability stack (Grafana + Loki + Prometheus + Tempo)
- Alert rules for core availability, failure, and latency signals
- Dashboards for compile, retrieval, execution, and exception-store pathways
- An aggregated Execution Monitoring dashboard covering shared run, status, transition, latency, results/failures, compile, throughput, and executor-heartbeat signals across executors
- A shared Prometheus metric taxonomy for execution monitoring so multiple runtimes can contribute to one operational dashboard without runtime-specific naming drift

## 7. Verification and Evidence

Compliance evidence SHOULD include:
- sample structured logs showing mandatory fields
- alert definitions and alert test evidence
- dashboard snapshots/queries
- retention configuration screenshots or IaC configuration
- incident timeline examples showing correlation ID traceability

Policy compliance MUST be assessed quarterly and after major architecture changes.

## 8. Exceptions

Any exception to this policy MUST:
- be documented with justification and risk assessment
- have an approved owner and expiry date
- include compensating controls where possible

## 9. Related Documents

- architecture/adr/ADR-015-opentelemetry-instrumentation-for-distributed-tracing.md
- architecture/adr/ADR-016-iso27001-logging-and-monitoring-policy-adoption.md
- docs/technical/LOGGING_AND_MONITORING_POLICY_IMPLEMENTATION_CHECKLIST.md
- docs/technical/EXECUTION_MONITORING_METRIC_TAXONOMY.md
- docs/implementation-details/DQ_7_4_GX_SUITE_ORCHESTRATION_IMPLEMENTATION_DETAILS.md
