# WF-3: Rule Versioning & Rollback - API Endpoints Design

## Overview

This document specifies the REST API endpoints for the rule versioning and rollback feature (WF-3). All endpoints follow RESTful conventions and return JSON responses.

## Base URL

```
/rulebuilder/v1/rules/{ruleId}/versions
/rulebuilder/v1/rules/{ruleId}/rollbacks
```

## Authentication

All endpoints require:
- **Bearer Token** via `Authorization` header
- **Workspace Context** via `X-Workspace-Id` header or query parameter
- User must have appropriate role permissions for the action

## Common Response Headers

```
Content-Type: application/json
X-Request-Id: uuid
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1234567890
```

---

## 1. Get Version History

**Endpoint:** `GET /rulebuilder/v1/rules/&#123;ruleId&#125;/versions`

**Description:** Retrieve complete version history for a rule with pagination and filtering

**Authentication:** Required (roles: viewer, editor, reviewer, admin)

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Max results per page (1-100) |
| `offset` | integer | 0 | Pagination offset |
| `sort` | string | `created_at:desc` | Sort field and direction |
| `changeType` | string | - | Filter by change type (created, modified, approved, activated, deactivated, rollback) |
| `createdBy` | string | - | Filter by who created the version |
| `tags` | string | - | Filter by tags (comma-separated) |
| `startDate` | ISO8601 | - | Filter versions after this date |
| `endDate` | ISO8601 | - | Filter versions before this date |

### Response: 200 OK

```json
{
  "ruleId": "rule-123",
  "ruleName": "Customer Completeness Check",
  "versioning": {
    "enabled": true,
    "currentVersion": 5,
    "totalVersions": 5,
    "firstVersionDate": "2026-01-15T10:00:00Z",
    "lastVersionDate": "2026-03-03T14:22:00Z"
  },
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 5,
    "hasMore": false
  },
  "versions": [
    {
      "id": "rv-8a2f5c91",
      "versionNumber": 5,
      "createdAt": "2026-03-03T14:22:00Z",
      "createdBy": {
        "id": "user-456",
        "name": "Jane Smith",
        "email": "jane@example.com"
      },
      "changeType": "modified",
      "changeDescription": "Updated expression to include NOT EMPTY validation",
      "tags": ["production", "approved"],
      "changedFields": 1,
      "isCurrentVersion": true,
      "linkedApprovals": [
        {
          "id": "app-789",
          "status": "approved",
          "approvedAt": "2026-03-03T15:00:00Z"
        }
      ],
      "linkedTestProofs": [
        {
          "id": "tp-999",
          "testDate": "2026-03-03T14:30:00Z",
          "passed": true,
          "coverage": 98.5
        }
      ]
    },
    {
      "id": "rv-7b1e4d82",
      "versionNumber": 4,
      "createdAt": "2026-03-01T09:15:00Z",
      "createdBy": {
        "id": "user-789",
        "name": "John Doe",
        "email": "john@example.com"
      },
      "changeType": "approved",
      "changeDescription": null,
      "tags": ["staging"],
      "changedFields": 0,
      "isCurrentVersion": false,
      "linkedApprovals": [],
      "linkedTestProofs": []
    },
    {
      "id": "rv-6c0d3c73",
      "versionNumber": 3,
      "createdAt": "2026-02-28T16:45:00Z",
      "createdBy": {
        "id": "user-123",
        "name": "Alice Johnson",
        "email": "alice@example.com"
      },
      "changeType": "modified",
      "changeDescription": "Fixed null handling logic",
      "tags": [],
      "changedFields": 2,
      "isCurrentVersion": false,
      "linkedApprovals": [],
      "linkedTestProofs": []
    }
  ]
}
```

### Response: 400 Bad Request

```json
{
  "error": "INVALID_PARAMETERS",
  "message": "Invalid pagination parameters",
  "details": {
    "limit": "Must be between 1 and 100"
  }
}
```

### Response: 403 Forbidden

```json
{
  "error": "INSUFFICIENT_PERMISSIONS",
  "message": "User does not have permission to view this rule's versions"
}
```

### Response: 404 Not Found

```json
{
  "error": "RULE_NOT_FOUND",
  "message": "Rule 'rule-123' does not exist or versioning is not enabled"
}
```

---

## 2. Get Single Version Details

