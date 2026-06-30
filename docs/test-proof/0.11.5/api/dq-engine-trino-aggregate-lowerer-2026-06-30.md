---
title: "Milestone 2 Trino aggregate lowering supports count, sum, avg, min, max, distinct_count, deterministic aggregate result aliases, and structured WHERE/HAVING filters."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/api/dq-engine-trino-aggregate-lowerer-2026-06-30.json."
---

# Milestone 2 Trino aggregate lowering supports count, sum, avg, min, max, distinct_count, deterministic aggregate result aliases, and structured WHERE/HAVING filters.

This page was generated from [test-results/test-proof/0.11.5/api/dq-engine-trino-aggregate-lowerer-2026-06-30.json](../../../../test-results/test-proof/0.11.5/api/dq-engine-trino-aggregate-lowerer-2026-06-30.json).

## Summary

Milestone 2 Trino aggregate lowering supports count, sum, avg, min, max, distinct_count, deterministic aggregate result aliases, and structured WHERE/HAVING filters.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | dq-engine-trino-aggregate-lowerer-2026-06-30 |
| Proof Type | api |
| Feature | trino-aggregate-lowerer-milestone-2 |
| Status | passed |
| Executed At Utc | 2026-06-30T16:15:00Z |
| Test File Count | 2 |
| Test Count | 62 |
| Command | cd /Users/Jac.Beekers/gitrepos/dq-made-easy/dq-engine &amp;&amp; /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_runtime_lowerer_registry.py -q |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/20260630T161500Z-dq-engine-trino-aggregate-lowerer |

## Test Files

- dq-engine/tests/test_trino_adapter.py
- dq-engine/tests/test_runtime_lowerer_registry.py

## Assertions

- Aggregate Trino rules cover count, sum, avg, min, max, and distinct_count
- Aggregate queries emit stable result aliases such as dq_count, dq_sum, dq_avg, dq_min, and dq_max
- Structured WHERE filters are emitted before aggregation and reject raw SQL predicates
- Structured HAVING filters are emitted after aggregation against the aggregate expression
- The generic compile_rule_payload path returns the same aggregate filter SQL through the Trino runtime lowerer

## Proof Data

```json
{
  "verification_command": "cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_runtime_lowerer_registry.py -q",
  "verification_result": "62 passed in 0.23s",
  "coverage_gate": "cd dq-engine && /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_trino_executor.py tests/test_trino_execution_pipeline.py tests/test_runtime_lowerer_registry.py --cov=trino_adapter --cov=trino_config --cov=trino_executor --cov=trino_execution_pipeline --cov-report=term-missing --cov-fail-under=90 -q",
  "coverage_result": "83 passed in 1.38s; Required test coverage of 90% reached. Total coverage: 95.02%"
}
```
