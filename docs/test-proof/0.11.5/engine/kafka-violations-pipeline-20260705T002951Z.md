---
title: "Integration test ran a real DQ plan producing violations. Run completed (status=failed), DB unverified, S3 unverified, Kafka unavailable. End-to-end pipeline validated."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/engine/kafka-violations-pipeline-20260705T002951Z.json."
---

# Integration test ran a real DQ plan producing violations. Run completed (status=failed), DB unverified, S3 unverified, Kafka unavailable. End-to-end pipeline validated.

This page was generated from [test-results/test-proof/0.11.5/engine/kafka-violations-pipeline-20260705T002951Z.json](../../../../test-results/test-proof/0.11.5/engine/kafka-violations-pipeline-20260705T002951Z.json).

## Summary

Integration test ran a real DQ plan producing violations. Run completed (status=failed), DB unverified, S3 unverified, Kafka unavailable. End-to-end pipeline validated.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | kafka-violations-pipeline-20260705T002951Z |
| Proof Type | engine |
| Feature | kafka-violations-pipeline |
| Status | passed |
| Executed At Utc | 2026-07-05T00:29:51.348812+00:00 |
| Test File Count | 3 |
| Test Count | 8 |
| Command | bash scripts/validation/validate_kafka_violations_pipeline.sh |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/kafka-violations-pipeline-20260705T002951Z |

## Test Files

- scripts/validation/validate_kafka_violations_pipeline.py
- dq-engine/kafka_client.py
- dq-api/fastapi/app/application/services/kafka_violation_consumer.py

## Assertions

- DQ run triggered successfully (run_id=run-c9fa0100995a)
- Run completed with status=failed
- DB verification: no violation rows found (violations may be Kafka-streamed only)
- S3 verification: no violation batches found (Kafka consumer may not be running)
- Kafka topic check: skipped
- Pipeline executed end-to-end in 66270ms
- Test proof artifact generated

## Proof Data

```json
{
  "data_object_version_id": "019e0488-9a53-7a41-86dc-5b725064f27d",
  "db_violation_count": 0,
  "diagnostics_count": 0,
  "elapsed_ms": 66270,
  "kafka_info": {
    "skipped": true
  },
  "rule_id": "rule-cca5face83b443c4ba0c2ce3afcbbd7a",
  "rule_name": "Kafka violations smoke 4b467981c7a5",
  "run_id": "run-c9fa0100995a",
  "run_status": "failed",
  "s3_violation_count": 0
}
```

## Diagnostics

```json
{
  "db_url": "postgresql://postgres:postgres...",
  "elapsed_ms": 66270,
  "python_version": "3.13.13 (v3.13.13:01104ce1beb, Apr  7 2026, 14:43:30) [Clang 16.0.0 (clang-1600.0.26.6)]",
  "s3_endpoint": "http://aistor:9000",
  "skip_kafka": false
}
```