**Endpoint:** `GET /rulebuilder/v1/rules/&#123;ruleId&#125;/versions/&#123;versionId&#125;`

**Description:** Retrieve complete details of a specific rule version

**Authentication:** Required

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `ruleId` | string (UUID) | Rule identifier |
| `versionId` | string (UUID) | Version identifier |

### Response: 200 OK

```json
{
  "id": "rv-8a2f5c91",
  "ruleId": "rule-123",
  "versionNumber": 5,
  "createdAt": "2026-03-03T14:22:00Z",
  "createdBy": {
    "id": "user-456",
    "name": "Jane Smith",
    "email": "jane@example.com"
  },
  "changeType": "modified",
  "changeDescription": "Updated expression to include NOT EMPTY validation",
  "tags": ["production", "approved"],
  "rule": {
    "name": "Customer Completeness Check",
    "description": "Validates that customer ID is not null and not empty",
    "expression": "customer_id IS NOT NULL AND customer_id != ''",
    "dimension": "Completeness",
    "active": true,
    "isTemplate": false,
    "templateId": null
  },
  "relationships": {
    "approvals": [
      {
        "id": "app-789",
        "status": "approved",
        "approvedBy": {
          "id": "user-099",
          "name": "Manager Name",
          "email": "manager@example.com"
        },
        "approvedAt": "2026-03-03T15:00:00Z",
        "comments": "Looks good, approved for production"
      }
    ],
    "testProofs": [
      {
        "id": "tp-999",
        "testDate": "2026-03-03T14:30:00Z",
        "passed": true,
        "coverage": 98.5,
        "recordsTestedCount": 150000,
        "failuresFound": 2250,
        "successRate": 98.5
      }
    ]
  },
  "markedForRollback": false,
  "rollbackHistory": {
    "hasBeenRolledBackFrom": false,
    "hasBeenRolledBackTo": false
  }
}
```

### Response: 404 Not Found

```json
{
  "error": "VERSION_NOT_FOUND",
  "message": "Version 'rv-8a2f5c91' not found for rule 'rule-123'"
}
```

---

## 3. Compare Two Versions

**Endpoint:** `GET /rulebuilder/v1/rules/&#123;ruleId&#125;/versions/&#123;versionId1&#125;/compare/&#123;versionId2&#125;`

**Description:** Compare two versions and show what changed between them

**Authentication:** Required

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `ruleId` | string | Rule identifier |
| `versionId1` | string | From version (older) |
| `versionId2` | string | To version (newer) |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | string | `detailed` | Response format: `detailed` or `summary` |

### Response: 200 OK

```json
{
  "fromVersion": {
    "id": "rv-6c0d3c73",
    "versionNumber": 3,
    "createdAt": "2026-02-28T16:45:00Z",
    "createdBy": "Alice Johnson"
  },
  "toVersion": {
    "id": "rv-8a2f5c91",
    "versionNumber": 5,
    "createdAt": "2026-03-03T14:22:00Z",
    "createdBy": "Jane Smith"
  },
  "changes": {
    "summary": {
      "fieldsChanged": 2,
      "fieldsAdded": 0,
      "fieldsRemoved": 0,
      "totalChanges": 2
    },
    "details": [
      {
        "field": "expression",
        "fieldLabel": "Rule Expression",
        "fieldType": "text",
        "oldValue": "customer_id IS NOT NULL",
        "newValue": "customer_id IS NOT NULL AND customer_id != ''",
        "changeType": "modified",
        "severity": "major"
      },
      {
        "field": "description",
        "fieldLabel": "Description",
        "fieldType": "text",
        "oldValue": "Validates that customer ID is not null",
        "newValue": "Validates that customer ID is not null and not empty",
        "changeType": "modified",
        "severity": "minor"
      }
    ]
  },
  "impactAnalysis": {
    "versionsBetween": 1,
    "timeSpanDays": 3,
    "approvalChanges": false,
    "activationStateChanged": false,
    "testResultsAvailable": true
  }
}
```

### Response (Summary Format): 200 OK

```json
{
  "fromVersion": {
    "versionNumber": 3
  },
  "toVersion": {
    "versionNumber": 5
  },
  "summary": {
    "fieldsChanged": 2,
    "major": 1,
    "minor": 1
  }
}
```

