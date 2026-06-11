# ISO 27001 Logging & Monitoring Implementation - Ownership Matrix

**Document Version:** 1.0  
**Last Updated:** March 22, 2026  
**Review Cycle:** Annually or upon organizational restructuring  

## Overview

This matrix defines clear ownership, responsibilities, and escalation paths for all components of the ISO 27001-aligned logging and monitoring policy.

---

## 1. API Team (dq-api-team)

**Primary Focus:** FastAPI endpoint instrumentation, structured logging, request correlation

### Responsibilities

| Component | Task | Ownership | Escalation |
|---|---|---|---|
| API endpoint instrumentation | Add/update `log_event()` calls in critical endpoints | dq-api-team | Technical lead |
| Structured logging | Ensure all critical flows emit JSON with required fields | dq-api-team | Technical lead |
| Correlation propagation | Generate and forward `X-Correlation-ID` header | dq-api-team | Tech lead → ops-team-observability |
| Authentication logging | Log auth attempts, successes, failures with user identity | dq-api-team | Tech lead |
| Request/response logging | Capture HTTP method, path, status, duration for critical endpoints | dq-api-team | Tech lead |
| Sensitive data redaction | Implement and test redaction in [dq-api/fastapi/app/core/log_event.py](../../dq-api/fastapi/app/core/log_event.py) | dq-api-team | Tech lead |
| Upstream correlation propagation | Forward correlation ID to downstream services (engine, external APIs) | dq-api-team | Tech lead |
| Log governance integration | Participate in quarterly access reviews, respond to audit requests | dq-api-team | Manager |

### Testing Obligations
- Unit tests for redaction logic: [dq-api/fastapi/tests/core/test_log_event_redaction.py](../../dq-api/fastapi/tests/core/test_log_event_redaction.py)
- Middleware tests for correlation: [dq-api/fastapi/tests/middleware/test_middleware_focus.py](../../dq-api/fastapi/tests/middleware/test_middleware_focus.py)
- Request context tests: [dq-api/fastapi/tests/core/test_request_context.py](../../dq-api/fastapi/tests/core/test_request_context.py)

### Escalation Path
1. **Technical Issues:** Report to API Technical Lead (code review, tests, design)
2. **Policy Questions:** Escalate to ops-team-observability
3. **Compliance:** Escalate to security-team

---

## 2. Engine Team (dq-engine-team)

**Primary Focus:** Rule compilation, execution, exception recording with structured telemetry

### Responsibilities

| Component | Task | Ownership | Escalation |
|---|---|---|---|
| Engine execution logging | Instrument main.py with structured events (start, fetch, execute, post, complete) | dq-engine-team | Technical lead |
| Rule compilation telemetry | Log compilation success/failure with rule ID, status, duration | dq-engine-team | Technical lead |
| Exception recording | Emit exception events with `correlationId`, `ruleId`, `dataObjectId`, severity | dq-engine-team | Technical lead |
| Correlation propagation | Receive correlation ID from API, forward to worker via payload | dq-engine-team | Tech lead → ops-team-observability |
| Worker communication logging | Log queue depth, job submission, result retrieval with timing | dq-engine-team | Tech lead |
| Performance metrics emission | Export execution latency, throughput gauges to Prometheus | dq-engine-team | Tech lead |
| JSON logging utilities | Maintain [dq-utils/src/dq_utils/logging_utils.py](../../dq-utils/src/dq_utils/logging_utils.py) | dq-engine-team | Tech lead |
| Testing and validation | Unit tests for logging, smoke tests for correlation chain | dq-engine-team | Tech lead |

### Testing Obligations
- Correlation tests: [dq-engine/tests/test_correlation.py](../../dq-engine/tests/test_correlation.py)
- Runtime chain fixture: [dq-engine/tests/test_correlation_runtime_chain.py](../../dq-engine/tests/test_correlation_runtime_chain.py)

### Escalation Path
1. **Code Issues:** API Technical Lead (logging design, performance)
2. **Correlation Chain:** ops-team-observability (cross-service tracing)
3. **Database/Storage:** Platform team (exception store capacity, queries)
4. **Compliance:** security-team

---

## 3. Profiling/Worker Team (dq-profiling-team)

**Primary Focus:** Bull queue processing, job events, worker-level telemetry

