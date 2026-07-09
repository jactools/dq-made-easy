# WF-3: Rule Versioning & Rollback - Workflow Integration

Current-state references:
- [WF-3 comprehensive summary](/docs/features/WF3_COMPREHENSIVE_SUMMARY/)
- [Management feature summary](https://github.com/jactools/dq-rulebuilder/blob/main/features/MANAGEMENT_FEATURE_SUMMARY.md)

## Overview

This document specifies how rule versioning integrates with existing Data Quality Made Easy workflows, including approval processes, testing, auditing, and rule lifecycle management.

---

## 1. Rule Lifecycle with Versioning

### State Transitions

```
┌─────────────────────────────────────────────────────────┐
│ Versioning-Enhanced Rule Lifecycle                      │
└─────────────────────────────────────────────────────────┘

                    Create Rule
                        │
                        ▼
    ┌───────────────────────────────────────┐
    │  1. DRAFT (Version 1)                │
    │  ├─ Rule created                      │
    │  ├─ Can edit expression/attributes    │
    │  ├─ New version created on save       │
    │  └─ Each save = new version           │
    └───────────────────────────────────────┘
                        │
                  Submit for Testing
                        │
                        ▼
    ┌───────────────────────────────────────┐
    │  2. TESTING (Version 2, 3, ...)      │
    │  ├─ Can still edit rule               │
    │  ├─ Run tests on any version          │
    │  ├─ Each iteration may create version │
    │  └─ Test results linked to version    │
    └───────────────────────────────────────┘
                        │
                  Tests Pass + Submit
                        │
                        ▼
    ┌───────────────────────────────────────┐
    │  3. PENDING APPROVAL (Version N)      │
    │  ├─ Rule locked (prevent edits)       │
    │  ├─ Approval created for this version │
    │  ├─ Cannot change expression now      │
    │  └─ Reviewer can view test results    │
    └───────────────────────────────────────┘
                        │
                  Reviewer Decision
                        │
                ┌───────┴───────┐
                │               │
            APPROVED        REJECTED
                │               │
                │          Rule reverts
                │          to DRAFT
                │          for rework
                │               │
                └───────┬───────┘
                        │
    ┌───────────────────────────────────────┐
    │  4. APPROVED (Version N)              │
    │  ├─ Ready for activation              │
    │  ├─ Can be rolled back from           │
    │  ├─ Immutable (snapshot stored)       │
    │  └─ Test results visible              │
    └───────────────────────────────────────┘
                        │
              Request Activation
                        │
                        ▼
    ┌───────────────────────────────────────┐
    │  5. ACTIVATED (Version N)             │
    │  ├─ Rule active in production         │
    │  ├─ Can be rolled back                │
    │  ├─ Rollback creates new version      │
    │  └─ Current version marked            │
    └───────────────────────────────────────┘
                        │
                   Other States
                        │
    ┌───────────────────────────────────────┐
    │  6. DEACTIVATED                       │
    │  ├─ Rule disabled                     │
    │  ├─ Can reactivate previous version   │
    │  └─ Deactivation creates version      │
    └───────────────────────────────────────┘

ROLLBACK FLOW (From any activated version):
                        │
                   Request Rollback
                        │
                        ▼
    ┌───────────────────────────────────────┐
    │  Rollback Operation                   │
    │  ├─ Select target version             │
    │  ├─ Create new version (N+1)          │
    │  ├─ Copy snapshot from target         │
    │  ├─ Mark as "rollback" change type    │
    │  └─ Reset to previous state           │
    └───────────────────────────────────────┘
                        │
              Does new version need
              re-approval?
                        │
                ┌───────┴───────┐
                │               │
              YES              NO
                │               │
                ▼               ▼
            PENDING      ACTIVATED
            APPROVAL     (auto-activate
                         if allowed)
```

### Version Numbers Across States

```
Scenario: Rule with approvals and rollback

Version 1 (DRAFT):
  Created: 2026-01-15
  Status: Draft (initial)

Version 2 (TESTING):
  Modified: 2026-01-16
  Status: Testing

Version 3 (TESTING):
  Modified: 2026-01-17
  Tests Pass / Submit for Approval
  Status: Pending Approval → Approved → Activated

Version 4 (TESTING):
  Modified: 2026-02-28
  Status: Testing (concurrent work)

Version 5 (ACTIVATED):
  Approved: 2026-03-01
  Activated: 2026-03-02
  Status: Active in Production

[Rollback from V5 to V3]:
  Status: Rollback requested
  
Version 6 (ROLLBACK):
  Created: 2026-03-04
  Change Type: "rollback"
  Copied From: V3
  Status: May require approval depending on policy
  
[If auto-approved]:
  Version 6 Activated: 2026-03-04
```

---

## 2. Approval Workflow Integration

### Approval-Version Relationship

```
┌─────────────────────────────────────────────────────────┐
│ Approval Process with Versioning                        │
└─────────────────────────────────────────────────────────┘

BEFORE VERSIONING:
- Approval created for rule
- No explicit version link
- Ambiguous which version was approved

WITH VERSIONING:
- Approval explicitly linked to version
- Version is immutable snapshot at approval time
- Clear audit trail: "Version 3 was approved by Jane"
- Can compare what changed before/after approval
```

### Database Structure

```sql
-- Approval now has explicit version link
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS version_id TEXT;
ALTER TABLE approvals ADD FOREIGN KEY (version_id) 
  REFERENCES rule_versions(id);

-- Relationship table for complex linking
CREATE TABLE IF NOT EXISTS rule_version_relationships (
  version_id TEXT NOT NULL,
  approval_id TEXT,
  test_proof_id TEXT,
  FOREIGN KEY (version_id) REFERENCES rule_versions(id),
  FOREIGN KEY (approval_id) REFERENCES approvals(id)
);
```

### Approval Workflow Steps

```
Step 1: Rule submitted for approval
┌─────────────────────────────────────────────┐
│ Action: User clicks "Submit for Approval"   │
│ Current State: Testing                      │
│ Current Version: 5                          │
└─────────────────────────────────────────────┘
         │
         ▼
Step 2: Create approval record
┌─────────────────────────────────────────────┐
│ - New Approval created                      │
│ - Linked to Version 5 (immutable snapshot)  │
│ - Status: Pending                           │
│ - Rule locked (prevent user edits)          │
│ - Notification sent to reviewers            │
└─────────────────────────────────────────────┘
         │
         ▼
Step 3: Reviewer examines
┌─────────────────────────────────────────────┐
│ - Reviewer opens approval                   │
│ - Can view Version 5 details                │
│ - Can see test results for V5               │
│ - Can compare with previous approved version│
│ - Can view full rule snapshot               │
└─────────────────────────────────────────────┘
         │
    ┌────┴──────────┐
    │               │
  APPROVE        REJECT
    │               │
    ▼               ▼
Step 4a:        Step 4b:
APPROVE         REJECT
┌────────────┐  ┌─────────────┐
│ - Status:  │  │ - Status:   │
│   Approved │  │   Rejected  │
│ - Comment: │  │ - Reason:   │
│   Optional │  │   Required  │
│ - Time:    │  │ - Time:     │
│   recorded │  │   recorded  │
│ - Version  │  │ - Rule back │
│   approved │  │   to Draft  │
│ - Can now  │  │ - User can  │
│   activate │  │   edit rule │
└────────────┘  └─────────────┘
```

### Approval + Version Details View

**Reviewer sees:**

```json
{
  "approval": {
    "id": "app-789",
    "status": "pending",
    "requestedBy": "user-123",
    "requestedAt": "2026-03-03T10:00:00Z",
    "approvalDeadline": "2026-03-05T10:00:00Z"
  },
  "version": {
    "id": "rv-8a2f5c91",
    "versionNumber": 5,
    "createdAt": "2026-03-03T09:45:00Z",
    "createdBy": "Jane Smith",
    "changeType": "modified",
    "changeDescription": "Updated expression to include NOT EMPTY validation",
    "ruleSnapshot": {
      "name": "Customer Completeness Check",
      "expression": "customer_id IS NOT NULL AND customer_id != ''",
      "dimension": "Completeness"
    },
    "changesFromPrevious": {
      "fieldsChanged": 1,
      "details": [
        {
          "field": "expression",
          "oldValue": "customer_id IS NOT NULL",
          "newValue": "customer_id IS NOT NULL AND customer_id != ''"
        }
      ]
    },
    "linkedTestProofs": [
      {
        "id": "tp-999",
        "testDate": "2026-03-03T09:50:00Z",
        "passed": true,
        "coverage": 98.5,
        "failuresFound": 2250
      }
    ],
    "previouslyApprovedVersion": {
      "versionNumber": 3,
      "approvedAt": "2026-02-28T15:00:00Z",
      "approvedBy": "Manager Name"
    }
  }
}
```

### Concurrent Changes Protection

```
Scenario: User edits rule while approval pending

1. Version 5 submitted for approval
   └─ Rule locked

2. User tries to edit expression
   └─ Error: "Cannot edit while approval pending"
   └─ Options:
      - Wait for approval decision
      - Withdraw approval (cancel)
      - Create new draft (if allowed)

3. If approval rejected
   └─ Rule returned to DRAFT
   └─ User can edit again
   └─ Creates new version when saved

4. If approval withdrawn
   └─ Rule returned to DRAFT
   └─ Edits can resume
```

---

## 3. Test Results Integration

### Test Proof Linking

```sql
-- Test proofs now explicitly link to versions
ALTER TABLE test_proofs ADD COLUMN IF NOT EXISTS version_id TEXT;
ALTER TABLE test_proofs ADD FOREIGN KEY (version_id) 
  REFERENCES rule_versions(id);

-- Enable testing history per version
CREATE TABLE IF NOT EXISTS version_test_history (
  version_id TEXT NOT NULL,
  test_proof_id TEXT,
  test_order INT, -- sequence of tests for this version
  FOREIGN KEY (version_id) REFERENCES rule_versions(id),
  FOREIGN KEY (test_proof_id) REFERENCES test_proofs(id)
);
```

### Test Workflow with Versions

```
Rule in TESTING state with multiple versions

Version 4:
  - Created: 2026-02-28 16:00
  - Status: Testing
  - Tests: Not run yet
  
Version 5:
  - Created: 2026-03-01 10:00
  - Status: Testing
  - Tests: [Test Run 1] ✓ Passed (98.5%)
  - Tests: [Test Run 2] ✓ Passed (99.2%)
  - Ready for approval

User action: "Test this version"
  └─ System determines which version to test
  └─ Creates test_proof with version_id = rv-xxxx
  └─ Runs test against that version's expression
  └─ Stores results linked to version
  └─ Display: "Version 5: 2 test runs, 100% passed"

User action: "Revert to Version 4"
  └─ Only if not in approval
  └─ Creates new draft version (6)
  └─ Copies Definition from Version 4
  └─ Can run tests on new Version 6
```

### Test Evidence in Rollback Decision

```
Reviewer evaluating rollback request:

"Should we rollback from V5 to V3?"

Evidence Shown:
├─ Version 3
│  ├─ Test Results: [Run 1] ✓ Passed (97.8%)
│  ├─ Test Results: [Run 2] ✓ Passed (98.2%)
│  ├─ Status: Stable, production-tested
│  └─ Last tested: 2026-02-28
│
├─ Version 5
│  ├─ Test Results: [Run 1] ✓ Passed (98.5%)
│  ├─ Test Results: [Run 2] ❌ NEW ISSUES FOUND
│  │  ├─ 5000 false positives detected
│  │  ├─ Coverage drop to 95%
│  │  └─ Last tested: 2026-03-04
│  └─ Status: Issues detected
│
└─ RECOMMENDATION: ✓ Safe to rollback
   (V3 has proven test history)
```

---

## 4. Audit Trail Enhancement

### Versioning Events in Audit Trail

```
Timeline for rule "Customer Completeness Check"

2026-01-15 10:00:00 | RULE CREATED
                    | User: Admin
                    | Version: 1 (initial)

2026-01-16 14:30:00 | RULE MODIFIED
                    | User: Jane Smith
                    | Version: 2 (expression updated)
                    | Changes: expression field

2026-01-17 09:15:00 | TEST PROOF CREATED
                    | Version: 2
                    | Results: 98.5% pass rate
                    | Coverage: 150,000 records

2026-01-20 11:00:00 | RULE MODIFIED
                    | User: John Doe
                    | Version: 3 (description updated)

2026-02-28 16:45:00 | APPROVAL REQUESTED
                    | User: Jane Smith
                    | Version: 3 (submitted for approval)
                    | Status: Pending Approval

2026-03-01 10:00:00 | APPROVAL GRANTED
                    | User: Manager Name
                    | Version: 3
                    | Comment: "Approved for production"

2026-03-02 08:00:00 | RULE ACTIVATED
                    | Version: 3 is now active

2026-03-03 14:22:00 | RULE MODIFIED (Post-Activation)
                    | User: Jane Smith
                    | Version: 4 (expression updated for v2)
                    | Note: This runs in parallel, not approved yet

2026-03-04 10:30:00 | ROLLBACK INITIATED
                    | User: Jane Smith
                    | From Version: 4
                    | To Version: 3
                    | Reason: "Version 4 had production issues"
                    | Action: Rollback success
                    | New Version Created: 5
                    | Status: Version 5 requires re-approval

2026-03-04 10:30:15 | NEW VERSION CREATED (Rollback)
                    | Version: 5
                    | Change Type: Rollback
                    | Copied From: Version 3
                    | Status: Pending Approval
```

### Audit Table Structure

```sql
-- Enhanced audit table for versioning
CREATE TABLE IF NOT EXISTS audit_extended (
  id TEXT PRIMARY KEY,
  ruleId TEXT NOT NULL,
  versionId TEXT,
  actionType TEXT, -- 'created', 'modified', 'tested', 'approved', 'activated', 'rollback', etc.
  actor TEXT NOT NULL,
  timestamp TIMESTAMP,
  previousVersionId TEXT, -- For rollbacks
  changesSummary TEXT,
  details JSONB, -- Full change details
  FOREIGN KEY (ruleId) REFERENCES rules(id),
  FOREIGN KEY (versionId) REFERENCES rule_versions(id)
);
```

### Query Examples

```sql
-- Show all changes for a rule with versions
SELECT 
  a.timestamp,
  a.actionType,
  a.actor,
  rv.versionNumber,
  rv.changeDescription
FROM audit_extended a
LEFT JOIN rule_versions rv ON a.versionId = rv.id
WHERE a.ruleId = 'rule-123'
ORDER BY a.timestamp DESC;

-- Show rollback history
SELECT 
  rb.rolled_back_at,
  rb.rolled_back_by,
  rv_from.versionNumber AS from_version,
  rv_to.versionNumber AS to_version,
  rb.reason
FROM rule_rollbacks rb
LEFT JOIN rule_versions rv_from ON rb.from_version_id = rv_from.id
LEFT JOIN rule_versions rv_to ON rb.to_version_id = rv_to.id
WHERE rb.rule_id = 'rule-123'
ORDER BY rb.rolled_back_at DESC;
```

---

## 5. Activation/Deactivation Workflow

### State Management

```
ACTIVATION FLOW:

Approved Version 5
       │
       ▼
[Activate Button]
       │
       ├─ Check: Is version approved? ✓
       ├─ Check: No incompatibilities? ✓
       ├─ Check: Tests passed? ✓
       │
       ▼
Version 5 Status Changed to ACTIVATED
└─ Rule becomes active in production
└─ Create audit entry
└─ Notify users

DEACTIVATION FLOW:

Active Version 5
       │
       ▼
[Deactivate Button]
       │
       ├─ Requires justification
       ├─ Requires reviewer approval (maybe)
       │
       ▼
Version 5 Status Changed to DEACTIVATED
└─ Rule no longer executes
└─ Create version snapshot marked "deactivated"
└─ Create audit entry
└─ Previous active version not auto-reactivated

RE-ACTIVATION FLOW:

Deactivated Version 3
       │
       ▼
[Reactivate Button]
       │
       ├─ Requires approval (maybe)
       │
       ▼
Version 3 Re-activated
└─ Creates new version (copy of V3)
└─ Or reuses Version 3
```

### Version Status Mapping

```
rule_versions table - change_type & active columns:

Version 1:
  change_type: 'created'
  active: false
  status: Draft/Testing

Version 2:
  change_type: 'modified'
  active: false
  status: Testing

Version 3:
  change_type: 'approved'
  active: false
  status: Approved / Pending Activation

Version 4:
  change_type: 'activated'
  active: true
  status: Active

Version 5:
  change_type: 'modified'
  active: true
  status: Active (concurrent work)

Version 6:
  change_type: 'deactivated'
  active: false
  status: Deactivated

Version 7:
  change_type: 'rollback'
  active: false
  status: Pending Approval
```

---

## 6. Approval Policy with Versioning

### Configuration Options

```
Settings > Workflow > Approval Policies

Policy: Require Approval for All Changes
├─ When: Any version created
├─ Who: Reviewer or Admin
├─ If rejected: Version discarded, rule reverts

Policy: Require Approval for Activation
├─ When: Version being activated
├─ Who: Admin only
├─ If rejected: Version stays inactive

Policy: Auto-Approve Minor Changes
├─ When: Only metadata changes (description, tags)
├─ Auto approve: After 24 hours without review
├─ Applies to: Description, tags, dimension only
├─ NOT to: Expression (always requires approval)

Policy: Rollback Approval
├─ When: Rollback requested
├─ Who: Reviewer or Admin
├─ Auto-approve: If rolling back to previously approved
├─ Require-approval: If rolling back beyond approved
└─ Fast-track: Can be expedited
```

### Rollback Approval Logic

```
Rollback Request: V4 → V2

Check: Was V2 previously approved?
       ✓ YES
       
       └─ Configure rollback approval policy:
          └─ Policy: "AUTO_APPROVE_APPROVED_VERSIONS"
          └─ V2 was approved on 2026-02-28
          └─ Auto-approve rollback
          └─ Create V5 with status: ACTIVATED (auto)

Check: Was V2 previously approved?
       ✗ NO
       
       └─ Configure rollback approval policy:
          └─ Policy: "REQUIRE_APPROVAL_ALL_ROLLBACKS"
          └─ V2 was draft/testing
          └─ Require explicit approval
          └─ Create V5 with status: PENDING_APPROVAL
          └─ Notify reviewers
```

---

## 7. Notification Integration

### Event-Based Notifications

```
Version Creation Events:
├─ version.created
│  └─ Send: None (automatic)
├─ version.modified
│  └─ Send: To rule owner (optional)
└─ version.snapshot_created
   └─ Send: To rule owner (on approval/activation)

Approval Events:
├─ approval.requested
│  └─ Send: To reviewers (email)
│  └─ Content: Version N submitted, changes summary
├─ approval.granted
│  └─ Send: To rule owner (email)
│  └─ Content: Approved, can activate
└─ approval.rejected
   └─ Send: To rule owner (email)
   └─ Content: Rejection reason, resubmit changes

Rollback Events:
├─ rollback.initiated
│  └─ Send: To rule owner (email)
│  └─ Content: Rollback in progress
├─ rollback.completed
│  └─ Send: To rule owner + stakeholders (email)
│  └─ Content: Rollback successful, new version status
└─ rollback.approval_required
   └─ Send: To reviewers (email)
   └─ Content: New version requires approval
```

### Notification Content Example

**Email: Approval Granted for Version 5**

```
Subject: Rule "Customer Completeness Check" - Approval Granted

Dear Jane,

Your rule "Customer Completeness Check" (Version 5) has been approved 
for activation.

Approval Details:
├─ Approved By: Manager Name
├─ Approved At: 2026-03-03 15:00
├─ Review Time: 5 hours
└─ Comments: "Looks good, approved for production"

Changes in This Version:
├─ Field: Expression
├─ Old: customer_id IS NOT NULL
└─ New: customer_id IS NOT NULL AND customer_id != ''

Test Results:
├─ Coverage: 98.5%
├─ Pass Rate: 100%
└─ Records Tested: 150,000

Next Steps:
[1] Review the changes: [Link to Version Details]
[2] Activate the rule: [Link to Activation Page]

If you have questions, contact: review-team@company.com

---
Data Quality Made Easy
```

---

## 8. Deployment Workflow

### Version Deployment Scenario

```
Production Deployment Process

Step 1: Version Approved and Activated
        Version: 5
        Status: Activated
        Active Since: 2026-03-02

Step 2: Monitor in Production
        ├─ Rule executes regularly
        ├─ Test results collected
        ├─ No issues detected (first 48 hours)

Step 3: Issues Detected
        ├─ Spike in false positives
        ├─ Customer complaints
        ├─ Test coverage drops to 92%
        
Step 4: Remediation Decision
        ├─ Option A: Quick Rollback (minutes)
        │  └─ Rollback to V3 (proven stable)
        │  └─ Create V6 as rollback version
        │  └─ Immediate activation (maybe auto-approve)
        │
        ├─ Option B: Fix Forward (hours/days)
        │  └─ Create V7 (modified expression)
        │  └─ Run tests (98.5% pass, issues fixed)
        │  └─ Go through approval again
        │  └─ Activate V7
        │
        └─ Decision: Quick Rollback (via UI)

Step 5: Rollback Execution
        ├─ V6 created (from V3 snapshot)
        ├─ Change type: rollback
        ├─ Approval status: PENDING (policy-dependent)
        │
        ├─ If AUTO_APPROVE: V6 auto-activated
        │  └─ 5 minutes total downtime
        │  └─ Users notified immediately
        │
        └─ If MANUAL_APPROVE: 
           ├─ Reviewer notified (urgent)
           ├─ Fast-track approval (10 minutes)
           └─ Rule reactivated with V6

Resulting State:
├─ V3: Approved, previously active
├─ V4: Draft/testing, was never approved
├─ V5: Activated, then marked as problematic
├─ V6: Active (current), rollback marker, approved
└─ Audit trail: Complete history visible
```

---

## 9. Error Handling & Rollback

### Validation During Workflow

```
When User Attempts Action          Check             On Failure
──────────────────────────────────────────────────────────────────

Submit Version 5 for Approval      Is rule locked?   Error: Rule locked
                                   Has tests run?    Warning: Run tests first
                                   Is approved?      OK: Proceed

Approve Version 5                  Is pending?       Error: Not pending
                                   User reviewer?    Error: Unauthorized
                                   Valid reason?     Warning: Reason empty

Activate Version 5                 Is approved?      Error: Not approved
                                   Is locked?        Error: Locked by other
                                   Already active?   Error: Already active

Rollback to Version 3              Still exists?     Error: Version deleted
                                   Is older?         Error: Can't "rollback" forward
                                   Can approve?      Ask: Approval needed?
                                   Already active?   Error: Can't rollback to current

Create New Version                 Editing draft?    OK: Auto-save new version
                                   Approved?         Error: Locked while approved
                                   Draft edits?      OK: Create next version
```

### Handling Concurrent Operations

```
Scenario: User A and User B editing same rule

Timeline:
├─ 10:00: User A opens rule draft (Version 4)
├─ 10:05: User B opens rule draft (Version 4)
├─ 10:10: User A saves (expression changed)
│         └─ New Version 5 created
│         └─ User A sees "Version 5 (latest)"
├─ 10:12: User B saves (description changed)
│         └─ Conflict: Version 5 already exists
│         └─ Options:
│            a) Reject: "Rule was updated by User A"
│            b) Merge: Create V6 (merge changes)
│               └─ Auto-merge if no field conflicts
│               └─ Manual review if conflicts exist
│
└─ Resolution: 
   ├─ V5 created by User A (10:10)
   └─ V6 created by User B's merge (10:12)
     └─ Show merge confirmation
     └─ Option to view merged result
```

---

## 10. Data Consistency & Constraints

### Referential Integrity

```sql
-- Version must exist when linked to approval
ALTER TABLE approvals 
  ADD CONSTRAINT fk_approval_version 
  FOREIGN KEY (version_id) REFERENCES rule_versions(id);

-- Test results must reference version
ALTER TABLE test_proofs
  ADD CONSTRAINT fk_test_version
  FOREIGN KEY (version_id) REFERENCES rule_versions(id);

-- Rollback must reference versions
ALTER TABLE rule_rollbacks
  ADD CONSTRAINT fk_rollback_from
  FOREIGN KEY (from_version_id) REFERENCES rule_versions(id),
  ADD CONSTRAINT fk_rollback_to
  FOREIGN KEY (to_version_id) REFERENCES rule_versions(id),
  ADD CONSTRAINT fk_rollback_new
  FOREIGN KEY (new_version_created_id) REFERENCES rule_versions(id);

-- Current version must exist  
ALTER TABLE rules
  ADD CONSTRAINT fk_rules_current
  FOREIGN KEY (current_version_id) REFERENCES rule_versions(id);
```

### Cascade & Soft Delete Rules

```
When Rule Deleted (soft delete):
├─ Set rules.deleted_on = NOW()
├─ Keep all versions (data integrity)
├─ De-list from UI (but keep queryable)
└─ Keep audit trail intact

When Version Deleted (force hard delete):
├─ Check: Are there approvals linked?
│  └─ Error: Cannot delete (referential integrity)
├─ Check: Are there rollbacks linked?
│  └─ Error: Cannot delete (history needed)
├─ Only allow if:
│  └─ Admin AND
│  └─ No approvals AND
│  └─ No rollbacks AND
│  └─ Migration complete
```

---

## 11. Integration with Rule Activation

### Pre-Activation Checks

```
When User Clicks "Activate"

Checks Performed:
├─ [1] Version Status Check
│      Is version in APPROVED state?
│      └─ If No: Error "Must be approved first"
│
├─ [2] Lock Check
│      Is rule locked for editing?
│      └─ If Yes: Error "Rule is locked"
│
├─ [3] Approval Check
│      Does current policy require re-approval?
│      └─ If Yes: Error "Requires approval"
│
├─ [4] Test Check (configurable)
│      Have tests been run on this version?
│      └─ If No: Warning "No tests, continue anyway?"
│
├─ [5] Compatibility Check
│      Are there schema/environment issues?
│      └─ If Yes: Warning "May have issues in env X"
│
├─ [6] Version Conflict Check
│      Is another version active?
│      └─ If Yes: Warn "Will deactivate V3"
│
└─ [7] Audit Check
       Record activation in audit trail

If All Pass:
  ├─ Update rules.active = true
  ├─ Update rule_versions.active = true
  ├─ Create audit entry
  ├─ Send notifications
  └─ Return success
```

### Post-Activation Monitoring

```
After Version Activated:

Keep track of:
├─ Activation timestamp
├─ Activated by (user)
├─ Time in active state
├─ Any rollback markers
├─ Test execution during active period
└─ Issues reported while active

Enable tracking for quick rollback decision:
├─ "How long has this been active?" → 12 hours
├─ "Have there been issues?" → Yes, 500 false positives
├─ "What version before this?" → V3
├─ "Was V3 stable?" → Yes, 48 hours without issues
├─ "Recommend rollback?" → YES ⚡
```

---

## 12. Preview Feature Integration

### Feature Flag Behavior

```
Settings > Preview Features > Rule Versioning

When DISABLED (default):
├─ No version history UI shown
├─ No version columns in lists
├─ Versioning in background (for future)
├─ Existing workflows unchanged
└─ No performance impact

When ENABLED (preview):
├─ Version history tab visible
├─ Version badges in lists
├─ Rollback controls shown
├─ Versioning active
├─ Backward compatible (non-versioned rules work)
└─ Can be disabled anytime

Per-Rule Enable:
├─ Rule detail > Settings > "Enable Versioning"
├─ Creates initial version (snapshot)
├─ Versioning required approvals
└─ Can disable to pause versioning
```

---

## 13. Bulk Operations with Versions

### Bulk Approve

```
User selects multiple rules for approval

Approval Bulk Dialog:
├─ Version 5 of "Customer ID Check"
├─ Version 3 of "Name Validation"  
├─ Version 7 of "Amount Range Check"
│
└─ Bulk Approve:
   ├─ Create 3 approval records
   ├─ Each linked to specific version
   ├─ All locked simultaneously
   ├─ All notifications sent
   └─ Audit trail: "Bulk approved 3 versions"
```

### Bulk Activate

```
Similar to bulk approve

├─ Pre-checks run
├─ Multiple versions activated
├─ Previous active versions auto-deactivated
├─ Notifications sent
└─ Audit trail records each activation
```

---

## 14. Workflow State Diagram

```
┌──────────────────────────────────────────────────────────────┐
│ Complete Workflow State Machine                              │
└──────────────────────────────────────────────────────────────┘

                    ┌─────────────┐
                    │   Created   │
                    │ (Version 1) │
                    └──────┬──────┘
                           │
                           │ Edit Expression
                           ▼
                    ┌─────────────────┐
                    │ DRAFT/TESTING   │
                    │ (Versions 2-N)  │
                    │ (Editable)      │
                    └──────┬──────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
       Continue      Run Tests    Submit for Approval
       Editing       (linked to   (lock rule)
       (version      version)     │
        +1)          │            │
            │        │            │
        ────┴────────┘            ▼
                          ┌──────────────────┐
                          │ PENDING APPROVAL │
                          │ (locked)         │
                          └──────┬───────────┘
                                 │
                        ┌────────┴────────┐
                        │                 │
                    APPROVED         REJECTED
                        │                 │
                        │           (return to
                        │            DRAFT)
                        │                 │
                        ▼                 │
                    ┌─────────────┐       │
                    │ APPROVED    │───────┘
                    │ (Version N) │
                    │ (Locked)    │
                    └──────┬──────┘
                           │
                      Activate
                           │
                           ▼
                    ┌─────────────┐
                    │  ACTIVATED  │
                    │ (Version N) │
                    │ (Active)    │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
       Deactivate   Request Rollback   Monitor
            │         (to older V)       │
            │              │             │
            ▼              ▼             ▼
       ┌─────────┐    ┌─────────────────────────┐
       │DEACTIVATE    │ Create New Version      │
       │(V deactivated)   │ (from target V)         │
       └───────────    │ (pending approval)      │
                       └─────────────────────────┘
                              │
                         ┌────┴────┐
                         │          │
                    Auto-Approve Require Approval
                         │          │
                         ├──────────┤
                         │          │
                         ▼          ▼
                    ACTIVATED   PENDING_APPROVAL
                     (current)      (review)
                         │              │
                         │         ┌────┴────┐
                         │         │          │
                         │      APPROVED  REJECTED
                         │         │          │
                         └────────┬┘    (discard)
                                  │
                                  ▼
                            ACTIVATED (new)
```

---

## 15. Migration Path for Existing Rules

### Phase 1: Schema Migration (Non-Breaking)
- Create versioning tables
- Add versioning columns to rules table
- No changes to rules that don't opt-in

### Phase 2: Enable Preview Feature
- Users can opt-into versioning
- Some power users enable for important rules

### Phase 3: Gradual Rollout
- Enable for entire workspace (optional)
- Create initial versions for all rules
- Existing approvals/tests linked to v1

### Phase 4: Full Adoption (Future)
- Make versioning mandatory
- Deprecation period for non-versioned rules
- All workflows use versioning
