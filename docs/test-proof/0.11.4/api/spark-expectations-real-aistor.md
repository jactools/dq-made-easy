---
title: "The Spark Expectations real-data validation against AIStor-backed parquet passed end to end in the latest 0.11.4 run."
description: "Human-readable test proof generated from test-results/test-proof/0.11.4/api/spark-expectations-real-aistor.json."
---

# The Spark Expectations real-data validation against AIStor-backed parquet passed end to end in the latest 0.11.4 run.

This page was generated from [test-results/test-proof/0.11.4/api/spark-expectations-real-aistor.json](../../../../test-results/test-proof/0.11.4/api/spark-expectations-real-aistor.json).

## Summary

The Spark Expectations real-data validation against AIStor-backed parquet passed end to end in the latest 0.11.4 run.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.4 |
| Proof Id | spark-expectations-real-aistor |
| Proof Type | api |
| Feature | spark-expectations-real-aistor |
| Status | passed |
| Executed At Utc | 2026-06-27T20:39:41Z |
| Test File Count | 1 |
| Test Count | 25 |
| Command | bash scripts/validation/validate_spark_expectations_real_aistor.sh |
| Raw Evidence Directory | test-results/evidence/0.11.4/api/20260627T203941Z-spark-expectations-real-aistor |

## Test Files

- dq-engine/tests/test_spark_expectations_real_aistor_validation.py

## Assertions

- The Spark Expectations adapter lowers supported constructs correctly
- The real AIStor parquet validation run succeeds end to end
- The latest 0.11.4 validation completes with passing assertions

## Proof Data

```json
{
  "verification_command": "bash scripts/validation/validate_spark_expectations_real_aistor.sh",
  "verification_result": "25 passed in 9.20s"
}
```
