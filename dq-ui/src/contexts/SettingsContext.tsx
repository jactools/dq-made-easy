import React, { createContext, useState, useCallback, ReactNode, useEffect, useMemo } from 'react'
import { clearPersistedAuthSession, getAuthToken } from './AuthContext'
import { getConfiguredApiBaseUrl, normalizeApiBaseUrl, toApiGroupV1Base } from '../config/api'
import { createSupportReferenceId } from '../utils/supportReference'
import {
  AllSettings,
  AlertRoutingPolicy,
  UserSettings,
  NotificationSettings,
  DisplaySettings,
  WorkspaceSettings,
  SecuritySettings,
  APISettings,
  ApplicationSettings,
  SettingsUpdatePayload,
} from '../types/settings'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { resolvePersonName } from '../utils/personName'
import { DEFAULT_STYLE_PACKAGE, normalizeStylePackageName } from './styleThemeCatalog'

interface SettingsPreferences {
  profile?: Partial<UserSettings>
  notifications?: Partial<NotificationSettings>
  display?: Partial<DisplaySettings>
  workspace?: Partial<WorkspaceSettings>
  security?: Partial<SecuritySettings>
  api?: Partial<APISettings>
  application?: Partial<ApplicationSettings>
}

const normalizeDisplayTheme = (value: unknown): DisplaySettings['theme'] => {
  if (value === 'light' || value === 'dark' || value === 'auto') {
    return value
  }
  if (value === 'system') {
    return 'auto'
  }
  return 'auto'
}

const normalizeAlertRoutingPolicy = (value: unknown): AlertRoutingPolicy | undefined => {
  if (!value || typeof value !== 'object') {
    return undefined
  }

  const source = value as Record<string, unknown>
  const deliveryTarget = source.deliveryTarget === 'itsm' || source.deliveryTarget === 'both' ? source.deliveryTarget : 'app'
  const channels = Array.isArray(source.channels)
    ? Array.from(new Set(source.channels.map((item) => String(item).trim()).filter(Boolean)))
        .filter((item): item is AlertRoutingPolicy['channels'][number] =>
          item === 'in_app' || item === 'email' || item === 'teams' || item === 'slack' || item === 'pagerduty'
        )
    : ['in_app']

  return {
    deliveryTarget,
    channels: channels.length > 0 ? channels : ['in_app'],
    mandatoryCategories: Array.isArray(source.mandatoryCategories)
      ? Array.from(new Set(source.mandatoryCategories.map((item) => String(item).trim()).filter(Boolean)))
      : [],
    mandatoryRoles: Array.isArray(source.mandatoryRoles)
      ? Array.from(new Set(source.mandatoryRoles.map((item) => String(item).trim()).filter(Boolean)))
      : [],
  }
}

const normalizeBoolean = (value: unknown, fallback: boolean): boolean => (
  typeof value === 'boolean' ? value : fallback
)

const normalizeNumber = (value: unknown, fallback: number): number => (
  typeof value === 'number' && Number.isFinite(value) ? value : fallback
)

const normalizeDateFormat = (value: unknown, fallback: DisplaySettings['preferredDateFormat']): DisplaySettings['preferredDateFormat'] => {
  if (value === 'MM/DD/YYYY' || value === 'DD/MM/YYYY' || value === 'YYYY-MM-DD') {
    return value
  }
  return fallback
}

export const normalizeDisplayPreferences = (display: unknown): Partial<DisplaySettings> => {
  if (!display || typeof display !== 'object') {
    return {}
  }

  const source = display as Record<string, unknown>
  const participateCandidate =
    source.participate_in_previews !== undefined
      ? source.participate_in_previews
      : source.participateInPreviews
  return {
    ...(typeof source.user_id === 'string' ? { userId: source.user_id } : {}),
    theme: normalizeDisplayTheme(source.theme),
    itemsPerPage: normalizeNumber(source.items_per_page, 10),
    compactMode: normalizeBoolean(source.compact_mode, false),
    showTooltips: normalizeBoolean(source.show_tooltips, true),
    preferredDateFormat: normalizeDateFormat(source.preferred_date_format, 'DD/MM/YYYY'),
    participateInPreviews: normalizeBoolean(participateCandidate, false),
    ...(typeof source.catalog_term_match_threshold_pct === 'number'
      ? { catalogTermMatchThresholdPct: source.catalog_term_match_threshold_pct }
      : typeof source.catalogTermMatchThresholdPct === 'number'
        ? { catalogTermMatchThresholdPct: source.catalogTermMatchThresholdPct }
        : {}),
    ...(typeof source.updated_at === 'string' ? { updatedAt: source.updated_at } : {}),
  }
}

export const normalizeApplicationPreferences = (application: unknown): Partial<ApplicationSettings> => {
  if (!application || typeof application !== 'object') {
    return {}
  }

  const source = snakeToCamel<Record<string, unknown>>(application as Record<string, unknown>)
  const normalizedApiBaseUrl =
    typeof source.apiBaseUrl === 'string'
      ? normalizeApiBaseUrl(source.apiBaseUrl)
      : source.apiBaseUrl
  const normalizedStylePackage =
    typeof source.stylePackage === 'string'
      ? normalizeStylePackageName(source.stylePackage)
      : undefined

  return {
    ...source,
    ...(normalizedApiBaseUrl ? { apiBaseUrl: normalizedApiBaseUrl } : {}),
    ...(normalizedStylePackage ? { stylePackage: normalizedStylePackage } : {}),
  } as Partial<ApplicationSettings>
}

const serializeDisplayPreferences = (display: Partial<DisplaySettings> | undefined): Record<string, unknown> | undefined => {
  if (!display) {
    return undefined
  }

  return {
    ...(typeof display.userId === 'string' ? { user_id: display.userId } : {}),
    ...(display.theme ? { theme: normalizeDisplayTheme(display.theme) } : {}),
    ...(typeof display.itemsPerPage === 'number' ? { items_per_page: display.itemsPerPage } : {}),
    ...(typeof display.compactMode === 'boolean' ? { compact_mode: display.compactMode } : {}),
    ...(typeof display.showTooltips === 'boolean' ? { show_tooltips: display.showTooltips } : {}),
    ...(display.preferredDateFormat ? { preferred_date_format: display.preferredDateFormat } : {}),
    ...(typeof display.participateInPreviews === 'boolean' ? { participate_in_previews: display.participateInPreviews } : {}),
    ...(typeof display.catalogTermMatchThresholdPct === 'number'
      ? { catalog_term_match_threshold_pct: display.catalogTermMatchThresholdPct }
      : {}),
    ...(typeof display.updatedAt === 'string' ? { updated_at: display.updatedAt } : {}),
  }
}

