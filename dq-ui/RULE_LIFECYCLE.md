# Rule Lifecycle & Approval Workflow Documentation

## Overview

Data Quality Made Easy now implements a comprehensive rule lifecycle management system with a complete approval workflow, testing capabilities, and full audit trail tracking. This ensures data quality rules are properly tested, reviewed, and approved before activation.

## Rule Lifecycle Stages

### 1. **Draft** 📝
- Rule is created but not yet ready for testing
- Only the creator (editor/admin) can view and edit
- Can transition to: **Testing**

### 2. **Testing** 🧪
- Rule is undergoing testing
- System runs validation tests on sample data
- Can transition to: **Tested**

### 3. **Tested** ✓
- Tests have been completed and results are available
- Test coverage and pass/fail rates are recorded
- Ready to be submitted for approval
- Can transition to: **Pending Approval**

### 4. **Pending Approval** 📤
- Rule has been submitted for review
- Awaiting approval from a Reviewer or Admin
- Can transition to: **Approved** or **Rejected**

### 5. **Approved** ✅
- Rule has been reviewed and approved
- Ready to be activated
- Can transition to: **Activated**

### 6. **Activated** 🚀
- Rule is now active and running in production
- Continuously monitoring data quality
- Can transition to: **Rejected** (if issues found)

### 7. **Rejected** ❌
- Rule has been rejected during approval or after issues found
- Can transition back to: **Draft** (for rework)

## Role-Based Permissions

### Admin
- ✅ Create rules
- ✅ Test rules
- ✅ Approve rules
- ✅ Activate rules
- ✅ View audit trail
- ✅ Manage all aspects

### Editor
- ✅ Create rules
- ✅ Test rules
- ✅ Submit for approval
- ❌ Cannot approve own rules (approval by Reviewer)
- ✅ View audit trail

### Reviewer
- ❌ Cannot create rules
- ❌ Cannot test rules
- ✅ Approve/Reject rules submitted by others
- ✅ View audit trail
- ✅ Add comments during review

### Viewer
- ✅ View rules and their status
- ✅ View audit trail
- ❌ Cannot make any modifications

## Components

### 1. Rules Component (`Rules.tsx`)
**Location:** `/src/components/Rules.tsx`

Displays all rules in the current workspace with:
- **Status Filtering:** Filter by draft, testing, tested, pending-approval, approved, activated, rejected
- **Status Badges:** Visual indicators for current rule status
- **Risk Level Badges:** Display risk levels (low, medium, high)
- **Workflow Actions:** Contextual buttons for next valid transitions
- **Test Coverage Display:** Shows test coverage percentage when tests have been run
- **Expandable Details:** Click to see full rule information including attributes and data objects

**Key Features:**
```
- Real-time filtering and sorting
- Role-based action availability
- Test result summaries
- Affected data objects display
```

### 2. Approvals Component (`Approvals.tsx`)
**Location:** `/src/components/Approvals.tsx`

Workflow for reviewing and approving rules:
- **Pending Review Section:** Shows rules awaiting approval
  - Rule details and test results
  - Comment field for reviewer feedback
  - Approve/Reject buttons
- **Processing History:** Shows previously approved/rejected rules
- **Role-Based Access:** Only reviewers and admins can approve
- **Comments:** Required for rejections, optional for approvals

**Key Features:**
```
- Pending approvals count
- Quick access to rule details
- Test coverage visibility
- Comment history
- Status badges for approved/rejected
```

### 3. Audit Trail Component (`AuditTrail.tsx`)
**Location:** `/src/components/AuditTrail.tsx`

Complete history of all rule events:
- **Timeline View:** Chronological display of all actions
- **Event Types:**
  - 📝 Created
  - ✓ Tested (with coverage %)
  - 📤 Submitted for Approval
  - ✅ Approved (with reviewer comment)
  - ❌ Rejected (with reason)
  - 🚀 Activated
  - ✏️ Modified

**Display Details:**
```
- Action icon
- Timestamp
- User who performed action
- Detailed comments
- Test results (when applicable)
- Status transitions (from → to)
- Color-coded by action type
```

## Data Models

### Rule Type
```typescript
interface Rule {
  id: string
  workspaceId: string
  name: string
  description: string
  status: RuleStatus
  createdBy: string
  createdAt: string
  updatedAt: string
  testResults?: RuleTestResult
  attributes: string[]
  riskLevel: 'low' | 'medium' | 'high'
  affectedDataObjects: string[]
}
```

### Rule Approval
```typescript
interface RuleApproval {
  id: string
  ruleId: string
  requestedBy: string
  requestedAt: string
  reviewedBy?: string
  reviewedAt?: string
  status: 'pending' | 'approved' | 'rejected'
  comments?: string
  workspaceId: string
}
```

