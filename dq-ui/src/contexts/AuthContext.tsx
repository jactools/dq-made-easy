import React, { createContext, useState, useCallback, ReactNode, useEffect, useContext, useRef } from 'react'
import { User, UserRole, UserWorkspaceRole, Workspace, AuthState } from '../types/keycloak'
import { SettingsContext } from './SettingsContext'
import { getConfiguredApiBaseUrl, toApiGroupV1Base } from '../config/api'
import { withUiSpan } from '../telemetry'
import { camelToSnake } from '../utils/caseConverters'
import { createSupportReferenceId } from '../utils/supportReference'
import { formatPersonName, resolvePersonName } from '../utils/personName'
import {
  buildSsoRedirectUrl,
  readSsoCallbackTokens,
} from '../auth/browserAuthClient'
import { setUiSessionActive } from '../telemetry'

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>
  loginWithSso: () => Promise<void>
  logout: () => void
  refreshAuthToken: () => Promise<boolean>
  refreshUnavailable: boolean
  switchWorkspace: (workspaceId: string) => void
  getCurrentUserRole: () => UserRole | null
  isAdminModeEnabled: boolean
  setAdminModeEnabled: (enabled: boolean) => void
  hasScope: (scope: string) => boolean
  hasAnyScope: (scopes: string[]) => boolean
  clearError: () => void
  canCreateRule: () => boolean
  canTestRule: () => boolean
  canApproveRule: () => boolean
  canActivateRule: () => boolean
  canReadAcrossWorkspaces: () => boolean
  canManageUsers: () => boolean
  canEditGovernance: () => boolean
  canApproveGovernance: () => boolean
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined)

const SESSION_ACTIVITY_STORAGE_KEY = 'dq-session-last-activity-at'
const AUTH_TOKEN_OBSERVED_AT_STORAGE_KEY = 'dq-auth-token-observed-at'
const WORKSPACE_SELECTION_PENDING_STORAGE_KEY = 'dq-workspace-selection-pending'
const ADMIN_MODE_STORAGE_KEY = 'dq-admin-mode-enabled'

type KeycloakSessionConfig = {
  issuerUrl: string
  clientId: string
}

const mapRoleIdsToPrimaryRole = (roleIds: string[]): UserRole => {
  if (roleIds.some(r => r.toLowerCase().includes('governance-admin'))) {
    return 'governance-admin'
  }
  if (roleIds.some(r => r.toLowerCase().includes('governance-editor'))) {
    return 'governance-editor'
  }
  if (roleIds.some(r => r.toLowerCase().includes('exception-fact-investigator'))) {
    return 'exception-fact-investigator'
  }
  if (roleIds.some(r => r.toLowerCase().includes('exception-fact-reader'))) {
    return 'exception-fact-reader'
  }
  if (roleIds.some(r => r.toLowerCase().includes('admin') || r === 'r11' || r === 'r12' || r === 'r13' || r === 'r14' || r === 'r15')) {
    return 'admin'
  }
  if (roleIds.some(r => r.toLowerCase().includes('auditor'))) {
    return 'auditor'
  }
  if (roleIds.some(r => r.toLowerCase().includes('regulator'))) {
    return 'regulator'
  }
  if (roleIds.some(r => r.toLowerCase().includes('steward') || r.toLowerCase().includes('approver') || r.toLowerCase().includes('reviewer'))) {
    return 'data-steward'
  }
  if (roleIds.some(r => r.toLowerCase().includes('analyst') || r.toLowerCase().includes('editor') || r.toLowerCase().includes('owner') || r.startsWith('r0') && r.endsWith('1'))) {
    return 'analyst'
  }
  return 'viewer'
}

const EMPTY_AUTH_STATE: AuthState = {
  user: null,
  currentWorkspaceId: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  errorReferenceId: null,
}