export const serializePreferencesForApi = (prefs: SettingsPreferences): Record<string, unknown> => ({
  ...(prefs.profile ? { profile: prefs.profile } : {}),
  ...(prefs.notifications ? { notifications: prefs.notifications } : {}),
  ...(prefs.display ? { display: serializeDisplayPreferences(prefs.display) } : {}),
  ...(prefs.workspace ? { workspace: prefs.workspace } : {}),
  ...(prefs.security ? { security: prefs.security } : {}),
  ...(prefs.api ? { api: prefs.api } : {}),
  ...(prefs.application ? { application: prefs.application } : {}),
})

export interface AdminUserSummary {
  id: string
  firstName?: string
  lastName?: string
  email?: string
  roles: string[]
  workspaces: string[]
  workspaceRoles: Array<{ workspaceId: string; role: string }>
}

export interface AdminRoleSummary {
  id: string
  name: string
  workspace: string
  permissions: string[]
}

export interface SettingsContextType {
  userSettings: UserSettings | null
  notificationSettings: NotificationSettings | null
  displaySettings: DisplaySettings | null
  workspaceSettings: WorkspaceSettings | null
  securitySettings: SecuritySettings | null
  apiSettings: APISettings | null
  applicationSettings: ApplicationSettings | null
  adminUsers: AdminUserSummary[]
  adminRoles: AdminRoleSummary[]
  isLoading: boolean
  error: string | null
  errorReferenceId: string | null
  updateSettings: (payload: SettingsUpdatePayload) => Promise<void>
  loadSettings: () => Promise<void>
  loadAdminUsers: () => Promise<void>
  loadAdminRoles: () => Promise<void>
  updateAdminUser: (userId: string, payload: { roles: string[]; workspaces: string[] }) => Promise<void>
  createAdminRole: (payload: { id: string; name: string; workspace: string; permissions: string[] }) => Promise<void>
  updateAdminRole: (roleId: string, payload: { name: string; workspace: string; permissions: string[] }) => Promise<void>
  resetUserProfile: (userId: string) => Promise<void>
  resetUserSettings: (userId: string) => Promise<void>
  saveAPIKey: () => Promise<string>
  revokeAPIKey: (keyId: string) => Promise<void>
  enableTwoFactor: () => Promise<string>
  clearError: () => void
}

export const SettingsContext = createContext<SettingsContextType | undefined>(undefined)

type CompleteSettings = Omit<AllSettings, 'apiSettings' | 'applicationSettings'> & {
  apiSettings: APISettings
  applicationSettings: ApplicationSettings
}

// Get theme preference from localStorage or system preference
const getInitialTheme = (): 'light' | 'dark' | 'auto' => {
  const saved = localStorage.getItem('dq-theme-preference')
  if (saved === 'light' || saved === 'dark' || saved === 'auto') {
    return saved
  }

  return 'auto'
}

const parseWorkspaceId = (user: any): string => {
  const workspaces = Array.isArray(user?.workspaces)
    ? user.workspaces
    : typeof user?.workspaces === 'string'
      ? user.workspaces.split(';')
      : user?.workspace
        ? [String(user.workspace)]
        : []
  return String(workspaces[0] || 'default')
}

const viteEnv: Record<string, string | undefined> = {
  VITE_ALLOW_LOCAL_AUTH: import.meta.env.VITE_ALLOW_LOCAL_AUTH,
  VITE_SSO_ENABLED: import.meta.env.VITE_SSO_ENABLED,
  VITE_SSO_CLIENT_ID: import.meta.env.VITE_SSO_CLIENT_ID,
  VITE_SSO_ISSUER_URL: import.meta.env.VITE_SSO_ISSUER_URL,
  VITE_SSO_PROVIDER: import.meta.env.VITE_SSO_PROVIDER,
}

const getViteEnvString = (key: keyof typeof viteEnv): string => {
  const value = viteEnv[key]
  return typeof value === 'string' ? value.trim() : ''
}

const getViteEnvBoolean = (key: keyof typeof viteEnv, defaultValue: boolean): boolean => {
  const value = getViteEnvString(key).toLowerCase()
  if (value === 'true') return true
  if (value === 'false') return false
  return defaultValue
}

const getDefaultSsoProvider = (): ApplicationSettings['ssoProvider'] => {
  const provider = getViteEnvString('VITE_SSO_PROVIDER').toLowerCase()
  if (provider === 'keycloak' || provider === 'azure' || provider === 'okta' || provider === 'none') {
    return provider
  }
  return 'none'
}

