# API-1 New Data Source Connectors

Goal: Enable onboarding of external data platforms through a consistent connector framework for metadata discovery, profiling, and rule execution readiness.

Related work: [API-7 Real DQ Rule Execution](/docs/features/API_7_REAL_DQ_RULE_EXECUTION/)

## Phase 1: Connector Framework

- Define a pluggable connector interface in `dq-api` for `configure`, `validate`, `discover`, `sync`, and `health`.
- Add connector registry to support provider-based loading and capability flags.
- Create common error model for connection/auth/schema failures.
- Add secure config contract for connector credentials and secrets references.

## Phase 2: MVP Connectors

- Implement `PostgreSQL` connector for schema and table discovery.
- Implement `SQL Server` connector for enterprise onboarding parity.
- Implement `Azure ADLS` connector for warehouse use cases.
- Implement `S3/Blob` file connector for dataset-level metadata ingestion.

## Phase 3: API + UX Surface

- Add endpoints to create/update connector configs per workspace/tenant.
- Add `test-connection` and `discover-assets` endpoints.
- Add metadata sync endpoint with job status tracking.
- Add UI flow for connector setup, validation, and sync status.

## Phase 4: Operations, Governance, and Security

- Add retry/backoff and observable sync job states.
- Add audit trail for connector configuration changes.
- Enforce least-privilege guidance and redact secrets in logs/responses.
- Add connector health dashboard indicators and stale-sync alerts.

## Acceptance Criteria

- At least two connector types can be configured and synced end-to-end.
- Synced metadata is available for rule attribute assignment.
- Connection failures return actionable diagnostics.
- Secrets are never exposed in API responses or standard logs.
- Connector sync status is visible to users with timestamps.

## Tracked Work Items (Proposed)

- [x] `API-1.1` Connector interface + registry
- [x] `API-1.2` Secure connector config schema + secrets handling
- [x] `API-1.3` PostgreSQL connector (discover + sync)
- [x] `API-1.4` SQL Server connector (discover + sync)
- [x] `API-1.5` External API connector (discover + sync)
- [x] `API-1.6` Azure ADLS connector (discover + sync)
- [x] `API-1.7` S3/Blob connector metadata ingestion
- [x] `API-1.8` Connection test + discovery endpoints
- [x] `API-1.9` Metadata sync job orchestration + status model
- [x] `UX-1.5` Connector setup and sync UI flow
- [x] `WF-1.5` Connector audit trail + governance hooks
- [x] `DOC-1.5` Connector onboarding runbook ([runbook](/docs/technical/CONNECTOR_ONBOARDING_RUNBOOK/))
- [x] `API-1.10` Async sync job queue with status polling (background jobs, job history, cancellation)
- [x] `API-1.11` Retry/backoff policy for transient connection failures (exponential backoff with jitter)
- [x] `API-1.12` Scheduled connector syncs (cron/frequency-based, next-run computation)
- [x] `API-1.13` Incremental sync support (asset snapshots, checksum-based drift detection)
- [x] `API-1.14` Staleness health indicators (age-based staleness check endpoint)
- [x] `API-1.15` Background sync worker (db-polling, claim-and-process, retry loop)

## Delivery Milestones

- Milestone A (Framework): `API-1.1` to `API-1.2`
- Milestone B (Connectors): `API-1.3` to `API-1.6`
- Milestone C (API/Jobs): `API-1.7` to `API-1.8`
- Milestone D (UX/Governance/Docs): `UX-1.5`, `WF-1.5`, `DOC-1.5`
- Milestone E (Async Operations): `API-1.10` to `API-1.15`
