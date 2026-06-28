# WF-3: Rule Versioning & Rollback - Schema Design

## Overview

This document outlines the database schema design for implementing rule versioning and rollback functionality as a preview feature in Data Quality Made Easy.

## Current State

The existing `rules` table stores:
- `id` - Primary key
- `name`, `description`, `expression` - Rule definition
- `dimension`, `active`, `is_template` - Rule attributes
- `workspace`, `createdBy` - Ownership
- `last_approval_*` - Approval tracking
- `deleted_on`, `deleted_by` - Soft delete
- `template_id`, `suggestion_id` - References

## Proposed Schema

### 1. Rule Versions Table

Store immutable snapshots of each rule change:

```sql
CREATE TABLE rule_versions (
  id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL,
  version_number INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by TEXT NOT NULL,
  change_type TEXT, -- 'created', 'modified', 'approved', 'activated', 'deactivated'
  change_description TEXT,
  
  -- Snapshot of rule state at this version
  name TEXT NOT NULL,
  description TEXT,
  expression TEXT NOT NULL,
  dimension TEXT,
  active BOOLEAN,
  is_template BOOLEAN,
  template_id TEXT,
  
  -- Versioning metadata
  tags TEXT[], -- Optional tags like 'production', 'staging'
  marked_for_rollback BOOLEAN DEFAULT false,
  
  FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE,
  UNIQUE (rule_id, version_number)
);

-- Index for efficient querying
CREATE INDEX idx_rule_versions_rule_id ON rule_versions(rule_id);
CREATE INDEX idx_rule_versions_created_at ON rule_versions(created_at);
```

### 2. Version Changes Table (Diff Tracking)

Track what changed between versions for UI display:

```sql
CREATE TABLE rule_version_diffs (
  id TEXT PRIMARY KEY,
  from_version_id TEXT NOT NULL,
  to_version_id TEXT NOT NULL,
  field_name TEXT NOT NULL, -- 'name', 'expression', 'description', etc.
  old_value TEXT,
  new_value TEXT,
  
  FOREIGN KEY (from_version_id) REFERENCES rule_versions(id) ON DELETE CASCADE,
  FOREIGN KEY (to_version_id) REFERENCES rule_versions(id) ON DELETE CASCADE
);

CREATE INDEX idx_version_diffs_versions ON rule_version_diffs(from_version_id, to_version_id);
```

### 3. Rollback History Table

Track rollback operations:

```sql
CREATE TABLE rule_rollbacks (
  id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL,
  from_version_id TEXT NOT NULL,
  to_version_id TEXT NOT NULL,
  rolled_back_by TEXT NOT NULL,
  rolled_back_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  reason TEXT,
  
  FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE,
  FOREIGN KEY (from_version_id) REFERENCES rule_versions(id) ON DELETE CASCADE,
  FOREIGN KEY (to_version_id) REFERENCES rule_versions(id) ON DELETE CASCADE
);

CREATE INDEX idx_rollbacks_rule_id ON rule_rollbacks(rule_id);
```

### 4. Version Relationships Table

Link versions to approvals, test results, deployments:

```sql
CREATE TABLE rule_version_relationships (
  version_id TEXT NOT NULL,
  approval_id TEXT,
  test_proof_id TEXT,
  deployment_id TEXT,
  
  FOREIGN KEY (version_id) REFERENCES rule_versions(id) ON DELETE CASCADE,
  FOREIGN KEY (approval_id) REFERENCES approvals(id) ON DELETE SET NULL,
  FOREIGN KEY (test_proof_id) REFERENCES test_proofs(id) ON DELETE SET NULL
);
```

### 5. Rules Table Updates

Add versioning metadata to existing `rules` table:

```sql
ALTER TABLE rules ADD COLUMN IF NOT EXISTS current_version_id TEXT;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS total_versions INT DEFAULT 1;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS versioning_enabled BOOLEAN DEFAULT false;

-- Add foreign key constraint
ALTER TABLE rules 
ADD CONSTRAINT fk_rules_current_version 
FOREIGN KEY (current_version_id) REFERENCES rule_versions(id) ON DELETE SET NULL;

CREATE INDEX idx_rules_current_version ON rules(current_version_id);
```

## Migration Strategy

### Step 1: Create New Tables (Non-breaking)

```sql
-- Create versioning tables with no impact on existing data
-- Version 1.1.0 schema bump
```

### Step 2: Migrate Existing Data

When versioning is enabled for a rule, create its initial version:

