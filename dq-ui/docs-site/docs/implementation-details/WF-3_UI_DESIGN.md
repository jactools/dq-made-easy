# WF-3: Rule Versioning & Rollback - UI Layer Design

## Overview

This document specifies the user interface design for the rule versioning and rollback feature (WF-3) as a preview feature in Data Quality Made Easy.

## Feature Flag Integration

**Settings Location:**
```
Settings > Preview Features > Rule Versioning
```

**Scope:**
- Per workspace (admin can enable/disable)
- Per user (users can opt-in)
- Per rule (users enable versioning individually)

**UI Behavior:**
- Version controls hidden until enabled
- Graceful degradation for non-versioned rules
- Feature can be toggled at any time

---

## 1. Version History View

### Location
- **Primary:** Rules Detail Page → "📋 Version History" tab
- **Secondary:** Quick link in rule header
- **Accessibility:** Keyboard shortcut `V` when on rule detail

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Rule: Customer Completeness Check                    v 5/5  │
├─────────────────────────────────────────────────────────────┤
│ 📋 Details | 🧪 Tests | 📋 Version History | 📊 Audit Trail│
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Version History                                              │
│ ─────────────────────────────────                           │
│ 5 versions total • Created 47 days ago • 1 rollback        │
│                                                              │
│ 🔍 [Search by change type...] [Filters ↓]                 │
│                                                              │
│ Version 5 (CURRENT)           📌 ⚡ 🏷️                     │
│ ├─ Modified 2 hours ago                                    │
│ ├─ By: Jane Smith                                          │
│ ├─ Change: "Updated expression to include NOT EMPTY"      │
│ ├─ Fields changed: 1                                       │
│ ├─ Tags: production, approved                              │
│ ├─ Linked: 1 approval, 1 test proof                        │
│ └─ [View Details] [Compare] [Rollback]                    │
│                                                              │
│ Version 4                      🏷️                          │
│ ├─ Approved 2 days ago                                     │
│ ├─ By: John Doe                                            │
│ ├─ Change: (approval only, no field changes)              │
│ ├─ Fields changed: 0                                       │
│ ├─ Tags: staging                                           │
│ └─ [View Details] [Compare] [Rollback]                    │
│                                                              │
│ Version 3                      🔴                          │
│ ├─ Modified 3 days ago                                     │
│ ├─ By: Alice Johnson                                       │
│ ├─ Change: "Fixed null handling logic"                     │
│ ├─ Fields changed: 2                                       │
│ ├─ Tags: (none)                                            │
│ └─ [View Details] [Compare] [Rollback]                    │
│                                                              │
│ Version 2                                                   │
│ ├─ Modified 5 days ago                                     │
│ ├─ By: Alice Johnson                                       │
│ └─ [View Details] [Compare] [Rollback]                    │
│                                                              │
│ Version 1 (ORIGINAL)                                        │
│ ├─ Created 47 days ago                                     │
│ ├─ By: System                                              │
│ └─ [View Details]                                          │
│                                                              │
│ 📄 LEGEND:                                                  │
│    📌 = Current version                                     │
│    ⚡ = Marked for rollback                                │
│    🏷️ = Has tags                                           │
│    🔴 = Issues detected                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Filters & Search

Dropdown menu with preset filters:

```
[Filters ↓]
├─ By Change Type
│  ├─ Modified
│  ├─ Approved
│  ├─ Activated
│  ├─ Deactivated
│  └─ Rollback
├─ By User
│  ├─ [Select user dropdown]
├─ Date Range
│  ├─ Last 7 days
│  ├─ Last 30 days
│  ├─ Last 90 days
│  └─ Custom...
├─ By Tags
│  ├─ [Searchable tag list]
└─ [Clear All]
```

### Interactive States

**Hover on version item:**
- Background highlight
- Show full text of truncated fields
- Highlight version number

**Click version item:**
- Expand to show full details
- Display timeline position on scroll

**Mobile (< 768px):**
- Single column layout
- Buttons stack vertically
- Tag display wraps
- "..." menu for actions

---

## 2. Version Details Modal