const normalizeWorkspaceId = (value: unknown, fallback = ''): string => {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

const normalizeWorkspaceRole = (value: unknown): UserRole => {
  const normalized = String(value ?? '').trim().toLowerCase()
  if (normalized === 'admin' || normalized === 'data-steward' || normalized === 'analyst' || normalized === 'viewer' || normalized === 'auditor' || normalized === 'regulator' || normalized === 'exception-fact-reader' || normalized === 'exception-fact-investigator' || normalized === 'governance-admin' || normalized === 'governance-editor') {
    return normalized as UserRole
  }
  if (normalized.includes('governance-admin')) {
    return 'governance-admin'
  }
  if (normalized.includes('governance-editor')) {
    return 'governance-editor'
  }
  if (normalized.includes('admin')) {
    return 'admin'
  }
  if (normalized.includes('auditor')) {
    return 'auditor'
  }
  if (normalized.includes('regulator')) {
    return 'regulator'
  }
  if (normalized.includes('exception-fact-investigator') || normalized.includes('jit-investigator') || normalized.includes('raw-detail')) {
    return 'exception-fact-investigator'
  }
  if (normalized.includes('exception-fact-reader') || normalized.includes('jit-reader')) {
    return 'exception-fact-reader'
  }
  if (normalized.includes('steward') || normalized.includes('approver') || normalized.includes('reviewer')) {
    return 'data-steward'
  }
  if (normalized.includes('analyst') || normalized.includes('editor') || normalized.includes('owner')) {
    return 'analyst'
  }
  return mapRoleIdsToPrimaryRole([String(value ?? '')])
}

const resolveActiveWorkspaceId = (backendUser: any): string => {
  // Prefer explicit active-workspace fields returned by login.
  const explicitCandidates = [
    backendUser?.workspace,
    backendUser?.workspaceId,
    backendUser?.workspace_id,
    backendUser?.currentWorkspaceId,
    backendUser?.current_workspace_id,
  ]

  for (const candidate of explicitCandidates) {
    const normalized = normalizeWorkspaceId(candidate, '')
    if (normalized) {
      return normalized
    }
  }

  // Backward-compat fallback for payloads that only include a workspace collection.
  const workspaceCollection =
    backendUser?.workspaces ?? backendUser?.workspaceIds ?? backendUser?.workspace_ids ?? null

  if (Array.isArray(workspaceCollection)) {
    for (const candidate of workspaceCollection) {
      const normalized = normalizeWorkspaceId(candidate, '')
      if (normalized) {
        return normalized
      }
    }
    return ''
  }

  if (typeof workspaceCollection === 'string') {
    const firstWorkspace = workspaceCollection
      .split(/[;,]/)
      .map(item => item.trim())
      .find(Boolean)
    return normalizeWorkspaceId(firstWorkspace, '')
  }

  return ''
}

export const extractWorkspaceRoles = (backendUser: any): UserWorkspaceRole[] => {
  const rawWorkspaceRoles = backendUser?.workspace_roles ?? backendUser?.workspaceRoles
  if (Array.isArray(rawWorkspaceRoles) && rawWorkspaceRoles.length > 0) {
    return rawWorkspaceRoles
      .map((entry: any) => {
        const workspaceId = normalizeWorkspaceId(entry?.workspace_id ?? entry?.workspaceId ?? entry?.workspace ?? '', '')
        if (!workspaceId) {
          return null
        }
        return {
          workspaceId,
          role: normalizeWorkspaceRole(entry?.role ?? entry?.role_id ?? entry?.roleId ?? entry?.workspace_role ?? entry?.workspaceRole),
          joinedAt: new Date(),
        }
      })
      .filter((entry): entry is UserWorkspaceRole => entry !== null)
  }

  const workspaceId = resolveActiveWorkspaceId(backendUser)
  if (!workspaceId) {
    return []
  }

  return [{
    workspaceId,
    role: mapRoleIdsToPrimaryRole(extractRoleIds(backendUser)),
    joinedAt: new Date(),
  }]
}

const normalizeScopes = (scopes: unknown): string[] => {
  if (Array.isArray(scopes)) {
    return scopes
      .flatMap((entry) => String(entry).split(/[\s,;]+/))
      .map((scope) => scope.trim())
      .filter(Boolean)
  }

  if (typeof scopes === 'string') {
    return scopes
      .split(/[\s,;]+/)
      .map((scope) => scope.trim())
      .filter(Boolean)
  }

  return []
}

const hasMatchingScope = (grantedScopes: string[], requiredScope: string): boolean => {
  if (!requiredScope) {
    return false
  }

  if (grantedScopes.includes('dq:*')) {
    return true
  }

  if (grantedScopes.includes(requiredScope)) {
    return true
  }

  const requiredParts = requiredScope.split(':')

  for (let i = requiredParts.length - 1; i > 0; i -= 1) {
    const parentScope = `${requiredParts.slice(0, i).join(':')}:*`
    if (grantedScopes.includes(parentScope)) {
      return true
    }
  }

  return false
}

const isPrivilegedReadScope = (scope: string): boolean => {
  return scope === 'dq:admin:read' || scope === 'dq:workspace:read'
}

const decodeJwtPayload = (token?: string | null): Record<string, unknown> | null => {
  if (!token) {
    return null
  }

  const payloadSegment = token.split('.')[1]
  if (!payloadSegment) {
    return null
  }

  try {
    const normalizedPayload = payloadSegment.replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(normalizedPayload)) as Record<string, unknown>
  } catch {
    return null
  }
}

const markSessionActivity = (timestamp = Date.now()): void => {
  if (typeof window === 'undefined') {
    return
  }

  try {
    localStorage.setItem(SESSION_ACTIVITY_STORAGE_KEY, String(timestamp))
  } catch {
    // ignore
  }
}

const markAuthTokenObservedAt = (timestamp = Date.now()): void => {
  if (typeof window === 'undefined') {
    return
  }

  try {
    localStorage.setItem(AUTH_TOKEN_OBSERVED_AT_STORAGE_KEY, String(timestamp))
  } catch {
    // ignore
  }
}

export const getSessionLastActivityAt = (): number | null => {
  try {
    const rawValue = localStorage.getItem(SESSION_ACTIVITY_STORAGE_KEY)
    if (!rawValue) {
      return null
    }

    const timestamp = Number(rawValue)
    return Number.isFinite(timestamp) ? timestamp : null
  } catch {
    return null
  }
}

export const getAuthTokenObservedAt = (): number | null => {
  try {
    const rawValue = localStorage.getItem(AUTH_TOKEN_OBSERVED_AT_STORAGE_KEY)
    if (!rawValue) {
      return null
    }

    const timestamp = Number(rawValue)
    return Number.isFinite(timestamp) ? timestamp : null
  } catch {
    return null
  }
}

export const getAuthTokenExpiresAt = (): number | null => {
  try {
    const token = localStorage.getItem('authToken')
    if (!token) {
      return null
    }

    const payload = decodeJwtPayload(token)
    const expVal = payload?.exp
    const exp = typeof expVal === 'number' ? expVal : typeof expVal === 'string' ? parseInt(expVal, 10) : NaN
    if (Number.isNaN(exp)) {
      return null
    }

    return exp * 1000
  } catch {
    return null
  }
}

const extractBackendScopes = (backendUser: any, token?: string | null): string[] => {
  const tokenPayload = decodeJwtPayload(token)
  const candidateScopes: unknown[] = [
    backendUser?.granted_scopes,
    backendUser?.grantedScopes,
    backendUser?.permissions,
    backendUser?.scope,
    tokenPayload?.scope,
    tokenPayload?.scp,
    tokenPayload?.permissions,
  ]

  for (const candidate of candidateScopes) {
    const normalized = normalizeScopes(candidate)
    if (normalized.length > 0) {
      return Array.from(new Set(normalized))
    }
  }

  return []
}

const extractRoleIds = (backendUser: any): string[] => {
  const rawRoles = backendUser?.roles ?? backendUser?.role_ids ?? backendUser?.roleIds
  return Array.from(new Set(normalizeScopes(rawRoles)))
}

// Helper function to get all workspaces for a user
const getUserWorkspaces = (user: User) => {
  return user.workspaceRoles.map(wr => ({
    id: normalizeWorkspaceId(wr.workspaceId),
    name: `Workspace ${normalizeWorkspaceId(wr.workspaceId).toUpperCase()}`,
    role: wr.role,
    joinedAt: wr.joinedAt,
  }))
}

