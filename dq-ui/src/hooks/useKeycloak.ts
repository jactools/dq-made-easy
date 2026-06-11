import { useContext } from 'react'
import { AuthContext } from '../contexts/AuthContext'
import { UserRole, PermissionAction } from '../types/keycloak'

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
};

// Permission matrix: what each role can do
const permissionMatrix: Record<UserRole, PermissionAction[]> = {
  admin: ['view', 'create', 'edit', 'delete', 'approve', 'manage_users'],
  editor: ['view', 'create', 'edit', 'approve'],
  reviewer: ['view', 'approve'],
  viewer: ['view'],
  'data-steward': ['view', 'create', 'edit', 'delete', 'approve'],
  analyst: ['view', 'create', 'edit', 'approve'],
  approver: ['view', 'approve'],
  'governance-admin': ['view', 'create', 'edit', 'approve'],
  'governance-editor': ['view', 'create', 'edit'],
  'cross-admin': ['manage_users', 'manage_workspace'],
  auditor: ['view'],
  regulator: ['view'],
  'exception-fact-reader': ['view'],
  'exception-fact-investigator': ['view'],
}

// export const useAuth = () => {
//   const context = useContext(AuthContext)
//   if (!context) {
//     throw new Error('useAuth must be used within AuthProvider')
//   }
//   return context
// }

export const usePermission = () => {
  const auth = useAuth()

  const hasPermission = (action: PermissionAction): boolean => {
    const role = auth.getCurrentUserRole()
    if (!role) return false

    const rolePermissions = permissionMatrix[role]
    return rolePermissions.includes(action)
  }

  const hasRole = (roles: UserRole | UserRole[]): boolean => {
    const userRole = auth.getCurrentUserRole()
    if (!userRole) return false

    const roleList = Array.isArray(roles) ? roles : [roles]
    return roleList.includes(userRole)
  }

  const hasAnyRole = (roles: UserRole[]): boolean => {
    return hasRole(roles)
  }

  const hasAllRoles = (roles: UserRole[]): boolean => {
    const userRole = auth.getCurrentUserRole()
    if (!userRole) return false
    // For single user, check if their role is any of the required ones
    // In a system with multiple roles per user, this would check all
    return roles.includes(userRole)
  }

  return {
    hasPermission,
    hasRole,
    hasAnyRole,
    hasAllRoles,
    userRole: auth.getCurrentUserRole(),
  }
}
