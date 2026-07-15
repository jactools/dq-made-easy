---
title: "Trino scalar row checks support structured params.where filters before the scalar expectation while continuing to reject raw SQL predicates."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/api/dq-engine-trino-scalar-filters-2026-06-30.json."
---

# Trino scalar row checks support structured params.where filters before the scalar expectation while continuing to reject raw SQL predicates.

This page was generated from [test-results/test-proof/0.11.5/api/dq-engine-trino-scalar-filters-2026-06-30.json](../../../../test-results/test-proof/0.11.5/api/dq-engine-trino-scalar-filters-2026-06-30.json).

## Summary

Trino scalar row checks support structured params.where filters before the scalar expectation while continuing to reject raw SQL predicates.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | dq-engine-trino-scalar-filters-2026-06-30 |
| Proof Type | api |
| Feature | trino-scalar-where-filters |
| Status | passed |
| Executed At Utc | 2026-06-30T16:30:00Z |
| Test File Count | 2 |
| Test Count | 67 |
| Command | cd /Users/Jac.Beekers/gitrepos/dq-made-easy/dq-engine &amp;&amp; /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_runtime_lowerer_registry.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/20260630T163000Z-dq-engine-trino-scalar-filters |

## Test Files

- dq-engine/tests/test_trino_adapter.py
- dq-engine/tests/test_runtime_lowerer_registry.py

## Assertions

- Scalar row checks compose structured params.where filters before the scalar expectation
- Scalar WHERE filters support comparison and set operators through the shared Trino filter formatter
- Invalid scalar WHERE filter payloads fail fast instead of accepting raw SQL predicates
- The generic compile_rule_payload path returns scalar WHERE filter SQL through the Trino runtime lowerer

## Proof Data

```json
{
  "verification_command": "cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_runtime_lowerer_registry.py -q",
  "verification_result": "67 passed in 0.23s",
  "coverage_gate": "cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_trino_executor.py tests/test_trino_execution_pipeline.py tests/test_runtime_lowerer_registry.py --cov=trino_adapter --cov=trino_config --cov=trino_executor --cov=trino_execution_pipeline --cov-report=term-missing --cov-fail-under=90 -q",
  "coverage_result": "88 passed in 0.64s; Required test coverage of 90% reached. Total coverage: 95.05%"
}
```
