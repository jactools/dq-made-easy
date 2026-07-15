---
title: "The Trino AIStor catalog seed script validates the dq-db/mock-data CSV inputs, plans the Currency v1 parquet delivery needed by the Trino real AIStor validation in dry-run mode, and fails live seeding when AIStor is not already running."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/api/dq-engine-trino-aistor-catalog-seed-2026-06-30.json."
---

# The Trino AIStor catalog seed script validates the dq-db/mock-data CSV inputs, plans the Currency v1 parquet delivery needed by the Trino real AIStor validation in dry-run mode, and fails live seeding when AIStor is not already running.

This page was generated from [test-results/test-proof/0.11.5/api/dq-engine-trino-aistor-catalog-seed-2026-06-30.json](../../../../test-results/test-proof/0.11.5/api/dq-engine-trino-aistor-catalog-seed-2026-06-30.json).

## Summary

The Trino AIStor catalog seed script validates the dq-db/mock-data CSV inputs, plans the Currency v1 parquet delivery needed by the Trino real AIStor validation in dry-run mode, and fails live seeding when AIStor is not already running.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | dq-engine-trino-aistor-catalog-seed-2026-06-30 |
| Proof Type | api |
| Feature | trino-aistor-catalog-seed-script |
| Status | passed |
| Executed At Utc | 2026-06-30T17:02:51Z |
| Test File Count | 8 |
| Test Count | 1 |
| Command | cd /Users/Jac.Beekers/gitrepos/dq-made-easy &amp;&amp; bash -n scripts/seed_trino_aistor_catalogs.sh &amp;&amp; bash -n scripts/start-containers.sh &amp;&amp; scripts/seed_trino_aistor_catalogs.sh --dry-run &amp;&amp; &#123; scripts/seed_trino_aistor_catalogs.sh; exit_code=$?; echo exit_code=$exit_code; [[ $exit_code -eq 1 ]]; &#125; &amp;&amp; grep -n 'Running Trino AIStor catalog seed after --seed-all' scripts/start-containers.sh |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/20260630T165600Z-dq-engine-trino-aistor-catalog-seed |

## Test Files

- scripts/start-containers.sh
- scripts/seed_trino_aistor_catalogs.sh
- scripts/seed_delivery_objects.py
- dq-db/mock-data/data-deliveries.csv
- dq-db/mock-data/data-delivery-notes.csv
- dq-db/mock-data/data-objects.csv
- dq-db/mock-data/data-object-versions.csv
- dq-db/mock-data/attributes-catalog.csv

## Assertions

- The seed script shell syntax validates successfully
- The seed script dry-run reads dq-db/mock-data CSV inputs through the existing delivery seeding implementation
- The default Trino validation delivery id resolves to the Currency v1 AIStor parquet path
- The planned upload has 180 rows, 2 parquet files, and 5 columns as defined by the mock delivery/catalog CSV files
- Dry-run mode does not write to AIStor or require live containers
- Live mode does not start AIStor and fails with exit code 1 when the AIStor container is not already running
- start-containers.sh --seed-all invokes the Trino AIStor seed after post-stack delivery seeding when delivery seeding is enabled

## Proof Data

```json
{
  "delivery_id": "019e0488-9a53-72c3-9444-dbd3c1a2baf7",
  "physical_output_uri": "s3a://retail-banking/standardized/analytics/Currency/v1/LOAD_DTS=20260220T071500000Z",
  "record_count": 180,
  "file_count": 2,
  "column_count": 5,
  "delivery_format": "parquet",
  "requires_live_aistor_container": true,
  "container_lifecycle_managed_by_script": false,
  "start_containers_seed_all_invokes_seed_script": true,
  "start_containers_seed_all_order": "after seed_stack.sh post-stack delivery seeding",
  "start_containers_no_seed_deliveries_skips_seed_script": true,
  "live_without_aistor_result": "exit_code=1; AIStor container is not running",
  "live_seed_command": "cd /Users/Jac.Beekers/gitrepos/dq-made-easy && scripts/seed_trino_aistor_catalogs.sh"
}
```
