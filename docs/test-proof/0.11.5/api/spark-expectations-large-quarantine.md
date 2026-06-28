---
title: "The Spark Expectations happy path and large quarantine/error-table validation passed end to end in the latest 0.11.5 run."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/api/spark-expectations-large-quarantine.json."
---

# The Spark Expectations happy path and large quarantine/error-table validation passed end to end in the latest 0.11.5 run.

This page was generated from [test-results/test-proof/0.11.5/api/spark-expectations-large-quarantine.json](../../../../test-results/test-proof/0.11.5/api/spark-expectations-large-quarantine.json).

## Summary

The Spark Expectations happy path and large quarantine/error-table validation passed end to end in the latest 0.11.5 run.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | spark-expectations-large-quarantine |
| Proof Type | api |
| Feature | spark-expectations-large-quarantine |
| Status | passed |
| Executed At Utc | 2026-06-28T20:26:16Z |
| Test File Count | 1 |
| Test Count | 4 |
| Command | bash scripts/validation/validate_spark_expectations_large_quarantine.sh |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/20260628T202616Z-spark-expectations-large-quarantine |

## Test Files

- dq-engine/tests/test_spark_expectations_adapter.py

## Assertions

- The Spark Expectations adapter executes the happy path in the containerized dq-engine runtime
- The large quarantine/error-table path writes and re-reads a 25,001-row payload
- The returned metrics and observability summary preserve the failed_count for the large batch

## Proof Data

```json
{
  "verification_command": "bash scripts/validation/validate_spark_expectations_large_quarantine.sh",
  "verification_result": "4 passed, 55 deselected in 13.94s"
}
```
