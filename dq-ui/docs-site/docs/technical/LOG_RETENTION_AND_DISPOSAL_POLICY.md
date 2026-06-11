# Log Retention and Disposal Policy

**Compliance:** ISO 27001 Annex A 8.15 (Logging/Monitoring) & 5.3.2 (Retention of Information)  
**Last Updated:** March 2026  
**Review Cycle:** Annually (Q4)

## Retention Policy Overview

### Purpose
Define retention schedules for logs, metrics, and traces across environments to:
- Maintain sufficient operational history for incident investigation
- Balance cost with compliance and operational requirements
- Ensure timely disposal of no-longer-needed data per privacy regulations

### General Principles
1. **Centrally Managed:** All retention policies defined in this document, version-controlled in Git
2. **UTC-Based:** Retention windows calculated from UTC timestamps in logs
3. **Environment-Specific:** Different tiers (dev/test/stage/prod) have different retention
4. **Automated:** Retention policies enforced by observability stack (Prometheus retention flags, Loki retention config, Tempo, etc.)
5. **Auditable:** All retention operations logged with deletion counts and affected records counts

## Retention Schedule By Environment

### Production (Prod)

#### Structured Logs (Loki)
- **Duration:** 90 days
- **Rationale:** Sufficient for multi-week incident investigations; cost-optimized for PROD
- **TTL Label:** All logs auto-tagged with `retention: prod90`
- **Cleanup:** Automated daily at 02:00 UTC via Loki retention job

#### Metrics (Prometheus)
- **Duration:** 15 days (default local) + 90 days archived (cloud object storage)
- **Rationale:** Real-time alerts need current metrics; archive retained for long-term trends
- **Scrape Interval:** 15s (high frequency for accuracy)
- **TSDB Retention:** `--storage.tsdb.retention.time=15d`
- **Archive:** Daily snapshot to S3 at 03:00 UTC, retained 90 days

#### Distributed Traces (Tempo)
- **Duration:** 72 hours (3 days)
- **Rationale:** Sufficient for same-day incident triage; high cost per trace
- **Sampling Rate:** 100% for errors, 10% for success (adaptive sampling)
- **Distributed Tracing:** All traces include `correlationId` for linking to logs
- **Archive:** Traces for production incidents manually exported to S3 for 90 days

#### Exception Store (PostgreSQL)
- **Duration:** 365 days (rolling)
- **Rationale:** Full year retention for compliance audits and root cause data
- **Cleanup Query:** `DELETE FROM exceptions WHERE created_at < NOW() - INTERVAL '365 days';`
- **Schedule:** Weekly cleanup at 04:00 UTC on Sundays
- **Archive:** Monthly export of exceptions to S3 for 3 years (compliance)

---

### Staging & Test (Staging/UAT)

#### Structured Logs (Loki)
- **Duration:** 30 days
- **Rationale:** Lower cost; sufficient for staging testing cycles
- **TTL Label:** `retention: staging30`
- **Cleanup:** Automated daily at 02:30 UTC

#### Metrics (Prometheus)
- **Duration:** 7 days
- **Rationale:** Reduced cost; staging metrics primarily for load tests
- **TSDB Retention:** `--storage.tsdb.retention.time=7d`
- **No Archive:** Staging metrics not archived (can be regenerated)

#### Distributed Traces (Tempo)
- **Duration:** 24 hours (1 day)
- **Rationale:** Minimal cost; short retention for test coverage validation
- **Sampling Rate:** 100% for all traces (full capture for test validation)

#### Exception Store (PostgreSQL)
- **Duration:** 90 days (rolling)
- **Cleanup Query:** `DELETE FROM exceptions WHERE created_at < NOW() - INTERVAL '90 days';`
- **Schedule:** Weekly cleanup at 05:00 UTC on Sundays

---

### Development (Dev)

#### Structured Logs (Loki)
- **Duration:** 7 days
- **Rationale:** Minimal retention; local development cleanup
- **TTL Label:** `retention: dev7`
- **Cleanup:** Daily cleanup at 06:00 UTC

#### Metrics (Prometheus)
- **Duration:** 3 days
- **Rationale:** Local dev metrics; can be reset anytime
- **TSDB Retention:** `--storage.tsdb.retention.time=3d`

#### Distributed Traces (Tempo)
- **Duration:** 12 hours (0.5 day)
- **Rationale:** Minimal retention for local testing

#### Exception Store (PostgreSQL)
- **Duration:** 30 days
- **Cleanup Query:** `DELETE FROM exceptions WHERE created_at < NOW() - INTERVAL '30 days';`
- **Schedule:** Weekly cleanup at 07:00 UTC

---

## Retention Configuration

### Docker Compose (Local/Dev Deployments)

```yaml
  prometheus:
    environment:
      # Override with: --storage.tsdb.retention.time=<duration>
      PROMETHEUS_RETENTION_TIME: 3d  # Dev/Test
      PROMETHEUS_RETENTION_SIZE: 5GB

  loki:
    environment:
      # Set table retention in config
      LOG_LEVEL: info
    volumes:
      - ./observability/loki/loki-config-dev.yml:/etc/loki/local-config.yml

  tempo:
    environment:
      # Configured in tempo-config.yml
      TEMPO_RETENTION: 12h  # Dev; 72h for Prod
```

### Loki Configuration (loki-config.yml)

```yaml
limits_config:
  retention_period: 7d  # Dev
  # Prod: 90d

schema_config:
  configs:
    - from: 2020-01-01
      store: boltdb
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h
```

### Tempo Configuration (tempo-config.yml)

```yaml
distributor:
  # Sampling policies to reduce ingestion
  trace_idle_period: 10s
  max_block_duration: 5m

ingester:
  # Block duration smaller for faster falloff
  block_retention: 72h  # Prod; 12h for Dev
```

