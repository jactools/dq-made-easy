---
title: "The data-catalog API now persists immutable natural-language draft request history and exposes a dedicated audit-history endpoint. The internal API contract registry recognizes the new route, and the endpoint returns the request's append-only audit trail in canonical snake_case JSON."
description: "Human-readable test proof generated from test-results/test-proof/0.11.3/api/ws8-a01-data-catalog-history-2026-06-05.json."
---

# The data-catalog API now persists immutable natural-language draft request history and exposes a dedicated audit-history endpoint. The internal API contract registry recognizes the new route, and the endpoint returns the request's append-only audit trail in canonical snake_case JSON.

This page was generated from [test-results/test-proof/0.11.3/api/ws8-a01-data-catalog-history-2026-06-05.json](../../../../test-results/test-proof/0.11.3/api/ws8-a01-data-catalog-history-2026-06-05.json).

## Summary

The data-catalog API now persists immutable natural-language draft request history and exposes a dedicated audit-history endpoint. The internal API contract registry recognizes the new route, and the endpoint returns the request's append-only audit trail in canonical snake_case JSON.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.3 |
| Proof Id | ws8-a01-data-catalog-history-2026-06-05 |
| Proof Type | api |
| Feature | WS8-A01 |
| Status | passed |
| Executed At Utc | 2026-06-05T21:39:22Z |
| Test File Count | 1 |
| Test Count | 33 |
| Command | cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi &amp;&amp; APP_CONFIG_ENCRYPTION_KEY='ksYUPwhhthla8CFag5CLNRqEYhwPIOHKkxfEgkVn9zk=' PYTHONPATH=/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-utils/src:/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-domain-validation/src /Users/jacbeekers/gitrepos/dq-rulebuilder/scripts/python_arm64.sh --python-bin /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest -o addopts='' tests/api/test_data_catalog_endpoints.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.2/command/20260605T213922Z-ws8-a01-data-catalog-history |

## Test Files

- tests/api/test_data_catalog_endpoints.py

## Assertions

- The new GET /api/data-catalog/v1/data-definition-tasks/requests/&#123;request_id&#125;/history endpoint returned 200 for an existing request and exposed the append-only request trail.
- The internal API contract registry resolved the new history route after the aggregate bundle was updated.
- The full data-catalog API regression file still passed after the contract and repository changes.

## Proof Data

```json
{
  "endpoint_status": 200,
  "registry_lookup": "resolved",
  "tests_passed": 33,
  "warnings": 2
}
```
