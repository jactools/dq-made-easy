# Incident Runbooks

This directory contains playbooks for responding to critical production alerts in the dq-made-easy system.

## Overview

Each runbook provides:
- **Alert Condition:** What triggers the alert
- **Investigation Steps:** How to diagnose the root cause
- **Mitigation:** Immediate and short-term fixes
- **Recovery:** How to return to normal operation
- **Escalation:** When to involve on-call personnel

All runbooks emphasize the use of **correlation IDs** for tracing requests across services and identifying the scope of impact.

## Critical Alerts

### [API 5xx Error Spike](/docs/runbooks/INCIDENT_API_5XX_SPIKE/)
- **Service:** dq-api (FastAPI)
- **Trigger:** HTTP 5xx error rate > 1% over 5 minutes
- **Severity:** Critical
- **Root Causes:** DB connection failures, auth issues, resource exhaustion
- **Key Actions:** Check logs by correlationId, verify DB/Redis, restart API if needed

### [Compile Failure Spike](/docs/runbooks/INCIDENT_COMPILE_FAILURE_SPIKE/)
- **Service:** dq-engine (Python)
- **Trigger:** Rule compilation failure rate > 10% over 5 minutes
- **Severity:** High
- **Root Causes:** Invalid rule syntax, schema mismatches, engine resource issues
- **Key Actions:** Identify affected rules by ruleId, check for recent changes, disable if needed

### [Executor Timeout Spike](/docs/runbooks/INCIDENT_EXECUTOR_TIMEOUT_SPIKE/)
- **Service:** dq-engine + dq-profiling (worker)
- **Trigger:** Execution timeout rate > 5% over 5 minutes
- **Severity:** High
- **Root Causes:** Slow database queries, complex rules, resource contention
- **Key Actions:** Check resource usage, identify rule complexity, increase timeout threshold temporarily

### [Exception Store Write Failure](/docs/runbooks/INCIDENT_EXCEPTION_STORE_WRITE_FAILURE/)
- **Service:** dq-engine + Database (PostgreSQL)
- **Trigger:** Exception write failures > 5 minutes or > 10 consecutive failures
- **Severity:** Critical (data loss risk)
- **Root Causes:** DB connectivity, disk space, permission issues, schema problems
- **Key Actions:** Verify DB connectivity, check disk space, restart DB if needed

## Using Runbooks

1. **Identify the Alert:** Match the alert name to the runbook title
2. **Read the Overview Section:** Understand the severity and scope
3. **Follow Investigation Steps:** Use provided commands to diagnose
4. **Apply Mitigation:** Implement immediate fixes as needed
5. **Document:** Save correlation IDs and timeline for incident review
6. **Escalate if Needed:** Follow escalation criteria based on time/scope

## Correlation ID Tracing

All runbooks leverage `correlationId` fields in structured JSON logs to:
- Follow a single request across API → Engine → Worker services
- Correlate exceptions in the exception store with originating requests
- Audit the complete lifecycle of a rule execution

Access logs by correlation ID in Loki/ELK:
```
{correlationId="<id>"}
```

## Retention and Updates

- Runbooks are reviewed and updated quarterly or whenever alert rules change
- Each runbook should be tested in staging before deployment
- Keep runbooks concise and command-ready for on-call responders