### Trigger
Click "[View Details]" on any version

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│ Close (X)    Version 5 • Modified • 2 hours ago             │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│ METADATA                                                      │
│ ────────────────────────────────────────────────────────────│
│ Version Number:        5                                      │
│ Status:                Current (Active)                       │
│ Created:               2026-03-03 14:22:00 UTC               │
│ Created By:            Jane Smith (jane@example.com)         │
│ Change Type:           Modified                              │
│ Change Description:    Updated expression to include NOT ... │
│                                                               │
│ RULE DEFINITION (Snapshot at this version)                  │
│ ────────────────────────────────────────────────────────────│
│ Name:                  Customer Completeness Check           │
│ Description:           Validates that customer ID is not ... │
│ Expression:            customer_id IS NOT NULL AND      ...  │
│ Dimension:             Completeness                          │
│ Active:                ✓ Yes                                 │
│ Is Template:           No                                    │
│                                                               │
│ RELATIONSHIPS                                                │
│ ────────────────────────────────────────────────────────────│
│ Approvals:             1 linked                              │
│ ├─ Status: Approved                                          │
│ ├─ By: Manager Name                                          │
│ ├─ On: 2026-03-03 15:00:00                                  │
│ └─ Comment: "Looks good, approved for production"           │
│                                                               │
│ Test Proofs:           1 linked                              │
│ ├─ Date: 2026-03-03 14:30:00                                │
│ ├─ Status: Passed ✓                                          │
│ ├─ Coverage: 98.5%                                           │
│ └─ [View Test Results]                                      │
│                                                               │
│ TAGS                                                          │
│ ────────────────────────────────────────────────────────────│
│ [production]  [approved]  [+ Add Tag]                       │
│                                                               │
│ ACTIONS                                                       │
│ ────────────────────────────────────────────────────────────│
│ [Compare with Previous]  [Compare with...] [Rollback]       │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Full Expression Display

Clicking expression field opens code viewer:

```
┌────────────────────────────────────┐
│ Expression Viewer         [Copy] [X]│
├────────────────────────────────────┤
│                                    │
│ customer_id IS NOT NULL AND        │
│ customer_id != '' AND              │
│ customer_id NOT LIKE '%test%'      │
│                                    │
│ Syntax: SQL                        │
│                                    │
└────────────────────────────────────┘
```

---

## 3. Version Comparison View

### Access
- Click "[Compare]" button on any version
- Default: Compare with previous version
- Option: "Compare with..." opens version picker

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│ Version Comparison           Close (X)                        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│ From Version: 3 (2026-02-28 16:45)  →  To Version: 5 (2026) │
│                                    [Select different version] │
│                                                               │
│ CHANGES SUMMARY                                              │
│ ────────────────────────────────────────────────────────────│
│ Fields Changed: 2 fields (1 major, 1 minor)                 │
│ Time Between: 3 days, 21 hours                              │
│ Versions Between: 1 intermediate version                     │
│                                                               │
│ DETAILED CHANGES                                             │
│ ────────────────────────────────────────────────────────────│
│                                                               │
│ 1. EXPRESSION (MAJOR CHANGE)                                │
│    ─────────────────────────────────────────────────────────│
│                                                               │
│    Version 3 (Old):                                          │
│    ┌──────────────────────────────────────────────────────┐ │
│    │ customer_id IS NOT NULL                             │ │
│    └──────────────────────────────────────────────────────┘ │
│                                                               │
│    Version 5 (New):                                          │
│    ┌──────────────────────────────────────────────────────┐ │
│    │ customer_id IS NOT NULL AND customer_id != ''       │ │
│    └──────────────────────────────────────────────────────┘ │
│                                                               │
│    Difference:                                               │
│    customer_id IS NOT NULL [unchanged]                      │
│    [+ AND customer_id != '' ] [ADDED]                      │
│                                                               │
│ 2. DESCRIPTION (MINOR CHANGE)                               │
│    ─────────────────────────────────────────────────────────│
│                                                               │
│    Version 3: "Validates that customer ID is not null"      │
│    Version 5: "Validates that customer ID is not null and"  │
│               "not empty"                                    │
│                                                               │
│ [No other changes]                                           │
│                                                               │
│ IMPACT ANALYSIS                                              │
│ ────────────────────────────────────────────────────────────│
│ Test Results Impact:    ✓ Both versions tested               │
│ Approval Status:        ⚠️  Version 3 approved, V5 pending   │
│ Active Status:          No change (both active)              │
│                                                               │
│ [View Version 3 Details]  [View Version 5 Details]          │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Diff Display Options

Dropdown for different diff formats:

```
Display:  [Split View ↓]
├─ Split View (side-by-side)
├─ Inline (highlighted)
├─ Unified (unified diff)
└─ Raw JSON
```

