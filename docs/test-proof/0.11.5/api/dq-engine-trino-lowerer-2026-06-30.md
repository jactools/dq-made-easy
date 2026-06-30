---
title: "Milestone 1 Trino lowering now generates valid Trino SQL for row, aggregate, and query rules, and rejects unsupported constructs before parameter validation."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json."
---

# Milestone 1 Trino lowering now generates valid Trino SQL for row, aggregate, and query rules, and rejects unsupported constructs before parameter validation.

This page was generated from [test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json](../../../../test-results/test-proof/0.11.5/api/dq-engine-trino-lowerer-2026-06-30.json).

## Summary

Milestone 1 Trino lowering now generates valid Trino SQL for row, aggregate, and query rules, and rejects unsupported constructs before parameter validation.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | dq-engine-trino-lowerer-2026-06-30 |
| Proof Type | api |
| Feature | trino-lowerer-milestone-1 |
| Status | passed |
| Executed At Utc | 2026-06-30T13:58:05Z |
| Test File Count | 2 |
| Test Count | 33 |
| Command | cd /Users/Jac.Beekers/gitrepos/dq-made-easy/dq-engine &amp;&amp; /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_runtime_lowerer_registry.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/20260630T135805Z-dq-engine-trino-lowerer |

## Test Files

- dq-engine/tests/test_trino_adapter.py
- dq-engine/tests/test_runtime_lowerer_registry.py

## Assertions

- Row-level Trino rules cover not_null, is_null, equals, not_equal, between, in, not_in, min, and max
- Aggregate Trino rules cover count, sum, avg, min, max, and distinct_count
- Unsupported Trino constructs are rejected before parameter validation and are reported as compile failures
- The runtime registry resolves the trino engine type through compile_rule_payload

## Proof Data

```json
{
  "verification_command": "cd /Users/Jac.Beekers/gitrepos/dq-made-easy/dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_runtime_lowerer_registry.py -q",
  "verification_result": "33 passed in 0.27s"
}
```
