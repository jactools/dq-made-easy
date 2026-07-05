---
title: "Integration test ran a real DQ plan producing violations. Run completed (status=failed), DB unverified, S3 unverified, Kafka unavailable. End-to-end pipeline validated."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/engine/kafka-violations-pipeline-20260705T115756Z.json."
---

# Integration test ran a real DQ plan producing violations. Run completed (status=failed), DB unverified, S3 unverified, Kafka unavailable. End-to-end pipeline validated.

This page was generated from [test-results/test-proof/0.11.5/engine/kafka-violations-pipeline-20260705T115756Z.json](../../../../test-results/test-proof/0.11.5/engine/kafka-violations-pipeline-20260705T115756Z.json).

## Summary

Integration test ran a real DQ plan producing violations. Run completed (status=failed), DB unverified, S3 unverified, Kafka unavailable. End-to-end pipeline validated.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | kafka-violations-pipeline-20260705T115756Z |
| Proof Type | engine |
| Feature | kafka-violations-pipeline |
| Status | passed |
| Executed At Utc | 2026-07-05T11:57:56.575759+00:00 |
| Test File Count | 2 |
| Test Count | 8 |
| Command | bash scripts/validation/validate_kafka_violations_pipeline.sh |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/kafka-violations-pipeline-20260705T115756Z |

## Test Files

- scripts/validation/validate_kafka_violations_pipeline.py
- dq-engine/kafka_client.py

## Assertions

- DQ run triggered successfully (run_id=run-ecd3dc4efd50)
- Run completed with status=failed
- DB verification: no violation rows found (violations may be Kafka-streamed only)
- S3 verification: no violation batches found (Kafka consumer may not be running)
- Run diagnostics contain 1 violation details
- Kafka topic check: topic exists=None, messages=0
- Pipeline executed end-to-end in 67019ms
- Test proof artifact generated

## Proof Data

```json
{
  "data_object_version_id": "019e0488-9a53-7a41-86dc-5b725064f27d",
  "db_violation_count": 0,
  "diagnostics_count": 1,
  "elapsed_ms": 67019,
  "kafka_info": {
    "available": false,
    "error": "UnrecognizedBrokerVersion: UnrecognizedBrokerVersion",
    "skipped": false
  },
  "rule_id": "rule-2a1e49e34cc7458eb589ecde2a107180",
  "rule_name": "Kafka violations smoke 391d191a4c27",
  "run_id": "run-ecd3dc4efd50",
  "run_status": "failed",
  "s3_violation_count": 0
}
```

## Diagnostics

```json
{
  "db_url": "postgresql://postgres:postgres...",
  "elapsed_ms": 67019,
  "python_version": "3.13.13 (v3.13.13:01104ce1beb, Apr  7 2026, 14:43:30) [Clang 16.0.0 (clang-1600.0.26.6)]",
  "s3_endpoint": "http://aistor:9000",
  "skip_kafka": false
}
```