---

## 4. Rollback Dialog

### Trigger
Click "[Rollback]" button on any version

### Step 1: Rollback Confirmation

```
┌────────────────────────────────────────────────────────────┐
│ Confirm Rollback                                     [X]    │
├────────────────────────────────────────────────────────────┤
│                                                             │
│ ⚠️  You are about to rollback this rule                    │
│                                                             │
│ ROLLBACK DETAILS                                            │
│ ────────────────────────────────────────────────────────────│
│ Current Version:       5 (active, in production)            │
│ Rollback To:           3 (stable, tested)                  │
│ New Version Created:   6 (will be created)                 │
│                                                             │
│ WHAT WILL CHANGE                                            │
│ ────────────────────────────────────────────────────────────│
│ ✓ Expression will be reverted                              │
│ ✓ Description will be reverted                             │
│                                                             │
│ IMPACT                                                      │
│ ────────────────────────────────────────────────────────────│
│ ⚠️  Active: The rule is currently ACTIVE in production     │
│ ⚠️  Approval: Version 3 was previously approved            │
│     ℹ️  New version 6 will require re-approval             │
│ ✓  Tests: Version 3 has test results (98.5% pass rate)    │
│                                                             │
│ REASON (recommended)                                        │
│ ────────────────────────────────────────────────────────────│
│ [Text area]                                                 │
│ "Version 5 had unintended side effects in production.      │
│  Rolling back to stable version 3."                        │
│                                                             │
│ ADDITIONAL OPTIONS                                          │
│ ────────────────────────────────────────────────────────────│
│ ☐ Add tags to new version (e.g., "rollback", "stability") │
│ ☐ Request immediate re-approval                           │
│ ☐ Schedule activation for specific time                    │
│                                                             │
│ [Cancel]  [Preview Changes]  [Execute Rollback]            │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Step 2: Processing

After clicking "Execute Rollback":

```
┌────────────────────────────────────────────────────────────┐
│ Processing Rollback...                           [Cancel]   │
├────────────────────────────────────────────────────────────┤
│                                                             │
│ ⏳ Creating version 6 from version 3...                    │
│ ✓ Recording rollback operation...                          │
│ ✓ Updating approval status...                              │
│ ⏳ Creating audit trail entry...                           │
│ ⏳ Notifying rule owner...                                 │
│                                                             │
│ Estimated time: 2-3 seconds                                │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Step 3: Success

```
┌────────────────────────────────────────────────────────────┐
│ ✓ Rollback Successful                              [X]     │
├────────────────────────────────────────────────────────────┤
│                                                             │
│ Rule has been rolled back to version 3                     │
│                                                             │
│ DETAILS                                                    │
│ ─────────────────────────────────────────────────────────  │
│ Original Version:      5                                    │
│ Rolled Back To:        3                                    │
│ New Version Created:   6                                    │
│ Rollback ID:           rb-0a1b2c3d                         │
│ Completed At:          2026-03-04 10:30:15 UTC            │
│ Rolled Back By:        Jane Smith                          │
│                                                             │
│ NEXT STEPS                                                  │
│ ─────────────────────────────────────────────────────────  │
│ ⚠️  New version 6 requires approval before activation      │
│                                                             │
│ [View Version 6] [Go to Rule] [Close]                     │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Step 3: Error

```
┌────────────────────────────────────────────────────────────┐
│ ❌ Rollback Failed                                  [X]     │
├────────────────────────────────────────────────────────────┤
│                                                             │
│ Error: Rule is currently locked for editing                │
│                                                             │
│ DETAILS                                                    │
│ ─────────────────────────────────────────────────────────  │
│ Another user is currently editing this rule.               │
│ Please try again in a few moments.                         │
│                                                             │
│ [Retry] [Close]                                            │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

## 5. Rollback History

### Location
Rules Detail Page → "🔄 Rollback History" subtab in Version History

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Rollback History (2 rollbacks)                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Rollback #1 (Most Recent)                                  │
│ ├─ From Version 5 → To Version 3 (New Version: 6)         │
│ ├─ Rolled back: 2026-03-04 10:30:00 by Jane Smith         │
│ ├─ Reason: "Version 5 had unintended side effects in      │
│ │           production. Rolling back to stable version 3."  │
│ ├─ Status: ✓ Completed                                     │
│ └─ [View Details] [View Version 6] [Timeline]             │
│                                                              │
│ Rollback #2 (Initial Rollback)                             │
│ ├─ From Version 2 → To Version 1 (New Version: 3)         │
│ ├─ Rolled back: 2026-02-15 14:22:00 by Alice Johnson     │
│ ├─ Reason: "Initial rollback during testing phase"        │
│ ├─ Status: ✓ Completed                                     │
│ └─ [View Details] [View Version 3] [Timeline]             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Inline Version Controls

