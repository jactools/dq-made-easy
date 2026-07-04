---
title: "DQPlanTemplateEntity and related entities serialization/deserialization test"
description: "Human-readable test proof generated from test-results/test-proof/api/api/test-template-entities-001.json."
---

# DQPlanTemplateEntity and related entities serialization/deserialization test

This page was generated from [test-results/test-proof/api/api/test-template-entities-001.json](../../../../test-results/test-proof/api/api/test-template-entities-001.json).

## Summary

DQPlanTemplateEntity and related entities serialization/deserialization test

## Metadata

| Field | Value |
| --- | --- |
| App Version | api |
| Proof Id | test-template-entities-001 |
| Proof Type | api |
| Feature | DQPlanTemplateEntity serialization |
| Status | passed |
| Executed At Utc | 2026-07-04T00:00:00Z |
| Test File Count | 1 |
| Test Count | 6 |
| Command | python3 -c "from app.domain.entities.dq_plan_template import DQPlanTemplateEntity; template = DQPlanTemplateEntity(template_id='test-123', template_name='Test Template', template_type='data_quality', domain='test', tags=['test', 'validation'], parameters=[&#123;'name': 'dataset_name', 'type': 'string', 'required': True&#125;], suites=[&#123;'suite_name': 'test_suite', 'engine_type': 'gx'&#125;], is_active=True, is_default=True); data = template.model_dump(by_alias=True); restored = DQPlanTemplateEntity.model_validate(data); assert restored.template_id == 'test-123'" |
| Raw Evidence Directory | evidence/test-template-entities-001.json |

## Test Files

- /Users/jacbeekers/gitrepos/dq-made-easy/dq-api/fastapi/app/domain/entities/dq_plan_template.py

## Assertions

- DQPlanTemplateEntity creation successful
- Template ID preserved: test-123
- Template Name preserved: Test Template
- Parameter count: 1
- Suite count: 1
- Serialization round-trip successful

## Proof Data

```json
{
  "input_template": {
    "template_id": "test-123",
    "template_name": "Test Template"
  },
  "results": {
    "template_id": "test-123",
    "template_name": "Test Template",
    "parameters_count": 1,
    "suites_count": 1
  }
}
```

## Diagnostics

```json
{
  "python_version": "3.13.13",
  "pydantic_version": "2.x",
  "execution_time_ms": 500
}
```
