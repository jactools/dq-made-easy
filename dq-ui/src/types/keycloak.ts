// Role definitions with granular permissions
export type UserRole = 
  | 'admin'            // Full access to all features within a workspace, system administration
  | 'data-steward'     // Can profile data, request profiling, manage data quality
  | 'analyst'          // Can create/edit rules, request profiling, view suggestions
  | 'viewer'           // Read-only access to rules and reports
  | 'auditor'          // Read-only access to all views including administration
  | 'regulator'        // Read-only access to all views including administration
  | 'exception-fact-reader'  // Temporary read access to exception facts
  | 'exception-fact-investigator'  // Temporary raw-detail access to exception facts
  | 'editor'           // Can create/edit rules but cannot manage users or workspaces
  | 'approver'         // Can approve rules and profiling requests but cannot create/edit rules
  | 'reviewer'         // Can view and approve but cannot create/edit rules or manage users
  | 'governance-admin' // Can manage governance workflows and approve policy changes
  | 'governance-editor' // Can draft and submit governance policy changes
  | 'cross-admin'       // Can manage users and workspaces but cannot create/edit rules or approve requests


// Workspace represents a logical grouping of rules and users
export interface Workspace {
  id: string
  name: string
  description?: string
  createdAt: Date
  isActive: boolean
}

// UserWorkspaceRole defines a user's role within a specific workspace
export interface UserWorkspaceRole {
  workspaceId: string
  role: UserRole
  joinedAt: Date
}

// User interface with workspace memberships
export interface User {
  id: string
  email: string
  firstName: string
  lastName: string
  name: string
  avatarUrl?: string
  grantedScopes?: string[]
  sourceRoles?: string[]
  workspaceRoles: UserWorkspaceRole[]
  createdAt: Date
  isActive: boolean
}

// Auth state managed by context
export interface AuthState {
  user: User | null
  currentWorkspaceId: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  errorReferenceId: string | null
}

// Permission checks
export type PermissionAction = 
  | 'view'
  | 'create'
  | 'edit'
  | 'delete'
  | 'approve'
  | 'manage_users'
  | 'manage_workspace'

// Menu item with permission requirements
export interface ProtectedMenuItem {
  id: string
  label: string
  icon: string
  requiredRole?: UserRole[]  // If undefined, available to all authenticated users
  requiredPermission?: PermissionAction
  children?: ProtectedMenuItem[]
}