---

## 4. Get Rollback History

**Endpoint:** `GET /rulebuilder/v1/rules/&#123;ruleId&#125;/rollbacks`

**Description:** Retrieve rollback history for a rule

**Authentication:** Required

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Max results per page |
| `offset` | integer | 0 | Pagination offset |
| `sort` | string | `rolled_back_at:desc` | Sort field |

### Response: 200 OK

```json
{
  "ruleId": "rule-123",
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 2,
    "hasMore": false
  },
  "rollbacks": [
    {
      "id": "rb-0a1b2c3d",
      "fromVersionNumber": 5,
      "toVersionNumber": 3,
      "newVersionCreated": {
        "id": "rv-9f3e2d1c",
        "versionNumber": 6
      },
      "rolledBackBy": {
        "id": "user-456",
        "name": "Jane Smith",
        "email": "jane@example.com"
      },
      "rolledBackAt": "2026-03-04T10:30:00Z",
      "reason": "Version 5 had unintended side effects in production. Rolling back to stable version 3.",
      "status": "completed",
      "completedAt": "2026-03-04T10:30:15Z"
    },
    {
      "id": "rb-1b2c3d4e",
      "fromVersionNumber": 2,
      "toVersionNumber": 1,
      "newVersionCreated": {
        "id": "rv-8a2f5c91",
        "versionNumber": 3
      },
      "rolledBackBy": {
        "id": "user-123",
        "name": "Alice Johnson",
        "email": "alice@example.com"
      },
      "rolledBackAt": "2026-02-15T14:22:00Z",
      "reason": "Initial rollback during testing phase",
      "status": "completed",
      "completedAt": "2026-02-15T14:22:30Z"
    }
  ]
}
```

---

## 5. Rollback Rule to Previous Version

**Endpoint:** `POST /rulebuilder/v1/rules/&#123;ruleId&#125;/rollback`

**Description:** Rollback a rule to a previous version

**Authentication:** Required (roles: editor, reviewer, admin)

**Rate Limit:** 10 per minute

### Request Body

```json
{
  "targetVersionId": "rv-6c0d3c73",
  "reason": "Version had performance issues in production, reverting to stable version",
  "skipApproval": false,
  "tags": ["maintenance"]
}
```

### Request Validation

- `targetVersionId` - Required, must exist and be older than current version
- `reason` - Optional but recommended (max 500 characters)
- `skipApproval` - Optional, default false (requires admin role if true)
- `tags` - Optional array of strings for the new rollback version

### Response: 202 Accepted

```json
{
  "id": "rb-0a1b2c3d",
  "status": "processing",
  "fromVersion": {
    "id": "rv-8a2f5c91",
    "versionNumber": 5
  },
  "toVersion": {
    "id": "rv-6c0d3c73",
    "versionNumber": 3
  },
  "newVersionCreated": {
    "id": "rv-9f3e2d1c",
    "versionNumber": 6,
    "status": "pending_approval"
  },
  "rolledBackBy": {
    "name": "Jane Smith"
  },
  "rolledBackAt": "2026-03-04T10:30:00Z",
  "estimatedCompletionTime": "2026-03-04T10:30:30Z",
  "links": {
    "checkStatus": "/rulebuilder/v1/rules/rule-123/rollbacks/rb-0a1b2c3d",
    "viewNewVersion": "/rulebuilder/v1/rules/rule-123/versions/rv-9f3e2d1c"
  }
}
```

### Response: 400 Bad Request

```json
{
  "error": "INVALID_ROLLBACK",
  "message": "Cannot rollback to the current version",
  "details": {
    "targetVersion": "Must be older than current version (5)"
  }
}
```

### Response: 403 Forbidden

```json
{
  "error": "APPROVAL_REQUIRED",
  "message": "Rollback requires approval from reviewer",
  "details": {
    "skipApproval": "Requires admin role"
  }
}
```

### Response: 409 Conflict

```json
{
  "error": "RULE_LOCKED",
  "message": "Rule is currently locked for editing or approval"
}
```

---

## 6. Add/Update Version Tags

**Endpoint:** `PATCH /rulebuilder/v1/rules/&#123;ruleId&#125;/versions/&#123;versionId&#125;/tags`

**Description:** Add or remove tags from a version for categorization