### Location
Rule detail header (when versioning enabled)

### Layout

```
┌──────────────────────────────────────────────────────────┐
│ Customer Completeness Check                              │
│                                                           │
│ Status: ⚫ Active  |  Version: 5 of 5  |  ⏰ 2 hours ago │
│                                                           │
│ [Previous ▲] [Version Selector ▼] [Next ▼]  [History]  │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

**Version Selector Dropdown:**
```
[Version Selector ▼]
├─ Version 5 (CURRENT) ✓
├─ Version 4
├─ Version 3
├─ Version 2
└─ Version 1 (ORIGINAL)

[Browse all versions]
```

**Behavior:**
- Quick switching between versions for comparison
- Read-only display of non-current versions
- Click "Browse all versions" opens full history

---

## 7. Version Info Tooltip

Shows when hovering over version number

```
╔────────────────────────────────╗
║ Version 5                      ║
║ ────────────────────────────   ║
║ Modified 2 hours ago           ║
║ By: Jane Smith                 ║
║                                ║
║ Changes:                       ║
║ • Expression (major)           ║
║ • Description (minor)          ║
║                                ║
║ Status: Active                 ║
║ Tags: production, approved     ║
║                                ║
║ [View Full Details]            ║
╚────────────────────────────────╝
```

---

## 8. Rules List Integration

### Version Badge
In rules list, show version indicator:

```
┌────────────────────────────────────────────────────────────┐
│ Rules List                                                  │
├────────────────────────────────────────────────────────────┤
│                                                              │
│ ☐ Customer Completeness Check        v5  📋  ⏰ 2h ago   │
│ ☐ Product Name Validation             v2  📋  ⏰ 5d ago   │
│ ☐ Order Amount Range Check            -   -   ⏰ 30d ago  │
│                                                              │
│ Legend:                                                     │
│ v# = Version number (clickable to history)                │
│ 📋 = Versioning enabled                                    │
│ - = Versioning not enabled                                │
│                                                              │
└────────────────────────────────────────────────────────────┘
```

---

## 9. Timeline Visualization

### Location
Version History → Timeline view

```
┌─────────────────────────────────────────────────────────┐
│ Timeline View                                      [List]│
├─────────────────────────────────────────────────────────┤
│                                                          │
│  47 days ago                                Today       │
│  │                                              │       │
│  ●─────●─────●──────●─────●──────●────────────●       │
│  v1    v2    v3    v4    v5 (current)               │
│ (orig)(mod) (mod) (app)  (mod)                      │
│                    ↑                                   │
│              Rollback from                            │
│                    │                                   │
│                 v1← v2 (rb-001)                       │
│                                                          │
│ Click any version on timeline for quick details        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 10. Version Enable/Disable Dialog

### Location
Rules Detail → Settings → Enable Versioning

### Dialog

```
┌────────────────────────────────────────────────────────┐
│ Enable Rule Versioning                             [X] │
├────────────────────────────────────────────────────────┤
│                                                         │
│ ℹ️  Enable version tracking for this rule              │
│                                                         │
│ BENEFITS                                               │
│ ─────────────────────────────────────────────────────── │
│ ✓ Track all changes to rule definition                │
│ ✓ Compare versions to see what changed                │
│ ✓ Rollback to any previous version                    │
│ ✓ Full audit trail of who changed what when          │
│                                                         │
│ STORAGE & PERFORMANCE                                  │
│ ─────────────────────────────────────────────────────── │
│ • Each version: ~500 bytes                            │
│ • 10 versions: ~5KB (negligible impact)              │
│ • No impact on rule execution performance            │
│                                                         │
│ NOTE: This will create version 1 (snapshot of current) │
│                                                         │
│ [Cancel]  [Enable Versioning]                         │
│                                                         │
└────────────────────────────────────────────────────────┘
```

---

## 11. Mobile Responsive Design

### Breakpoints

