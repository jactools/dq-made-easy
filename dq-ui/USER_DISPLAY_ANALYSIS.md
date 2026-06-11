# DQ-UI User Display & Storage Analysis

## 1. User Type Definitions

### Core User Interface (src/types/auth.ts)
```typescript
export interface User {
  id: string                           // Unique user identifier
  email: string                        // Email address
  name: string                         // Display name
  avatarUrl?: string                   // Profile picture URL
  workspaceRoles: UserWorkspaceRole[]  // User's role(s) per workspace
  createdAt: Date                      // Account creation date
  isActive: boolean                    // Account status
}

export interface UserWorkspaceRole {
  workspaceId: string
  role: UserRole  // admin | data-steward | analyst | viewer
  joinedAt: Date
}
```

### User Settings (src/types/settings.ts)
```typescript
export interface UserSettings {
  userId: string
  email: string
  firstName: string
  lastName: string
  phone?: string
  avatarUrl?: string
  language: 'en' | 'nl' | 'de' | 'fr'
  timezone: string
  updatedAt: string
}

export interface AdminUserSummary {
  id: string
  name?: string
  email?: string
}
```

## 2. RuleApproval & Notification User Fields

### RuleApproval (src/types/rules.ts)
**How user info is stored in approvals:**
```typescript
export interface RuleApproval {
  id: string
  ruleId: string
  requestedBy: string          // ⚠️  Stores user name or ID (currently strings)
  requestedAt: string
  reviewedBy?: string          // ⚠️  Optional reviewer name/ID
  reviewedAt?: string
  status: 'pending' | 'approved' | 'rejected'
  requestType?: 'activation' | 'deactivation'
  comments?: string
  commentThread?: ApprovalComment[]
  history?: ApprovalHistoryEvent[]
  emailNotifications?: EmailNotification[]
  teamsNotifications?: TeamsNotification[]
  delegation?: ApprovalDelegation
  workspaceId: string
}
```

### Comment Threads with User Info
```typescript
export interface ApprovalComment {
  id: string
  authorId: string             // ✅ User ID
  authorName: string           // ✅ User display name
  content: string
  type: 'note' | 'concern' | 'question' | 'general'
  createdAt: string
  edited?: boolean
  editedAt?: string
}
```

### Approval History Events with User Info
```typescript
export interface ApprovalHistoryEvent {
  id: string
  eventType: 'requested' | 'commented' | 'approved' | 'rejected' | 'escalated'
  userId: string               // ✅ User ID
  userName: string             // ✅ User display name
  timestamp: string
  details?: {
    comment?: string
    reason?: string
    previousStatus?: string
    escalationReason?: string
  }
}
```

### Email Notifications with User Info
```typescript
export interface EmailNotification {
  id: string
  recipientId: string          // ✅ User ID
  recipientEmail: string       // ✅ Email
  recipientName: string        // ✅ User display name
  eventType: 'submitted' | 'commented' | 'approved' | 'rejected' | 'escalated'
  subject: string
  sentAt: string
  status: 'sent' | 'failed' | 'pending'
}
```

### Teams Notifications with User Info
```typescript
export interface TeamsNotification {
  id: string
  recipientId: string          // ✅ User ID
  recipientName: string        // ✅ User display name
  teamsChannelId: string
  teamsChannelName: string
  eventType: 'submitted' | 'commented' | 'approved' | 'rejected' | 'escalated'
  message: string
  sentAt: string
  status: 'sent' | 'failed' | 'pending'
}
```

### Audit Log Entries with User Info
```typescript
export interface AuditLogEntry {
  id: string
  ruleId: string
  action: AuditAction  // created | tested | submitted-for-approval | approved | rejected | activated | deactivated | modified
  userId: string       // ✅ User ID
  userName: string     // ✅ User display name
  timestamp: string
  // ... details
}
```

## 3. How User Info is Accessed in Components

### Authentication Context (src/contexts/AuthContext.tsx)
**Primary user data source:**
```typescript
// From useAuth() hook
const auth = useAuth()

// Access current user:
auth.user?.id
auth.user?.email
auth.user?.name          // Most common for display
auth.user?.avatarUrl
auth.user?.workspaceRoles

// Current workspace info:
auth.currentWorkspaceId
auth.user?.workspaceRoles.find(wr => wr.workspaceId === auth.currentWorkspaceId)?.role
```

**User stored in localStorage** as:
```javascript
localStorage.getItem('authState')  // Full auth state with user object
localStorage.getItem('authToken')  // JWT token for API calls
```

