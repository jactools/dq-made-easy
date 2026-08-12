---
title: "The Delivery Registry app can be imported, mounted, and exercised through its health check and /v1 routes while using the shared metadata-utils and metadata-sdk packages. The delivery repository and domain entities import successfully, and the focused delivery unit validation passed."
description: "Human-readable test proof generated from test-results/test-proof/0.11.6/api/delivery-metadata-unit-20260721.json."
---

# The Delivery Registry app can be imported, mounted, and exercised through its health check and /v1 routes while using the shared metadata-utils and metadata-sdk packages. The delivery repository and domain entities import successfully, and the focused delivery unit validation passed.

This page was generated from [test-results/test-proof/0.11.6/api/delivery-metadata-unit-20260721.json](../../../../test-results/test-proof/0.11.6/api/delivery-metadata-unit-20260721.json).

## Summary

The Delivery Registry app can be imported, mounted, and exercised through its health check and /v1 routes while using the shared metadata-utils and metadata-sdk packages. The delivery repository and domain entities import successfully, and the focused delivery unit validation passed.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.6 |
| Proof Id | delivery-metadata-unit-20260721 |
| Proof Type | api |
| Feature | Delivery API smoke validation using metadata packages |
| Status | passed |
| Executed At Utc | 2026-08-04T11:06:16Z |
| Test File Count | 1 |
| Test Count | 4 |
| Command | scripts/run_test_evidence.sh command --label delivery-metadata-unit-20260721 -- bash -lc 'venv/bin/python -m pip install -e /Users/Jac.Beekers/gitrepos/metadata-as-a-service/packages/metadata-utils -e /Users/Jac.Beekers/gitrepos/metadata-as-a-service/packages/metadata-delivery-id -e /Users/Jac.Beekers/gitrepos/metadata-as-a-service/packages/metadata-models -e /Users/Jac.Beekers/gitrepos/metadata-as-a-service/packages/metadata-sdk --no-deps &gt;/dev/null &amp;&amp; venv/bin/python -m pytest dq-api/fastapi/delivery/tests/test_delivery_app.py -q -o addopts=' |
| Raw Evidence Directory | test-results/evidence/0.11.6/command/20260804T110616Z-delivery-metadata-unit-20260721 |

## Test Files

- dq-api/fastapi/delivery/tests/test_delivery_app.py

## Assertions

- Delivery app can be imported and created
- Delivery app exposes health check and /v1 routes
- Delivery repository can be imported and instantiated
- Delivery entities can be imported and created

## Proof Data

```json
{
  "files_modified": [
    "dq-api/fastapi/delivery/main.py",
    "dq-api/fastapi/delivery/repository.py",
    "dq-api/fastapi/delivery/domain/entities.py",
    "dq-api/fastapi/delivery/endpoints/deliveries.py",
    "dq-api/fastapi/delivery/tests/test_delivery_app.py",
    "dq-api/fastapi/requirements.txt",
    "dq-api/Dockerfile.fastapi"
  ],
  "packages_installed_editable": [
    "metadata-utils",
    "metadata-delivery-id",
    "metadata-models",
    "metadata-sdk"
  ]
}
```
