---
title: "All Trino-related unit, dispatch, and live-container tests passed with focused Trino module coverage above the 90% acceptance threshold."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/api/dq-engine-trino-coverage-gate-2026-06-30.json."
---

# All Trino-related unit, dispatch, and live-container tests passed with focused Trino module coverage above the 90% acceptance threshold.

This page was generated from [test-results/test-proof/0.11.5/api/dq-engine-trino-coverage-gate-2026-06-30.json](../../../../test-results/test-proof/0.11.5/api/dq-engine-trino-coverage-gate-2026-06-30.json).

## Summary

All Trino-related unit, dispatch, and live-container tests passed with focused Trino module coverage above the 90% acceptance threshold.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | dq-engine-trino-coverage-gate-2026-06-30 |
| Proof Type | api |
| Feature | trino-phase-1-coverage-gate |
| Status | passed |
| Executed At Utc | 2026-06-30T15:00:00Z |
| Test File Count | 5 |
| Test Count | 78 |
| Command | cd /Users/Jac.Beekers/gitrepos/dq-made-easy/dq-engine &amp;&amp; DQ_TRINO_HOST=127.0.0.1 DQ_TRINO_PORT=8084 DQ_TRINO_CATALOG=memory DQ_TRINO_SCHEMA=default /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_trino_executor.py tests/test_trino_execution_pipeline.py tests/test_runtime_lowerer_registry.py tests/test_trino_live_container.py --cov=trino_adapter --cov=trino_config --cov=trino_executor --cov=trino_execution_pipeline --cov-report=term-missing --cov-fail-under=90 -q -rs |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/20260630T150000Z-dq-engine-trino-coverage-gate |

## Test Files

- dq-engine/tests/test_trino_adapter.py
- dq-engine/tests/test_trino_executor.py
- dq-engine/tests/test_trino_execution_pipeline.py
- dq-engine/tests/test_runtime_lowerer_registry.py
- dq-engine/tests/test_trino_live_container.py

## Assertions

- Trino adapter lowering and validation branches are covered for supported and rejected rules
- Trino executor streaming, connection, validation, metrics, and structured error mapping branches are covered
- Trino execution pipeline success, persistence, structured validation error, and generic dispatch reporting flows are covered
- Live Trino smoke and pipeline tests pass against the repo-managed Trino container started through stack_ctl
- Focused coverage for trino_adapter, trino_config, trino_executor, and trino_execution_pipeline is at least 90%

## Proof Data

```json
{
  "verification_command": "cd dq-engine && DQ_TRINO_HOST=127.0.0.1 DQ_TRINO_PORT=8084 DQ_TRINO_CATALOG=memory DQ_TRINO_SCHEMA=default /Users/Jac.Beekers/gitrepos/dq-made-easy/venv/bin/python -m pytest tests/test_trino_adapter.py tests/test_trino_executor.py tests/test_trino_execution_pipeline.py tests/test_runtime_lowerer_registry.py tests/test_trino_live_container.py --cov=trino_adapter --cov=trino_config --cov=trino_executor --cov=trino_execution_pipeline --cov-report=term-missing --cov-fail-under=90 -q -rs",
  "verification_result": "78 passed in 1.00s",
  "coverage_result": "Required test coverage of 90% reached. Total coverage: 96.12%",
  "module_coverage": {
    "trino_adapter.py": "99%",
    "trino_config.py": "93%",
    "trino_execution_pipeline.py": "95%",
    "trino_executor.py": "96%"
  }
}
```
