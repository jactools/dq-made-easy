---
title: "The connector test-connection and discover-assets endpoints now route through the connector registry, validate connector configuration payloads, and return connector health and discovery results behind the internal API contract gate."
description: "Human-readable test proof generated from test-results/test-proof/0.11.3/api/api-1.8-connector-test-discovery-2026-06-05.json."
---

# The connector test-connection and discover-assets endpoints now route through the connector registry, validate connector configuration payloads, and return connector health and discovery results behind the internal API contract gate.

This page was generated from [test-results/test-proof/0.11.3/api/api-1.8-connector-test-discovery-2026-06-05.json](../../../../test-results/test-proof/0.11.3/api/api-1.8-connector-test-discovery-2026-06-05.json).

## Summary

The connector test-connection and discover-assets endpoints now route through the connector registry, validate connector configuration payloads, and return connector health and discovery results behind the internal API contract gate.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.3 |
| Proof Id | api-1.8-connector-test-discovery-2026-06-05 |
| Proof Type | api |
| Feature | API-1.8 |
| Status | passed |
| Executed At Utc | 2026-06-05T23:27:55Z |
| Test File Count | 1 |
| Test Count | 3 |
| Command | cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi &amp;&amp; PYTHONPATH=/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-utils/src:/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-domain-validation/src /Users/jacbeekers/gitrepos/dq-rulebuilder/scripts/python_arm64.sh --python-bin /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest -o addopts='' tests/api/test_connector_endpoints.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.3/api/20260605T232755Z-api-1.8-connector-test-discovery |

## Test Files

- tests/api/test_connector_endpoints.py

## Assertions

- The test-connection route returns a healthy connector result for the configured provider.
- The discover-assets route returns connector discovery data for the configured provider.
- A provider mismatch is rejected with a 400 response.

## Proof Data

```json
{
  "routes": 2,
  "warnings": 2
}
```
