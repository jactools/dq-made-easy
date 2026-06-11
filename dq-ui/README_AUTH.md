# 🔐 Authentication & Workspace System - Complete Implementation

## 📖 Start Here

This document is your entry point to the complete authentication and role-based access control system.

### **Reading Order**

1. 📋 **This file** - Overview and navigation
2. 🚀 **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - How to test and deploy
3. ⚡ **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Quick usage examples (5 min read)
4. 📚 **[AUTH_SYSTEM.md](AUTH_SYSTEM.md)** - Comprehensive documentation
5. 📁 **[FILE_MANIFEST.md](FILE_MANIFEST.md)** - Complete file reference
6. 📝 **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - What was built

---

## 🎯 What Was Built

A complete user authentication and role-based access control system with:

✅ **User Authentication**
- Login/logout with demo accounts
- Persistent session (localStorage)
- Auto-login on page refresh

✅ **Role-Based Access Control (RBAC)**
- 4 roles: Admin, Editor, Reviewer, Viewer
- Role-specific permissions (view, create, edit, delete, approve, manage)
- Menu items automatically show/hide based on role

✅ **Workspace Support**
- Users can belong to multiple workspaces
- Different roles in different workspaces
- Workspace switcher in header

✅ **Protected Components**
- ProtectedRoute wrapper for access control
- IfPermitted component for conditional rendering
- useAuth and usePermission hooks

✅ **Professional UI**
- Login modal with demo accounts
- Workspace selector dropdown
- User avatar and name in header
- Logout button

---

## 🚀 Quick Start (5 minutes)

```bash
# 1. Navigate to project
cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-ui

# 2. Start the HTTPS-aware local dev server
./scripts/start_local.sh

# 3. Open browser
# https://dq-made-easy.jac.dot:5174

# 4. The certs are loaded from ../tmp/certs/

# 5. Click "Open Login"

# 6. Try demo account:
# admin@example.com (any password)
```

That's it! You're logged in with admin access.

---

## 📊 System Architecture

```
User (email, name, avatar)
    ↓
    ├─ Workspace A (admin role)
    ├─ Workspace B (editor role)
    └─ Workspace C (viewer role)

Admin Role:
  ├─ view, create, edit, delete
  ├─ approve, publish
  ├─ manage_users, manage_workspace
  └─ All menu items visible

Editor Role:
  ├─ view, create, edit
  ├─ approve
  └─ Dashboard, Rules, Templates, Reports

Reviewer Role:
  ├─ view
  ├─ approve
  └─ Dashboard, Rules, Reports

Viewer Role:
  ├─ view only
  └─ Dashboard, Reports
```

---

## 🎮 Demo Accounts

| Account | Password | Role | Workspaces | Menu Items |
|---------|----------|------|-----------|-----------|
| `admin@example.com` | any | Admin | ws-1, ws-2 | All (5) |
| `editor@example.com` | any | Editor | ws-1 | Dashboard, Rules, Templates, Reports |
| `reviewer@example.com` | any | Reviewer | ws-1, ws-2 | Dashboard, Rules, Reports |
| `viewer@example.com` | any | Viewer | ws-2 | Dashboard, Reports |

---

## 💻 Usage Examples

### Check if user is logged in
```tsx
import { useAuth } from '@/hooks/useAuth'

function MyComponent() {
  const { isAuthenticated, user } = useAuth()
  
  if (!isAuthenticated) return <p>Please login</p>
  
  return <h1>Welcome {user.name}</h1>
}
```

### Check permissions
```tsx
import { usePermission } from '@/hooks/useAuth'

function MyComponent() {
  const { hasPermission, hasRole } = usePermission()
  
  if (hasPermission('create')) {
    return <button>Create</button>
  }
  
  if (hasRole('admin')) {
    return <AdminPanel />
  }
}
```

### Protect a component
```tsx
import { ProtectedRoute } from '@/components/ProtectedRoute'

function App() {
  return (
    <ProtectedRoute requiredRoles={['admin', 'editor']}>
      <Editor />
    </ProtectedRoute>
  )
}
```

---

## 📁 File Structure

```
src/
├── contexts/
│   └── AuthContext.tsx          ← Auth state & login logic
├── hooks/
│   └── useAuth.ts               ← Authentication & permission hooks
├── components/
│   ├── AuthModal.tsx            ← Login form modal
│   ├── AuthModal.css            ← Login styles
│   ├── Header.tsx               ← Updated with user info
│   ├── Sidebar.tsx              ← Role-based menu
│   ├── WorkspaceSelector.tsx    ← Workspace switcher
│   └── ProtectedRoute.tsx       ← Access control
├── types/
│   └── auth.ts                  ← TypeScript types
└── App.tsx                      ← Wrapped with AuthProvider

Documentation/
├── DEPLOYMENT_GUIDE.md          ← Testing & deployment
├── QUICK_REFERENCE.md           ← Quick examples
├── AUTH_SYSTEM.md               ← Full documentation
├── FILE_MANIFEST.md             ← File reference
└── IMPLEMENTATION_SUMMARY.md    ← What was built
```

---

## 🔑 Key Hooks