### Responsibilities

| Component | Task | Ownership | Escalation |
|---|---|---|---|
| Worker instrumentation | Convert worker.ts string logs to structured JSON events | dq-profiling-team | Technical lead |
| Job lifecycle logging | Log job start, status updates, completion, failures with correlationId | dq-profiling-team | Technical lead |
| Queue monitoring | Emit queue depth, job processing latency to Prometheus | dq-profiling-team | Tech lead |
| Correlation propagation | Extract correlation ID from job payload, propagate in all worker events | dq-profiling-team | Tech lead |
| Error/exception handling | Log worker crashes, timeouts, resource exhaustion with context | dq-profiling-team | Tech lead |
| Concurrency safety | Ensure logging thread-safe (Node.js async context) | dq-profiling-team | Tech lead |
| JSON logger utility | Maintain [dq-profiling/src/logger.ts](../../dq-profiling/src/logger.ts) | dq-profiling-team | Tech lead |
| Testing | Unit tests for logging, integration tests for Bull event correlation | dq-profiling-team | Tech lead |

### Testing Obligations
- Smoke chain validation includes worker events: [scripts/verify_correlation_chain_smoke.sh](../../scripts/verify_correlation_chain_smoke.sh)
- Correlation propagation gate includes worker checks: [scripts/validate_correlation_propagation.sh](../../scripts/validate_correlation_propagation.sh)

### Escalation Path
1. **Code Issues:** Tech lead (Node.js async context, logging)
2. **Queue/Job Issues:** Platform team (Bull queue, Redis config)
3. **Correlation:** ops-team-observability
4. **Compliance:** security-team

---

## 4. Observability & Operations Team (ops-team-observability)

**Primary Focus:** Observability stack operation, governance, alerting, runbooks

### Responsibilities

| Component | Task | Ownership | Escalation |
|---|---|---|---|
| Infrastructure management | Operate Prometheus, Loki, Tempo, Grafana, databases | ops-team-observability | Team lead |
| Alert rule ownership | Create/update/maintain alert rules in [observability/prometheus/alerts.yml](../../observability/prometheus/alerts.yml) | ops-team-observability | Tech lead → CISO |
| Runbook creation | Author and maintain incident runbooks in [docs/runbooks/](../../docs/runbooks/) | ops-team-observability | Tech lead |
| Dashboard provisioning | Create/update Grafana dashboards under [observability/grafana/dashboards/](../../observability/grafana/dashboards/) | ops-team-observability | Tech lead |
| Retention policy enforcement | Configure and monitor log/metric/trace retention by environment | ops-team-observability | Tech lead |
| Access control management | Maintain GitHub CODEOWNERS, Grafana roles, Prometheus ACLs | ops-team-observability | Team lead → security-team |
| Quarterly access reviews | Audit and document active observability user roles | ops-team-observability | Team lead → security-team |
| Governance gate maintenance | Update CI/CD orchestration and validation scripts | ops-team-observability | Tech lead |
| Incident response | Respond to observability-related incidents per runbooks | ops-team-observability | Team lead → on-call escalation |
| Capacity planning | Monitor ingest rates, storage growth, project future capacity costs | ops-team-observability | Team lead → finance |
| Policy compliance | Ensure all changes comply with ISO 27001 throughout implementation | ops-team-observability | Team lead → security-team |

### Key Metrics Owned
- Alert SLA: Alert fires within 5 minutes of threshold breach
- Dashboard refresh: < 10 seconds
- Log ingestion latency: < 5 seconds (Loki)
- Trace sampling: Maintain < 500 GB/day ingest
- Governance gate success: 100% pass rate on main/master branches

### Escalation Path
1. **Operational:** Team lead (infrastructure, platform issues)
2. **Policy Violations:** security-team, CISO (compliance concerns)
3. **Budget:** Finance team (cost overruns)
4. **Executive:** Program lead (policy implementation status)

---

## 5. Security & Governance Team (security-team)

**Primary Focus:** Policy compliance, access control, data protection, audit

### Responsibilities

