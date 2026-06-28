---
title: "The Spark Expectations execution path is now routed through the GX dispatch worker and verified by a dedicated regression test that exercises the worker entrypoint and persists execution/error artifacts."
description: "Human-readable test proof generated from test-results/test-proof/0.11.4/api/spark-expectations-dispatch.json."
---

# The Spark Expectations execution path is now routed through the GX dispatch worker and verified by a dedicated regression test that exercises the worker entrypoint and persists execution/error artifacts.

This page was generated from [test-results/test-proof/0.11.4/api/spark-expectations-dispatch.json](../../../../test-results/test-proof/0.11.4/api/spark-expectations-dispatch.json).

## Summary

The Spark Expectations execution path is now routed through the GX dispatch worker and verified by a dedicated regression test that exercises the worker entrypoint and persists execution/error artifacts.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.4 |
| Proof Id | spark-expectations-dispatch |
| Proof Type | api |
| Feature | spark-expectations-dispatch |
| Status | passed |
| Executed At Utc | 2026-06-26T22:13:42Z |
| Test File Count | 1 |
| Test Count | 10 |
| Command | ./scripts/run_test_evidence.sh api --label spark-expectations-dispatch -- dq-engine/tests/test_spark_expectations_adapter.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.4/api/20260626T221541Z-spark-expectations-dispatch |

## Test Files

- dq-engine/tests/test_spark_expectations_adapter.py

## Assertions

- Spark Expectations dispatch messages are recognized before the GX-only payload validation path
- The worker invokes the execution endpoint and writes execution/error artifacts
- Targeted Spark Expectations adapter and dispatch regression tests pass

## Proof Data

```json
{
  "verification_command": "/Users/jacbeekers/gitrepos/dq-made-easy/scripts/python_arm64.sh --python-bin /Users/jacbeekers/gitrepos/dq-made-easy/venv/bin/python -m pytest dq-engine/tests/test_spark_expectations_adapter.py -q",
  "verification_result": "10 passed, 1 warning in 0.41s"
}
```