**Authentication:** Required (roles: editor, reviewer, admin)

### Request Body

```json
{
  "tags": ["production", "stable", "v1.0"],
  "action": "replace"
}
```

### Action Options

- `replace` - Replace all tags
- `add` - Add these tags (union)
- `remove` - Remove these tags

### Response: 200 OK

```json
{
  "id": "rv-8a2f5c91",
  "versionNumber": 5,
  "tags": ["production", "stable", "v1.0"],
  "updatedAt": "2026-03-04T11:00:00Z",
  "updatedBy": {
    "id": "user-456",
    "name": "Jane Smith"
  }
}
```

---

## 7. Mark Version for Potential Rollback

**Endpoint:** `PATCH /rulebuilder/v1/rules/&#123;ruleId&#125;/versions/&#123;versionId&#125;/mark-for-rollback`

**Description:** Flag a version as potentially problematic for quick rollback reference

**Authentication:** Required (roles: reviewer, admin)

### Request Body

```json
{
  "markedForRollback": true,
  "reason": "This version had production issues"
}
```

### Response: 200 OK

```json
{
  "id": "rv-8a2f5c91",
  "versionNumber": 5,
  "markedForRollback": true,
  "markedAt": "2026-03-04T11:00:00Z",
  "markedBy": {
    "name": "Jane Smith"
  },
  "reason": "This version had production issues"
}
```

---

## 8. Get Version Statistics

**Endpoint:** `GET /rulebuilder/v1/rules/&#123;ruleId&#125;/versions/stats`

**Description:** Get statistics about rule versions

**Authentication:** Required

### Response: 200 OK

```json
{
  "ruleId": "rule-123",
  "statistics": {
    "totalVersions": 5,
    "currentVersionNumber": 5,
    "oldestVersion": {
      "versionNumber": 1,
      "createdAt": "2026-01-15T10:00:00Z"
    },
    "newestVersion": {
      "versionNumber": 5,
      "createdAt": "2026-03-03T14:22:00Z"
    },
    "versionAgeInDays": 47,
    "totalRollbacks": 1,
    "changesPerVersion": {
      "average": 1.2,
      "max": 2,
      "min": 0
    },
    "mostActiveContributors": [
      {
        "name": "Jane Smith",
        "versionsCreated": 3
      },
      {
        "name": "Alice Johnson",
        "versionsCreated": 2
      }
    ],
    "changeTypeDistribution": {
      "created": 1,
      "modified": 3,
      "approved": 0,
      "activated": 0,
      "deactivated": 0,
      "rollback": 1
    }
  }
}
```

---

## Error Handling

### Common Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `RULE_NOT_FOUND` | 404 | Rule does not exist |
| `VERSIONING_NOT_ENABLED` | 400 | Rule versioning is not enabled |
| `VERSION_NOT_FOUND` | 404 | Specific version not found |
| `INVALID_PARAMETERS` | 400 | Invalid request parameters |
| `INSUFFICIENT_PERMISSIONS` | 403 | User lacks required permissions |
| `RULE_LOCKED` | 409 | Rule is locked for editing |
| `INVALID_ROLLBACK` | 400 | Rollback request is invalid |
| `APPROVAL_REQUIRED` | 403 | Rollback requires approval |
| `WORKSPACE_MISMATCH` | 400 | Rule not in requested workspace |

### Error Response Format

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable error message",
  "details": {
    "field": "Additional context about what went wrong"
  },
  "traceId": "uuid-for-debugging",
  "timestamp": "2026-03-04T11:00:00Z"
}
```

---

## Rate Limiting

- **Default Limit:** 1000 requests per hour
- **Rollback Operations:** 10 per minute
- **Response Headers:** Include `X-RateLimit-*` headers

---

## Pagination

All list endpoints support pagination:

```
GET /rulebuilder/v1/rules/{ruleId}/versions?limit=20&offset=0
```

Response includes:
```json
{
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 147,
    "hasMore": true
  }
}
```

---

## Webhook Events (Future)

Future integration with webhook system:

```
rule.version.created
rule.version.modified
rule.rollback.initiated
rule.rollback.completed
```

---

## OpenAPI/Swagger Integration

These endpoints are documented in OpenAPI 3.0 format and available at:
```
GET /api-docs
```

Query for `versioning` tags to see all version-related endpoints.