### Current User Retrieval in RuleContext
```typescript
const getCurrentReviewer = useCallback((): string => {
  try {
    const saved = localStorage.getItem('authState')
    if (saved) {
      const parsed = JSON.parse(saved)
      const user = parsed?.user
      if (typeof user?.name === 'string' && user.name.trim()) return user.name
      if (typeof user?.email === 'string' && user.email.trim()) return user.email
      if (typeof user?.id === 'string' && user.id.trim()) return user.id
    }
  } catch {
    // Ignore
  }
}, [])
```
**Priority order**: name > email > id

## 4. Component Display Patterns

### Approvals Component (src/components/Approvals.tsx)

**Displaying Approval Requester:**
```typescript
<span className="approval-requester">
  Requested by {approval.requestedBy || 'Unknown user'}
</span>
```

**Displaying Approval Reviewer:**
```typescript
<span>Reviewed by: {approval.reviewedBy || 'N/A'}</span>
```

**Comment Author Display:**
```typescript
<span className="comment-author">{comment.authorName}</span>
```

**History Event User:**
```typescript
<span className="event-user">{event.userName}</span>
```

**⚠️  Issue - Missing User Properties in Auth:**
```typescript
// Currently referenced but AUTH CONTEXT DOESN'T PROVIDE:
authorId: auth.userId || 'user-3'        // ⚠️  Falls back
authorName: auth.userName || 'Reviewer'  // ⚠️  Falls back

// Should be:
authorId: auth.user?.id || 'user-3'
authorName: auth.user?.name || 'Reviewer'
```

### AuditTrail Component (src/components/AuditTrail.tsx)

**Displaying audit entry user:**
```typescript
const getDetailsSummary = (entry: AuditLogEntry): string => {
  // ...
  if (entry.action === 'approved' || entry.action === 'rejected') {
    return `By ${entry.userName}`
  }
  // ...
}

// In JSX:
<span className="user-info">By {entry.userName}</span>
```

### Header Component (src/components/Header.tsx)

**Current user display:**
```typescript
const getCurrentWorkspaceName = () => {
  if (!auth.user || !auth.currentWorkspaceId) return ''
  const workspace = auth.user.workspaceRoles.find(
    wr => wr.workspaceId === auth.currentWorkspaceId
  )
  const workspaceId = String(workspace?.workspaceId ?? '').trim()
  return workspaceId ? `Workspace ${workspaceId.replace(/^ws-/, '').toUpperCase()}` : ''
}

// Is admin check:
const isAdminUser = Boolean(
  auth.user?.workspaceRoles?.some((workspaceRole) => workspaceRole.role === 'admin')
)
```

### Welcome Component

**Simple greeting:**
```typescript
<Welcome userName={auth.user?.name || 'Guest'} />

// In component:
<h2>Welcome back, {userName}! 👋</h2>
```

### NotificationCenter Component (src/components/NotificationCenter.tsx)

**Notification message with approval requester:**
```typescript
title: approval.requestType === 'deactivation' 
  ? 'Deactivation Awaiting Approval' 
  : 'Rule Awaiting Approval',
message: `${approval.requestedBy || 'Unknown user'} requested ${approval.requestType === 'deactivation' ? 'deactivation' : 'approval'} review`
```

### RuleVersioning Component

**Tracking who changed a rule:**
```typescript
changedBy: entry.userId  // Uses userId from audit entry
```

## 5. User Lookup & Resolution Logic

### Admin Users Lookup (SettingsContext.tsx)

**Fetching admin users:**
```typescript
const loadAdminUsers = useCallback(async (): Promise<void> => {
  try {
    const token = getAuthToken()
    const response = await fetch(`${apiBase}/users`, {
      headers: {
        ...(token && { 'Authorization': `Bearer ${token}` }),
      },
    })
    if (!response.ok) {
      throw new Error('Failed to fetch users')
    }
    const data = await response.json()
    const items = Array.isArray(data?.data) ? data.data : (Array.isArray(data) ? data : [])
    const users = Array.isArray(items)
      ? items.map((u: any) => ({
          id: String(u.id),
          name: u.name ? String(u.name) : undefined,
          email: u.email ? String(u.email) : undefined,
        }))
      : []
    setAdminUsers(users)
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Failed to load users')
  }
}, [apiBase])
```

**Storage:**
```typescript
const [adminUsers, setAdminUsers] = useState<AdminUserSummary[]>([])
```

### Backend User Mapping in AuthContext

