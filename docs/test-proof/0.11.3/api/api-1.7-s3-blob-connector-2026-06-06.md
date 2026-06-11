---
title: "The S3/Blob connector now ingests metadata from configured s3:// or s3a:// delivery locations, redacts secret values from the public configuration, and registers the s3_blob provider in the connector catalog."
description: "Human-readable test proof generated from test-results/test-proof/0.11.3/api/api-1.7-s3-blob-connector-2026-06-06.json."
---

# The S3/Blob connector now ingests metadata from configured s3:// or s3a:// delivery locations, redacts secret values from the public configuration, and registers the s3_blob provider in the connector catalog.

This page was generated from [test-results/test-proof/0.11.3/api/api-1.7-s3-blob-connector-2026-06-06.json](../../../../test-results/test-proof/0.11.3/api/api-1.7-s3-blob-connector-2026-06-06.json).

## Summary

The S3/Blob connector now ingests metadata from configured s3:// or s3a:// delivery locations, redacts secret values from the public configuration, and registers the s3_blob provider in the connector catalog.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.3 |
| Proof Id | api-1.7-s3-blob-connector-2026-06-06 |
| Proof Type | api |
| Feature | API-1.7 |
| Status | passed |
| Executed At Utc | 2026-06-06T00:02:00Z |
| Test File Count | 2 |
| Test Count | 8 |
| Command | cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-api/fastapi &amp;&amp; PYTHONPATH=/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-utils/src:/Users/jacbeekers/gitrepos/dq-rulebuilder/dq-domain-validation/src /Users/jacbeekers/gitrepos/dq-rulebuilder/scripts/python_arm64.sh --python-bin /Users/jacbeekers/gitrepos/dq-rulebuilder/venv/bin/python -m pytest -o addopts='' tests/domain/test_connector_registry.py tests/application/services/test_s3_blob_connector.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.3/api/20260606T000200Z-api-1.7-s3-blob-connector |

## Test Files

- tests/domain/test_connector_registry.py
- tests/application/services/test_s3_blob_connector.py

## Assertions

- The connector registry exposes the s3_blob provider and loads the S3BlobConnector implementation path.
- The connector returns a redacted public configuration without a credentials field.
- Discovery returns bucket, folder, and object items for the configured S3/Blob root.
- Sync invokes the sink with the public configuration and discovery result.
- The configuration model rejects empty delivery_locations values.

## Proof Data

```json
{
  "provider": "s3_blob",
  "bucket_count": 1,
  "folder_count": 2,
  "object_count": 2,
  "warnings": 2
}
```
