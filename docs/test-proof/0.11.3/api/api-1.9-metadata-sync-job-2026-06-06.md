---
title: "The connector sync endpoint now orchestrates metadata sync jobs, returns a completed job record with synced counts, and the governance status model exposes connector_sync_job lifecycle states."
description: "Human-readable test proof generated from test-results/test-proof/0.11.3/api/api-1.9-metadata-sync-job-2026-06-06.json."
---

# The connector sync endpoint now orchestrates metadata sync jobs, returns a completed job record with synced counts, and the governance status model exposes connector_sync_job lifecycle states.

This page was generated from [test-results/test-proof/0.11.3/api/api-1.9-metadata-sync-job-2026-06-06.json](../../../../test-results/test-proof/0.11.3/api/api-1.9-metadata-sync-job-2026-06-06.json).

## Summary

The connector sync endpoint now orchestrates metadata sync jobs, returns a completed job record with synced counts, and the governance status model exposes connector_sync_job lifecycle states.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.3 |
| Proof Id | api-1.9-metadata-sync-job-2026-06-06 |
| Proof Type | api |
| Feature | API-1.9 |
| Status | passed |
| Executed At Utc | 2026-06-05T23:32:23Z |
| Test File Count | 2 |
| Test Count | 10 |
| Command | cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi &amp;&amp; APP_CONFIG_ENCRYPTION_KEY='i0aU2BE0dzqEVAWxfEsvffw5zw93FjFZrr24RPVyo8c=' PYTHONPATH=/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-utils/src:/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-domain-validation/src /Users/jacbeekers/gitrepos/dq-rulebuilder/scripts/python_arm64.sh --python-bin /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest -o addopts='' tests/api/test_connector_endpoints.py tests/api/test_status_governance_endpoint.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.3/api/20260605T233223Z-api-1.9-metadata-sync-job |

## Test Files

- tests/api/test_connector_endpoints.py
- tests/api/test_status_governance_endpoint.py

## Assertions

- The connector sync route returns a completed job record for the configured provider.
- The sync job payload includes the completed metadata sync result and correlation id.
- The governance status model exposes connector_sync_job lifecycle states and transitions.

## Proof Data

```json
{
  "provider": "external_api",
  "sync_status": "completed",
  "status_model_entity": "connector_sync_job",
  "status_values": 5,
  "warnings": 2
}
```
