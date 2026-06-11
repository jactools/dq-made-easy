# API-6.9 Dual-Run Behavior Report

Generated: 2026-03-15T21:32:33+00:00
Legacy base URL: http://127.0.0.1:4001
FastAPI base URL: http://127.0.0.1:4010

## Summary

- Total scenarios: 2
- Passed: 2
- Failed: 0
- Skipped: 0

## Scenario Results

### PASS GET /api/v1/readiness (Readiness auth gate parity)
- Legacy: status=401 durationMs=3.122
- FastAPI: status=401 durationMs=0.672

### PASS GET /api/v1/workspaces (Workspaces auth gate parity)
- Legacy: status=401 durationMs=2.495
- FastAPI: status=401 durationMs=0.537
