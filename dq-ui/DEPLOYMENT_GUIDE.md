# Authentication System Deployment Guide

## ✅ Implementation Status

**Complete and Ready for Testing**

All authentication, role-based access control, and workspace management features have been implemented and are fully functional.

---

## 🚀 How to Get Started

### 1. Start the Development Server

```bash
cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-ui
npm install  # if dependencies not yet installed
./scripts/start_local.sh  # starts the HTTPS local UI on https://dq-made-easy.jac.dot:5174
```

### 2. Open in Browser

Navigate to: **https://dq-made-easy.jac.dot:5174** (or the HTTPS port shown in terminal)

The local dev server automatically uses the cert pair in `../tmp/certs/`:
- `dq-made-easy.jac.dot+3-key.pem`
- `dq-made-easy.jac.dot+3.pem`

### Runtime API Endpoint Configuration (Container Deployments)

The frontend requires an explicit runtime API URL and supports overriding it without rebuilding:

```bash
KONG_PUBLIC_URL=http://kong:9111
```

This value is injected into `/runtime-config.js` at container start and consumed by `src/config/api.ts`.
If `KONG_PUBLIC_URL` is missing, the frontend container entrypoint exits non-zero.

### 3. Test Authentication

Click **"Open Login"** button in the top-right corner to open the login modal.

### 4. Use Demo Accounts

Choose any demo account from the quick-login buttons:

```
👤 Admin User
Email: admin@example.com
Role: Admin in ws-1, ws-2
Menu: All items (Dashboard, Rules, Templates, Settings)

👤 Editor User  
Email: editor@example.com
Role: Editor in ws-1
Menu: Dashboard, Rules, Templates, Reports (no Settings)

👤 Reviewer User
Email: reviewer@example.com
Role: Reviewer in ws-1, ws-2
Menu: Dashboard, Rules, Reports (no Templates)

👤 Viewer User
Email: viewer@example.com
Role: Viewer in ws-2
Menu: Dashboard, Reports only
```

---

## 📚 Documentation Files

### For Understanding the System
1. **`QUICK_REFERENCE.md`** - 5-minute overview with examples
2. **`AUTH_SYSTEM.md`** - Comprehensive documentation and usage patterns
3. **`FILE_MANIFEST.md`** - Complete file listing with purposes
4. **`IMPLEMENTATION_SUMMARY.md`** - What was built and how to test

### Read in Order
1. Start: `QUICK_REFERENCE.md`
2. Deep dive: `AUTH_SYSTEM.md`
3. Reference: `FILE_MANIFEST.md`
4. Summary: `IMPLEMENTATION_SUMMARY.md`

---

## 🎯 Testing Scenarios

### Scenario 1: Admin Access
1. Log in as `admin@example.com`
2. Should see: Dashboard, Rules, Templates, Settings
3. Should see user name "Admin User" in header
4. Workspace selector shows: ws-1 (Admin), ws-2 (Admin)

### Scenario 2: Editor Access
1. Log in as `editor@example.com`
2. Should see: Dashboard, Rules, Templates, Reports (NO Settings)
3. Workspace selector shows: ws-1 (Editor)
4. Click Settings if it appears → nothing happens (permission denied)

### Scenario 3: Reviewer Access
1. Log in as `reviewer@example.com`
2. Should see: Dashboard, Rules, Reports (NO Templates)
3. Workspace selector shows: ws-1 (Reviewer), ws-2 (Reviewer)
4. Rules menu available for review approval only

### Scenario 4: Viewer Access
1. Log in as `viewer@example.com`
2. Should see: Dashboard, Reports only
3. Workspace selector shows: ws-2 (Viewer)
4. Can view but cannot create/edit

### Scenario 5: Workspace Switching
1. Log in as `admin@example.com` (has 2 workspaces)
2. Header shows "Workspace: ws-1 (admin)"
3. Click dropdown, select ws-2
4. Should switch to ws-2

### Scenario 6: Logout
1. Log in as any user
2. Click Logout button (top-right)
3. Should return to login screen
4. Log in again → auth state restored (persistent login)

---

## 🔧 Architecture

```
App
├─ AuthProvider
│  ├─ AuthContext (manages auth state, login/logout)
│  └─ Provides: isAuthenticated, user, currentWorkspaceId
│
├─ Header
│  ├─ Shows: Logo
│  ├─ Shows: WorkspaceSelector (when logged in)
│  ├─ Shows: User avatar & name (when logged in)
│  └─ Shows: Login/Logout buttons
│
├─ LoginModal
│  ├─ Email/password form
│  ├─ Demo account quick-login
│  └─ Error handling
│
├─ Sidebar (when authenticated)
│  ├─ Filters menu items by user role
│  ├─ Dashboard (all)
│  ├─ Rules (editor+)
│  ├─ Templates (editor+)
│  ├─ Reports (all)
│  └─ Settings (admin only)
│
└─ Main Content
   └─ Protected by ProtectedRoute or IfPermitted
```

---

## 🔑 Key Files to Know

