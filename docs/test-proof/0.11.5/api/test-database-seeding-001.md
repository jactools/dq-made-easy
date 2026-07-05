---
title: "Mock data seeding into PostgreSQL validation tables"
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/api/test-database-seeding-001.json."
---

# Mock data seeding into PostgreSQL validation tables

This page was generated from [test-results/test-proof/0.11.5/api/test-database-seeding-001.json](../../../../test-results/test-proof/0.11.5/api/test-database-seeding-001.json).

## Summary

Mock data seeding into PostgreSQL validation tables

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | test-database-seeding-001 |
| Proof Type | api |
| Feature | Database seeding |
| Status | passed |
| Executed At Utc | 2026-07-04T00:00:00Z |
| Test File Count | 3 |
| Test Count | 8 |
| Command | docker exec dq-made-easy-db psql -U postgres -d dq -c "SELECT COUNT(*) FROM validation_run_plans; SELECT COUNT(*) FROM validation_run_plan_versions; SELECT COUNT(*) FROM validation_run_items;" |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/test-database-seeding-001 |

## Test Files

- /Users/jacbeekers/gitrepos/dq-made-easy/dq-db/mock-data/validation-run-plans.csv
- /Users/jacbeekers/gitrepos/dq-made-easy/dq-db/mock-data/validation-run-plan-versions.csv
- /Users/jacbeekers/gitrepos/dq-made-easy/dq-db/mock-data/validation-run-items.csv

## Assertions

- validation_run_plans count: 9
- Active plans: 7
- Draft plans: 2
- validation_run_plan_versions count: 10
- Active versions: 6
- Draft versions: 4
- validation_run_items count: 3
- Foreign key integrity verified

## Proof Data

```json
{
  "database_summary": {
    "validation_run_items": {
      "failed": 1,
      "passed": 2,
      "total": 3,
      "warnings": 1
    },
    "validation_run_plan_versions": {
      "active": 6,
      "draft": 4,
      "total": 10
    },
    "validation_run_plans": {
      "active": 7,
      "draft": 2,
      "total": 9
    }
  },
  "foreign_key_integrity": true
}
```

## Diagnostics

```json
{
  "database": "postgres://localhost:5432/dq",
  "execution_time_ms": 1200
}
```
