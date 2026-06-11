# Quick Reference: Authentication & Workspaces

## Login Interface

The login modal provides:
- Email/password form
- 4 demo account quick-login buttons
- Auto-fills email when clicking demo buttons

**Launch Login**: Click "Open Login" button (top-right when not logged in)

## Demo Accounts to Test

```
🔓 ADMIN (Full Access)
Email: admin@example.com
Workspaces: ws-1, ws-2

📝 EDITOR (Create & Edit)
Email: editor@example.com
Workspaces: ws-1

✅ REVIEWER (Approve Only)
Email: reviewer@example.com
Workspaces: ws-1, ws-2

👁️ VIEWER (Read-Only)
Email: viewer@example.com
Workspaces: ws-2
```

## What Each Role Can Do

| Action | Admin | Editor | Reviewer | Viewer |
|--------|-------|--------|----------|--------|
| View data | ✅ | ✅ | ✅ | ✅ |
| Create items | ✅ | ✅ | ❌ | ❌ |
| Edit items | ✅ | ✅ | ❌ | ❌ |
| Delete items | ✅ | ❌ | ❌ | ❌ |
| Approve/Publish | ✅ | ✅ | ✅ | ❌ |
| Manage users | ✅ | ❌ | ❌ | ❌ |
| Workspace settings | ✅ | ❌ | ❌ | ❌ |

## Menu Visibility by Role

Currently logged-in users see:

**All Authenticated Users**: Dashboard, Reports

**Editors+**: Rules

**Editors & Admins**: Templates

**Admins Only**: Settings

## How to Use in Code

### 1. Use Auth Hook
```tsx
import { useAuth } from '@/hooks/useAuth'

const { user, isAuthenticated, logout } = useAuth()
```

### 2. Check Permissions
```tsx
import { usePermission } from '@/hooks/useAuth'

const { hasPermission, hasRole } = usePermission()

if (hasPermission('create')) { /* show create button */ }
if (hasRole('admin')) { /* show admin panel */ }
```

### 3. Protect Content
```tsx
import { ProtectedRoute } from '@/components/ProtectedRoute'

<ProtectedRoute requiredRoles={['admin', 'editor']}>
  <Editor />
</ProtectedRoute>
```

### 4. Conditional Rendering
```tsx
import { IfPermitted } from '@/components/ProtectedRoute'

<IfPermitted permission="create">
  <button>Create Rule</button>
</IfPermitted>
```

## Structure

- **Users**: People with email, name, avatar
- **Roles**: Permissions level (Admin, Editor, Reviewer, Viewer)
- **Workspaces**: Separate project/environment with its own rules/templates
- **UserWorkspaceRole**: Link between user, workspace, and their role

Example: 
- John = Admin in WorkspaceA, Editor in WorkspaceB
- Jane = Viewer in WorkspaceA, Reviewer in WorkspaceC

## Files to Understand

| File | Purpose |
|------|---------|
| `src/contexts/AuthContext.tsx` | Login, logout, auth state |
| `src/hooks/useAuth.ts` | Permission checking |
| `src/types/auth.ts` | Type definitions |
| `src/components/AuthModal.tsx` | Login UI |
| `src/components/WorkspaceSelector.tsx` | Workspace switcher |
| `src/components/ProtectedRoute.tsx` | Access control |

## Customize Menu Items

Edit `Sidebar.tsx`:
```tsx
const menuItems: MenuItem[] = [
  { 
    id: 'dashboard', 
    label: 'Dashboard', 
    icon: 'app-icon-database'
    // No role requirement = all authenticated users
  },
  { 
    id: 'rules', 
    label: 'Rules', 
    icon: 'app-icon-list',
    requiredRoles: ['editor', 'reviewer', 'admin'] // Only these roles
  },
]
```

## Current App Flow

```
App (wrapped in AuthProvider)
├─ Not Authenticated
│  └─ Welcome page + Login button
│
└─ Authenticated
   ├─ Header (with user name, workspace selector, logout)
   ├─ Sidebar (showing only accessible menu items)
   └─ Main content (shows components based on selection)
```

## Practical Testing Checklist

- [ ] Login as admin → see all menu items (Dashboard, Rules, Templates, Settings)
- [ ] Switch workspace → dropdown shows available workspaces
- [ ] Logout → back to login screen
- [ ] Login as editor → Settings menu disappears
- [ ] Login as reviewer → Templates menu disappears
- [ ] Login as viewer → Rules and Templates menus disappear
- [ ] Open browser console → no permission errors

## Next Steps to Integrate Backend

1. Replace `mockUsers` in `AuthContext.tsx` with real API
2. Change `login()` to POST to `/api/auth/login`
3. Store JWT token in session storage
4. Update `switchWorkspace()` to call `/api/workspaces/:id/verify`
5. Add token refresh logic
6. Handle token expiration gracefully

See `AUTH_SYSTEM.md` for code examples.

---

**Production:** Replace mock data with real backend endpoints
**Demo:** Test with provided accounts at http://localhost:5177
