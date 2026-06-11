---
title: "The external API connector accepts an explicit API operation inventory, augments discovery from an optional OpenAPI document when available, redacts secret values from public configuration, and registers the external_api provider in the connector catalog."
description: "Human-readable test proof generated from test-results/test-proof/0.11.3/api/api-1.5-external-api-connector-2026-06-06.json."
---

# The external API connector accepts an explicit API operation inventory, augments discovery from an optional OpenAPI document when available, redacts secret values from public configuration, and registers the external_api provider in the connector catalog.

This page was generated from [test-results/test-proof/0.11.3/api/api-1.5-external-api-connector-2026-06-06.json](../../../../test-results/test-proof/0.11.3/api/api-1.5-external-api-connector-2026-06-06.json).

## Summary

The external API connector accepts an explicit API operation inventory, augments discovery from an optional OpenAPI document when available, redacts secret values from public configuration, and registers the external_api provider in the connector catalog.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.3 |
| Proof Id | api-1.5-external-api-connector-2026-06-06 |
| Proof Type | api |
| Feature | API-1.5 |
| Status | passed |
| Executed At Utc | 2026-06-06T00:00:00Z |
| Test File Count | 2 |
| Test Count | 8 |
| Command | cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi &amp;&amp; PYTHONPATH=/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-utils/src:/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-domain-validation/src /Users/jacbeekers/gitrepos/dq-rulebuilder/scripts/python_arm64.sh --python-bin /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest -o addopts='' tests/domain/test_connector_registry.py tests/application/services/test_external_api_connector.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.3/api/20260606T000000Z-api-1.5-external-api-connector |

## Test Files

- tests/domain/test_connector_registry.py
- tests/application/services/test_external_api_connector.py

## Assertions

- The connector registry exposes the external_api provider and loads the ExternalApiConnector implementation path.
- The connector returns a redacted public configuration without a credentials field.
- Discovery merges configured operations with optional OpenAPI operations without duplicating entries.
- Sync invokes the sink with the public configuration and discovery result.
- The connector configuration rejects missing operation inventory at construction time.

## Proof Data

```json
{
  "provider": "external_api",
  "configured_operation_count": 1,
  "discovered_operation_count": 2,
  "warnings": 2
}
```