```
Mobile (< 576px):
• Single column layout
• Bottom sheet for modals
• Condensed details
• Stack buttons vertically

Tablet (576px - 992px):
• 2 column layouts where appropriate
• Side drawer for navigation
• Horizontal button layout

Desktop (> 992px):
• Full layout as designed
• Modals centered
• All controls visible
```

### Mobile Version History

```
┌─────────────────────┐
│ Version History  [v]│
├─────────────────────┤
│ 5 versions total    │
│ [Filter ⚙️]         │
│                     │
│ Version 5 (Current) │
│ ├─ Modified 2h ago │
│ ├─ By: Jane Smith  │
│ ├─ 1 field changed │
│ └─ [⋮]             │
│                     │
│ Version 4           │
│ ├─ Approved 2d ago │
│ ├─ By: John Doe    │
│ └─ [⋮]             │
│                     │
│ Version 3           │
│ ├─ Modified 3d ago │
│ └─ [⋮]             │
│                     │
│ [Load More]         │
│                     │
└─────────────────────┘
```

---

## 12. Accessibility Features

### Keyboard Navigation
- `Tab` - Navigate between elements
- `Enter` - Activate buttons/links
- `Escape` - Close modals/dropdowns
- `↑/↓` - Navigate version list (when focused)
- `V` - Open version history from rule detail
- `C` - Compare versions (when in history)
- `R` - Rollback (when in history)

### Screen Reader Support
- ARIA labels for all buttons
- Region landmarks for main content areas
- Alt text for status icons
- Descriptive link text (not "Click here")
- Form input labels and descriptions

### Visual Accessibility
- Minimum 4.5:1 contrast ratio for text
- Color not sole indicator (icons + text)
- Clear focus indicators on interactive elements
- Font size: 14-16px minimum for body text
- Line height: 1.5 minimum for readability

### Motor Accessibility
- Minimum 44x44px touch targets (mobile)
- Keyboard accessible all functionality
- No time-based interactions (adjustable timeouts)
- Support for sticky keys/voice control

---

## 13. State Management

### Local State
```typescript
// Version History View
{
  versions: Version[],
  selectedVersion: string | null,
  filters: {
    changeType: string | null,
    createdBy: string | null,
    dateRange: DateRange | null,
    tags: string[],
  },
  pagination: {
    limit: 20,
    offset: 0,
    total: number,
  },
  loading: boolean,
  error: Error | null,
}

// Version Comparison
{
  version1: Version,
  version2: Version,
  diffs: VersionDiff[],
  loading: boolean,
  mode: 'split' | 'inline' | 'unified',
}

// Rollback Dialog
{
  isOpen: boolean,
  targetVersion: string,
  reason: string,
  tags: string[],
  isProcessing: boolean,
  error: Error | null,
}
```

### Global State (Redux/Zustand)
```
rules/
├── currentRule: Rule
├── versions: Version[]
├── versioning: {
│   enabled: boolean,
│   isLoading: boolean,
│   error?: string,
│   lastUpdated: timestamp,
├── rollbacks: Rollback[]
└── featureFlags: {
    versioningEnabled: boolean,
    userOptedIn: boolean,
  }
```

---

## 14. Error States & Recovery

### Network Error

```
┌──────────────────────────────────┐
│ ⚠️  Unable to Load Versions       │
├──────────────────────────────────┤
│                                   │
│ There was an error loading the    │
│ version history.                  │
│                                   │
│ Error: Network timeout            │
│                                   │
│ [Retry]  [Cancel]                │
│                                   │
└──────────────────────────────────┘
```

### Validation Error

```
┌──────────────────────────────────┐
│ ⚠️  Cannot Rollback               │
├──────────────────────────────────┤
│                                   │
│ Version 3 is no longer valid     │
│ (it has been deleted)             │
│                                   │
│ [Choose Different Version]        │
│ [Cancel]                          │
│                                   │
└──────────────────────────────────┘
```

### Permission Error

```
┌──────────────────────────────────┐
│ 🔒 Insufficient Permissions       │
├──────────────────────────────────┤
│                                   │
│ Only reviewers and admins can    │
│ perform rollbacks in this        │
│ workspace.                        │
│                                   │
│ Contact your workspace admin.    │
│                                   │
│ [Close]                           │
│                                   │
└──────────────────────────────────┘
```

---

## 15. Loading States

### Skeleton Loaders

