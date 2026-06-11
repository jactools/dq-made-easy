# Log Integrity and Access Control Policy

**Compliance:** ISO 27001 Annex A 8.1 (User Access Management) & 8.15 (Logging/Monitoring)  
**Last Updated:** March 2026  
**Status:** Operational

## Least-Privilege Access Control

### 1. Grafana Access Tiers

#### Viewer (Read-Only)
- **Who:** On-call engineers, SREs, developers
- **Permissions:**
  - View all dashboards
  - View metrics and logs
  - Export dashboard JSON
- **Restrictions:**
  - No alert configuration changes
  - No data source modifications
  - No user management
- **Role:** `Viewer`
- **Provisioning:** OAuth/OIDC auto-assignment based on team membership

#### Editor
- **Who:** Dedicated observability team, senior engineers
- **Permissions:**
  - Create/edit dashboards
  - Modify alert rules
  - Manage datasources
  - Configure notification channels
- **Restrictions:**
  - No user role changes
  - No admin settings
  - No authentication backend changes
- **Role:** `Editor`
- **Provisioning:** Manual assignment by admin with quarterly review

#### Admin
- **Who:** SRE team lead, platform engineers
- **Permissions:**
  - Full system access
  - User/team management
  - Authentication configuration
  - Backup/restore operations
- **Restrictions:**
  - Require 2FA (MFA)
  - All actions logged to audit trail
  - Requires approval for prod-critical changes
- **Role:** `Admin`
- **Provisioning:** Manual assignment with signed policy acknowledgment

### 2. Prometheus Access Control

#### Scrape Configuration
- **Responsibility:** ops-team-observability
- **Access Level:** Restricted file-based (Git-based change control)
- **Changes Require:**
  - Git pull request review (minimum 2 approvals)
  - Automated validation of scrape targets
  - Testing in staging environment

#### Alert Rules Modification
- **Responsibility:** ops-team-observability + on-call escalation lead
- **Access Level:** Same as scrape configuration (Git-based)
- **Changes Require:**
  - Associated Jira ticket or incident ID
  - Testing of alert firing condition in test environment
  - Runbook update before deployment

### 3. Loki/Log Aggregation Access Control

#### Log Read Access
- **Who:** All authenticated users (by default)
- **Restrictions:** Optional filtering by label/namespace (not by default to preserve debugging)
- **Exceptions:** See "Sensitive Data Redaction" below

#### Log Retention Admin
- **Who:** ops-team-observability only
- **Permissions:**
  - Modify retention policies
  - Execute retention cleanup jobs
  - Archive/export logs for audit

### 4. Tempo (Distributed Tracing) Access Control

#### Trace Read Access
- **Who:** All authenticated users
- **Restrictions:** Can query by trace ID, correlationId, service name
- **Limitations:** No wildcard query timeouts > 24 hours

#### Trace Configuration
- **Who:** ops-team-storage (trace backend)
- **Permissions:**
  - Modify ingestion rate limits
  - Configure sampling policies
  - Manage storage retention

## Audit Trail and Accountability

### Grafana Audit Logging

All dashboard and alert modifications logged with:
- **User:** OIDC identity (email/username)
- **Timestamp:** UTC timestamp
- **Action:** Create/Update/Delete + detailed change
- **IP Address:** Source network origin
- **Change Details:** Before/after JSON diff

**Configuration:**
```yaml
[audit]
enabled = true
log_path = /var/log/grafana/audit.log
log_mode = file
log_maxdays = 90
log_maxsize = 100
```

### Prometheus Configuration Audit

All changes to prometheus.yml and alerts.yml tracked via Git:
- Commits include user, timestamp, change description
- All changes require PR review (Git blame per line)
- CI/CD validates syntax and semantics before merge

### API Access Logging

API calls to create/modify observability resources logged with:
- User identity from JWT token
- Request timestamp (UTC)
- Resource type and ID
- HTTP status code
- Request duration

Example API events:
```json
{
  "ts": "2026-03-22T10:15:00Z",
  "event": "observability_api_call",
  "action": "create_alert",
  "user": "ops-engineer@example.com",
  "resource_type": "alert_rule",
  "resource_id": "dq_exception_store_write_failure",
  "status_code": 201,
  "duration_ms": 145
}
```

## Sensitive Data Redaction in Logs

### Automatic Redaction

