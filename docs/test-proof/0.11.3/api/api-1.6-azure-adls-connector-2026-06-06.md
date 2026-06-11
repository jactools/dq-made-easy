---
title: "The Azure ADLS connector now discovers filesystems, directories, and files from configured roots, redacts secret values from the public configuration, and registers the azure_adls provider in the connector catalog."
description: "Human-readable test proof generated from test-results/test-proof/0.11.3/api/api-1.6-azure-adls-connector-2026-06-06.json."
---

# The Azure ADLS connector now discovers filesystems, directories, and files from configured roots, redacts secret values from the public configuration, and registers the azure_adls provider in the connector catalog.

This page was generated from [test-results/test-proof/0.11.3/api/api-1.6-azure-adls-connector-2026-06-06.json](../../../../test-results/test-proof/0.11.3/api/api-1.6-azure-adls-connector-2026-06-06.json).

## Summary

The Azure ADLS connector now discovers filesystems, directories, and files from configured roots, redacts secret values from the public configuration, and registers the azure_adls provider in the connector catalog.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.3 |
| Proof Id | api-1.6-azure-adls-connector-2026-06-06 |
| Proof Type | api |
| Feature | API-1.6 |
| Status | passed |
| Executed At Utc | 2026-06-06T00:01:00Z |
| Test File Count | 2 |
| Test Count | 8 |
| Command | cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi &amp;&amp; PYTHONPATH=/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-utils/src:/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-domain-validation/src /Users/jacbeekers/gitrepos/dq-rulebuilder/scripts/python_arm64.sh --python-bin /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest -o addopts='' tests/domain/test_connector_registry.py tests/application/services/test_azure_adls_connector.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.3/api/20260606T000100Z-api-1.6-azure-adls-connector |

## Test Files

- tests/domain/test_connector_registry.py
- tests/application/services/test_azure_adls_connector.py

## Assertions

- The connector registry exposes the azure_adls provider and loads the AzureAdlsConnector implementation path.
- The connector returns a redacted public configuration without a credentials field.
- Discovery returns filesystem, directory, and file items for the configured ADLS roots.
- Sync invokes the sink with the public configuration and discovery result.
- The configuration model rejects missing account_url values.

## Proof Data

```json
{
  "provider": "azure_adls",
  "filesystem_count": 1,
  "directory_count": 1,
  "file_count": 1,
  "warnings": 2
}
```
