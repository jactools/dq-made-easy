---
title: "The standard API evidence run was executed for dq-engine/tests/test_spark_expectations_adapter.py, but the local environment failed during pytest collection because pydantic_core is built for incompatible architecture (arm64 vs x86_64). The underlying adapter functionality was still verified separately with a direct pytest run that passed 8 tests."
description: "Human-readable test proof generated from test-results/test-proof/0.11.4/api/spark-expectations-large-errors.json."
---

# The standard API evidence run was executed for dq-engine/tests/test_spark_expectations_adapter.py, but the local environment failed during pytest collection because pydantic_core is built for incompatible architecture (arm64 vs x86_64). The underlying adapter functionality was still verified separately with a direct pytest run that passed 8 tests.

This page was generated from [test-results/test-proof/0.11.4/api/spark-expectations-large-errors.json](../../../../test-results/test-proof/0.11.4/api/spark-expectations-large-errors.json).

## Summary

The standard API evidence run was executed for dq-engine/tests/test_spark_expectations_adapter.py, but the local environment failed during pytest collection because pydantic_core is built for incompatible architecture (arm64 vs x86_64). The underlying adapter functionality was still verified separately with a direct pytest run that passed 8 tests.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.4 |
| Proof Id | spark-expectations-large-errors |
| Proof Type | api |
| Feature | spark-expectations-large-errors |
| Status | failed |
| Executed At Utc | 2026-06-27T00:00:00Z |
| Test File Count | 1 |
| Test Count | 8 |
| Command | ./scripts/run_test_evidence.sh api --label spark-expectations-large-errors -- dq-engine/tests/test_spark_expectations_adapter.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.4/api/20260626T215936Z-spark-expectations-large-errors |

## Test Files

- dq-engine/tests/test_spark_expectations_adapter.py

## Assertions

- Spark Expectations adapter lowerer supports not_null/min/max rules
- Chunked error management handles large batches
- Compile path exposes neutral artifact envelope

## Proof Data

```json
{
  "direct_verification_command": "/Users/jacbeekers/gitrepos/dq-made-easy/venv/bin/python -m pytest dq-engine/tests/test_spark_expectations_adapter.py -q",
  "direct_verification_result": "8 passed, 14 warnings in 0.19s"
}
```

## Diagnostics

```json
{
  "error": "ImportError: pydantic_core incompatible architecture (arm64 vs x86_64) during pytest collection"
}
```