| Component | Task | Ownership | Escalation |
|---|---|---|---|
| Policy definition | Author and maintain ISO 27001 policies in docs/technical/ | security-team | CISO |
| Access control review | Approve role assignments, review quarterly access audits | security-team | CISO |
| Sensitive data handling | Review redaction policies, ensure PII/credentials protected | security-team | CISO |
| Compliance audits | Validate implementation against policy requirements | security-team | CISO |
| Incident escalation | Receive and review observability incidents > severity-high | security-team | CISO |
| Evidence pack curation | Archive compliance evidence for audit/export | security-team | CISO |
| Privacy requests | Process GDPR/CCPA deletion requests with ops teams | security-team | Legal |
| Policy update schedule | Maintain quarterly review cycle + annual attestation | security-team | CISO |

### Escalation Path
1. **Policy Questions:** CISO (strategic direction)
2. **Regulatory:** Legal team (compliance implications)
3. **Executive:** Audit committee (compliance status)

---

## 6. Database/Storage Team (dq-db-team)

**Primary Focus:** PostgreSQL exception store, schema management, query optimization

### Responsibilities

| Component | Task | Ownership | Escalation |
|---|---|---|---|
| Exception store schema | Design and maintain exceptions table with correlationId, required fields | dq-db-team | DBA lead |
| Query optimization | Ensure exception insert/select/delete queries meet SLA | dq-db-team | DBA lead |
| Retention cleanup | Schedule and run weekly DELETE operations for expired records | dq-db-team | DBA lead |
| Archive procedures | Export monthly exception records to S3 with encryption | dq-db-team | DBA lead |
| Capacity planning | Monitor table growth, project storage needs, recommend archival | dq-db-team | DBA lead |
| Backup/recovery | Ensure exception data is backed up and recoverable | dq-db-team | DBA lead |
| Performance monitoring | Alert on slow queries, connection leaks, write failures | dq-db-team | DBA lead |
| Access control | Grant minimal permissions to engine service for write operations | dq-db-team | DBA lead → security-team |

### Escalation Path
1. **Performance:** DBA lead (queries, indexing)
2. **Capacity:** Team lead → Finance (additional storage)
3. **Security:** security-team (access control, encryption)

---

## 7. On-Call / Incident Response (on-call-escalation)

**Primary Focus:** Respond to alerts, execute runbooks, escalate when needed

### Responsibilities

| Component | Task | Ownership | Escalation |
|---|---|---|---|
| Alert response | Monitor and respond to critical alerts per runbooks | on-call-rotation | ops-team lead |
| Incident triage | Determine root cause using correlation IDs and logs | on-call-rotation | ops-team lead |
| Runbook execution | Follow documented investigation/mitigation steps | on-call-rotation | ops-team lead |
| Escalation | Contact service owners (API, Engine, Worker teams) if needed | on-call-rotation | ops-team lead |
| Documentation | Update incident ticket with timeline, findings, and remediation | on-call-rotation | ops-team lead |
| Post-incident | Participate in incident review, suggest runbook updates | on-call-rotation | ops-team lead |

### Escalation Path
1. **Uncertain Severity:** ops-team-observability lead (severity assessment)
2. **Multi-service:** ops-team lead + service technical leads
3. **Policy Violation:** security-team (if compliance impact)
4. **Executive:** Program lead (if revenue impact or major incident)

---

## 8. Ownership Summary Table

### By Policy Area

| Policy Area | Primary Owner | Secondary Owner | Tertiary Owner |
|---|---|---|---|
| **Structured Logging** | dq-api-team | dq-engine-team, dq-profiling-team | ops-team-observability |
| **Correlation ID Propagation** | dq-api-team | dq-engine-team, dq-profiling-team | ops-team-observability |
| **Monitoring & Alerts** | ops-team-observability | dq-api-team, dq-engine-team | security-team |
| **Dashboards** | ops-team-observability | dq-api-team, dq-engine-team | — |
| **Incident Runbooks** | ops-team-observability | dq-api-team, dq-engine-team, dq-profiling-team | on-call-rotation |
| **Time Synchronization** | ops-team-observability | dq-api-team, dq-engine-team, dq-profiling-team | — |
| **Data Redaction** | dq-api-team | dq-engine-team | security-team |
| **Access Control** | ops-team-observability | security-team | CISO |
| **Retention & Disposal** | ops-team-observability | dq-db-team | security-team |
| **Evidence & Compliance** | security-team | ops-team-observability | CISO |
| **Quarterly Reviews** | security-team | ops-team-observability | CISO |