const buildDefaultSettings = (user: any): CompleteSettings => {
  const userId = String(user?.id || '')
  const email = String(user?.email || '')
  const { firstName, lastName } = resolvePersonName(user)
  const workspaceId = parseWorkspaceId(user)
  const now = new Date().toISOString()

  return {
    userSettings: {
      userId,
      email,
      firstName,
      lastName,
      phone: '',
      avatarUrl: '',
      language: 'en',
      timezone: 'UTC',
      updatedAt: now,
    },
    notificationSettings: {
      userId,
      emailOnApproval: true,
      emailOnRejection: true,
      emailOnTestingFailure: true,
      emailDigestFrequency: 'daily',
      pushNotifications: true,
      teamsIntegration: false,
      updatedAt: now,
    },
    displaySettings: {
      userId,
      theme: getInitialTheme(),
      itemsPerPage: 10,
      compactMode: false,
      showTooltips: true,
      preferredDateFormat: 'DD/MM/YYYY',
      participateInPreviews: false,
      catalogTermMatchThresholdPct: undefined,
      updatedAt: now,
    },
    workspaceSettings: {
      workspaceId,
      name: 'Workspace',
      description: '',
      alertRoutingPolicy: {
        deliveryTarget: 'app',
        channels: ['in_app'],
        mandatoryCategories: [],
        mandatoryRoles: [],
      },
      defaultRiskLevel: 'medium',
      requiresApprovalForActivation: true,
      requiresTestingBeforeApproval: true,
      autoRetestInterval: 7,
      ruleNamingPrefix: 'DQ_',
      maxListItems: 25,
      enabledDataSources: ['postgresql'],
      reconciliationDataSources: [],
      updatedAt: now,
    },
    securitySettings: {
      userId,
      twoFactorEnabled: false,
      lastPasswordChange: now,
      ipWhitelist: [],
      apiKeys: [],
      lastLogin: now,
      updatedAt: now,
    },
    apiSettings: {
      workspaceId,
      webhookUrl: '',
      rateLimitPerMinute: 60,
      allowedOrigins: ['http://localhost:3000'],
      encryptionEnabled: true,
      auditLoggingEnabled: true,
      apiTimeout: 30,
      updatedAt: now,
    },
    applicationSettings: {
      debounceMs: 300,
      iconProvider: 'tabler',
      stylePackage: DEFAULT_STYLE_PACKAGE,
      alertRoutingPolicy: {
        deliveryTarget: 'app',
        channels: ['in_app'],
        mandatoryCategories: [],
        mandatoryRoles: [],
      },
      ssoEnabled: getViteEnvBoolean('VITE_SSO_ENABLED', false),
      ssoProvider: getDefaultSsoProvider(),
      ssoIssuerUrl: getViteEnvString('VITE_SSO_ISSUER_URL'),
      ssoClientId: getViteEnvString('VITE_SSO_CLIENT_ID'),
      allowLocalAuth: getViteEnvBoolean('VITE_ALLOW_LOCAL_AUTH', false),
      apiBaseUrl: getConfiguredApiBaseUrl(),
      apiVersion: 'v1',
      apiRetryAttempts: 3,
      apiRetryDelay: 1000,
      maxUsersPerWorkspace: 100,
      maxWorkspaces: 50,
      maxRulesPerWorkspace: 1000,
      maxTemplatesPerWorkspace: 100,
      maxConcurrentTests: 5,
      allowedWorkspaceDataSourceTypes: ['adls', 's3', 'oracle', 'sql_server'],
      defaultRuleThresholdPct: 0,
      defaultCatalogTermMatchThresholdPct: 70,
      maintenanceMode: false,
      maintenanceMessage: '',
      allowSignup: true,
      requireEmailVerification: false,
      defaultUserRole: 'viewer',
      assistanceRequestMode: 'email',
      assistanceRequestDestinations: ['email'],
      assistanceRequestEmailAddress: 'dq-made-easy-support@jaccloud.nl',
      assistanceRequestItsmSystem: 'Zammad',
      assistanceRequestItsmEndpointUrl: '',
      assistanceRequestItsmAuthToken: '',
      assistanceRequestTeamsWebhookUrl: 'https://example.com/teams/workflow-webhook',
      alertingSlackWebhookUrl: '',
      alertingPagerDutyRoutingKey: '',
      supportEmailSmtpHost: 'smtp.strato.com',
      supportEmailSmtpPort: 465,
      supportEmailSmtpUsername: 'dq-made-easy-support@jaccloud.nl',
      supportEmailSmtpPassword: '',
      supportEmailSmtpUseStartTls: true,
      supportEmailFromAddress: 'dq-made-easy-support@jaccloud.nl',
      dataProtectionMaskingMethods: ['none', 'redact', 'partial', 'tokenize'],
      dataProtectionEncryptionMethods: ['fernet'],
      logLevel: 'info',
      enableAnalytics: true,
      enableCrashReporting: true,
      enableSuggestions: false,
      enableBulkOperations: true,
      enableVersioning: true,
      enableExport: true,
      auditLogRetentionDays: 90,
      testResultsRetentionDays: 30,
      deletedItemsRetentionDays: 30,
      exceptionFactRetentionDays: 30,
      exceptionFactArchiveRetentionDays: 180,
      exceptionAnalyticsProjectionRetentionDays: 365,
      exceptionFactPurgeBatchSize: 5000,
      exceptionFactJitRequestTimeoutMinutes: 30,
      sessionTimeoutMinutes: 0,
      sessionTimeoutWarningMinutes: 5,
      agentSessionTimeoutMinutes: 60,
      maxToolCallsPerSession: 100,
      updatedAt: now,
    },
  }
}

const mergeSettings = <T extends { updatedAt: string }>(base: T, overrides?: Partial<T>): T => {
  if (!overrides) return base
  return {
    ...base,
    ...overrides,
    updatedAt: overrides.updatedAt || base.updatedAt,
  }
}

const normalizeSupportDestinations = (value: unknown): Array<'email' | 'itsm' | 'teams'> | undefined => {
  const values = Array.isArray(value)
    ? value
    : typeof value === 'string'
      ? value.split(',')
      : null

  if (!values) {
    return undefined
  }

  const normalized = values
    .map((entry) => String(entry || '').trim().toLowerCase())
    .filter((entry): entry is 'email' | 'itsm' | 'teams' => entry === 'email' || entry === 'itsm' || entry === 'teams')

  return Array.from(new Set(normalized))
}

export const normalizePreferences = (prefs: any): SettingsPreferences => {
  if (!prefs || typeof prefs !== 'object') return {}

  return {
    profile: snakeToCamel(prefs.profile || {}),
    notifications: snakeToCamel(prefs.notifications || {}),
    display: normalizeDisplayPreferences(prefs.display),
    workspace: snakeToCamel(prefs.workspace || {}),
    security: snakeToCamel(prefs.security || {}),
    api: snakeToCamel(prefs.api || {}),
    application: normalizeApplicationPreferences(prefs.application),
  }
}

const isInvalidPersistedSession = (status: number, errorText: string): boolean => {
  if (status !== 401) {
    return false
  }

  return /invalid signature|signature verification failed|token.*expired|invalid token/i.test(errorText)
}