### Audit Log Entry
```typescript
interface AuditLogEntry {
  id: string
  ruleId: string
  action: AuditAction
  userId: string
  userName: string
  timestamp: string
  details: {
    previousStatus?: RuleStatus
    newStatus?: RuleStatus
    comments?: string
    testResults?: { coverage: number; passed: boolean }
    [key: string]: any
  }
  workspaceId: string
}
```

## Workflow Transitions

### Valid State Transitions
```
Draft → Testing
Testing → Tested
Tested → Pending Approval
Pending Approval → Approved (by Reviewer/Admin)
Pending Approval → Rejected (by Reviewer/Admin)
Approved → Activated (by Admin only)
Activated → Rejected (if issues found)
Rejected → Draft (for rework)
```

## Context API

### RuleContext (`RuleContext.tsx`)
Manages all rule-related state and operations:

```typescript
interface RuleContextType {
  rules: Rule[]
  approvals: RuleApproval[]
  auditLog: AuditLogEntry[]
  
  // Operations
  createRule: (rule: Omit<Rule, 'id' | 'createdAt' | 'updatedAt'>) => Promise<Rule>
  updateRuleStatus: (ruleId: string, newStatus: RuleStatus) => Promise<void>
  submitForApproval: (ruleId: string, comments?: string) => Promise<void>
  approveRule: (approvalId: string, comments?: string) => Promise<void>
  rejectRule: (approvalId: string, comments: string) => Promise<void>
  activateRule: (ruleId: string) => Promise<void>
  
  // Queries
  getRulesByWorkspace: (workspaceId: string) => Rule[]
  getApprovalsPending: () => RuleApproval[]
  getAuditTrail: (ruleId?: string) => AuditLogEntry[]
  calculateStats: (workspaceId: string) => RuleStats
}
```

### AuthContext Enhancements
Permission checking functions added:
```typescript
canCreateRule: () => boolean    // Admin, Editor
canTestRule: () => boolean      // Admin, Editor
canApproveRule: () => boolean   // Admin, Reviewer
canActivateRule: () => boolean  // Admin only
canManageUsers: () => boolean   // Admin only
```

## Navigation

Access rule management features from the sidebar:
- **Rules** - Browse and manage all rules
- **Approvals** - Review pending approvals (Reviewer/Admin only)
- **Audit Trail** - View complete action history

## Mock Data

The system includes comprehensive mock data:
- 6 rules across 2 workspaces (ws-1, ws-2)
- Various status states (draft, tested, pending-approval, approved, activated)
- Test results with coverage metrics
- Complete audit trails with historical events
- Mock approvals showing both approved and rejected rules

## Integration Points

### Current Implementation
- ✅ Role-based access control
- ✅ Workspace-aware state management
- ✅ Mock data with all lifecycle states
- ✅ Complete audit trail tracking
- ✅ Approval workflow with comments

### Future Enhancements (TODO)
- [ ] Backend API integration for rule CRUD operations
- [ ] Real database for persistent storage
- [ ] Email notifications on approval/rejection
- [ ] Rule versioning and rollback
- [ ] Advanced test result analytics
- [ ] Schedule-based rule enforcement
- [ ] Integration with actual data sources

## Usage Examples

### Create a Rule
```typescript
const { createRule } = useRules()

const newRule = await createRule({
  workspaceId: 'ws-1',
  name: 'Email Format Validation',
  description: 'Validates email addresses',
  status: 'draft',
  createdBy: 'user-2',
  attributes: ['attr-email'],
  riskLevel: 'medium',
  affectedDataObjects: ['customers'],
})
```

### Submit for Approval
```typescript
await submitForApproval(ruleId, 'Ready for review - tests passed 98%')
```

### Approve a Rule
```typescript
await approveRule(approvalId, 'Looks good, approved for activation')
```

### View Audit Trail
```typescript
const trail = getAuditTrail(ruleId) // For specific rule
const allTrail = getAuditTrail()    // For all events
```

## Testing the Workflow

### Demo Accounts
- **Admin:** admin@example.com - All permissions
- **Editor:** editor@example.com - Create and test rules
- **Reviewer:** reviewer@example.com - Approve/reject rules
- **Viewer:** viewer@example.com - View only

### Test Scenario
1. Login as Editor
2. Navigate to Rules section (click "Rules" in sidebar)
3. See all available rules
4. Click to expand a draft rule
5. Switch to Reviewer account
6. Go to Approvals section
7. Approve or reject pending rules
8. View Audit Trail to see complete history