```
Version History (Loading)
┌─────────────────────────────────┐
│ ▓▓▓▓▓ (Shimmer)                │
│ ▓▓▓▓▓ ▓▓▓ ▓▓▓                   │
│ ▓▓▓ ▓▓▓ ▓▓▓                     │
│                                 │
│ ▓▓▓▓▓ (Shimmer)                │
│ ▓▓▓▓▓ ▓▓▓ ▓▓▓                   │
│ ▓▓▓ ▓▓▓ ▓▓▓                     │
│                                 │
│ ▓▓▓▓▓ (Shimmer)                │
│ ▓▓▓▓▓ ▓▓▓ ▓▓▓                   │
│ ▓▓▓ ▓▓▓ ▓▓▓                     │
│                                 │
└─────────────────────────────────┘
```

---

## 16. Empty States

### No Versions (Before Enable)

```
┌─────────────────────────────────┐
│ 📋 No Version History            │
├─────────────────────────────────┤
│                                 │
│ Versioning is not enabled for   │
│ this rule.                       │
│                                 │
│ Enable versioning to start      │
│ tracking changes.               │
│                                 │
│ [Enable Versioning]             │
│                                 │
└─────────────────────────────────┘
```

### No Rollbacks

```
┌─────────────────────────────────┐
│ 🔄 No Rollback History          │
├─────────────────────────────────┤
│                                 │
│ This rule has never been        │
│ rolled back.                    │
│                                 │
└─────────────────────────────────┘
```

---

## 17. Notifications & Toast Messages

### Success Messages

```
✓ Version created successfully
✓ Rollback completed
✓ Tags updated successfully
✓ Version marked for rollback
```

### Info Messages

```
ℹ️  Rollback requires approval
ℹ️  New version created: v6
ℹ️  Version 3 has been tested
```

### Warning Messages

```
⚠️  This version is marked for rollback
⚠️  Rule is active in production
⚠️  Approval status may have changed
```

### Error Messages

```
❌ Unable to create version
❌ Rollback failed: Rule is locked
❌ Network error, please retry
```

---

## 18. Dark Mode Support

All UI components adapt to dark theme:

```
Light Mode:
- Background: #FFFFFF
- Text: #1F2937
- Border: #E5E7EB
- Accent: #3B82F6

Dark Mode:
- Background: #1F2937
- Text: #F3F4F6
- Border: #374151
- Accent: #60A5FA
```

---

## 19. Component Library Integration

### App-Owned Components Used

- `app-button` - All action buttons
- `app-dialog` - Modal dialogs
- `app-tabs` - Tab navigation
- `app-input` - Text input fields

### Custom Components

- `VersionHistory` - Main history view
- `VersionDetails` - Single version details
- `VersionComparison` - Diff viewer
- `RollbackDialog` - Rollback flow
- `TimelineView` - Visual timeline
- `VersionFilters` - Filter controls

---

## 20. Testing Considerations

### Integration Tests

```typescript
test('displays version history for rule with versioning enabled')
test('navigates to version details when clicking version')
test('compares two versions correctly')
test('executes rollback and creates new version')
test('filters versions by change type')
test('shows error when versioning is disabled')
test('handles pagination correctly')
```

### E2E Tests

```
Scenario: User rolls back a rule
1. Navigate to rule detail
2. Open Version History tab
3. Click Rollback on version 3
4. Fill in reason
5. Execute rollback
6. Verify version 6 created
7. Verify approval status changed
```

### Accessibility Tests

```
- Keyboard navigation works
- Screen reader announces all content
- Contrast ratios meet WCAG AA
- Focus indicators visible
- Form labels present
```

---

## 21. Performance Considerations

### Lazy Loading
- Load versions on-demand (pagination)
- Load comparison diffs only when needed
- Debounce filter changes (300ms)

### Caching
- Cache version list (5 minute TTL)
- Cache version details (10 minute TTL)
- Invalidate on update/rollback

### Optimization
- Virtual scrolling for large lists
- Code splitting for modals
- Image lazy loading (if applicable)

---

## 22. Future Enhancements

- **Version Branching:** Create alternate version tracks
- **Merge Versions:** Combine changes from multiple versions
- **Comments:** Add comments to versions
- **Annotations:** Attach metadata to versions
- **Scheduled Rollback:** Schedule rollback for specific time
- **Automated Snapshots:** Auto-create versions on conditions
- **Version Templates:** Some versions as templates