// Mock user data - in production, this would come from a backend
const mockUsers: Record<string, User> = {
  'admin@example.com': {
    id: 'user-1',
    email: 'admin@example.com',
    firstName: 'Admin',
    lastName: 'User',
    name: 'Admin User',
    avatarUrl: 'https://i.pravatar.cc/150?img=1',
    workspaceRoles: [
      { workspaceId: 'retail-banking', role: 'admin', joinedAt: new Date('2026-01-01') },
      { workspaceId: 'corporate-banking', role: 'admin', joinedAt: new Date('2026-01-15') },
    ],
    createdAt: new Date('2026-01-01'),
    isActive: true,
  },
  'alice@example.com': {
    id: 'user-7',
    email: 'alice@example.com',
    firstName: 'Alice',
    lastName: 'Governance',
    name: 'Alice Governance',
    avatarUrl: 'https://i.pravatar.cc/150?img=7',
    workspaceRoles: [
      { workspaceId: 'retail-banking', role: 'governance-editor', joinedAt: new Date('2026-01-08') },
    ],
    createdAt: new Date('2026-01-08'),
    isActive: true,
  },
  'governance-admin@example.com': {
    id: 'user-8',
    email: 'governance-admin@example.com',
    firstName: 'Grace',
    lastName: 'Governance',
    name: 'Grace Governance',
    avatarUrl: 'https://i.pravatar.cc/150?img=8',
    workspaceRoles: [
      { workspaceId: 'retail-banking', role: 'governance-admin', joinedAt: new Date('2026-01-09') },
    ],
    createdAt: new Date('2026-01-09'),
    isActive: true,
  },
  'auditor@example.com': {
    id: 'user-5',
    email: 'auditor@example.com',
    firstName: 'Auditor',
    lastName: 'User',
    name: 'Auditor User',
    avatarUrl: 'https://i.pravatar.cc/150?img=5',
    workspaceRoles: [
      { workspaceId: 'global', role: 'auditor', joinedAt: new Date('2026-01-25') },
    ],
    createdAt: new Date('2026-01-25'),
    isActive: true,
  },
  'regulator@example.com': {
    id: 'user-6',
    email: 'regulator@example.com',
    firstName: 'Regulator',
    lastName: 'User',
    name: 'Regulator User',
    avatarUrl: 'https://i.pravatar.cc/150?img=6',
    workspaceRoles: [
      { workspaceId: 'global', role: 'regulator', joinedAt: new Date('2026-01-26') },
    ],
    createdAt: new Date('2026-01-26'),
    isActive: true,
  },
  'analyst@example.com': {
    id: 'user-2',
    email: 'analyst@example.com',
    firstName: 'Analyst',
    lastName: 'User',
    name: 'Analyst User',
    avatarUrl: 'https://i.pravatar.cc/150?img=2',
    workspaceRoles: [
      { workspaceId: 'retail-banking', role: 'analyst', joinedAt: new Date('2026-01-05') },
    ],
    createdAt: new Date('2026-01-05'),
    isActive: true,
  },
  'data-steward@example.com': {
    id: 'user-3',
    email: 'data-steward@example.com',
    firstName: 'Data',
    lastName: 'Steward',
    name: 'Data Steward User',
    avatarUrl: 'https://i.pravatar.cc/150?img=3',
    workspaceRoles: [
      { workspaceId: 'investment-banking', role: 'data-steward', joinedAt: new Date('2026-01-10') },
      { workspaceId: 'risk-compliance', role: 'data-steward', joinedAt: new Date('2026-01-16') },
    ],
    createdAt: new Date('2026-01-10'),
    isActive: true,
  },
  'viewer@example.com': {
    id: 'user-4',
    email: 'viewer@example.com',
    firstName: 'Viewer',
    lastName: 'User',
    name: 'Viewer User',
    avatarUrl: 'https://i.pravatar.cc/150?img=4',
    workspaceRoles: [
      { workspaceId: 'treasury', role: 'viewer', joinedAt: new Date('2026-01-20') },
    ],
    createdAt: new Date('2026-01-20'),
    isActive: true,
  },
}