### By Service

| Service | Primary Owner | Logging Responsibilities | Monitoring Responsibilities |
|---|---|---|---|
| dq-api (FastAPI) | dq-api-team | Endpoint events, correlation, redaction | HTTP status, latency, error rate |
| dq-engine (Python) | dq-engine-team | Execution events, exceptions | Compilation, execution, throughput |
| dq-profiling (Node.js) | dq-profiling-team | Job events, queue events | Job latency, queue depth |
| Prometheus | ops-team-observability | Alert rule definitions | Metric handling, storage |
| Loki | ops-team-observability | Log ingestion, retention | Query latency, storage growth |
| Tempo | ops-team-observability | Trace ingestion, sampling | Trace queries, retention |
| PostgreSQL (exceptions) | dq-db-team | Exception table schema | Exception store write latency |
| Grafana | ops-team-observability | Dashboard provisioning | Dashboard availability |

---

## 9. Communication and Escalation Paths

### Regular Syncs

| Frequency | Group | Topics |
|---|---|---|
| Weekly | ops-team-observability | Alert tuning, capacity, incidents |
| Bi-weekly | ops-team-observability + service leads | Governance gate results, logging improvements |
| Monthly | security-team + ops-team-observability | Compliance status, access reviews, incidents |
| Quarterly | CISO + all teams | Policy attestation, evidence pack review, roadmap |

### Incident Escalation Levels

**Severity 1 (Critical):** Data loss, compliance breach, complete service unavailability
- **Page:** On-call lead + ops-team-observability lead + service tech leads
- **Notify:** security-team (if compliance impact), CISO (if public impact)
- **Runbook:** Activate incident-response runbook, open Severity-1 ticket

**Severity 2 (High):** Significant alerts firing, partial unavailability, performance degradation
- **Page:** On-call engineer
- **Notify:** ops-team-observability lead, service technical lead
- **Runbook:** Follow service-specific incident runbook

**Severity 3 (Medium):** Minor alerts, degraded performance, individual service issues
- **Manual Review:** ops-team-observability during business hours
- **Runbook:** Document for future pattern recognition

**Severity 4 (Low):** Informational, warning-level alerts, minor degradation
- **Log & Monitor:** ops-team-observability during subsequent sprint planning

---

## 10. Role Definitions

### Technical Lead (per service)
- Makes technical decisions on logging/monitoring implementation
- Reviews PRs for logging compliance
- Represents service in bi-weekly syncs
- On-call rotation for service-specific incidents

### DBA Lead
- Designs and optimizes exception store schema
- Manages retention policies, cleanup, archival
- Capacity planning, performance monitoring

### ops-team-observability Lead
- Owns observability infrastructure (Prometheus, Loki, Tempo, Grafana)
- Coordinates governance gates and policy enforcement
- Escalation point for alert/monitoring questions

### security-team Lead / CISO
- Policy author and interpreter
- Compliance auditor and attestator
- Escalation point for security/compliance incidents

### on-call Lead
- Manages on-call rotation
- Escalation point for incidents beyond on-call engineer capability
- Schedules incident reviews

---

## 11. Change Control Process Ownership

| Phase | Owner | Duration | Approval Required |
|---|---|---|---|
| **Proposal** | Service team or ops-team-observability | 3 days | Technical lead |
| **Design Review** | ops-team-observability + affected service leads | 3 days | Tech leads (>1) |
| **Implementation** | Service team | Variable | Tech lead, code review |
| **Testing** | Service team + ops-team-observability | Variable | All governance gates pass |
| **Deployment** | ops-team-observability | N/A | CISO (if policy-impacting) |
| **Verification** | ops-team-observability + on-call | 1 day | ops-team lead |
| **Post-Implementation** | ops-team-observability | 30 days | Document findings |

---

## 12. Feedback Channels

- **Policy Feedback:** security-team slack channel or quarterly review session
- **Runbook Updates:** ops-team-observability-internal
- **Logging Questions:** dq-engineering slack channel or team syncs
- **Escalations:** ops-team lead or CISO (depending on subject)

---

## Document History

| Date | Version | Author | Changes |
|---|---|---|---|
| 2026-03-22 | 1.0 | ops-team-observability | Initial ownership matrix for ISO 27001 policy implementation |