```typescript
const mapBackendUserToUser = useCallback((backendUser: any): User => {
  // ... role mapping ...
  
  return {
    id: backendUser.id,
    email: backendUser.email,
    name: backendUser.name || backendUser.email,  // Falls back to email
    avatarUrl: `https://i.pravatar.cc/150?email=${encodeURIComponent(backendUser.email)}`,
    workspaceRoles: [...],
    createdAt: new Date(backendUser.created_at || Date.now()),
    isActive: backendUser.is_active !== false,
  }
}, [mapRoleIdsToPrimaryRole])
```

## 6. Display Name Pattern Priority

When displaying user names throughout the app, the priority order is:

1. **ApprovalComment.authorName** - Explicitly stored with comment
2. **ApprovalHistoryEvent.userName** - Explicitly stored with event
3. **AuditLogEntry.userName** - Explicitly stored with audit entry
4. **auth.user.name** - Current authenticated user's name
5. **auth.user.email** - If name not available
6. **requestedBy / reviewedBy** - Direct approval fields (currently strings)
7. **"Unknown user" / "N/A" / "Reviewer"** - Default fallbacks

## 7. Current Limitations & Issues

### Issue 1: ⚠️ Missing auth.userId and auth.userName Properties
**Location**: Approvals.tsx lines 205-206
```typescript
authorId: auth.userId || 'user-3'        // UNDEFINED
authorName: auth.userName || 'Reviewer'  // UNDEFINED
```
**Should access**: `auth.user.id` and `auth.user.name`

### Issue 2: No User Lookup Service
- Approval fields store user **names** not IDs
- No reverse lookup (ID → display name) for approvals
- Admin users API available but not used for display resolution

### Issue 3: Name Parsing Not Used
**In SettingsContext:**
```typescript
const parseName = (name?: string) => {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean)
  return {
    firstName: parts[0] || '',
    lastName: parts.slice(1).join(' '),
  }
}
```
This function exists but is not actively used for splitting display names.

### Issue 4: Avatar Generation
```typescript
avatarUrl: `https://i.pravatar.cc/150?email=${encodeURIComponent(backendUser.email)}`
```
- Uses external service (pravatar.cc)
- Not displayed in approval/audit contexts
- Only available on User object, not propagated to approvals

### Issue 5: Inconsistent User ID Storage
- `ApprovalComment.authorId` - Stores user ID
- `ApprovalHistoryEvent.userId` - Stores user ID
- `RuleApproval.requestedBy / reviewedBy` - Stores names/IDs (string, type ambiguous)
- `AuditLogEntry.userId` - Stores user ID

## 8. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Authentication Flow                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Backend: POST /login  →  Response: { token, user: {...} }  │
│                             ↓                                │
│                     LocalStorage {                           │
│                       authToken,                             │
│                       authState: {                           │
│                         user: { id, name, email, ... },      │
│                         currentWorkspaceId                   │
│                       }                                      │
│                     }                                        │
│                             ↓                                │
│                    useAuth() → auth.user                     │
│                             ↓                                │
│            Components (Header, Welcome, etc.)                │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 Approval User Info Flow                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  API: POST /rules/{id}/submit-approval                       │
│    Body: {                                                   │
│      comments: "...",                                        │
│      requestedBy: auth.user.name                             │
│    }                                                         │
│                             ↓                                │
│  Backend stores → RuleApproval {                             │
│    requestedBy: string | name                                │
│    reviewedBy: string | name | null                          │
│    commentThread: [{                                         │
│      authorId: userId,                                       │
│      authorName: displayName,                                │
│      ...                                                     │
│    }],                                                       │
│    history: [{                                               │
│      userId: userId,                                         │
│      userName: displayName,                                  │
│      ...                                                     │
│    }]                                                        │
│  }                                                           │
│                             ↓                                │
│  Frontend displays:                                          │
│    - {approval.requestedBy}  ← Direct display               │
│    - {comment.authorName}    ← From thread                  │
│    - {event.userName}        ← From history                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  Audit Log User Info Flow                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Backend: audit_log_entries {                                │
│    userId: userId,                                           │
│    userName: displayName,  ← Resolved on backend             │
│    action: 'approved' | 'rejected' | ...,                    │
│    ...                                                       │
│  }                                                           │
│                             ↓                                │
│  Frontend (AuditTrail):                                      │
│    "By {entry.userName}"                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 9. Recommendations for Improvement

1. **Fix auth.userId and auth.userName** - Add computed properties or document that they should use auth.user.id/name

2. **Implement User Lookup Service** - Create hook to resolve user IDs to display names:
   ```typescript
   const useUserDisplay = (userId?: string) => {
     // Lookup user from cache or API
     return { name, email, avatar }
   }
   ```

3. **Standardize User ID Storage** - All user references should store IDs, not names (for data integrity)

4. **Add Avatar Display** - Show user avatars in approval threads and audit entries using User.avatarUrl

5. **Cache User List** - Cache admin users from `/users` endpoint for local resolution

6. **Name Parsing** - Use the existing `parseName()` utility to separate first/last names for better display options

7. **User Search/Filter** - Leverage AdminUserSummary[] for filtering approvals by user

8. **Notification User Display** - Update notifications to include avatar and better user context