### Prometheus Docker Compose

```yaml
prometheus:
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.path=/prometheus'
    - '--storage.tsdb.retention.time=15d'  # Prod; 3d for Dev, 7d for Staging
    - '--storage.tsdb.retention.size=50GB'  # Adjust per environment capacity
```

## Disposal Process

### Automated Cleanup

All retention policies rely on **automated cleanup jobs** executed by observability stack:

1. **Loki:** Built-in retention enforcer, runs daily after cutoff time
2. **Prometheus:** TSDB cleanup runs on compaction cycle
3. **Tempo:** Built-in retention policy enforcer
4. **PostgreSQL Exception Store:** Scheduled SQL DELETE via pg_cron or external scheduler

### Manual/Ad-Hoc Cleanup

**Authorized Personnel:** ops-team-observability lead + DBA  
**Justification:** Incident response, privacy requests, compliance holds

**Process:**
1. File change request ticket
2. Document reason (e.g., "GDPR user data deletion request for user X")
3. Generate preview of affected records (count + time range)
4. Obtain approval from security-team
5. Execute deletion with transaction logging
6. Document deletion counts + time in ticket

**Example Privacy Request Deletion:**
```sql
-- Preview affected records (non-destructive)
SELECT COUNT(*) FROM log_entries 
WHERE user_id = '<user-uuid>' AND created_at BETWEEN '2025-01-01' AND '2025-03-22';

-- Execute deletion (in transaction, logged)
DELETE FROM log_entries 
WHERE user_id = '<user-uuid>' AND created_at BETWEEN '2025-01-01' AND '2025-03-22';

-- Verify deletion
VACUUM ANALYZE log_entries;
```

### Archival Before Disposal

**For Compliance & Audit:**

1. **Exception Store (Prod):** Monthly archival to S3 `dq-compliance-archive/exceptions/monthly-YYYY-MM.tar.gz`
2. **Incident Traces (Prod):** Manual export of relevant traces to S3 after incident closure
3. **Audit Logs:** All configuration changes (from Git + API audit logs) exported quarterly to S3 with signed certificate

**Archive Format:**
```
s3://dq-compliance-archive/
├── exceptions/
│   └── monthly-2026-03.tar.gz
├── incidents/
│   ├── 2026-03-15-api-5xx-spike/
│   │   ├── traces-export.json
│   │   ├── logs-sample.jsonl
│   │   └── incident-summary.md
└── audit-logs/
    └── quarterly-2026-Q1-audit.tar.gz.gpg
```

**Lifecycle:**
- Production data archived 3 years before final deletion
- Encrypted (GPG/KMS) and integrity-checked (SHA256)
- Access requires security-team approval + audit trail

## Cost Optimization

### Sampling Strategies

**Error-Driven Sampling:**
```yaml
Tempo sampling:
  # 100% of errors (severity=ERROR or exception present)
  # 50% of span > 1s duration
  # 10% of normal success paths
```

**Metric Downsampling:**
- Prometheus: Keep raw 15s metrics for 15 days; downsample to 5m interval for >15 days in archive
- Example: `rate(metric[1m])` auto-downsampled to `rate(metric[5m])` in archive

### Size Estimates

**Typical Production Footprint (Daily Ingest):**
- **Logs (Loki):** ~500 GB/day (1000s of events/sec) → 90-day retention = ~45 TB
- **Metrics (Prometheus):** ~50 GB/day (15s scrape interval) → 15-day retention = ~750 GB + 90-day archive = ~4.5 TB
- **Traces (Tempo):** ~20 GB/day (10% sampling) → 3-day retention = ~60 GB
- **Exception Store:** ~2 GB/day → 365-day retention = ~730 GB

**Total:** ~51 TB current, ~6 TB archive growth/month

### Cost Reduction Levers

1. **Reduce Sampling:** Lower error sampling to 50%, normal to 5% (reduces trace ingest 50%)
2. **Increase Scrape Interval:** Change Prometheus from 15s to 30s (50% cost reduction, acceptable for non-real-time alerts)
3. **Shorten Retention:** Move Prod logs from 90→60 days (less applicable; retention driven by compliance)
4. **Metric Exclusion:** Drop low-value metrics (e.g., debug-only counters)

## Monitoring & Alerting

### Capacity Alerts

**Alert:** `loki_storage_capacity_warning` fires when usage > 70% of allocated space  
**Action:** Reduce retention or increase capacity

**Alert:** `prometheus_tsdb_size_warning` fires when > 40 GB  
**Action:** Review scrape interval or sampling

### Audit

**Monthly Report:**
- Data ingestion rates by component
- Retention policy enforcement (count of deleted records)
- Archive creation confirmations
- Cost trends

**Owner:** ops-team-observability  
**Distribution:** Monthly to finance + ops leadership

## Compliance Attestation

This retention policy satisfies:
- ✅ **ISO 27001 A.5.3.2:** Information retention justified and documented
- ✅ **ISO 27001 A.8.15:** Logging retention protects logs from unauthorized access/modification
- ✅ **GDPR Article 5(1)(e):** Data stored no longer than necessary ("storage limitation")
- ✅ **SOC 2 CC6.1:** Appropriate retention for audit and compliance

## Policy Changes

**Review Schedule:** Annually in Q4 (October)  
**Change Process:**
1. File GitHub issue in `quarterly-governance-reminder` (Oct 1st)
2. Review and update retention numbers based on:
   - Current cost trends
   - Compliance changes
   - New observability tools
3. PR with updated doc + updated docker-compose examples
4. Deploy to all environments after approval

**Last Review:** March 2026 (inaugural version)  
**Next Review:** October 2026