export async function refreshAuthTokenBackend(apiBaseUrl: string, refreshToken: string): Promise<any | null> {
  try {
    const authApiBase = toApiGroupV1Base('auth', apiBaseUrl)
    const resp = await fetch(`${authApiBase}/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(camelToSnake({ refreshToken })),
    })
    if (!resp.ok) return null
    const body = await resp.json()
    return body
  } catch {
    return null
  }
}

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const settings = useContext(SettingsContext)
  const authApiBase = toApiGroupV1Base('auth', settings?.applicationSettings?.apiBaseUrl)
  const adminApiBase = toApiGroupV1Base('admin', settings?.applicationSettings?.apiBaseUrl)
  
  const [authState, setAuthState] = useState<AuthState>(EMPTY_AUTH_STATE)
  const [refreshUnavailable, setRefreshUnavailable] = useState(false)
  const [adminModeEnabled, setAdminModeEnabledState] = useState<boolean>(() => {
    try {
      const storedValue = localStorage.getItem(ADMIN_MODE_STORAGE_KEY)
      return storedValue === null ? true : storedValue === 'true'
    } catch {
      return true
    }
  })
  const refreshTimerRef = useRef<number | null>(null)
  const inactivityTimerRef = useRef<number | null>(null)
  const refreshAuthTokenFnRef = useRef<(() => Promise<boolean>) | null>(null)
  const refreshInFlightRef = useRef<Promise<boolean> | null>(null)
  const refreshTokenInvalidatedRef = useRef(false)
  const sessionBootstrapAttemptedRef = useRef(false)

  useEffect(() => {
    if (!authState.isAuthenticated) {
      setAdminModeEnabledState(true)
    }
  }, [authState.isAuthenticated])

  const mapBackendUserToUser = useCallback((backendUser: any, token?: string | null): User => {
    const roleIds = extractRoleIds(backendUser)
    const grantedScopes = extractBackendScopes(backendUser, token)
    const workspaceRoles = extractWorkspaceRoles(backendUser)
    const { firstName, lastName } = resolvePersonName(backendUser)
    const displayName = formatPersonName(firstName, lastName, backendUser.email)

    return {
      id: backendUser.id,
      email: backendUser.email,
      firstName,
      lastName,
      name: displayName,
      avatarUrl: `https://i.pravatar.cc/150?email=${encodeURIComponent(backendUser.email)}`,
      grantedScopes,
      sourceRoles: roleIds,
      workspaceRoles,
      createdAt: new Date(backendUser.created_at || Date.now()),
      isActive: backendUser.is_active !== false,
    }
  }, [])

  // Restore auth state from localStorage on mount
  useEffect(() => {
    const savedAuthState = localStorage.getItem('authState')
    const savedToken = localStorage.getItem('authToken')
    if (savedAuthState) {
      try {
        const state = JSON.parse(savedAuthState) as AuthState
        // Cookie-based sessions may not have an authToken in storage.
        // Check for old workspace ID format (ws-1, ws-2, etc.) and clear if found
        if (state.user && state.user.workspaceRoles.some(wr => normalizeWorkspaceId(wr.workspaceId, '').startsWith('ws-'))) {
          console.log('Old workspace ID format detected, clearing cached auth state')
          localStorage.removeItem('authState')
          localStorage.removeItem('recentWorkspaceId')
          return
        }
        // Restore dates as Date objects
        if (state.user) {
          state.user.createdAt = new Date(state.user.createdAt)
          state.user.workspaceRoles = state.user.workspaceRoles.map(r => ({
            ...r,
            workspaceId: normalizeWorkspaceId((r as any).workspaceId),
            joinedAt: new Date(r.joinedAt),
          }))
          const restoredWorkspaceId = normalizeWorkspaceId((state as any).currentWorkspaceId ?? null, '')
          const hasRestoredWorkspace = restoredWorkspaceId && state.user.workspaceRoles.some(
            wr => normalizeWorkspaceId(wr.workspaceId, '') === restoredWorkspaceId
          )
          state.currentWorkspaceId = hasRestoredWorkspace
            ? restoredWorkspaceId
            : state.user.workspaceRoles.length === 1
              ? normalizeWorkspaceId(state.user.workspaceRoles[0]?.workspaceId ?? null, '') || null
              : null
          try {
            if (!state.currentWorkspaceId && state.user.workspaceRoles.length > 1) {
              sessionStorage.setItem(WORKSPACE_SELECTION_PENDING_STORAGE_KEY, '1')
            } else {
              sessionStorage.removeItem(WORKSPACE_SELECTION_PENDING_STORAGE_KEY)
            }
          } catch {
            // ignore
          }
        }
        setAuthState(state)
      } catch (e) {
        console.error('Failed to restore auth state:', e)
      }
    }
  }, [])

  useEffect(() => {
    const syncAuthStateFromStorage = () => {
      if (getAuthToken()) {
        return
      }

      // For cookie-based sessions, validate with /me instead of eagerly clearing.
      void (async () => {
        try {
          const resp = await fetch(`${adminApiBase}/me`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
            credentials: 'include',
          })
          if (resp.ok) {
            return
          }
        } catch {
          // ignore; fall through to clear
        }

        setAuthState(EMPTY_AUTH_STATE)
      })()
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('storage', syncAuthStateFromStorage)
      window.addEventListener('dq-auth-token-changed', syncAuthStateFromStorage)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('storage', syncAuthStateFromStorage)
        window.removeEventListener('dq-auth-token-changed', syncAuthStateFromStorage)
      }
    }
  }, [adminApiBase])

  // Persist auth state to localStorage
  const persistAuthState = useCallback((state: AuthState) => {
    localStorage.setItem('authState', JSON.stringify(state))
  }, [])

  const getSsoConfig = useCallback((): KeycloakSessionConfig | null => {
    const issuerUrl = String(
      settings?.applicationSettings?.ssoIssuerUrl
      || import.meta.env.VITE_SSO_ISSUER_URL
      || '',
    ).trim()
    const clientId = String(
      settings?.applicationSettings?.ssoClientId
      || import.meta.env.VITE_SSO_CLIENT_ID
      || '',
    ).trim()

    if (!issuerUrl || !clientId) {
      return null
    }

    return { issuerUrl, clientId }
  }, [settings?.applicationSettings?.ssoClientId, settings?.applicationSettings?.ssoIssuerUrl])

  const establishSessionFromTokens = useCallback(async (
    accessToken: string,
    options: {
      flow: string
      idToken?: string | null
      refreshToken?: string | null
    },
  ): Promise<boolean> => {
    return withUiSpan(
      'ui.auth.login_redirect',
      {
        'dq.auth.flow': options.flow,
      },
      async (span) => {
        try {
          const meResponse = await fetch(`${adminApiBase}/me`, {
            headers: { Authorization: `Bearer ${accessToken}` },
            credentials: 'include',
          })

          if (!meResponse.ok) {
            let errorBody = ''
            try { errorBody = await meResponse.text() } catch (_) { /* ignore */ }
            let tokenIss = 'unknown'
            try {
              const b64 = accessToken.split('.')[1]?.replace(/-/g, '+').replace(/_/g, '/')
              if (b64) tokenIss = (JSON.parse(atob(b64)) as Record<string, unknown>).iss as string || 'missing'
            } catch (_) { /* ignore */ }
            console.error('[Auth] SSO /me rejected — status:', meResponse.status, '| body:', errorBody, '| token.iss:', tokenIss)
            throw new Error(`Failed to resolve SSO user (${meResponse.status})`)
          }

          const backendUser = await meResponse.json()
          const user = mapBackendUserToUser(backendUser, accessToken)
          let currentWorkspaceId: string | null = null
          try {
            const resolved = resolveActiveWorkspaceId(backendUser)
            if (resolved && user.workspaceRoles.some(wr => normalizeWorkspaceId(wr.workspaceId) === resolved)) {
              currentWorkspaceId = resolved
            } else if (user.workspaceRoles.length === 1) {
              currentWorkspaceId = normalizeWorkspaceId(user.workspaceRoles[0]?.workspaceId ?? null, '') || null
            } else {
              currentWorkspaceId = null
            }
          } catch {
            currentWorkspaceId = user.workspaceRoles.length === 1
              ? normalizeWorkspaceId(user.workspaceRoles[0]?.workspaceId ?? null, '') || null
              : null
          }

          const newState: AuthState = {
            user,
            currentWorkspaceId,
            isAuthenticated: true,
            isLoading: false,
            error: null,
            errorReferenceId: null,
          }

          setAuthState(newState)
          if (user.workspaceRoles.some((workspaceRole) => workspaceRole.role === 'admin')) {
            setAdminModeEnabledState(false)
            localStorage.setItem(ADMIN_MODE_STORAGE_KEY, 'false')
          }
          persistAuthState(newState)
          refreshTokenInvalidatedRef.current = false
          setRefreshUnavailable(false)
          try {
            if (!currentWorkspaceId && user.workspaceRoles.length > 1) {
              sessionStorage.setItem(WORKSPACE_SELECTION_PENDING_STORAGE_KEY, '1')
            } else {
              sessionStorage.removeItem(WORKSPACE_SELECTION_PENDING_STORAGE_KEY)
            }
          } catch {
            /* ignore */
          }

          localStorage.setItem('authToken', accessToken)
          markSessionActivity()
          markAuthTokenObservedAt()
          if (options.idToken) {
            localStorage.setItem('oidcIdToken', options.idToken)
          }
          if (options.refreshToken) {
            try { localStorage.setItem('refreshToken', options.refreshToken) } catch {}
          }
          window.dispatchEvent(new Event('dq-auth-token-changed'))
          try { scheduleTokenRefresh(accessToken) } catch { /* ignore */ }
          span.setAttribute('dq.auth.result', 'success')
          return true
        } catch (e) {
          span.setAttribute('dq.auth.result', 'error')
          console.error('[Auth] Failed to initialize SSO session:', e)
          clearPersistedAuthSession()
          return false
        }
      },
    )
  }, [adminApiBase, mapBackendUserToUser, persistAuthState])

  // Cookie session bootstrap: if there is no token in localStorage, attempt
  // to load the active session from the backend via /me (credentials included
  // by the global fetch patch).
  useEffect(() => {
    if (!adminApiBase) {
      return
    }

    if (authState.isAuthenticated) {
      return
    }

    if (typeof window === 'undefined') {
      return
    }

    const callbackSearch = window.location.search || ''
    const callbackHash = window.location.hash || ''
    const callbackParamsPresent = ['auth_token', 'auth_id_token', 'refresh_token'].some(
      (name) => callbackSearch.includes(name) || callbackHash.includes(name),
    )

    const hasToken = Boolean(getAuthToken())
    if (hasToken && !callbackParamsPresent) {
      return
    }

    if (callbackParamsPresent) {
      console.info('[Auth] SSO callback URL detected', { search: callbackSearch, hash: callbackHash })
    }

    const tokens = readSsoCallbackTokens(callbackSearch, callbackHash)
    if (!tokens?.authToken) {
      if (callbackParamsPresent) {
        console.warn('[Auth] SSO callback URL contained callback params but no auth_token was extracted', { tokens, search: callbackSearch, hash: callbackHash })
      }
      return
    }

    console.info('[Auth] SSO callback tokens found', {
      authToken: Boolean(tokens.authToken),
      authIdToken: Boolean(tokens.authIdToken),
      refreshToken: Boolean(tokens.refreshToken),
    })

    let cancelled = false

    void (async () => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: null, errorReferenceId: null }))
      try {
        const success = await establishSessionFromTokens(tokens.authToken, {
          flow: 'sso_callback',
          idToken: tokens.authIdToken,
          refreshToken: tokens.refreshToken,
        })

        if (cancelled) {
          return
        }

        if (success) {
          const cleanedUrl = new URL(window.location.href)
          cleanedUrl.searchParams.delete('auth_token')
          cleanedUrl.searchParams.delete('auth_id_token')
          cleanedUrl.searchParams.delete('refresh_token')
          if (cleanedUrl.hash.includes('auth_token') || cleanedUrl.hash.includes('auth_id_token') || cleanedUrl.hash.includes('refresh_token')) {
            cleanedUrl.hash = ''
          }
          window.history.replaceState(null, '', cleanedUrl.toString())
          console.info('[Auth] SSO callback session established, cleaned callback URL')
        }
      } catch (error) {
        console.error('[Auth] Failed to process SSO callback tokens:', error)
      } finally {
        if (!cancelled) {
          setAuthState(prev => ({ ...prev, isLoading: false }))
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [adminApiBase, authState.isAuthenticated, establishSessionFromTokens])

  const login = useCallback(async (email: string, password: string) => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: null, errorReferenceId: null }))

    try {
      await withUiSpan(
        'ui.auth.login',
        {
          'dq.auth.flow': 'password_login',
        },
        async (span) => {
          const loginUrls = [`${authApiBase}/login`]

          let response: Response | null = null
          for (const loginUrl of Array.from(new Set(loginUrls))) {
            const candidate = await fetch(loginUrl, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(camelToSnake({ email })),
            })

            if (candidate.ok) {
              response = candidate
              break
            }

            // If gateway returns Unauthorized for login, try the next endpoint.
            if (candidate.status !== 401) {
              response = candidate
              break
            }
          }

          if (!response || !response.ok) {
            span.setAttribute('dq.auth.result', 'rejected')
            throw new Error('Invalid email or password')
          }

          const backendUser = await response.json()
          const token = backendUser.token

          const refresh = backendUser.refreshToken || backendUser.refresh_token || backendUser.refresh || null

          const user: User = mapBackendUserToUser(backendUser, token)

          console.log('[Auth] User mapped:', user)

            // Select active workspace as indicated by the backend; do not
            // consult previously-stored `recentWorkspaceId` here.
            let currentWorkspaceId: string | null = null
            try {
              const resolved = resolveActiveWorkspaceId(backendUser)
              if (resolved && user.workspaceRoles.some(wr => normalizeWorkspaceId(wr.workspaceId) === resolved)) {
                currentWorkspaceId = resolved
              } else if (user.workspaceRoles.length === 1) {
                currentWorkspaceId = normalizeWorkspaceId(user.workspaceRoles[0]?.workspaceId ?? null, '') || null
              } else {
                currentWorkspaceId = null
              }
            } catch {
              currentWorkspaceId = user.workspaceRoles.length === 1
                ? normalizeWorkspaceId(user.workspaceRoles[0]?.workspaceId ?? null, '') || null
                : null
            }

          const newState: AuthState = {
            user,
            currentWorkspaceId: currentWorkspaceId,
            isAuthenticated: true,
            isLoading: false,
            error: null,
            errorReferenceId: null,
          }

          console.log('[Auth] Setting auth state:', newState)
          setAuthState(newState)
          if (user.workspaceRoles.some((workspaceRole) => workspaceRole.role === 'admin')) {
            setAdminModeEnabledState(false)
            localStorage.setItem(ADMIN_MODE_STORAGE_KEY, 'false')
          }
          persistAuthState(newState)
          refreshTokenInvalidatedRef.current = false
          setRefreshUnavailable(false)
          localStorage.setItem('authToken', token)
          markSessionActivity()
          markAuthTokenObservedAt()
          if (refresh) {
            localStorage.setItem('refreshToken', String(refresh))
          }
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('dq-auth-token-changed'))
          }
          console.log('[Auth] Token stored:', token.substring(0, 20) + '...')
          console.log('[Auth] Backend user data:', backendUser)
          try { scheduleTokenRefresh(token) } catch { /* ignore */ }
          span.setAttribute('dq.auth.result', 'success')
        }
      )
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Login failed'
      console.error('[Auth] Login error:', errorMessage, error)
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
        errorReferenceId: createSupportReferenceId(),
        isAuthenticated: false,
      }))
      throw error
    }
  }, [mapBackendUserToUser, persistAuthState])

  const loginWithSso = useCallback(async (): Promise<void> => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: null, errorReferenceId: null }))

    const ssoConfig = getSsoConfig()
    if (!ssoConfig) {
      const error = new Error('SSO is not configured')
      setAuthState(prev => ({ ...prev, isLoading: false, error: error.message, errorReferenceId: createSupportReferenceId() }))
      throw error
    }

    const uiOrigin = typeof window !== 'undefined'
      ? `${window.location.origin}/`
      : ''

    const apiBase = toApiGroupV1Base('auth', settings?.applicationSettings?.apiBaseUrl || getConfiguredApiBaseUrl())
    const redirectUrl = buildSsoRedirectUrl(apiBase, uiOrigin, typeof window !== 'undefined' ? window.location.hostname : undefined)

    if (typeof window !== 'undefined') {
      console.info('[Auth] SSO redirect flow starting', { redirectUrl: redirectUrl.toString() })
      window.location.assign(redirectUrl.toString())
    }
    return
  }, [getSsoConfig, settings?.applicationSettings?.apiBaseUrl])

  // Helper: schedule proactive token refresh based on JWT exp claim.
  const scheduleTokenRefresh = useCallback((token: string | null) => {
    if (typeof window === 'undefined') {
      return
    }

    if (refreshTimerRef.current) {
      try {
        window.clearTimeout(refreshTimerRef.current)
      } catch {
        /* ignore */
      }
      refreshTimerRef.current = null
    }

    const refreshToken = localStorage.getItem('refreshToken')
    if (!token || !refreshToken) {
      return
    }

    const payload = decodeJwtPayload(token)
    const expVal = payload?.exp
    const expSeconds = typeof expVal === 'number' ? expVal : typeof expVal === 'string' ? parseInt(expVal, 10) : NaN
    if (!Number.isFinite(expSeconds)) {
      return
    }

    const expiresAtMs = expSeconds * 1000
    const leadMs = 60 * 1000
    const activeGraceMs = 2 * 60 * 1000

    const scheduleAttempt = (delayMs: number) => {
      const safeDelay = Math.max(1000, Math.floor(delayMs))
      refreshTimerRef.current = window.setTimeout(() => {
        void (async () => {
          const currentToken = localStorage.getItem('authToken')
          const currentRefresh = localStorage.getItem('refreshToken')
          if (!currentToken || !currentRefresh) {
            return
          }

          const nowMs = Date.now()
          const tokenExpiresAt = getAuthTokenExpiresAt()
          if (tokenExpiresAt !== null && tokenExpiresAt <= nowMs + 10_000) {
            // Too close to expiry; let getAuthToken() clear it / force re-login.
          }

          const lastActivityAt = getSessionLastActivityAt()
          const isActive = lastActivityAt !== null && nowMs - lastActivityAt <= activeGraceMs

          if (!isActive) {
            return
          }

          const fn = refreshAuthTokenFnRef.current
          if (!fn) {
            return
          }

          await fn()
          // On success, refreshAuthToken() updates storage and reschedules.
        })()
      }, safeDelay) as unknown as number
    }

    const fireAtMs = expiresAtMs - leadMs
    scheduleAttempt(Math.max(1000, fireAtMs - Date.now()))
  }, [])

  // Refresh token flow: call backend refresh endpoint and update stored tokens.
  const refreshAuthToken = useCallback(async (): Promise<boolean> => {
    const refreshToken = localStorage.getItem('refreshToken')
    if (!refreshToken || refreshTokenInvalidatedRef.current) return false

    if (refreshInFlightRef.current) {
      return refreshInFlightRef.current
    }

    const run = (async () => {
      try {
        const resp = await fetch(`${authApiBase}/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(camelToSnake({ refreshToken })),
        })

        if (!resp.ok) {
          // Fail-fast on invalid refresh tokens (4xx), but avoid throwing users out
          // immediately when the current access token is still valid.
          if (resp.status >= 400 && resp.status < 500) {
            const expiresAt = getAuthTokenExpiresAt()
            const nowMs = Date.now()
            const tokenExpired = expiresAt === null || expiresAt <= nowMs
            if (tokenExpired) {
              clearPersistedAuthSession(true)
              setAuthState(EMPTY_AUTH_STATE)
            } else {
              refreshTokenInvalidatedRef.current = true
              setRefreshUnavailable(true)
              localStorage.removeItem('refreshToken')
              window.dispatchEvent(new Event('dq-auth-token-changed'))
            }
          }
          return false
        }

        const body = await resp.json()
        const newToken = body.token || body.accessToken || null
        const newRefresh = body.refreshToken || body.refresh_token || null
        if (newToken) {
          localStorage.setItem('authToken', String(newToken))
          markAuthTokenObservedAt()
          if (newRefresh) localStorage.setItem('refreshToken', String(newRefresh))
          window.dispatchEvent(new Event('dq-auth-token-changed'))
          setRefreshUnavailable(false)
          try { scheduleTokenRefresh(String(newToken)) } catch {}
          return true
        }

        // No token returned — force expiration
        clearPersistedAuthSession(true)
        setAuthState(EMPTY_AUTH_STATE)
        return false
      } catch (e) {
        // Network errors: do not immediately clear session. The existing access
        // token may still be valid; subsequent activity will retry refresh.
        return false
      } finally {
        refreshInFlightRef.current = null
      }
    })()

    refreshInFlightRef.current = run
    return run
  }, [authApiBase])

  useEffect(() => {
    refreshAuthTokenFnRef.current = refreshAuthToken
  }, [refreshAuthToken])

  // Track activity even when idle timeout policy is disabled.
  useEffect(() => {
    if (!authState.isAuthenticated) {
      return
    }

    let lastMarkedAt = 0
    let lastRefreshAttemptAt = 0
    const refreshLeadMs = 60 * 1000
    const handler = () => {
      const nowMs = Date.now()
      if (nowMs - lastMarkedAt < 1000) {
        return
      }
      lastMarkedAt = nowMs
      markSessionActivity(nowMs)

      // Only refresh when the user is active (this handler is triggered by activity).
      // Throttle refresh attempts to avoid refresh token rotation races.
      if (nowMs - lastRefreshAttemptAt < 15000) {
        return
      }

      const refreshToken = localStorage.getItem('refreshToken')
      const expiresAt = getAuthTokenExpiresAt()
      if (!refreshToken || expiresAt === null) {
        return
      }

      if (expiresAt - nowMs <= refreshLeadMs) {
        lastRefreshAttemptAt = nowMs
        void refreshAuthTokenFnRef.current?.()
      }
    }

    const activityEvents: Array<keyof WindowEventMap> = [
      'mousemove',
      'mousedown',
      'keydown',
      'touchstart',
      'scroll',
      'wheel',
      'click',
      'focus',
    ]

    activityEvents.forEach((ev) => window.addEventListener(ev, handler))
    return () => activityEvents.forEach((ev) => window.removeEventListener(ev, handler))
  }, [authState.isAuthenticated])

  // Schedule refresh after auth restore/login.
  useEffect(() => {
    if (!authState.isAuthenticated) {
      try { scheduleTokenRefresh(null) } catch { /* ignore */ }
      return
    }
    const token = localStorage.getItem('authToken')
    if (token) {
      try { scheduleTokenRefresh(token) } catch { /* ignore */ }
    }
  }, [authState.isAuthenticated, scheduleTokenRefresh])

  useEffect(() => {
    if (!authState.isAuthenticated) {
      return
    }

    const token = localStorage.getItem('authToken')
    if (token && getAuthToken() === null) {
      clearPersistedAuthSession(true)
      setAuthState(EMPTY_AUTH_STATE)
    }
  }, [authState.isAuthenticated])

  const logout = useCallback(() => {
    const frontendOrigin = typeof window !== 'undefined' ? `${window.location.origin}/` : ''

    refreshTokenInvalidatedRef.current = false
    setRefreshUnavailable(false)
    setAuthState(EMPTY_AUTH_STATE)
    clearPersistedAuthSession()

    if (typeof window !== 'undefined' && frontendOrigin) {
      const logoutUrl = `${authApiBase}/logout?frontend=${encodeURIComponent(frontendOrigin)}`
      window.location.assign(logoutUrl)
    }
  }, [authApiBase])

  const switchWorkspace = useCallback((workspaceId: string) => {
    const normalizedWorkspaceId = normalizeWorkspaceId(workspaceId)
    setAuthState(prev => {
      const nextState = {
        ...prev,
        currentWorkspaceId: normalizedWorkspaceId,
      }
      persistAuthState(nextState)
      return nextState
    })
    // Save the most recent workspace for next login
    localStorage.setItem('recentWorkspaceId', normalizedWorkspaceId)
    sessionStorage.removeItem(WORKSPACE_SELECTION_PENDING_STORAGE_KEY)
  }, [])

  const getCurrentUserRole = useCallback((): UserRole | null => {
    if (!authState.user || !authState.currentWorkspaceId) {
      return null
    }

    const workspaceRoles = authState.user.workspaceRoles.filter(
      r => normalizeWorkspaceId(r.workspaceId) === authState.currentWorkspaceId
    )
    const role = workspaceRoles[0]?.role ?? null
    if (role === 'admin' && !adminModeEnabled) {
      const fallbackRole = workspaceRoles.find((workspaceRole) => workspaceRole.role !== 'admin')?.role ?? null
      return fallbackRole
    }

    return role || null
  }, [authState.user, authState.currentWorkspaceId, adminModeEnabled])

  const setAdminModeEnabled = useCallback((enabled: boolean) => {
    const nextEnabled = Boolean(enabled)
    setAdminModeEnabledState(nextEnabled)
    try {
      localStorage.setItem(ADMIN_MODE_STORAGE_KEY, String(nextEnabled))
    } catch {
      // ignore storage failures
    }
  }, [])

  const clearError = useCallback(() => {
    setAuthState(prev => ({ ...prev, error: null, errorReferenceId: null }))
  }, [])

  const hasScope = useCallback((scope: string): boolean => {
    const grantedScopes = authState.user?.grantedScopes ?? []
    if (!adminModeEnabled && authState.user?.workspaceRoles.some((workspaceRole) => workspaceRole.role === 'admin') && isPrivilegedReadScope(scope)) {
      return false
    }
    return hasMatchingScope(grantedScopes, scope)
  }, [adminModeEnabled, authState.user?.grantedScopes, authState.user?.workspaceRoles])

  const hasAnyScope = useCallback((scopes: string[]): boolean => {
    if (scopes.length === 0) {
      return true
    }

    return scopes.some((scope) => hasScope(scope))
  }, [hasScope])

  const canCreateRule = useCallback((): boolean => {
    return hasAnyScope(['dq:rules:create', 'dq:rules:write', 'dq:rules:*', 'dq:*'])
  }, [hasAnyScope])

  const canTestRule = useCallback((): boolean => {
    return hasAnyScope(['dq:rules:test', 'dq:rules:write', 'dq:rules:*', 'dq:*'])
  }, [hasAnyScope])

  const canApproveRule = useCallback((): boolean => {
    return hasAnyScope(['dq:rules:approve', 'dq:rules:write', 'dq:rules:*', 'dq:*'])
  }, [hasAnyScope])

  const canActivateRule = useCallback((): boolean => {
    return hasAnyScope(['dq:rules:activate', 'dq:rules:write', 'dq:rules:*', 'dq:*'])
  }, [hasAnyScope])

  const canReadAcrossWorkspaces = useCallback((): boolean => {
    return hasAnyScope(['dq:workspace:read', 'dq:*'])
  }, [hasAnyScope])

  const canManageUsers = useCallback((): boolean => {
    if (!adminModeEnabled && getCurrentUserRole() === null && authState.user?.workspaceRoles.some((workspaceRole) => workspaceRole.role === 'admin')) {
      return false
    }
    return hasAnyScope(['dq:users:manage', 'dq:*'])
  }, [adminModeEnabled, authState.user?.workspaceRoles, getCurrentUserRole, hasAnyScope])

  const canEditGovernance = useCallback((): boolean => {
    const currentRole = getCurrentUserRole()
    return currentRole === 'governance-admin' || currentRole === 'governance-editor'
  }, [getCurrentUserRole])

  const canApproveGovernance = useCallback((): boolean => {
    const currentRole = getCurrentUserRole()
    return currentRole === 'governance-admin'
  }, [getCurrentUserRole])

  // Enforce global idle timeout policy (if configured via application settings).
  useEffect(() => {
    if (!settings || !settings.applicationSettings) return
    const timeoutMinutes = settings.applicationSettings.sessionTimeoutMinutes ?? 0
    if (!authState.isAuthenticated || !timeoutMinutes || timeoutMinutes <= 0) {
      // clear any existing inactivity timer/listeners
      if (inactivityTimerRef.current) {
        window.clearTimeout(inactivityTimerRef.current)
        inactivityTimerRef.current = null
      }
      return
    }

    const timeoutMs = Math.max(0, Math.floor(timeoutMinutes) * 60 * 1000)

    const resetTimer = () => {
      if (inactivityTimerRef.current) {
        window.clearTimeout(inactivityTimerRef.current)
        inactivityTimerRef.current = null
      }
      markSessionActivity()
      inactivityTimerRef.current = window.setTimeout(() => {
        // force session expiry
        clearPersistedAuthSession(true)
        setAuthState(EMPTY_AUTH_STATE)
      }, timeoutMs) as unknown as number
    }

    const activityEvents: Array<keyof WindowEventMap> = [
      'mousemove',
      'mousedown',
      'keydown',
      'touchstart',
      'scroll',
      'wheel',
      'click',
      'focus',
    ]

    // Start timer and attach listeners
    resetTimer()
    activityEvents.forEach((ev) => window.addEventListener(ev, resetTimer))

    return () => {
      if (inactivityTimerRef.current) {
        window.clearTimeout(inactivityTimerRef.current)
        inactivityTimerRef.current = null
      }
      activityEvents.forEach((ev) => window.removeEventListener(ev, resetTimer))
    }
  }, [settings, settings?.applicationSettings?.sessionTimeoutMinutes, authState.isAuthenticated])

  useEffect(() => {
    setUiSessionActive(authState.isAuthenticated)
  }, [authState.isAuthenticated])

  return (
    <AuthContext.Provider
      value={{
        ...authState,
        login,
        loginWithSso,
        logout,
        refreshAuthToken,
        refreshUnavailable,
        switchWorkspace,
        getCurrentUserRole,
        isAdminModeEnabled: adminModeEnabled,
        setAdminModeEnabled,
        hasScope,
        hasAnyScope,
        clearError,
        canCreateRule,
        canTestRule,
        canApproveRule,
        canActivateRule,
        canReadAcrossWorkspaces,
        canManageUsers,
        canEditGovernance,
        canApproveGovernance,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

// Helper function to get auth token from localStorage
const isTokenExpired = (token: string, graceSeconds = 10): boolean => {
  try {
    const payload = decodeJwtPayload(token)
    const expVal = payload?.exp
    const exp = typeof expVal === 'number' ? expVal : typeof expVal === 'string' ? parseInt(expVal, 10) : NaN
    if (Number.isNaN(exp)) {
      return false
    }
    const now = Math.floor(Date.now() / 1000)
    return exp < now + graceSeconds
  } catch {
    return false
  }
}

export function getAuthToken(): string | null {
  const token = localStorage.getItem('authToken')
  if (!token) return null

  const savedAuthState = localStorage.getItem('authState')
  if (!savedAuthState) {
    clearPersistedAuthSession(false)
    return null
  }

  try {
    const parsedAuthState = JSON.parse(savedAuthState) as Partial<AuthState> | null
    if (!parsedAuthState?.isAuthenticated) {
      clearPersistedAuthSession(false)
      return null
    }
  } catch {
    clearPersistedAuthSession(false)
    return null
  }

  if (isTokenExpired(token)) {
    clearPersistedAuthSession(false)
    return null
  }

  return token
}

export function clearPersistedAuthSession(expired = false): void {
  localStorage.removeItem('authState')
  localStorage.removeItem('authToken')
  localStorage.removeItem('oidcIdToken')
  localStorage.removeItem('refreshToken')
  localStorage.removeItem(ADMIN_MODE_STORAGE_KEY)
  localStorage.removeItem(SESSION_ACTIVITY_STORAGE_KEY)
  localStorage.removeItem(AUTH_TOKEN_OBSERVED_AT_STORAGE_KEY)

  if (typeof window !== 'undefined') {
    // Clear deferred UI-intent flags that could survive the logout/login redirect.
    sessionStorage.removeItem('dq-open-new-rule')
    sessionStorage.removeItem('dq-workspace-selection-pending')
    sessionStorage.removeItem('dq-browser-auth-bootstrap-pending')
    if (expired) {
      try {
        sessionStorage.setItem('dq-session-expired', '1')
      } catch {
        // ignore
      }
    }
    // Notify other windows/tabs that the token changed or session expired.
    window.dispatchEvent(new Event('dq-auth-token-changed'))
    if (expired) {
      try {
        window.dispatchEvent(new CustomEvent('dq-auth-session-expired', { detail: { reason: 'expired' } }))
      } catch {
        // ignore
      }
    }
  }
}