export const SettingsProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [userSettings, setUserSettings] = useState<UserSettings | null>(null)
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings | null>(null)
  const [displaySettings, setDisplaySettings] = useState<DisplaySettings | null>(null)
  const [workspaceSettings, setWorkspaceSettings] = useState<WorkspaceSettings | null>(null)
  const [securitySettings, setSecuritySettings] = useState<SecuritySettings | null>(null)
  const [apiSettings, setAPISettings] = useState<APISettings | null>(null)
  const [applicationSettings, setApplicationSettings] = useState<ApplicationSettings | null>(null)
  const [preferences, setPreferences] = useState<SettingsPreferences>({})
  const [adminUsers, setAdminUsers] = useState<AdminUserSummary[]>([])
  const [adminRoles, setAdminRoles] = useState<AdminRoleSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [errorReferenceId, setErrorReferenceId] = useState<string | null>(null)

  const setContextError = useCallback((message: string) => {
    setError(message)
    setErrorReferenceId(createSupportReferenceId())
  }, [])

  const clearContextError = useCallback(() => {
    setError(null)
    setErrorReferenceId(null)
  }, [])
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())

  // IMPORTANT: Use the same configured API base URL as the rest of the app.
  // Otherwise settings may be loaded/saved against a different backend host,
  // making user preferences (like preview opt-in) appear to "reset" after logout.
  const adminApiBase = useMemo(
    () => toApiGroupV1Base('admin', applicationSettings?.apiBaseUrl),
    [applicationSettings?.apiBaseUrl]
  )

  const resetSettingsState = useCallback(() => {
    setUserSettings(null)
    setNotificationSettings(null)
    setDisplaySettings(null)
    setWorkspaceSettings(null)
    setSecuritySettings(null)
    setAPISettings(null)
    setApplicationSettings(null)
    setPreferences({})
    setAdminUsers([])
    setAdminRoles([])
  }, [])

  const applyPreferences = useCallback((user: any, prefs: SettingsPreferences) => {
    const defaults = buildDefaultSettings(user)

    setUserSettings(mergeSettings(defaults.userSettings, prefs.profile))
    setNotificationSettings(mergeSettings(defaults.notificationSettings, prefs.notifications))
    setDisplaySettings(mergeSettings(defaults.displaySettings, prefs.display))
    setWorkspaceSettings(mergeSettings(defaults.workspaceSettings, prefs.workspace))
    setSecuritySettings(mergeSettings(defaults.securitySettings, prefs.security))
    setAPISettings(mergeSettings(defaults.apiSettings, prefs.api))
    setApplicationSettings(mergeSettings(defaults.applicationSettings, prefs.application))
  }, [])

  const persistPreferences = useCallback(async (nextPreferences: SettingsPreferences) => {
    const token = getAuthToken()
    const apiPreferences = serializePreferencesForApi(nextPreferences)
    const response = await fetch(`${adminApiBase}/me`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { 'Authorization': `Bearer ${token}` }),
      },
      body: JSON.stringify(camelToSnake({ preferences: apiPreferences })),
    })
    if (!response.ok) {
      const detail = await response.text().catch(() => '')
      throw new Error(`Failed to save settings (${response.status}): ${detail || response.statusText || 'Unknown error'}`)
    }
  }, [adminApiBase])

  const loadSettings = useCallback(async (): Promise<void> => {
    const token = authToken || getAuthToken()

    if (!token) {
      setIsLoading(false)
      clearContextError()
      return
    }

    setIsLoading(true)
    clearContextError()

    try {
      console.log('[Settings] Loading settings from:', `${adminApiBase}/me`)
      console.log('[Settings] Loading settings, token present:', Boolean(token))
      
      const response = await fetch(`${adminApiBase}/me`, {
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
        credentials: 'include',
      })
      
      if (!response.ok) {
        const errorText = await response.text()
        if (response.status === 401) {
          clearPersistedAuthSession(true)
          resetSettingsState()
          setAuthToken(null)
          clearContextError()
          return
        }
        if (isInvalidPersistedSession(response.status, errorText)) {
          clearPersistedAuthSession()
          resetSettingsState()
          clearContextError()
          return
        }
        console.error('[Settings] /me failed:', response.status, errorText)
        if (response.status === 401) {
          throw new Error('Unauthorized while refreshing settings')
        }
        throw new Error(`Failed to fetch user settings (${response.status})`)
      }

      const user = await response.json()
      const prefs = normalizePreferences(user?.preferences)
      const defaults = buildDefaultSettings(user)
      const mergedPrefs: SettingsPreferences = {
        profile: mergeSettings(defaults.userSettings, prefs.profile),
        notifications: mergeSettings(defaults.notificationSettings, prefs.notifications),
        display: mergeSettings(defaults.displaySettings, prefs.display),
        workspace: mergeSettings(defaults.workspaceSettings, prefs.workspace),
        security: mergeSettings(defaults.securitySettings, prefs.security),
        api: mergeSettings(defaults.apiSettings, prefs.api),
        application: mergeSettings(defaults.applicationSettings, prefs.application),
      }

      setPreferences(mergedPrefs)
      applyPreferences(user, mergedPrefs)

      const workspaceId = String(mergedPrefs.workspace?.workspaceId || defaults.workspaceSettings.workspaceId || '').trim()
      const workspaceApiBase = toApiGroupV1Base('rulebuilder', mergedPrefs.application?.apiBaseUrl || defaults.applicationSettings.apiBaseUrl)
      if (workspaceId && workspaceApiBase) {
        try {
          const workspaceResponse = await fetch(`${workspaceApiBase}/workspaces`, {
            headers: {
              ...(token && { 'Authorization': `Bearer ${token}` }),
            },
          })
          if (workspaceResponse.ok) {
            const workspacePayload = await workspaceResponse.json().catch(() => null)
            const workspaceRows = Array.isArray(workspacePayload?.data) ? workspacePayload.data : []
            const workspaceRow = workspaceRows.find((item: any) => String(item?.id || '').trim() === workspaceId)
            const workspacePolicy = normalizeAlertRoutingPolicy(workspaceRow?.alertRoutingPolicy || workspaceRow?.alert_routing_policy)
            if (workspacePolicy) {
              setWorkspaceSettings((current) => (current ? { ...current, alertRoutingPolicy: workspacePolicy } : current))
            }
          }
        } catch (workspaceError) {
          console.warn('[Settings] Failed to load workspace alert routing policy:', workspaceError)
        }
      }
    } catch (err) {
      setContextError(err instanceof Error ? err.message : 'Failed to load settings')
    } finally {
      setIsLoading(false)
    }
  }, [adminApiBase, applyPreferences, authToken, resetSettingsState, clearContextError, setContextError])

  // Merge runtime app-config into applicationSettings.
  // This is required for truly global settings (like idle session timeout) that are persisted via /app-config.
  useEffect(() => {
    const token = authToken || getAuthToken()
    const apiBaseUrl = applicationSettings?.apiBaseUrl

    if (!apiBaseUrl || !token) {
      return
    }

    let cancelled = false

    const loadAppConfig = async () => {
      try {
        const systemApiBase = toApiGroupV1Base('system', apiBaseUrl)
        const response = await fetch(`${systemApiBase}/app-config`, {
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        })

        if (!response.ok) {
          // Avoid invalidating the session from a background refresh.
          return
        }

        const config = snakeToCamel<Record<string, unknown>>(await response.json().catch(() => null))
        if (cancelled || !config || typeof config !== 'object') {
          return
        }

          const nextTimeout = typeof (config as any).sessionTimeoutMinutes === 'number'
            ? (config as any).sessionTimeoutMinutes
          : undefined
          const nextWarning = typeof (config as any).sessionTimeoutWarningMinutes === 'number'
            ? (config as any).sessionTimeoutWarningMinutes
          : undefined
          const assistanceRequestMode = typeof (config as any).assistanceRequestMode === 'string'
            ? (config as any).assistanceRequestMode
          : undefined
          const assistanceRequestDestinations = normalizeSupportDestinations((config as any).assistanceRequestDestinations)
          const assistanceRequestEmailAddress = typeof (config as any).assistanceRequestEmailAddress === 'string'
            ? (config as any).assistanceRequestEmailAddress
          : undefined
          const assistanceRequestItsmSystem = typeof (config as any).assistanceRequestItsmSystem === 'string'
            ? (config as any).assistanceRequestItsmSystem
          : undefined
          const assistanceRequestItsmEndpointUrl = typeof (config as any).assistanceRequestItsmEndpointUrl === 'string'
            ? (config as any).assistanceRequestItsmEndpointUrl
          : undefined
          const assistanceRequestItsmAuthToken = typeof (config as any).assistanceRequestItsmAuthToken === 'string'
            ? (config as any).assistanceRequestItsmAuthToken
          : undefined
          const assistanceRequestTeamsWebhookUrl = typeof (config as any).assistanceRequestTeamsWebhookUrl === 'string'
            ? (config as any).assistanceRequestTeamsWebhookUrl
          : undefined
          const alertingSlackWebhookUrl = typeof (config as any).alertingSlackWebhookUrl === 'string'
            ? (config as any).alertingSlackWebhookUrl
          : undefined
          const alertingPagerDutyRoutingKey = typeof (config as any).alertingPagerDutyRoutingKey === 'string'
            ? (config as any).alertingPagerDutyRoutingKey
          : undefined
          const alertRoutingPolicy = normalizeAlertRoutingPolicy((config as any).alertRoutingPolicy)
          const iconProvider = typeof (config as any).iconProvider === 'string'
            ? (config as any).iconProvider
            : undefined
          const stylePackage = typeof (config as any).stylePackage === 'string'
            ? normalizeStylePackageName((config as any).stylePackage)
            : undefined
          const supportEmailSmtpHost = typeof (config as any).supportEmailSmtpHost === 'string'
            ? (config as any).supportEmailSmtpHost
          : undefined
          const supportEmailSmtpPort = typeof (config as any).supportEmailSmtpPort === 'number'
            ? (config as any).supportEmailSmtpPort
          : undefined
          const supportEmailSmtpUsername = typeof (config as any).supportEmailSmtpUsername === 'string'
            ? (config as any).supportEmailSmtpUsername
          : undefined
          const supportEmailSmtpPassword = typeof (config as any).supportEmailSmtpPassword === 'string'
            ? (config as any).supportEmailSmtpPassword
          : undefined
          const supportEmailSmtpUseStartTls = typeof (config as any).supportEmailSmtpUseStartTls === 'boolean'
            ? (config as any).supportEmailSmtpUseStartTls
          : undefined
          const supportEmailFromAddress = typeof (config as any).supportEmailFromAddress === 'string'
            ? (config as any).supportEmailFromAddress
          : undefined
          const dataProtectionMaskingMethods = Array.isArray((config as any).dataProtectionMaskingMethods)
            ? (config as any).dataProtectionMaskingMethods
            : undefined
          const dataProtectionEncryptionMethods = Array.isArray((config as any).dataProtectionEncryptionMethods)
            ? (config as any).dataProtectionEncryptionMethods
            : undefined
          const debounceMs = typeof (config as any).debounceMs === 'number'
            ? (config as any).debounceMs
          : undefined
          const allowedWorkspaceDataSourceTypes = Array.isArray((config as any).allowedWorkspaceDataSourceTypes)
            ? (config as any).allowedWorkspaceDataSourceTypes
            : undefined
          const defaultRuleThresholdPct = typeof (config as any).defaultRuleThresholdPct === 'number'
            ? (config as any).defaultRuleThresholdPct
          : undefined
          const defaultCatalogTermMatchThresholdPct = typeof (config as any).defaultCatalogTermMatchThresholdPct === 'number'
            ? (config as any).defaultCatalogTermMatchThresholdPct
          : undefined
          const exceptionFactJitRequestTimeoutMinutes = typeof (config as any).exceptionFactJitRequestTimeoutMinutes === 'number'
            ? (config as any).exceptionFactJitRequestTimeoutMinutes
          : undefined

        if (
          nextTimeout === undefined &&
          nextWarning === undefined &&
          assistanceRequestMode === undefined &&
          assistanceRequestDestinations === undefined &&
          assistanceRequestEmailAddress === undefined &&
          assistanceRequestItsmSystem === undefined &&
          assistanceRequestItsmEndpointUrl === undefined &&
          assistanceRequestItsmAuthToken === undefined &&
          assistanceRequestTeamsWebhookUrl === undefined &&
          alertingSlackWebhookUrl === undefined &&
          alertingPagerDutyRoutingKey === undefined &&
          alertRoutingPolicy === undefined &&
          iconProvider === undefined &&
          stylePackage === undefined &&
          supportEmailSmtpHost === undefined &&
          supportEmailSmtpPort === undefined &&
          supportEmailSmtpUsername === undefined &&
          supportEmailSmtpPassword === undefined &&
          supportEmailSmtpUseStartTls === undefined &&
          supportEmailFromAddress === undefined &&
          dataProtectionMaskingMethods === undefined &&
          dataProtectionEncryptionMethods === undefined &&
          debounceMs === undefined &&
          allowedWorkspaceDataSourceTypes === undefined &&
          defaultRuleThresholdPct === undefined &&
          defaultCatalogTermMatchThresholdPct === undefined &&
          exceptionFactJitRequestTimeoutMinutes === undefined
        ) {
          return
        }

        setApplicationSettings((prev) => {
          if (!prev) {
            return prev
          }

          const merged = {
            ...prev,
            ...(nextTimeout !== undefined ? { sessionTimeoutMinutes: nextTimeout } : {}),
            ...(nextWarning !== undefined ? { sessionTimeoutWarningMinutes: nextWarning } : {}),
            ...(assistanceRequestMode !== undefined ? { assistanceRequestMode } : {}),
            ...(assistanceRequestDestinations !== undefined ? { assistanceRequestDestinations } : {}),
            ...(assistanceRequestEmailAddress !== undefined ? { assistanceRequestEmailAddress } : {}),
            ...(assistanceRequestItsmSystem !== undefined ? { assistanceRequestItsmSystem } : {}),
            ...(assistanceRequestItsmEndpointUrl !== undefined ? { assistanceRequestItsmEndpointUrl } : {}),
            ...(assistanceRequestItsmAuthToken !== undefined ? { assistanceRequestItsmAuthToken } : {}),
            ...(assistanceRequestTeamsWebhookUrl !== undefined ? { assistanceRequestTeamsWebhookUrl } : {}),
            ...(alertingSlackWebhookUrl !== undefined ? { alertingSlackWebhookUrl } : {}),
            ...(alertingPagerDutyRoutingKey !== undefined ? { alertingPagerDutyRoutingKey } : {}),
            ...(alertRoutingPolicy !== undefined ? { alertRoutingPolicy } : {}),
            ...(iconProvider !== undefined ? { iconProvider } : {}),
            ...(stylePackage !== undefined ? { stylePackage } : {}),
            ...(supportEmailSmtpHost !== undefined ? { supportEmailSmtpHost } : {}),
            ...(supportEmailSmtpPort !== undefined ? { supportEmailSmtpPort } : {}),
            ...(supportEmailSmtpUsername !== undefined ? { supportEmailSmtpUsername } : {}),
            ...(supportEmailSmtpPassword !== undefined ? { supportEmailSmtpPassword } : {}),
            ...(supportEmailSmtpUseStartTls !== undefined ? { supportEmailSmtpUseStartTls } : {}),
            ...(supportEmailFromAddress !== undefined ? { supportEmailFromAddress } : {}),
            ...(dataProtectionMaskingMethods !== undefined ? { dataProtectionMaskingMethods } : {}),
            ...(dataProtectionEncryptionMethods !== undefined ? { dataProtectionEncryptionMethods } : {}),
            ...(debounceMs !== undefined ? { debounceMs } : {}),
            ...(allowedWorkspaceDataSourceTypes !== undefined ? { allowedWorkspaceDataSourceTypes } : {}),
            ...(defaultRuleThresholdPct !== undefined ? { defaultRuleThresholdPct } : {}),
            ...(defaultCatalogTermMatchThresholdPct !== undefined ? { defaultCatalogTermMatchThresholdPct } : {}),
            ...(exceptionFactJitRequestTimeoutMinutes !== undefined ? { exceptionFactJitRequestTimeoutMinutes } : {}),
          }

          if (
            merged.sessionTimeoutMinutes === prev.sessionTimeoutMinutes &&
            merged.sessionTimeoutWarningMinutes === prev.sessionTimeoutWarningMinutes &&
            merged.assistanceRequestMode === prev.assistanceRequestMode &&
            JSON.stringify(merged.assistanceRequestDestinations || []) === JSON.stringify(prev.assistanceRequestDestinations || []) &&
            merged.assistanceRequestEmailAddress === prev.assistanceRequestEmailAddress &&
            merged.assistanceRequestItsmSystem === prev.assistanceRequestItsmSystem &&
            merged.assistanceRequestItsmEndpointUrl === prev.assistanceRequestItsmEndpointUrl &&
            merged.assistanceRequestItsmAuthToken === prev.assistanceRequestItsmAuthToken &&
            merged.assistanceRequestTeamsWebhookUrl === prev.assistanceRequestTeamsWebhookUrl &&
            merged.alertingSlackWebhookUrl === prev.alertingSlackWebhookUrl &&
            merged.alertingPagerDutyRoutingKey === prev.alertingPagerDutyRoutingKey &&
            merged.supportEmailSmtpHost === prev.supportEmailSmtpHost &&
            merged.supportEmailSmtpPort === prev.supportEmailSmtpPort &&
            merged.supportEmailSmtpUsername === prev.supportEmailSmtpUsername &&
            merged.supportEmailSmtpPassword === prev.supportEmailSmtpPassword &&
            merged.supportEmailSmtpUseStartTls === prev.supportEmailSmtpUseStartTls &&
            merged.supportEmailFromAddress === prev.supportEmailFromAddress &&
            JSON.stringify(merged.dataProtectionMaskingMethods || []) === JSON.stringify(prev.dataProtectionMaskingMethods || []) &&
            JSON.stringify(merged.dataProtectionEncryptionMethods || []) === JSON.stringify(prev.dataProtectionEncryptionMethods || []) &&
            merged.debounceMs === prev.debounceMs &&
            merged.iconProvider === prev.iconProvider &&
            merged.stylePackage === prev.stylePackage &&
            JSON.stringify(merged.allowedWorkspaceDataSourceTypes || []) === JSON.stringify(prev.allowedWorkspaceDataSourceTypes || []) &&
            merged.defaultRuleThresholdPct === prev.defaultRuleThresholdPct &&
            merged.defaultCatalogTermMatchThresholdPct === prev.defaultCatalogTermMatchThresholdPct &&
            merged.exceptionFactJitRequestTimeoutMinutes === prev.exceptionFactJitRequestTimeoutMinutes
          ) {
            return prev
          }

          return merged
        })
      } catch {
        // Best-effort: do not fail settings load if app-config is unreachable.
      }
    }

    void loadAppConfig()

    return () => {
      cancelled = true
    }
  }, [applicationSettings?.apiBaseUrl, authToken])

  useEffect(() => {
    const syncTokenFromStorage = () => {
      setAuthToken(getAuthToken())
    }

    syncTokenFromStorage()
    if (typeof window !== 'undefined') {
      window.addEventListener('storage', syncTokenFromStorage)
      window.addEventListener('dq-auth-token-changed', syncTokenFromStorage)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('storage', syncTokenFromStorage)
        window.removeEventListener('dq-auth-token-changed', syncTokenFromStorage)
      }
    }
  }, [])

  useEffect(() => {
    if (!authToken) {
      return
    }

    void loadSettings()
  }, [authToken, loadSettings])

  const updateSettings = useCallback(async (payload: SettingsUpdatePayload): Promise<void> => {
    setIsLoading(true)
    clearContextError()

    try {
      const updatedAt = new Date().toISOString()
      const nextPreferences: SettingsPreferences = { ...preferences }

      switch (payload.category) {
        case 'profile': {
          if (!userSettings) break
          const next = { ...userSettings, ...payload.data, updatedAt } as UserSettings
          setUserSettings(next)
          nextPreferences.profile = next
          break
        }
        case 'notifications': {
          if (!notificationSettings) break
          const next = { ...notificationSettings, ...payload.data, updatedAt } as NotificationSettings
          setNotificationSettings(next)
          nextPreferences.notifications = next
          break
        }
        case 'display': {
          if (!displaySettings) break
          const next = {
            ...displaySettings,
            ...payload.data,
            ...(payload.data && 'theme' in payload.data
              ? { theme: normalizeDisplayTheme((payload.data as any).theme) }
              : {}),
            updatedAt,
          } as DisplaySettings
          setDisplaySettings(next)
          nextPreferences.display = next
          break
        }
        case 'workspace': {
          if (!workspaceSettings) break
          const next = { ...workspaceSettings, ...payload.data, updatedAt } as WorkspaceSettings
          setWorkspaceSettings(next)
          nextPreferences.workspace = next
          break
        }
        case 'security': {
          if (!securitySettings) break
          const next = { ...securitySettings, ...payload.data, updatedAt } as SecuritySettings
          setSecuritySettings(next)
          nextPreferences.security = next
          break
        }
        case 'api': {
          if (!apiSettings) break
          const next = { ...apiSettings, ...payload.data, updatedAt } as APISettings
          setAPISettings(next)
          nextPreferences.api = next
          break
        }
        case 'application': {
          if (!applicationSettings) break
          const next = { ...applicationSettings, ...payload.data, updatedAt } as ApplicationSettings
          setApplicationSettings(next)
          nextPreferences.application = next
          break
        }
      }

      setPreferences(nextPreferences)
      await persistPreferences(nextPreferences)
    } catch (err) {
      setContextError(err instanceof Error ? err.message : 'Failed to update settings')
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [preferences, userSettings, notificationSettings, displaySettings, workspaceSettings, securitySettings, apiSettings, applicationSettings, persistPreferences, clearContextError, setContextError])

  const loadAdminUsers = useCallback(async (): Promise<void> => {
    try {
      const token = getAuthToken()
      const response = await fetch(`${adminApiBase}/users`, {
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
        ? items.map((u: any) => {
            const { firstName, lastName } = resolvePersonName(u)
            const roles = Array.isArray(u.roles)
              ? u.roles.map((role: unknown) => String(role).trim()).filter(Boolean)
              : []
            const workspaces = Array.isArray(u.workspaces)
              ? u.workspaces.map((workspace: unknown) => String(workspace).trim()).filter(Boolean)
              : []
            const workspaceRoles = Array.isArray(u.workspace_roles)
              ? u.workspace_roles
                  .map((workspaceRole: any) => ({
                    workspaceId: String(workspaceRole.workspace_id ?? workspaceRole.workspaceId ?? '').trim(),
                    role: String(workspaceRole.role ?? '').trim(),
                  }))
                  .filter((workspaceRole: { workspaceId: string; role: string }) => Boolean(workspaceRole.workspaceId) && Boolean(workspaceRole.role))
              : []
            return {
              id: String(u.id),
              firstName: firstName || undefined,
              lastName: lastName || undefined,
              email: u.email ? String(u.email) : undefined,
              roles,
              workspaces,
              workspaceRoles,
            }
          })
        : []
      setAdminUsers(users)
    } catch (err) {
      setContextError(err instanceof Error ? err.message : 'Failed to load users')
    }
  }, [adminApiBase, setContextError])

  const loadAdminRoles = useCallback(async (): Promise<void> => {
    try {
      const token = getAuthToken()
      const response = await fetch(`${adminApiBase}/roles`, {
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
      })
      if (!response.ok) {
        throw new Error('Failed to fetch roles')
      }
      const data = await response.json()
      const items = Array.isArray(data) ? data : []
      const roles = items.map((role: any) => ({
        id: String(role.id),
        name: String(role.name || role.id),
        workspace: String(role.workspace || 'default'),
        permissions: Array.isArray(role.permissions)
          ? role.permissions.map((permission: unknown) => String(permission)).filter(Boolean)
          : [],
      }))
      setAdminRoles(roles)
    } catch (err) {
      setContextError(err instanceof Error ? err.message : 'Failed to load roles')
    }
  }, [adminApiBase, setContextError])

  const createAdminRole = useCallback(async (payload: { id: string; name: string; workspace: string; permissions: string[] }): Promise<void> => {
    setIsLoading(true)
    clearContextError()

    try {
      const token = getAuthToken()
      const response = await fetch(`${adminApiBase}/roles`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
        body: JSON.stringify(camelToSnake(payload)),
      })
      if (!response.ok) {
        const message = await response.text()
        throw new Error(message || 'Failed to create role')
      }
      await loadAdminRoles()
    } catch (err) {
      setContextError(err instanceof Error ? err.message : 'Failed to create role')
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [adminApiBase, loadAdminRoles, clearContextError, setContextError])

  const updateAdminRole = useCallback(async (roleId: string, payload: { name: string; workspace: string; permissions: string[] }): Promise<void> => {
    setIsLoading(true)
    clearContextError()

    try {
      const token = getAuthToken()
      const response = await fetch(`${adminApiBase}/roles/${encodeURIComponent(roleId)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
        body: JSON.stringify(camelToSnake(payload)),
      })
      if (!response.ok) {
        const message = await response.text()
        throw new Error(message || 'Failed to update role')
      }
      await loadAdminRoles()
    } catch (err) {
      setContextError(err instanceof Error ? err.message : 'Failed to update role')
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [adminApiBase, loadAdminRoles, clearContextError, setContextError])

  const updateAdminUser = useCallback(async (userId: string, payload: { roles: string[]; workspaces: string[] }): Promise<void> => {
    setIsLoading(true)
    clearContextError()

    try {
      const token = getAuthToken()
      const response = await fetch(`${adminApiBase}/users/${encodeURIComponent(userId)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
        body: JSON.stringify(camelToSnake(payload)),
      })
      if (!response.ok) {
        const message = await response.text()
        throw new Error(message || 'Failed to update user')
      }
      await loadAdminUsers()
    } catch (err) {
      setContextError(err instanceof Error ? err.message : 'Failed to update user')
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [adminApiBase, loadAdminUsers, clearContextError, setContextError])

  const resetUserProfile = useCallback(async (userId: string): Promise<void> => {
    setIsLoading(true)
    clearContextError()

    try {
      const token = getAuthToken()
      const response = await fetch(`${adminApiBase}/users/${userId}/reset-profile`, {
        method: 'POST',
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
      })
      if (!response.ok) {
        throw new Error('Failed to reset user profile')
      }
    } catch (err) {
      setContextError(err instanceof Error ? err.message : 'Failed to reset user profile')
    } finally {
      setIsLoading(false)
    }
  }, [adminApiBase, clearContextError, setContextError])

  const resetUserSettings = useCallback(async (userId: string): Promise<void> => {
    setIsLoading(true)
    clearContextError()

    try {
      const token = getAuthToken()
      const response = await fetch(`${adminApiBase}/users/${userId}/reset-settings`, {
        method: 'POST',
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
      })
      if (!response.ok) {
        throw new Error('Failed to reset user settings')
      }
    } catch (err) {
      setContextError(err instanceof Error ? err.message : 'Failed to reset user settings')
    } finally {
      setIsLoading(false)
    }
  }, [adminApiBase, clearContextError, setContextError])

  const saveAPIKey = useCallback(async (): Promise<string> => {
    if (!securitySettings) return ''
    setIsLoading(true)
    clearContextError()

    try {
      const newKeyId = `key_${Date.now()}`
      const newKey = {
        id: newKeyId,
        name: `API Key ${securitySettings.apiKeys.length + 1}`,
        createdAt: new Date().toISOString(),
      }
      const nextSecurity: SecuritySettings = {
        ...securitySettings,
        apiKeys: [...securitySettings.apiKeys, newKey],
        updatedAt: new Date().toISOString(),
      }
      const nextPreferences = { ...preferences, security: nextSecurity }
      setSecuritySettings(nextSecurity)
      setPreferences(nextPreferences)
      await persistPreferences(nextPreferences)

      return `sk_live_${Math.random().toString(36).substr(2, 20)}`
    } finally {
      setIsLoading(false)
    }
  }, [securitySettings, preferences, persistPreferences])

  const revokeAPIKey = useCallback(async (keyId: string): Promise<void> => {
    if (!securitySettings) return
    setIsLoading(true)
    clearContextError()

    try {
      const nextSecurity: SecuritySettings = {
        ...securitySettings,
        apiKeys: securitySettings.apiKeys.filter(key => key.id !== keyId),
        updatedAt: new Date().toISOString(),
      }
      const nextPreferences = { ...preferences, security: nextSecurity }
      setSecuritySettings(nextSecurity)
      setPreferences(nextPreferences)
      await persistPreferences(nextPreferences)
    } finally {
      setIsLoading(false)
    }
  }, [securitySettings, preferences, persistPreferences])

  const enableTwoFactor = useCallback(async (): Promise<string> => {
    if (!securitySettings) return ''
    setIsLoading(true)
    clearContextError()

    try {
      const secret = 'JBSWY3DPEBLW64TMMQ===='
      const nextSecurity: SecuritySettings = {
        ...securitySettings,
        twoFactorEnabled: true,
        updatedAt: new Date().toISOString(),
      }
      const nextPreferences = { ...preferences, security: nextSecurity }
      setSecuritySettings(nextSecurity)
      setPreferences(nextPreferences)
      await persistPreferences(nextPreferences)
      return secret
    } finally {
      setIsLoading(false)
    }
  }, [securitySettings, preferences, persistPreferences])

  const clearError = useCallback(() => {
    clearContextError()
  }, [clearContextError])

  const value: SettingsContextType = {
    userSettings,
    notificationSettings,
    displaySettings,
    workspaceSettings,
    securitySettings,
    apiSettings,
    applicationSettings,
    adminUsers,
    adminRoles,
    isLoading,
    error,
    errorReferenceId,
    updateSettings,
    loadSettings,
    loadAdminUsers,
    loadAdminRoles,
    updateAdminUser,
    createAdminRole,
    updateAdminRole,
    resetUserProfile,
    resetUserSettings,
    saveAPIKey,
    revokeAPIKey,
    enableTwoFactor,
    clearError,
  }

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}