| File | Purpose | When to Edit |
|------|---------|-------------|
| `src/contexts/AuthContext.tsx` | Auth state, login logic | Integrate with backend |
| `src/hooks/useAuth.ts` | Permission checking | Customize permissions |
| `src/components/Sidebar.tsx` | Menu items | Add/remove menu items |
| `src/types/auth.ts` | Type definitions | Add new roles or fields |
| `AUTH_SYSTEM.md` | Documentation | Reference for integration |

---

## 🔌 Backend Integration Steps

### Step 1: Update AuthContext.tsx
Replace the `mockUsers` object with API calls:

```tsx
const login = useCallback(async (email: string, password: string) => {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  
  const data = await response.json()
  // Handle response...
}, [])
```

### Step 2: Add Token Management
Store JWT token and include in API requests:

```tsx
const token = localStorage.getItem('authToken')
// Include in all API calls
headers: { 'Authorization': `Bearer ${token}` }
```

### Step 3: Update Permission Matrix
In `src/hooks/useAuth.ts`, if your backend permissions differ:

```tsx
const permissionMatrix: Record<UserRole, PermissionAction[]> = {
  // Update based on actual backend permissions
}
```

### Step 4: Connect Workspace Switching
Update `switchWorkspace()` to verify access:

```tsx
const switchWorkspace = useCallback(async (workspaceId: string) => {
  const response = await fetch(`/api/workspaces/${workspaceId}/verify`)
  // Only switch if user has access
}, [])
```

See `AUTH_SYSTEM.md` for complete integration examples.

---

## 🐛 Testing Checklist

- [ ] Login works with demo accounts
- [ ] Menu items show/hide based on role
- [ ] Workspace dropdown shows correct roles
- [ ] Logout clears session
- [ ] Page refresh maintains login (localStorage)
- [ ] Admin sees all menu items
- [ ] Editor doesn't see Settings
- [ ] Reviewer doesn't see Templates
- [ ] Viewer sees only Dashboard & Reports
- [ ] No console errors
- [ ] TypeScript compiles without errors
- [ ] Responsive on mobile (optional)

---

## ⚡ Quick Commands

### Check TypeScript Errors
```bash
cd /Users/jacbeekers/gitrepos/dq-rulebuilder/dq-ui
npx tsc --noEmit
```

### Build for Production
```bash
npm run build
```

### Preview Production Build
```bash
npm run preview
```

### Format Code
```bash
npx prettier --write src/
```

---

## 🔐 Security Notes

### Before Going to Production

1. **Replace Mock Users** - Currently using hardcoded demo data
2. **Add CSRF Protection** - Include CSRF tokens in requests
3. **Use Secure Cookies** - Don't store auth tokens in localStorage
4. **Implement Token Refresh** - Handle JWT expiration
5. **Add Rate Limiting** - Protect login endpoint
6. **Validate on Backend** - Never trust frontend permissions alone
7. **Use HTTPS** - Encrypt all auth communications
8. **Sanitize User Data** - Prevent XSS attacks
9. **Hash Passwords** - Never store plaintext passwords
10. **Log Auth Events** - Track login attempts and failures

---

## 📞 Support

### Common Issues

**Q: Login modal doesn't appear**  
A: Make sure AuthProvider wraps your app. Check App.tsx

**Q: Menu items not showing**  
A: Verify user is authenticated and has the correct role

**Q: Permission check not working**  
A: Make sure usePermission hook is used within AuthProvider

**Q: TypeScript errors**  
A: Run `npx tsc --noEmit` to see all errors

### Debug Tips

```tsx
// In any component, check auth state:
const auth = useAuth()
console.log('Auth:', auth)
console.log('Role:', auth.getCurrentUserRole())
console.log('Workspaces:', auth.user?.workspaceRoles)
```

---

## 🎓 Learning Resources

### Understand Role-Based Access Control
- See `permissionMatrix` in `useAuth.ts`
- Shows what each role can do

### Understand Workspace Concept  
- User = person with email
- Workspace = project/environment
- UserWorkspaceRole = user's role in that workspace

### Understand Component Protection
- `ProtectedRoute` wraps components
- `IfPermitted` for conditional rendering
- Both check current user role

---

## ✨ Features Implemented

✅ **Authentication**
- Login with email/password
- Demo accounts for testing
- Logout functionality

✅ **Authorization**  
- 4 roles (Admin, Editor, Reviewer, Viewer)
- Role-based menu visibility
- Permission checking

✅ **Workspaces**
- Users can belong to multiple workspaces
- Different roles per workspace
- Workspace switcher in header

✅ **UI Components**
- Professional login modal
- Workspace selector dropdown
- User info in header
- Protected route wrapper
- Permission-based rendering

✅ **Data Persistence**
- Auth state saved in localStorage
- Auto-login on page refresh
- Secure logout

✅ **Developer Experience**
- TypeScript support
- Comprehensive hooks (useAuth, usePermission)
- Well-documented code
- Demo accounts included

---

## 🚀 Next Steps

1. **Test** - Try all demo accounts and scenarios above
2. **Customize** - Adjust menu items, roles, permissions as needed
3. **Integrate** - Connect to your authentication backend
4. **Deploy** - Follow security checklist before production
5. **Monitor** - Log auth events and track issues

---

**Ready to go!** 🎉

Start the dev server and test the system at http://localhost:5173
