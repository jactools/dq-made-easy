# Authentication & Authorization System

This application implements a comprehensive role-based access control (RBAC) system with workspace support. Users can have different roles within different workspaces, and menu items/features can be restricted based on these roles.

## Core Concepts

### Users
- Each user has a global profile (`id`, `email`, `name`, `avatarUrl`)
- Users are members of one or more workspaces with specific roles
- User data is persisted in localStorage (mock implementation)

### Workspaces
- Logical groupings of rules, templates, and resources
- Users can switch between workspaces they belong to
- Each workspace is independent with its own Rules, Templates, and Settings

### Roles
- **Admin**: Full access - can create/edit/delete/approve rules, manage users and workspace settings
- **Editor**: Can create and edit rules, propose templates
- **Reviewer**: Can review and approve rules only (read-most, approve only)
- **Viewer**: Read-only access to rules and reports

### Permissions
Roles map to specific action permissions:
- `view` - Read data
- `create` - Create new items
- `edit` - Modify existing items
- `delete` - Remove items
- `approve` - Approve/publish items
- `manage_users` - Add/remove users from workspace
- `manage_workspace` - Workspace settings and configuration

## Usage

### 1. Accessing Auth State

```tsx
import { useAuth } from '@/hooks/useAuth'

function MyComponent() {
  const auth = useAuth()
  
  // Check if user is logged in
  if (!auth.isAuthenticated) {
    return <p>Please login</p>
  }
  
  // Access current user
  console.log(auth.user.name)
  
  // Get user's role in current workspace
  const role = auth.getCurrentUserRole()
  
  // Switch workspace
  auth.switchWorkspace('workspace-id')
  
  // Logout
  auth.logout()
}
```

### 2. Checking Permissions

```tsx
import { usePermission } from '@/hooks/useAuth'

function MyComponent() {
  const { hasPermission, hasRole } = usePermission()
  
  // Check specific permission
  if (hasPermission('create')) {
    // Show create button
  }
  
  // Check specific role
  if (hasRole('editor')) {
    // Show editor-only features
  }
  
  // Check multiple roles
  if (hasRole(['editor', 'admin'])) {
    // Show to editors and admins
  }
}
```

### 3. Protecting Routes/Sections

```tsx
import { ProtectedRoute } from '@/components/ProtectedRoute'

function App() {
  return (
    <ProtectedRoute requiredRoles={['admin', 'editor']}>
      <RulesEditor />
    </ProtectedRoute>
  )
}
```

### 4. Conditional Rendering

```tsx
import { IfPermitted } from '@/components/ProtectedRoute'

function RulesList() {
  return (
    <div>
      <h2>Rules</h2>
      
      <IfPermitted permission="create">
        <button>Create New Rule</button>
      </IfPermitted>
      
      <IfPermitted permission="delete" fallback={<p>No delete permission</p>}>
        <button>Delete</button>
      </IfPermitted>
    </div>
  )
}
```

### 5. Role-Based Menu Items

Menu items in the Sidebar automatically show/hide based on user role:

```tsx
const menuItems = [
  { id: 'dashboard', label: 'Dashboard', icon: '...' }, // Always visible when logged in
  { id: 'rules', label: 'Rules', icon: '...', requiredRoles: ['editor', 'reviewer', 'admin'] },
  { id: 'templates', label: 'Templates', icon: '...', requiredRoles: ['editor', 'admin'] },
  { id: 'settings', label: 'Settings', icon: '...', requiredRoles: ['admin'] },
]
```

## Demo Accounts

The application includes mock demo accounts for testing:

- **admin@example.com** - Admin role in ws-1 and ws-2
- **editor@example.com** - Editor role in ws-1
- **reviewer@example.com** - Reviewer role in ws-1 and ws-2
- **viewer@example.com** - Viewer role in ws-2

Any password works with these accounts in the demo.

## Integration with Backend

To integrate with a real authentication system:

1. **Update AuthContext.tsx**:
   - Replace `mockUsers` with API calls to your backend
   - Implement actual login/logout with JWT or similar
   - Call endpoints to fetch user workspaces and roles

2. **Example backend integration**:

```tsx
const login = useCallback(async (email: string, password: string) => {
  const response = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  
  if (!response.ok) throw new Error('Login failed')
  
  const user = await response.json()
  const newState = {
    user,
    currentWorkspaceId: user.workspaceRoles[0].workspaceId,
    isAuthenticated: true,
    isLoading: false,
    error: null,
  }
  
  setAuthState(newState)
  persistAuthState(newState)
}, [])
```

3. **Update workspace endpoint**:

```tsx
const switchWorkspace = useCallback(async (workspaceId: string) => {
  // Verify user has access to workspace
  const response = await fetch(`/api/workspaces/${workspaceId}/verify`)
  if (response.ok) {
    setAuthState(prev => ({
      ...prev,
      currentWorkspaceId: workspaceId,
    }))
  }
}, [])
```

## File Structure

```
src/
  contexts/
    AuthContext.tsx          # Auth state and login/logout logic
  hooks/
    useAuth.ts              # useAuth and usePermission hooks
  components/
    AuthModal.tsx           # Login form component
    AuthModal.css           # Login modal styles
    Header.tsx              # Updated with user info
    Sidebar.tsx             # Updated with role-based menu items
    ProtectedRoute.tsx      # Route/content protection
    WorkspaceSelector.tsx   # Workspace switcher
  types/
    auth.ts                 # Type definitions
  App.tsx                   # Updated with AuthProvider
```

## Security Considerations

- **Frontend checks are UI-only**: Always validate permissions on the backend
- **LocalStorage**: Auth state is persisted in localStorage - use secure HTTP-only cookies for production
- **Token expiration**: Implement token refresh logic for production systems
- **CSRF protection**: Use CSRF tokens when communicating with backend
- **XSS prevention**: Sanitize user data before displaying

## Future Enhancements

- [ ] Workspace creation and management UI
- [ ] User management (invite, remove, change roles)
- [ ] Team/organization hierarchy
- [ ] Permission customization per workspace
- [ ] Session management and token refresh
- [ ] Multi-factor authentication
- [ ] Audit logging of user actions
