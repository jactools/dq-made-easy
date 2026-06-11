/**
 * Settings types for user and workspace preferences
 */

export type SettingsCategory = 'profile' | 'workspace' | 'notifications' | 'display' | 'security' | 'api' | 'application'
export type IconProviderName = 'tabler' | 'lucide'
export type StylePackageName = 'custom-built-package' | 'tailwind' | 'astrowind' | 'data-web-css'

export interface AlertRoutingPolicy {
  deliveryTarget: 'app' | 'itsm' | 'both'
  channels: Array<'in_app' | 'email' | 'teams' | 'slack' | 'pagerduty'>
  mandatoryCategories: string[]
  mandatoryRoles: string[]
}

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

export interface NotificationSettings {
  userId: string
  emailOnApproval: boolean
  emailOnRejection: boolean
  emailOnTestingFailure: boolean
  emailDigestFrequency: 'immediate' | 'daily' | 'weekly' | 'never'
  pushNotifications: boolean
  teamsIntegration: boolean
  teamsWebhookUrl?: string
  teamsChannelId?: string
  teamsChannelName?: string
  teamsChannels?: Array<{ id: string; name: string; displayName: string }>
  /** ISO-8601 timestamp until which all notifications are silenced. Absent or past = not snoozed. */
  snoozedUntil?: string
  updatedAt: string
}

export interface DisplaySettings {
  userId: string
  theme: 'light' | 'dark' | 'auto'
  itemsPerPage: number
  compactMode: boolean
  showTooltips: boolean
  preferredDateFormat: 'MM/DD/YYYY' | 'DD/MM/YYYY' | 'YYYY-MM-DD'
  participateInPreviews: boolean
  catalogTermMatchThresholdPct?: number
  updatedAt: string
}

export interface WorkspaceSettings {
  workspaceId: string
  name: string
  description?: string
  alertRoutingPolicy?: AlertRoutingPolicy
  defaultRiskLevel: 'low' | 'medium' | 'high'
  requiresApprovalForActivation: boolean
  requiresTestingBeforeApproval: boolean
  autoRetestInterval?: number // days
  ruleNamingPrefix?: string
  maxListItems?: number
  enabledDataSources: string[]
  reconciliationDataSources: WorkspaceReconciliationDataSource[]
  disabledPlaygroundSourceBundleIds?: string[]
  updatedAt: string
}

export interface WorkspaceReconciliationDataSource {
  id: string
  name: string
  sourceType: string
  connectionString?: string
  connectionParameters: string
  description?: string
  updatedAt?: string
}

export interface SecuritySettings {
  userId: string
  twoFactorEnabled: boolean
  lastPasswordChange: string
  ipWhitelist: string[]
  apiKeys: Array<{
    id: string
    name: string
    createdAt: string
  }>
  lastLogin: string
  updatedAt: string
}

export interface APISettings {
  workspaceId: string
  webhookUrl: string
  rateLimitPerMinute: number
  allowedOrigins: string[]
  encryptionEnabled: boolean
  auditLoggingEnabled: boolean
  apiTimeout: number // seconds
  updatedAt: string
}

export interface ApplicationSettings {
  debounceMs: number
  alertRoutingPolicy?: AlertRoutingPolicy
  iconProvider?: IconProviderName
  stylePackage: StylePackageName

  // Authentication & SSO
  ssoEnabled: boolean
  ssoProvider: 'keycloak' | 'azure' | 'okta' | 'none'
  ssoIssuerUrl: string
  ssoClientId: string
  allowLocalAuth: boolean // Allow local login even if SSO is enabled
  
  // API Configuration
  apiBaseUrl: string
  apiVersion: string
  apiRetryAttempts: number
  apiRetryDelay: number // milliseconds
  
  // Admin Limits
  maxUsersPerWorkspace: number
  maxWorkspaces: number
  maxRulesPerWorkspace: number
  maxTemplatesPerWorkspace: number
  maxConcurrentTests: number
  allowedWorkspaceDataSourceTypes: string[]
  defaultRuleThresholdPct: number
  defaultCatalogTermMatchThresholdPct: number
  
  // Application Settings
  maintenanceMode: boolean
  maintenanceMessage: string
  allowSignup: boolean
  requireEmailVerification: boolean
  defaultUserRole: 'viewer' | 'editor' | 'reviewer'
  assistanceRequestMode?: 'email' | 'itsm'
  assistanceRequestDestinations: Array<'email' | 'itsm' | 'teams'>
  assistanceRequestEmailAddress: string
  assistanceRequestItsmSystem: string
  assistanceRequestItsmEndpointUrl: string
  assistanceRequestItsmAuthToken: string
  assistanceRequestTeamsWebhookUrl: string
  alertingSlackWebhookUrl: string
  alertingPagerDutyRoutingKey: string
  supportEmailSmtpHost: string
  supportEmailSmtpPort: number
  supportEmailSmtpUsername: string
  supportEmailSmtpPassword: string
  supportEmailSmtpUseStartTls: boolean
  supportEmailFromAddress: string
  dataProtectionMaskingMethods: string[]
  dataProtectionEncryptionMethods: string[]
  
  // Logging & Monitoring
  logLevel: 'debug' | 'info' | 'warn' | 'error'
  enableAnalytics: boolean
  enableCrashReporting: boolean
  
  // Feature Flags
  enableSuggestions: boolean
  enableBulkOperations: boolean
  enableVersioning: boolean
  enableExport: boolean
  
  // Data Retention
  auditLogRetentionDays: number
  testResultsRetentionDays: number
  deletedItemsRetentionDays: number
  exceptionFactRetentionDays: number
  exceptionFactArchiveRetentionDays: number
  exceptionAnalyticsProjectionRetentionDays: number
  exceptionFactPurgeBatchSize: number
  exceptionFactJitRequestTimeoutMinutes: number

  // Session management
  sessionTimeoutMinutes: number
  sessionTimeoutWarningMinutes: number

  // Agent session limits
  agentSessionTimeoutMinutes: number
  maxToolCallsPerSession: number

  // SIEM integration
  siemEnabled?: boolean
  siemEndpointUrl?: string | null
  siemApiToken?: string

  updatedAt: string
}

export interface AllSettings {
  userSettings: UserSettings
  notificationSettings: NotificationSettings
  // Global session timeout policy (minutes)
  sessionTimeoutMinutes?: number
  displaySettings: DisplaySettings
  workspaceSettings: WorkspaceSettings
  securitySettings: SecuritySettings
  apiSettings?: APISettings
  applicationSettings?: ApplicationSettings
}

export interface SettingsUpdatePayload {
  category: SettingsCategory
  data: Partial<UserSettings | NotificationSettings | DisplaySettings | WorkspaceSettings | SecuritySettings | APISettings | ApplicationSettings>
}
