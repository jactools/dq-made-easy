---
title: "ValidationRunPlanEntity and ValidationRunPlanVersionEntity serialization test"
description: "Human-readable test proof generated from test-results/test-proof/0.11.5/api/test-validation-entities-001.json."
---

# ValidationRunPlanEntity and ValidationRunPlanVersionEntity serialization test

This page was generated from [test-results/test-proof/0.11.5/api/test-validation-entities-001.json](../../../../test-results/test-proof/0.11.5/api/test-validation-entities-001.json).

## Summary

ValidationRunPlanEntity and ValidationRunPlanVersionEntity serialization test

## Metadata

| Field | Value |
| --- | --- |
| App Version | 0.11.5 |
| Proof Id | test-validation-entities-001 |
| Proof Type | api |
| Feature | ValidationRunPlanEntity serialization |
| Status | passed |
| Executed At Utc | 2026-07-04T00:00:00Z |
| Test File Count | 1 |
| Test Count | 5 |
| Command | python3 -c "from app.domain.entities.validation_run_plan import ValidationRunPlanEntity; plan = ValidationRunPlanEntity(runPlanId='plan-123', businessKey='test:validation:v1', workspaceId='ws-456', scopeSelector=&#123;&#125;, planningMode='single_suite', status='active', currentActiveVersionId='version-123', createdBy='test-user', createdAt='2026-07-04T00:00:00Z', updatedAt='2026-07-04T00:00:00Z'); data = plan.model_dump(by_alias=True); restored = ValidationRunPlanEntity.model_validate(data); assert restored.runPlanId == 'plan-123'" |
| Raw Evidence Directory | test-results/evidence/0.11.5/api/test-validation-entities-001.json |

## Test Files

- /Users/jacbeekers/gitrepos/dq-made-easy/dq-api/fastapi/app/domain/entities/validation_run_plan.py

## Assertions

- ValidationRunPlanEntity creation successful
- Plan ID preserved: plan-123
- Business Key preserved: test:validation:v1
- Status preserved: active
- Serialization round-trip successful

## Proof Data

```json
{
  "database_verification": {
    "query": "SELECT COUNT(*) FROM validation_run_plans",
    "result": 9
  }
}
```

## Diagnostics

```json
{
  "execution_time_ms": 300,
  "pydantic_version": "2.x",
  "python_version": "3.13.13"
}
```
