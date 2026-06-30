---
title: "The Trino Phase 1 validation wrapper runs the focused Trino coverage gate, supports dry-run mode without live Trino or AIStor parquet dependencies, and runs the repeatable Phase 1 benchmark with evidence captured under test-results."
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/api/dq-engine-trino-phase1-validation-2026-06-30.json."
---

# The Trino Phase 1 validation wrapper runs the focused Trino coverage gate, supports dry-run mode without live Trino or AIStor parquet dependencies, and runs the repeatable Phase 1 benchmark with evidence captured under test-results.

This page was generated from [test-results/test-proof/0.11.5/api/dq-engine-trino-phase1-validation-2026-06-30.json](../../../../test-results/test-proof/0.11.5/api/dq-engine-trino-phase1-validation-2026-06-30.json).

## Summary

The Trino Phase 1 validation wrapper runs the focused Trino coverage gate, supports dry-run mode without live Trino or AIStor parquet dependencies, and runs the repeatable Phase 1 benchmark with evidence captured under test-results.

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | dq-engine-trino-phase1-validation-2026-06-30 |
| Proof Type | api |
| Feature | trino-phase1-validation-script |
| Status | passed |
| Executed At Utc | 2026-06-30T16:40:12Z |
| Test File Count | 7 |
| Test Count | 88 |
| Command | cd /Users/Jac.Beekers/gitrepos/dq-made-easy &amp;&amp; scripts/validation/validate_trino_phase1.sh --dry-run |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/20260630T164012Z-dq-engine-trino-phase1-validation |

## Test Files

- scripts/validation/validate_trino_phase1.sh
- dq-engine/tests/test_trino_adapter.py
- dq-engine/tests/test_trino_executor.py
- dq-engine/tests/test_trino_execution_pipeline.py
- dq-engine/tests/test_runtime_lowerer_registry.py
- dq-engine/tests/test_trino_real_aistor_parquet_validation.py
- scripts/validation/benchmark_trino_phase1.py

## Assertions

- The Trino Phase 1 validation script accepts --dry-run and records dry_run: true in the evidence log
- Dry-run mode skips live Trino container and AIStor parquet validation while preserving the coverage gate and benchmark checks
- The focused Trino coverage gate passes with coverage above the 90% threshold
- The Phase 1 benchmark passes configured throughput and bounded large-result sampling checks
- Validation evidence is written under the canonical test-results/evidence application-version path

## Proof Data

```json
{
  "verification_result": "88 passed in 0.62s",
  "coverage_result": "Required test coverage of 90% reached. Total coverage: 95.05%",
  "module_coverage": {
    "trino_adapter.py": "96%",
    "trino_config.py": "93%",
    "trino_execution_pipeline.py": "95%",
    "trino_executor.py": "96%"
  },
  "dry_run": true,
  "skip_live": true,
  "skip_aistor_parquet_validation": true,
  "skip_benchmark": false,
  "benchmark_result": "passed",
  "benchmark_thresholds": {
    "min_lowering_rules_per_second": 1000,
    "min_pipeline_runs_per_second": 100,
    "max_bounded_sample_rows": 20
  },
  "benchmark_measurements": {
    "lowering_rules_per_second": 593797.7822123816,
    "pipeline_runs_per_second": 182933.812038987,
    "pipeline_p95_ms": 0.005500001861946657,
    "large_result_row_count": 2500000,
    "large_result_sample_count": 20,
    "large_result_truncated": true
  }
}
```