Logs from all services automatically redact:
- **Authentication Tokens:** `authorization`, `bearer_token`, `api_key`, `jwt`
- **Database Credentials:** `password`, `secret`, `db_password`, `connection_string`
- **PII:** Email addresses in certain contexts, user IDs beyond correlation purposes
- **Raw Payload Rows:** Values for keys matching `row|rows|record|records`

**Implementation:**
- FastAPI: [dq-api/fastapi/app/core/log_event.py](../../dq-api/fastapi/app/core/log_event.py)
- Contract validation: [scripts/validate_log_redaction_contract.sh](../../scripts/validate_log_redaction_contract.sh)

### Sensitive Endpoints

High-risk endpoints with additional redaction:
- `/auth/v1/login` - Redact password in request body logs
- `/auth/v1/refresh` - Redact token values
- `/rulebuilder/v1/rules/{id}/execute` - Redact raw data payloads in request
- `/rulebuilder/v1/approvals/{id}` - Redact approval comments if they contain PII

## Repository-Level Access Control

### Configuration File Ownership

**File:** `.github/CODEOWNERS`

```
# Observability configurations
observability/prometheus/ @ops-team-observability
observability/grafana/ @ops-team-observability
observability/loki/ @ops-team-logging
docs/runbooks/ @ops-team-observability @security-team

# Logging infrastructure
dq-api/fastapi/app/core/logging_config.py @dq-api-team @ops-team-observability
dq-utils/src/dq_utils/logging_utils.py @dq-engine-team @ops-team-observability
dq-profiling/src/logger.ts @dq-profiling-team @ops-team-observability

# Governance gates
scripts/validate_*.sh @ops-team-observability
scripts/verify_correlation_chain_smoke.sh @ops-team-observability
.github/workflows/governance-gates.yml @ops-team-observability
```

**Enforcement:**
- Pull requests to protected files require approval from code owners
- GitHub branch protection rule: "Require code owner review"

### Change Control Process

1. **Propose Change:** File GitHub issue with `audit-change` label
2. **Design Review:** Observability team reviews proposed change
3. **Implementation:** Create PR from design review ticket
4. **Testing:** Run governance gates in CI/CD
5. **Code Review:** Minimum 2 approvals (one from owning team)
6. **Approval:** Schedule change window if prod-impacting
7. **Deployment:** Merge and auto-deploy (if green CI/CD)
8. **Verification:** On-call runs validation script and confirms no regressions
9. **Audit Entry:** Change logged with issue link and reviewer names

## Quarterly Access Review

**Schedule:** First week of each quarter (Jan, Apr, Jul, Oct)  
**Owner:** ops-team-observability + security-team  
**Process:**

1. **Audit Active Roles**
   - Generate list of all Grafana/Prometheus users with current permissions
   - Cross-reference with personnel roster
   - Identify any orphaned or stale accounts (remove)

2. **Verify Team Assignments**
   - Confirm each user role matches their current job function
   - Escalate any mismatched roles to manager for correction

3. **Review Recent Changes**
   - Generate audit log of all configuration changes in last quarter
   - Verify each change had proper approval and has associated issue/ticket
   - Flag any orphaned changes without traceability

4. **Document Findings**
   - Create signed attestation of review completion
   - Archive in compliance folder
   - Link to incident tickets if issues found

5. **Remediation**
   - Add tickets for issues identified
   - Plan and execute fixes in next sprint

**Evidence Artifact:**
- File: `docs/compliance/quarterly-access-review-{YYYY-Q}.md`
- Content: Reviewer signatures, reviewed-user list, changes summary, findings/remediation plan

## Compliance Statements

### ISO 27001 A.8.1 (User Access Management)
✅ Principle: "Restrict access to information and information processing facilities only to authorized users"
- Implemented via OIDC-based role assignment and GitHub CODEOWNERS enforcement
- Quarterly access reviews ensure principle enforcement

### ISO 27001 A.8.15 (Logging)
✅ Principle: "Logging functions shall be protected against tampering"
- Prometheus/Loki configured with read-only replica mounts
- Git audit trail for all config changes with immutable commit history
- API audit logging includes user + timestamp for all observability operations

### ISO 27001 A.8.16 (Monitoring)
✅ Principle: "Monitoring activities should not reveal sensitive information"
- Automatic redaction of authentication tokens, credentials, PII, raw data payloads
- Redaction contract validated in CI/CD pipeline
- Sensitive endpoints have additional redaction rules
