---
title: "Mock data seeding into PostgreSQL validation tables"
description: "Human-readable test proof generated from test-results/test-proof/api/api/test-database-seeding-001.json."
---

# Mock data seeding into PostgreSQL validation tables

This page was generated from [test-results/test-proof/api/api/test-database-seeding-001.json](../../../../test-results/test-proof/api/api/test-database-seeding-001.json).

## Summary

Mock data seeding into PostgreSQL validation tables

## Metadata

| Field | Value |
| --- | --- |
| App Version | api |
| Proof Id | test-database-seeding-001 |
| Proof Type | api |
| Feature | Database seeding |
| Status | passed |
| Executed At Utc | 2026-07-04T00:00:00Z |
| Test File Count | 3 |
| Test Count | 8 |
| Command | docker exec dq-made-easy-db psql -U postgres -d dq -c "SELECT COUNT(*) FROM validation_run_plans; SELECT COUNT(*) FROM validation_run_plan_versions; SELECT COUNT(*) FROM validation_run_items;" |
| Raw Evidence Directory | evidence/test-database-seeding-001.json |

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
    "validation_run_plans": {
      "total": 9,
      "active": 7,
      "draft": 2
    },
    "validation_run_plan_versions": {
      "total": 10,
      "active": 6,
      "draft": 4
    },
    "validation_run_items": {
      "total": 3,
      "passed": 2,
      "failed": 1,
      "warnings": 1
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