```sql
INSERT INTO rule_versions (
  id, rule_id, version_number, created_at, created_by,
  change_type, name, description, expression, dimension, active, is_template, template_id
)
SELECT 
  generate_id(), -- UUID generator
  id,
  1,
  created_at OR CURRENT_TIMESTAMP,
  created_by OR 'system',
  'created',
  name,
  description,
  expression,
  dimension,
  active,
  is_template,
  template_id
FROM rules
WHERE versioning_enabled = true;

UPDATE rules 
SET 
  current_version_id = rule_versions.id,
  total_versions = 1
FROM rule_versions
WHERE rules.id = rule_versions.rule_id 
AND rule_versions.version_number = 1;
```

### Step 3: Enable Versioning Gradually

- Start as preview feature (opt-in per rule)
- Users enable versioning for specific rules
- System automatically creates versions on changes

## Data Flow

### Creating a New Rule Version

```
User modifies rule
    ↓
INSERT rule_version (with incremented version_number)
    ↓
Track changes in rule_version_diffs
    ↓
UPDATE rules SET current_version_id = new_version_id
    ↓
CREATE audit log entry
```

### Rollback Workflow

```
User requests rollback to previous version
    ↓
Copy previous version's data
    ↓
CREATE new rule_version (change_type='rollback')
    ↓
INSERT rule_rollback record (tracks reason)
    ↓
UPDATE rules SET current_version_id = new_version_id
    ↓
CREATE audit log entry
```

## API Design

### Version History Endpoint

```
GET /rulebuilder/v1/rules/{ruleId}/versions
Response:
{
  "rule_id": "rule-123",
  "current_version": 5,
  "total_versions": 5,
  "versions": [
    {
      "id": "version-456",
      "version_number": 5,
      "created_at": "2026-03-03T10:00:00Z",
      "created_by": "user@example.com",
      "change_type": "modified",
      "changes": 2,
      "tags": ["production"]
    },
    ...
  ]
}
```

### Compare Versions Endpoint

```
GET /rulebuilder/v1/rules/{ruleId}/versions/{version1}/compare/{version2}
Response:
{
  "from_version": 3,
  "to_version": 5,
  "changes": [
    {
      "field": "expression",
      "old_value": "col1 IS NOT NULL",
      "new_value": "col1 IS NOT NULL AND col1 != ''"
    },
    {
      "field": "description",
      "old_value": "Old description",
      "new_value": "Updated description"
    }
  ]
}
```

### Rollback Endpoint

```
POST /rulebuilder/v1/rules/{ruleId}/rollback
Request:
{
  "target_version": 3,
  "reason": "Previous version was more accurate for production"
}

Response:
{
  "id": "rollback-789",
  "rule_id": "rule-123",
  "from_version": 5,
  "to_version": 3,
  "new_version_created": 6,
  "completed_at": "2026-03-03T10:05:00Z"
}
```

## Feature Flag Configuration

Versioning as preview feature in settings:

```
Settings > Preview Features > Rule Versioning
- Enable/disable per workspace
- Enable/disable per user
- Default: disabled
```

## Impact Analysis

### Storage Impact
- ~500 bytes per version (depending on expression length)
- For rule with 10 versions: ~5KB additional storage
- Negligible impact for typical deployments

### Performance Impact
- Version queries: indexed by rule_id, minimal impact
- Rollback operation: O(1) copy from history
- No impact on active rule execution

### Backwards Compatibility
- Existing rules continue to work without versioning
- Versioning is opt-in per rule
- No breaking changes to existing API

## Considerations

### Approval Workflow Integration
- Each version can have its own approval state
- Rollback may require re-approval based on policies
- Test results tied to specific versions

### Test Results
- Test proofs should reference specific versions
- Rollback inherits previous version's test status
- Users can see "tested at version X" information

### Audit Trail
- All version changes logged to audit table
- Rollbacks logged separately for visibility
- Change type indicates nature of modification

## Implementation Phases

### Phase 1: Schema & Data Layer
- Create versioning tables
- Migrate existing data
- Add indexes for performance

### Phase 2: API Layer
- Version CRUD endpoints
- History retrieval
- Diff calculation
- Rollback operations

### Phase 3: UI Layer
- Version history UI
- Compare versions interface
- Rollback confirmation dialog
- Preview feature flag integration

### Phase 4: Workflow Integration
- Approval workflow updates
- Test result linking
- Audit trail enhancements

## Future Enhancements

- **Version Tags**: Label versions (e.g., "v1.0", "production-stable")
- **Version Annotations**: User comments on versions
- **Branching**: Create alternative versions for A/B testing
- **Merge Versions**: Combine changes from multiple versions
- **Auto-versioning**: Based on change frequency or time intervals