### `useAuth()`
```tsx
const {
  user,                    // Current user object
  isAuthenticated,         // Boolean
  currentWorkspaceId,      // Current workspace
  isLoading,              // Loading state
  error,                  // Error message
  login,                  // (email, password) => Promise
  logout,                 // () => void
  switchWorkspace,        // (workspaceId) => void
  getCurrentUserRole,     // () => UserRole | null
  clearError,            // () => void
} = useAuth()
```

### `usePermission()`
```tsx
const {
  hasPermission,   // (action) => boolean
  hasRole,         // (role | roles) => boolean
  hasAnyRole,      // (roles) => boolean
  hasAllRoles,     // (roles) => boolean
  userRole,        // Current role or null
} = usePermission()
```

---

## 🔐 Permission Matrix

| Permission | Admin | Editor | Reviewer | Viewer |
|-----------|-------|--------|----------|--------|
| view | ✅ | ✅ | ✅ | ✅ |
| create | ✅ | ✅ | ❌ | ❌ |
| edit | ✅ | ✅ | ❌ | ❌ |
| delete | ✅ | ❌ | ❌ | ❌ |
| approve | ✅ | ✅ | ✅ | ❌ |
| manage_users | ✅ | ❌ | ❌ | ❌ |
| manage_workspace | ✅ | ❌ | ❌ | ❌ |

---

## 🧪 Testing Checklist

- [ ] Click "Open Login" button
- [ ] Select demo account from quick-login
- [ ] See user name in header
- [ ] See workspace selector with role
- [ ] Sidebar shows correct menu items
- [ ] Menu items hide/show based on role
- [ ] Switch workspace in dropdown
- [ ] Click Logout button
- [ ] Back to login screen
- [ ] Log in again → auth persisted
- [ ] No TypeScript errors: `npx tsc --noEmit`

---

## 🔄 Backend Integration

### 1. Replace Mock Users
Edit `src/contexts/AuthContext.tsx`:
```tsx
const login = useCallback(async (email: string, password: string) => {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  const user = await response.json()
  // Handle response...
}, [])
```

### 2. Add Token Management
```tsx
const token = localStorage.getItem('authToken')
// Use in all API calls
```

### 3. Handle Expiration
```tsx
if (response.status === 401) {
  // Token expired, refresh or logout
  auth.logout()
}
```

See `AUTH_SYSTEM.md` for complete examples.

---

## ⚠️ Before Production

- [ ] Replace mock user data with API
- [ ] Implement JWT or OAuth2
- [ ] Add CSRF protection
- [ ] Use secure HTTP-only cookies
- [ ] Enable HTTPS
- [ ] Add token refresh logic
- [ ] Validate permissions on backend
- [ ] Log authentication events
- [ ] Rate limit login attempts
- [ ] Implement account lockout

---

## 🎓 Key Concepts

### User
A person with:
- Email (unique identifier)
- Name, avatar
- Multiple workspace memberships

### Workspace  
A project/environment containing:
- Rules, templates, settings
- Users with specific roles
- Independent from other workspaces

### Role
A permission level:
- Admin - full power
- Editor - create/edit
- Reviewer - approve only
- Viewer - read-only

### Permission
An action a role can perform:
- view, create, edit, delete, approve, manage_users, manage_workspace

---

## 🆘 Common Questions

**Q: How do I add a new user?**  
A: In production, via backend. For demo, add to `mockUsers` in AuthContext.tsx

**Q: How do I add a new workspace?**  
A: If using backend, create via API. Otherwise, modify user's `workspaceRoles` array.

**Q: Can a user have different roles in different workspaces?**  
A: Yes! That's the design. User can be Admin in ws-1 and Viewer in ws-2.

**Q: How do I add a new menu item?**  
A: Edit `menuItems` array in Sidebar.tsx and add `requiredRoles` if needed.

**Q: How do I add a new permission?**  
A: Add to `PermissionAction` type in auth.ts, add to `permissionMatrix` in useAuth.ts

**Q: Why use localStorage instead of cookies?**  
A: This is demo code. Production should use secure HTTP-only cookies.

---

## 📞 Documentation

| Document | Purpose | Read Time |
|----------|---------|-----------|
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | How to test & deploy | 10 min |
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | Quick examples | 5 min |
| [AUTH_SYSTEM.md](AUTH_SYSTEM.md) | Complete guide | 20 min |
| [FILE_MANIFEST.md](FILE_MANIFEST.md) | File reference | 15 min |
| [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) | What was built | 5 min |

---

## ✨ Features Summary

- ✅ User authentication (login/logout)
- ✅ 4-role RBAC system
- ✅ Multi-workspace support
- ✅ Role-based menu filtering
- ✅ Protected route components
- ✅ Permission checking hooks
- ✅ Professional login UI
- ✅ Workspace switcher
- ✅ Session persistence
- ✅ Full TypeScript support
- ✅ Demo accounts for testing
- ✅ Comprehensive documentation
- ✅ Zero external auth dependencies
- ✅ Ready for backend integration

---

## 🚀 Next Steps

1. **Read** → [QUICK_REFERENCE.md](QUICK_REFERENCE.md) (5 min)
2. **Test** → Start dev server and try demo accounts
3. **Understand** → Read [AUTH_SYSTEM.md](AUTH_SYSTEM.md)
4. **Integrate** → Connect to your backend
5. **Deploy** → Follow [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---

## 🎉 Ready?

```bash
cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-ui
npx vite
# Then go to http://localhost:5173
# Click "Open Login"
```

Enjoy! 🚀
