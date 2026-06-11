import React from 'react'
import { useAuth, usePermission } from '../hooks/useKeycloak'

interface ProtectedRouteProps {
  children: React.ReactNode
  requiredRoles?: string[]
  fallback?: React.ReactNode
}

/**
 * ProtectedRoute wraps components that should only be visible to authenticated users
 * with specific roles. If the user doesn't have the required role, optionally shows fallback content.
 */
export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requiredRoles,
  fallback,
}) => {
  const auth = useAuth()

  // Not authenticated
  if (!auth.isAuthenticated || !auth.user) {
    return fallback ? <>{fallback}</> : null
  }

  // No specific role requirement - show to all authenticated users
  if (!requiredRoles || requiredRoles.length === 0) {
    return <>{children}</>
  }

  // Check if user has one of the required roles in current workspace
  const userRole = auth.getCurrentUserRole()
  if (userRole && requiredRoles.includes(userRole)) {
    return <>{children}</>
  }

  // User doesn't have required role
  return fallback ? <>{fallback}</> : null
}

/**
 * Component wrapper for conditional rendering based on permissions
 */
export const IfPermitted: React.FC<{
  permission: string | string[]
  children: React.ReactNode
  fallback?: React.ReactNode
}> = ({ permission, children, fallback }) => {
  const { hasPermission: checkPermission } = usePermission()
  const permissions = Array.isArray(permission) ? permission : [permission]

  // Check if user has any of the required permissions
  const hasAnyPermission = permissions.some(p => 
    checkPermission(p as any)
  )

  if (hasAnyPermission) {
    return <>{children}</>
  }

  return fallback ? <>{fallback}</> : null
}
