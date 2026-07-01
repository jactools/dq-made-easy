import React, { useState, useEffect, useMemo, useRef } from 'react'
import { useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { useAuth } from '../hooks/useKeycloak'
import { toApiGroupV1Base } from '../config/api'
import { ApplicationSettings as ApplicationSettingsType, AlertRoutingPolicy, SecuritySettings, APISettings, WorkspaceSettings, type IconProviderName } from '../types/settings'
import { AppSelect, AppPageShell } from './app-primitives'
import { Button } from './Button'
import { PrimaryButton, SecondaryButton } from './Button'
import { AdminPageHeader } from './AdminPageHeader'
import { WorkspaceReconciliationDataSourcesEditor } from './WorkspaceReconciliationDataSourcesEditor'
import { AppIcon, AppTabs } from './app-primitives'
import './Settings.css'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { createSupportReferenceId, formatSupportReferenceId } from '../utils/supportReference'
import { PLAYGROUND_SOURCE_BUNDLES } from '../data/playgroundSourceBundles'
import { DEFAULT_STYLE_PACKAGE, STYLE_PACKAGE_OPTIONS, getStylePackageLabel } from '../contexts/styleThemeCatalog'
import type { StylePackageName } from '../types/settings'

type UiRegistryView = {
  source: string
  version: string
  cache_ttl_seconds?: number
  styles?: Array<{ id: string; label?: string }>
  component_bundles?: Array<{ id: string; label?: string }>
  metadata?: Record<string, unknown>
}

type AppSettingsTab = 'application' | 'security' | 'api'
type FeatureStage = 'off' | 'preview' | 'live'
type SettingsSection = { readonly id: string; readonly label: string }
type AgentDefaultAction = 'deny' | 'allow'

type AgentAccessAllowEntry = {
  agentType: string
  agentSource: string
  agentInstanceId: string
  requestOrigin: string
}

type AgentAccessPolicy = {
  defaultAction: AgentDefaultAction
  allowedAgents: AgentAccessAllowEntry[]
}

type FeatureLifecycleConfig = {
  debounceMs?: number
  iconProvider?: IconProviderName
  stylePackage?: StylePackageName
  ssoEnabled?: boolean
  ssoProvider?: 'keycloak' | 'azure' | 'okta' | 'none'
  ssoIssuer?: string | null
  ssoClientId?: string | null
  allowLocalAuth?: boolean
  apiVersion?: string
  apiRetryAttempts?: number
  apiRetryDelay?: number
  maxUsersPerWorkspace?: number
  maxWorkspaces?: number
  maxRulesPerWorkspace?: number
  maxTemplatesPerWorkspace?: number
  maxConcurrentTests?: number
  allowedWorkspaceDataSourceTypes?: string[]
  defaultRuleThresholdPct?: number
  defaultCatalogTermMatchThresholdPct?: number
  maintenanceMode?: boolean
  maintenanceMessage?: string
  allowSignup?: boolean
  requireEmailVerification?: boolean
  defaultUserRole?: 'viewer' | 'analyst' | 'data-steward' | 'editor' | 'reviewer'
  assistanceRequestMode?: 'email' | 'itsm'
  assistanceRequestDestinations?: Array<'email' | 'itsm' | 'teams'>
  assistanceRequestEmailAddress?: string
  assistanceRequestItsmSystem?: string
  assistanceRequestItsmEndpointUrl?: string
  assistanceRequestItsmAuthToken?: string
  assistanceRequestTeamsWebhookUrl?: string
  alertingSlackWebhookUrl?: string
  alertingPagerDutyRoutingKey?: string
  alertRoutingPolicy?: {
    deliveryTarget?: 'app' | 'itsm' | 'both'
    channels?: Array<'in_app' | 'email' | 'teams' | 'slack' | 'pagerduty'>
    mandatoryCategories?: string[]
    mandatoryRoles?: string[]
  }
  supportEmailSmtpHost?: string
  supportEmailSmtpPort?: number
  supportEmailSmtpUsername?: string
  supportEmailSmtpPassword?: string
  supportEmailSmtpUseStartTls?: boolean
  supportEmailFromAddress?: string
  dataProtectionMaskingMethods?: string[]
  dataProtectionEncryptionMethods?: string[]
  logLevel?: 'debug' | 'info' | 'warn' | 'error'
  enableAnalytics?: boolean
  enableCrashReporting?: boolean
  enableBulkOperations?: boolean
  enableVersioning?: boolean
  enableExport?: boolean
  auditLogRetentionDays?: number
  testResultsRetentionDays?: number
  deletedItemsRetentionDays?: number
  exceptionFactRetentionDays?: number
  exceptionFactArchiveRetentionDays?: number
  exceptionAnalyticsProjectionRetentionDays?: number
  exceptionFactPurgeBatchSize?: number
  exceptionFactJitRequestTimeoutMinutes?: number
  sessionTimeoutWarningMinutes?: number
  agentSessionTimeoutMinutes?: number
  maxToolCallsPerSession?: number
  metricsForwardingEnabled?: boolean
  metricsForwardUrl?: string | null
  siemEnabled?: boolean
  siemEndpointUrl?: string | null
  siemApiToken?: string | null
  openMetadataContractCacheTtlSeconds?: number
  agentAccessPolicy?: {
    defaultAction?: AgentDefaultAction
    allowedAgents?: Array<{
      agentType?: string
      agentSource?: string
      agentInstanceId?: string
      requestOrigin?: string
    }>
  }
  featureRuleValidation?: boolean
  featureRuleLifecycleManagement?: boolean
  featureRuleResultAggregation?: boolean
  featureRuleSuggestions?: boolean
  featureExceptionRecordHandling?: boolean
  featureRuleExecutionMonitoring?: boolean
  featureRuleDslV2?: boolean
  featureRuleValidationStage?: FeatureStage
  featureRuleLifecycleManagementStage?: FeatureStage
  featureRuleResultAggregationStage?: FeatureStage
  featureRuleSuggestionsStage?: FeatureStage
  featureExceptionRecordHandlingStage?: FeatureStage
  featureRuleExecutionMonitoringStage?: FeatureStage
}

const coerceBoolean = (value: unknown): boolean | null => {
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'number') {
    return value !== 0
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (['true', '1', 'yes', 'on'].includes(normalized)) {
      return true
    }
    if (['false', '0', 'no', 'off'].includes(normalized)) {
      return false
    }
  }
  return null
}

const APP_CONFIG_SAVE_VERIFY_KEYS = [
  'ssoEnabled',
  'ssoProvider',
  'iconProvider',
  'stylePackage',
  'ssoIssuer',
  'ssoClientId',
  'allowLocalAuth',
  'apiVersion',
  'apiRetryAttempts',
  'apiRetryDelay',
  'debounceMs',
  'maxUsersPerWorkspace',
  'maxWorkspaces',
  'maxRulesPerWorkspace',
  'maxTemplatesPerWorkspace',
  'maxConcurrentTests',
  'allowedWorkspaceDataSourceTypes',
  'defaultRuleThresholdPct',
  'defaultCatalogTermMatchThresholdPct',
  'maintenanceMode',
  'maintenanceMessage',
  'allowSignup',
  'requireEmailVerification',
  'defaultUserRole',
  'assistanceRequestMode',
  'assistanceRequestDestinations',
  'assistanceRequestEmailAddress',
  'assistanceRequestItsmSystem',
  'assistanceRequestItsmEndpointUrl',
  'assistanceRequestTeamsWebhookUrl',
  'alertRoutingPolicy',
  'supportEmailSmtpHost',
  'supportEmailSmtpPort',
  'supportEmailSmtpUsername',
  'supportEmailSmtpUseStartTls',
  'supportEmailFromAddress',
  'dataProtectionMaskingMethods',
  'dataProtectionEncryptionMethods',
  'logLevel',
  'enableAnalytics',
  'enableCrashReporting',
  'featureRuleSuggestions',
  'featureRuleValidation',
  'featureRuleLifecycleManagement',
  'featureRuleResultAggregation',
  'featureExceptionRecordHandling',
  'featureRuleExecutionMonitoring',
  'featureRuleDslV2',
  'featureRuleValidationStage',
  'featureRuleLifecycleManagementStage',
  'featureRuleResultAggregationStage',
  'featureRuleSuggestionsStage',
  'featureExceptionRecordHandlingStage',
  'featureRuleExecutionMonitoringStage',
  'featureGovernanceDrift',
  'featureGovernanceDriftStage',
  'enableBulkOperations',
  'enableVersioning',
  'enableExport',
  'auditLogRetentionDays',
  'testResultsRetentionDays',
  'deletedItemsRetentionDays',
  'exceptionFactRetentionDays',
  'exceptionFactArchiveRetentionDays',
  'exceptionAnalyticsProjectionRetentionDays',
  'exceptionFactPurgeBatchSize',
  'exceptionFactJitRequestTimeoutMinutes',
  'sessionTimeoutWarningMinutes',
  'agentSessionTimeoutMinutes',
  'maxToolCallsPerSession',
  'siemEnabled',
  'siemEndpointUrl',
  'siemApiToken',
  'agentAccessPolicy',
] as const

const APP_CONFIG_SECRET_FIELDS = new Set([
  'assistanceRequestItsmAuthToken',
  'supportEmailSmtpPassword',
  'alertingSlackWebhookUrl',
  'alertingPagerDutyRoutingKey',
  'siemApiToken',
])

const getConfigValue = (payload: Record<string, unknown>, key: string): unknown => payload[key]

type LoadAppConfigOptions = {
  clearExistingError?: boolean
}

type LoadAppConfigResult = FeatureLifecycleConfig | null

const areConfigValuesEquivalent = (expected: unknown, actual: unknown): boolean => {
  if (expected === actual) {
    return true
  }
  if ((expected === null || expected === undefined) && (actual === null || actual === undefined)) {
    return true
  }
  if (typeof expected === 'number' && typeof actual === 'number') {
    return Number.isFinite(expected) && Number.isFinite(actual) && expected === actual
  }
  if (typeof expected === 'boolean' && typeof actual === 'boolean') {
    return expected === actual
  }
  return String(expected ?? '') === String(actual ?? '')
}

const getRejectedConfigFields = (
  expectedPayload: Record<string, unknown>,
  persistedPayload: Record<string, unknown>,
  keysToVerify: readonly string[],
): string[] => {
  const rejected: string[] = []
  for (const key of keysToVerify) {
    if (!(key in expectedPayload)) {
      continue
    }

    const expectedValue = expectedPayload[key]
    const persistedValue = getConfigValue(persistedPayload, key)

    if (!areConfigValuesEquivalent(expectedValue, persistedValue)) {
      rejected.push(key)
    }
  }

  return rejected
}

const getChangedConfigFields = (
  previousConfig: FeatureLifecycleConfig | null,
  nextConfig: Record<string, unknown>,
): string[] => {
  if (!previousConfig) {
    return []
  }

  const changed: string[] = []
  for (const key of APP_CONFIG_SAVE_VERIFY_KEYS) {
    if (!(key in nextConfig)) {
      continue
    }
    const previousValue = getConfigValue(previousConfig as Record<string, unknown>, key)
    if (previousValue === undefined) {
      continue
    }

    const nextValue = nextConfig[key]
    if (!areConfigValuesEquivalent(previousValue, nextValue)) {
      changed.push(key)
    }
  }

  return changed
}

export const buildAppConfigPayload = (
  appConfigData: FeatureLifecycleConfig | null,
  applicationData: ApplicationSettingsType,
) => {
  const persistedConfig = appConfigData
    ? Object.fromEntries(Object.entries(appConfigData).filter(([key]) => !APP_CONFIG_SECRET_FIELDS.has(key)))
    : {}

  const includeSecretValue = (value: string | undefined): string | undefined => {
    const trimmed = (value || '').trim()
    return trimmed ? trimmed : undefined
  }

  return {
    ...persistedConfig,
    ssoEnabled: applicationData.ssoEnabled,
    ssoProvider: applicationData.ssoProvider,
    iconProvider: applicationData.iconProvider,
    stylePackage: applicationData.stylePackage,
    ssoIssuer: applicationData.ssoIssuerUrl,
    ssoClientId: applicationData.ssoClientId,
    allowLocalAuth: applicationData.allowLocalAuth,
    apiVersion: applicationData.apiVersion,
    apiRetryAttempts: applicationData.apiRetryAttempts,
    apiRetryDelay: applicationData.apiRetryDelay,
    debounceMs: applicationData.debounceMs,
    maxUsersPerWorkspace: applicationData.maxUsersPerWorkspace,
    maxWorkspaces: applicationData.maxWorkspaces,
    maxRulesPerWorkspace: applicationData.maxRulesPerWorkspace,
    maxTemplatesPerWorkspace: applicationData.maxTemplatesPerWorkspace,
    maxConcurrentTests: applicationData.maxConcurrentTests,
    allowedWorkspaceDataSourceTypes: applicationData.allowedWorkspaceDataSourceTypes,
    defaultRuleThresholdPct: applicationData.defaultRuleThresholdPct,
    defaultCatalogTermMatchThresholdPct: applicationData.defaultCatalogTermMatchThresholdPct,
    maintenanceMode: applicationData.maintenanceMode,
    maintenanceMessage: applicationData.maintenanceMessage,
    allowSignup: applicationData.allowSignup,
    requireEmailVerification: applicationData.requireEmailVerification,
    defaultUserRole: applicationData.defaultUserRole,
    assistanceRequestMode: applicationData.assistanceRequestMode,
    assistanceRequestDestinations: applicationData.assistanceRequestDestinations,
    assistanceRequestEmailAddress: applicationData.assistanceRequestEmailAddress,
    assistanceRequestItsmSystem: applicationData.assistanceRequestItsmSystem,
    assistanceRequestItsmEndpointUrl: applicationData.assistanceRequestItsmEndpointUrl,
    ...(includeSecretValue(applicationData.assistanceRequestItsmAuthToken)
      ? { assistanceRequestItsmAuthToken: applicationData.assistanceRequestItsmAuthToken }
      : {}),
    assistanceRequestTeamsWebhookUrl: applicationData.assistanceRequestTeamsWebhookUrl,
    ...(includeSecretValue(applicationData.alertingSlackWebhookUrl)
      ? { alertingSlackWebhookUrl: applicationData.alertingSlackWebhookUrl }
      : {}),
    ...(includeSecretValue(applicationData.alertingPagerDutyRoutingKey)
      ? { alertingPagerDutyRoutingKey: applicationData.alertingPagerDutyRoutingKey }
      : {}),
    alertRoutingPolicy: applicationData.alertRoutingPolicy,
    supportEmailSmtpHost: applicationData.supportEmailSmtpHost,
    supportEmailSmtpPort: applicationData.supportEmailSmtpPort,
    supportEmailSmtpUsername: applicationData.supportEmailSmtpUsername,
    ...(includeSecretValue(applicationData.supportEmailSmtpPassword)
      ? { supportEmailSmtpPassword: applicationData.supportEmailSmtpPassword }
      : {}),
    supportEmailSmtpUseStartTls: applicationData.supportEmailSmtpUseStartTls,
    supportEmailFromAddress: applicationData.supportEmailFromAddress,
    dataProtectionMaskingMethods: applicationData.dataProtectionMaskingMethods,
    dataProtectionEncryptionMethods: applicationData.dataProtectionEncryptionMethods,
    logLevel: applicationData.logLevel,
    enableAnalytics: applicationData.enableAnalytics,
    enableCrashReporting: applicationData.enableCrashReporting,
    // Always use the current UI toggle value when saving Suggestions.
    featureRuleSuggestions: applicationData.enableSuggestions,
    featureRuleDslV2: Boolean(appConfigData?.featureRuleDslV2),
    enableBulkOperations: applicationData.enableBulkOperations,
    enableVersioning: applicationData.enableVersioning,
    enableExport: applicationData.enableExport,
    auditLogRetentionDays: applicationData.auditLogRetentionDays,
    testResultsRetentionDays: applicationData.testResultsRetentionDays,
    deletedItemsRetentionDays: applicationData.deletedItemsRetentionDays,
    exceptionFactRetentionDays: applicationData.exceptionFactRetentionDays,
    exceptionFactArchiveRetentionDays: applicationData.exceptionFactArchiveRetentionDays,
    exceptionAnalyticsProjectionRetentionDays: applicationData.exceptionAnalyticsProjectionRetentionDays,
    exceptionFactPurgeBatchSize: applicationData.exceptionFactPurgeBatchSize,
    exceptionFactJitRequestTimeoutMinutes: applicationData.exceptionFactJitRequestTimeoutMinutes,
    siemEnabled:
      typeof applicationData.siemEnabled === 'boolean'
        ? applicationData.siemEnabled
        : (typeof appConfigData?.siemEnabled === 'boolean' ? appConfigData.siemEnabled : false),
    siemEndpointUrl:
      applicationData.siemEndpointUrl ?? appConfigData?.siemEndpointUrl ?? null,
    ...(includeSecretValue(applicationData.siemApiToken ?? appConfigData?.siemApiToken)
      ? { siemApiToken: applicationData.siemApiToken ?? appConfigData?.siemApiToken }
      : {}),
    openMetadataContractCacheTtlSeconds:
      typeof appConfigData?.openMetadataContractCacheTtlSeconds === 'number'
        ? appConfigData.openMetadataContractCacheTtlSeconds
        : 300,
    sessionTimeoutMinutes:
      typeof applicationData.sessionTimeoutMinutes === 'number' ? applicationData.sessionTimeoutMinutes : undefined,
    sessionTimeoutWarningMinutes:
      typeof applicationData.sessionTimeoutWarningMinutes === 'number' ? applicationData.sessionTimeoutWarningMinutes : undefined,
    agentSessionTimeoutMinutes:
      typeof applicationData.agentSessionTimeoutMinutes === 'number' ? applicationData.agentSessionTimeoutMinutes : undefined,
    maxToolCallsPerSession:
      typeof applicationData.maxToolCallsPerSession === 'number' ? applicationData.maxToolCallsPerSession : undefined,
  }
}

export const mergeApplicationDataFromSettings = (
  current: ApplicationSettingsType | null,
  settingsApplicationData: ApplicationSettingsType | null,
): ApplicationSettingsType | null => {
  if (!settingsApplicationData) {
    return current
  }

  if (!current) {
    return settingsApplicationData
  }

  // Only sync user-scoped preference fields from SettingsContext.
  // Global runtime toggles (SSO, feature flags) are sourced from /app-config.
  return {
    ...current,
    apiBaseUrl: settingsApplicationData.apiBaseUrl,
    iconProvider: settingsApplicationData.iconProvider,
    stylePackage: settingsApplicationData.stylePackage,
  }
}

const PREVIEW_FEATURE_ADMIN_FIELDS = [
  {
    id: 'ruleValidation',
    label: 'Rule Validation',
    enabledKey: 'featureRuleValidation',
    stageKey: 'featureRuleValidationStage',
  },
  {
    id: 'ruleLifecycleManagement',
    label: 'Rule Lifecycle Management',
    enabledKey: 'featureRuleLifecycleManagement',
    stageKey: 'featureRuleLifecycleManagementStage',
  },
  {
    id: 'ruleResultAggregation',
    label: 'Rule Result Aggregation',
    enabledKey: 'featureRuleResultAggregation',
    stageKey: 'featureRuleResultAggregationStage',
  },
  {
    id: 'ruleSuggestions',
    label: 'Rule Suggestions',
    enabledKey: 'featureRuleSuggestions',
    stageKey: 'featureRuleSuggestionsStage',
  },
  {
    id: 'exceptionRecordHandling',
    label: 'Exception Record Handling',
    enabledKey: 'featureExceptionRecordHandling',
    stageKey: 'featureExceptionRecordHandlingStage',
  },
  {
    id: 'ruleExecutionMonitoring',
    label: 'Rule Execution Monitoring',
    enabledKey: 'featureRuleExecutionMonitoring',
    stageKey: 'featureRuleExecutionMonitoringStage',
  },
] as const

const APPLICATION_SECTIONS = [
  { id: 'auth-sso', label: 'Authentication & SSO' },
  { id: 'api-config', label: 'API Configuration' },
  { id: 'admin-limits', label: 'Admin Limits' },
  { id: 'workspace-configuration', label: 'Workspace Configuration' },
  { id: 'datasource-governance', label: 'Datasource Governance' },
  { id: 'agent-access-control', label: 'Agent Access Control' },
  { id: 'app-behavior', label: 'Application Behavior' },
  { id: 'logging-monitoring', label: 'Logging & Monitoring' },
  { id: 'feature-flags', label: 'Feature Flags' },
  { id: 'feature-lifecycle', label: 'Preview Feature Lifecycle' },
  { id: 'data-retention', label: 'Data Retention' },
] as const

const SECURITY_SECTIONS = [
  { id: 'two-factor-auth', label: 'Two-Factor Authentication' },
  { id: 'ip-whitelist', label: 'IP Whitelist' },
  { id: 'api-keys', label: 'API Keys' },
  { id: 'last-login', label: 'Last Login' },
] as const

const API_SECTIONS = [
  { id: 'api-basic', label: 'API Configuration' },
] as const

const DEFAULT_ALERT_ROUTING_POLICY = {
  deliveryTarget: 'app' as const,
  channels: ['in_app'] as Array<'in_app' | 'email' | 'teams' | 'slack' | 'pagerduty'>,
  mandatoryCategories: [] as string[],
  mandatoryRoles: [] as string[],
}

const DEFAULT_AGENT_ACCESS_POLICY: AgentAccessPolicy = {
  defaultAction: 'deny',
  allowedAgents: [],
}

const normalizeAgentAccessPolicy = (value: unknown): AgentAccessPolicy => {
  const source = value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
  const defaultActionCandidate = String(source.defaultAction ?? source.default_action ?? 'deny').trim().toLowerCase()
  const defaultAction: AgentDefaultAction = defaultActionCandidate === 'allow' ? 'allow' : 'deny'
  const rawAllowedAgents = Array.isArray(source.allowedAgents)
    ? source.allowedAgents
    : Array.isArray(source.allowed_agents)
      ? source.allowed_agents
      : []

  const allowedAgents = rawAllowedAgents
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const entry = item as Record<string, unknown>
      return {
        agentType: String(entry.agentType ?? entry.agent_type ?? '').trim(),
        agentSource: String(entry.agentSource ?? entry.agent_source ?? '').trim(),
        agentInstanceId: String(entry.agentInstanceId ?? entry.agent_instance_id ?? '').trim(),
        requestOrigin: String(entry.requestOrigin ?? entry.request_origin ?? '').trim(),
      }
    })

  return {
    defaultAction,
    allowedAgents,
  }
}

const normalizeAlertRoutingPolicy = (value: unknown): AlertRoutingPolicy => {
  const source = value && typeof value === 'object' ? value as Record<string, unknown> : {}
  const channels = Array.isArray(source.channels)
    ? Array.from(new Set(source.channels.map((item) => String(item).trim()).filter(Boolean)))
    : [...DEFAULT_ALERT_ROUTING_POLICY.channels]
  const deliveryTarget = String(source.deliveryTarget ?? DEFAULT_ALERT_ROUTING_POLICY.deliveryTarget)
  return {
    deliveryTarget: deliveryTarget === 'itsm' || deliveryTarget === 'both' ? deliveryTarget : DEFAULT_ALERT_ROUTING_POLICY.deliveryTarget,
    channels: channels.filter((item) => ['in_app', 'email', 'teams', 'slack', 'pagerduty'].includes(item)) as Array<'in_app' | 'email' | 'teams' | 'slack' | 'pagerduty'>,
    mandatoryCategories: Array.isArray(source.mandatoryCategories)
      ? Array.from(new Set(source.mandatoryCategories.map((item) => String(item).trim()).filter(Boolean)))
      : [],
    mandatoryRoles: Array.isArray(source.mandatoryRoles)
      ? Array.from(new Set(source.mandatoryRoles.map((item) => String(item).trim()).filter(Boolean)))
      : [],
  }
}

const normalizeWorkspaceSettings = (workspaceData: WorkspaceSettings | null | undefined): WorkspaceSettings | null => {
  if (!workspaceData) {
    return null
  }

  return {
    ...workspaceData,
    alertRoutingPolicy: normalizeAlertRoutingPolicy(workspaceData.alertRoutingPolicy),
    enabledDataSources: Array.from(new Set(workspaceData.enabledDataSources.filter((source) => Boolean(source)))),
    disabledPlaygroundSourceBundleIds: Array.isArray(workspaceData.disabledPlaygroundSourceBundleIds)
      ? Array.from(new Set(workspaceData.disabledPlaygroundSourceBundleIds.filter((bundleId) => Boolean(bundleId))))
      : [],
    reconciliationDataSources: Array.isArray(workspaceData.reconciliationDataSources)
      ? workspaceData.reconciliationDataSources.map((datasource) => ({
          ...datasource,
          connectionString: datasource.connectionString || '',
          connectionParameters: datasource.connectionParameters || '{\n  "host": "",\n  "port": ""\n}',
          description: datasource.description || '',
        }))
      : [],
  }
}

const normalizeApplicationSettings = (
  applicationData: ApplicationSettingsType | null | undefined,
): ApplicationSettingsType | null => {
  if (!applicationData) {
    return null
  }

  return {
    ...applicationData,
    alertRoutingPolicy: normalizeAlertRoutingPolicy(applicationData.alertRoutingPolicy),
    allowedWorkspaceDataSourceTypes: Array.isArray(applicationData.allowedWorkspaceDataSourceTypes)
      ? Array.from(new Set(applicationData.allowedWorkspaceDataSourceTypes.filter((value) => Boolean(value))))
      : ['adls', 's3', 'oracle', 'sql_server'],
    iconProvider: applicationData.iconProvider || 'tabler',
    stylePackage: applicationData.stylePackage || DEFAULT_STYLE_PACKAGE,
  }
}

export const ApplicationSettings: React.FC = () => {
  const settings = useSettings()
  const auth = useAuth()
  const [activeTab, setActiveTab] = useState<AppSettingsTab>('application')
  const [hasChanges, setHasChanges] = useState(false)

  const [showSaveSuccess, setShowSaveSuccess] = useState(false)
  const [saveStatusMessage, setSaveStatusMessage] = useState<string | null>(null)
  const [appConfigError, setAppConfigError] = useState<string | null>(null)
  const [appConfigErrorReferenceId, setAppConfigErrorReferenceId] = useState<string | null>(null)
  const [show2FAModal, setShow2FAModal] = useState(false)
  const [qrSecret, setQRSecret] = useState('')
  const [newApiKey, setNewApiKey] = useState('')
  const [activeSection, setActiveSection] = useState<string>('')
  const [uiRegistryView, setUiRegistryView] = useState<UiRegistryView | null>(null)

  // Application tab state
  const [applicationData, setApplicationData] = useState<ApplicationSettingsType | null>(
    normalizeApplicationSettings(settings.applicationSettings)
  )

  const selectedStylePackage = applicationData?.stylePackage || DEFAULT_STYLE_PACKAGE
  const stylePackageOptions = useMemo(() => {
    if (STYLE_PACKAGE_OPTIONS.some((option) => option.value === selectedStylePackage)) {
      return STYLE_PACKAGE_OPTIONS
    }

    return [
      { value: selectedStylePackage, label: `${getStylePackageLabel(selectedStylePackage)} (current)` },
      ...STYLE_PACKAGE_OPTIONS,
    ]
  }, [selectedStylePackage])

  useEffect(() => {
    let cancelled = false

    const loadUiRegistry = async () => {
      try {
        const apiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
        const token = getAuthToken()
        const response = await fetch(`${apiBase}/ui-registry`, {
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        })

        if (!response.ok) {
          return
        }

        const view = (await response.json()) as UiRegistryView
        if (!cancelled) {
          setUiRegistryView(view)
        }
      } catch {
        if (!cancelled) {
          setUiRegistryView(null)
        }
      }
    }

    void loadUiRegistry()

    return () => {
      cancelled = true
    }
  }, [settings.applicationSettings?.apiBaseUrl])

  // Security tab state
  const [securityData, setSecurityData] = useState<SecuritySettings | null>(
    settings.securitySettings || null
  )

  // API tab state
  const [apiData, setApiData] = useState<APISettings | null>(settings.apiSettings || null)
  const [workspaceData, setWorkspaceData] = useState<WorkspaceSettings | null>(normalizeWorkspaceSettings(settings.workspaceSettings))
  const [appConfigData, setAppConfigData] = useState<FeatureLifecycleConfig | null>(null)
  const [dataEncryptionKeys, setDataEncryptionKeys] = useState<Array<{
    id: string
    keyName: string
    keyScope: string
    workspaceId: string | null
    keyAlgorithm: string
    keyFingerprint: string
    isActive: boolean
    createdAt: string | null
    updatedAt: string | null
    createdBy: string | null
  }>>([])
  const [newDataEncryptionKeyName, setNewDataEncryptionKeyName] = useState('')
  const [newDataEncryptionKeyScope, setNewDataEncryptionKeyScope] = useState<'app' | 'workspace'>('app')
  const [newDataEncryptionKeyWorkspaceId, setNewDataEncryptionKeyWorkspaceId] = useState('')
  const [newDataEncryptionKeyAlgorithm, setNewDataEncryptionKeyAlgorithm] = useState('fernet')
  const [newDataEncryptionKeyMaterial, setNewDataEncryptionKeyMaterial] = useState('')
  const [newDataEncryptionKeyActive, setNewDataEncryptionKeyActive] = useState(true)
  const latestAppConfigRequestRef = useRef(0)

  const currentWorkspaceId = useMemo(
    () => auth.currentWorkspaceId || auth.user?.workspaceRoles?.[0]?.workspaceId || null,
    [auth.currentWorkspaceId, auth.user?.workspaceRoles],
  )

  const canManageWorkspaceSettings = useMemo(
    () => Boolean(
      currentWorkspaceId
      && auth.user?.workspaceRoles?.some(
        (workspaceRole) => String(workspaceRole.workspaceId || '').trim() === currentWorkspaceId
          && workspaceRole.role === 'admin',
      ),
    ),
    [auth.user?.workspaceRoles, currentWorkspaceId],
  )
  const workspaceSettingsDisabled = !canManageWorkspaceSettings

  const loadAppConfig = async (
    apiBaseUrl?: string,
    options?: LoadAppConfigOptions,
  ): Promise<LoadAppConfigResult> => {
    const requestId = ++latestAppConfigRequestRef.current
    const clearExistingError = options?.clearExistingError ?? true
    if (clearExistingError) {
      setAppConfigError(null)
      setAppConfigErrorReferenceId(null)
    }
    try {
      const apiBase = toApiGroupV1Base('system', apiBaseUrl || settings.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/app-config`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })
      if (!response.ok) {
        if (requestId !== latestAppConfigRequestRef.current) {
          return null
        }
          setAppConfigError(`Unable to load application config (${response.status}).`) 
          setAppConfigErrorReferenceId(createSupportReferenceId())
        return null
      }
      const config = snakeToCamel<Record<string, unknown>>(await response.json())
      if (requestId !== latestAppConfigRequestRef.current) {
        return null
      }
      setAppConfigData(config)

      // Keep UI auth toggles aligned with runtime app-config values.
      setApplicationData((current) => {
        const base = normalizeApplicationSettings(current) || normalizeApplicationSettings(settings.applicationSettings)
        if (!base) return current

        const configRecord = snakeToCamel<Record<string, unknown>>(config)

        const ssoEnabled = coerceBoolean(getConfigValue(configRecord, 'ssoEnabled'))
        const allowLocalAuth = coerceBoolean(getConfigValue(configRecord, 'allowLocalAuth'))
        const enableSuggestions = coerceBoolean(getConfigValue(configRecord, 'featureRuleSuggestions'))

        return {
          ...base,
          sessionTimeoutMinutes:
            typeof getConfigValue(configRecord, 'sessionTimeoutMinutes') === 'number'
              ? (getConfigValue(configRecord, 'sessionTimeoutMinutes') as number)
              : base.sessionTimeoutMinutes,
          sessionTimeoutWarningMinutes:
            typeof getConfigValue(configRecord, 'sessionTimeoutWarningMinutes') === 'number'
              ? (getConfigValue(configRecord, 'sessionTimeoutWarningMinutes') as number)
              : base.sessionTimeoutWarningMinutes,
          agentSessionTimeoutMinutes:
            typeof getConfigValue(configRecord, 'agentSessionTimeoutMinutes') === 'number'
              ? (getConfigValue(configRecord, 'agentSessionTimeoutMinutes') as number)
              : base.agentSessionTimeoutMinutes,
          maxToolCallsPerSession:
            typeof getConfigValue(configRecord, 'maxToolCallsPerSession') === 'number'
              ? (getConfigValue(configRecord, 'maxToolCallsPerSession') as number)
              : base.maxToolCallsPerSession,
          assistanceRequestMode:
            (getConfigValue(configRecord, 'assistanceRequestMode') as ApplicationSettingsType['assistanceRequestMode']) ??
            base.assistanceRequestMode,
          assistanceRequestDestinations:
            (getConfigValue(configRecord, 'assistanceRequestDestinations') as ApplicationSettingsType['assistanceRequestDestinations']) ??
            base.assistanceRequestDestinations,
          assistanceRequestEmailAddress:
            (getConfigValue(configRecord, 'assistanceRequestEmailAddress') as string | undefined) ??
            base.assistanceRequestEmailAddress,
          assistanceRequestItsmSystem:
            (getConfigValue(configRecord, 'assistanceRequestItsmSystem') as ApplicationSettingsType['assistanceRequestItsmSystem']) ??
            base.assistanceRequestItsmSystem,
          assistanceRequestItsmEndpointUrl:
            (getConfigValue(configRecord, 'assistanceRequestItsmEndpointUrl') as string | undefined) ??
            base.assistanceRequestItsmEndpointUrl,
          assistanceRequestItsmAuthToken:
            (getConfigValue(configRecord, 'assistanceRequestItsmAuthToken') as string | undefined) ??
            base.assistanceRequestItsmAuthToken,
          assistanceRequestTeamsWebhookUrl:
            (getConfigValue(configRecord, 'assistanceRequestTeamsWebhookUrl') as string | undefined) ??
            base.assistanceRequestTeamsWebhookUrl,
          alertingSlackWebhookUrl:
            (getConfigValue(configRecord, 'alertingSlackWebhookUrl') as string | undefined) ??
            base.alertingSlackWebhookUrl,
          alertingPagerDutyRoutingKey:
            (getConfigValue(configRecord, 'alertingPagerDutyRoutingKey') as string | undefined) ??
            base.alertingPagerDutyRoutingKey,
          alertRoutingPolicy:
            (getConfigValue(configRecord, 'alertRoutingPolicy') as ApplicationSettingsType['alertRoutingPolicy'] | undefined) ??
            base.alertRoutingPolicy,
          supportEmailSmtpHost:
            (getConfigValue(configRecord, 'supportEmailSmtpHost') as string | undefined) ??
            base.supportEmailSmtpHost,
          supportEmailSmtpPort:
            typeof getConfigValue(configRecord, 'supportEmailSmtpPort') === 'number'
              ? (getConfigValue(configRecord, 'supportEmailSmtpPort') as number)
              : base.supportEmailSmtpPort,
          supportEmailSmtpUsername:
            (getConfigValue(configRecord, 'supportEmailSmtpUsername') as string | undefined) ??
            base.supportEmailSmtpUsername,
          supportEmailSmtpPassword:
            (getConfigValue(configRecord, 'supportEmailSmtpPassword') as string | undefined) ??
            base.supportEmailSmtpPassword,
          supportEmailSmtpUseStartTls:
            coerceBoolean(getConfigValue(configRecord, 'supportEmailSmtpUseStartTls')) ??
            base.supportEmailSmtpUseStartTls,
          supportEmailFromAddress:
            (getConfigValue(configRecord, 'supportEmailFromAddress') as string | undefined) ??
            base.supportEmailFromAddress,
          dataProtectionMaskingMethods:
            Array.isArray(getConfigValue(configRecord, 'dataProtectionMaskingMethods'))
              ? (getConfigValue(configRecord, 'dataProtectionMaskingMethods') as string[])
              : base.dataProtectionMaskingMethods,
          dataProtectionEncryptionMethods:
            Array.isArray(getConfigValue(configRecord, 'dataProtectionEncryptionMethods'))
              ? (getConfigValue(configRecord, 'dataProtectionEncryptionMethods') as string[])
              : base.dataProtectionEncryptionMethods,
          ssoEnabled: ssoEnabled ?? base.ssoEnabled,
          ssoProvider: (getConfigValue(configRecord, 'ssoProvider') as ApplicationSettingsType['ssoProvider'] | undefined) || base.ssoProvider,
          ssoIssuerUrl: (getConfigValue(configRecord, 'ssoIssuer') as string | undefined) || base.ssoIssuerUrl,
          ssoClientId: (getConfigValue(configRecord, 'ssoClientId') as string | undefined) || base.ssoClientId,
          allowLocalAuth: allowLocalAuth ?? base.allowLocalAuth,
          apiVersion: (getConfigValue(configRecord, 'apiVersion') as string | undefined) || base.apiVersion,
          apiRetryAttempts:
            typeof getConfigValue(configRecord, 'apiRetryAttempts') === 'number'
              ? (getConfigValue(configRecord, 'apiRetryAttempts') as number)
              : base.apiRetryAttempts,
          apiRetryDelay:
            typeof getConfigValue(configRecord, 'apiRetryDelay') === 'number'
              ? (getConfigValue(configRecord, 'apiRetryDelay') as number)
              : base.apiRetryDelay,
          allowedWorkspaceDataSourceTypes:
            Array.isArray(getConfigValue(configRecord, 'allowedWorkspaceDataSourceTypes'))
              ? (getConfigValue(configRecord, 'allowedWorkspaceDataSourceTypes') as string[])
              : base.allowedWorkspaceDataSourceTypes,
          debounceMs:
            typeof getConfigValue(configRecord, 'debounceMs') === 'number'
              ? (getConfigValue(configRecord, 'debounceMs') as number)
              : base.debounceMs,
          iconProvider:
            (getConfigValue(configRecord, 'iconProvider') as IconProviderName | undefined) ??
            base.iconProvider,
          stylePackage:
            (getConfigValue(configRecord, 'stylePackage') as StylePackageName | undefined) ??
            base.stylePackage,
          maxUsersPerWorkspace:
            typeof getConfigValue(configRecord, 'maxUsersPerWorkspace') === 'number'
              ? (getConfigValue(configRecord, 'maxUsersPerWorkspace') as number)
              : base.maxUsersPerWorkspace,
          maxWorkspaces:
            typeof getConfigValue(configRecord, 'maxWorkspaces') === 'number'
              ? (getConfigValue(configRecord, 'maxWorkspaces') as number)
              : base.maxWorkspaces,
          maxRulesPerWorkspace:
            typeof getConfigValue(configRecord, 'maxRulesPerWorkspace') === 'number'
              ? (getConfigValue(configRecord, 'maxRulesPerWorkspace') as number)
              : base.maxRulesPerWorkspace,
          maxTemplatesPerWorkspace:
            typeof getConfigValue(configRecord, 'maxTemplatesPerWorkspace') === 'number'
              ? (getConfigValue(configRecord, 'maxTemplatesPerWorkspace') as number)
              : base.maxTemplatesPerWorkspace,
          maxConcurrentTests:
            typeof getConfigValue(configRecord, 'maxConcurrentTests') === 'number'
              ? (getConfigValue(configRecord, 'maxConcurrentTests') as number)
              : base.maxConcurrentTests,
          defaultRuleThresholdPct:
            typeof getConfigValue(configRecord, 'defaultRuleThresholdPct') === 'number'
              ? (getConfigValue(configRecord, 'defaultRuleThresholdPct') as number)
              : base.defaultRuleThresholdPct,
          defaultCatalogTermMatchThresholdPct:
            typeof getConfigValue(configRecord, 'defaultCatalogTermMatchThresholdPct') === 'number'
              ? (getConfigValue(configRecord, 'defaultCatalogTermMatchThresholdPct') as number)
              : base.defaultCatalogTermMatchThresholdPct,
          maintenanceMode:
            typeof getConfigValue(configRecord, 'maintenanceMode') === 'boolean'
              ? (getConfigValue(configRecord, 'maintenanceMode') as boolean)
              : base.maintenanceMode,
          maintenanceMessage: (getConfigValue(configRecord, 'maintenanceMessage') as string | undefined) ?? base.maintenanceMessage,
          allowSignup:
            typeof getConfigValue(configRecord, 'allowSignup') === 'boolean'
              ? (getConfigValue(configRecord, 'allowSignup') as boolean)
              : base.allowSignup,
          requireEmailVerification:
            typeof getConfigValue(configRecord, 'requireEmailVerification') === 'boolean'
              ? (getConfigValue(configRecord, 'requireEmailVerification') as boolean)
              : base.requireEmailVerification,
          defaultUserRole:
            (getConfigValue(configRecord, 'defaultUserRole') as ApplicationSettingsType['defaultUserRole']) ??
            base.defaultUserRole,
          logLevel:
            (getConfigValue(configRecord, 'logLevel') as ApplicationSettingsType['logLevel']) ?? base.logLevel,
          enableAnalytics:
            typeof getConfigValue(configRecord, 'enableAnalytics') === 'boolean'
              ? (getConfigValue(configRecord, 'enableAnalytics') as boolean)
              : base.enableAnalytics,
          enableCrashReporting:
            typeof getConfigValue(configRecord, 'enableCrashReporting') === 'boolean'
              ? (getConfigValue(configRecord, 'enableCrashReporting') as boolean)
              : base.enableCrashReporting,
          enableSuggestions: enableSuggestions ?? base.enableSuggestions,
          enableBulkOperations:
            typeof getConfigValue(configRecord, 'enableBulkOperations') === 'boolean'
              ? (getConfigValue(configRecord, 'enableBulkOperations') as boolean)
              : base.enableBulkOperations,
          enableVersioning:
            typeof getConfigValue(configRecord, 'enableVersioning') === 'boolean'
              ? (getConfigValue(configRecord, 'enableVersioning') as boolean)
              : base.enableVersioning,
          enableExport:
            typeof getConfigValue(configRecord, 'enableExport') === 'boolean'
              ? (getConfigValue(configRecord, 'enableExport') as boolean)
              : base.enableExport,
          auditLogRetentionDays:
            typeof getConfigValue(configRecord, 'auditLogRetentionDays') === 'number'
              ? (getConfigValue(configRecord, 'auditLogRetentionDays') as number)
              : base.auditLogRetentionDays,
          testResultsRetentionDays:
            typeof getConfigValue(configRecord, 'testResultsRetentionDays') === 'number'
              ? (getConfigValue(configRecord, 'testResultsRetentionDays') as number)
              : base.testResultsRetentionDays,
          deletedItemsRetentionDays:
            typeof getConfigValue(configRecord, 'deletedItemsRetentionDays') === 'number'
              ? (getConfigValue(configRecord, 'deletedItemsRetentionDays') as number)
              : base.deletedItemsRetentionDays,
          exceptionFactRetentionDays:
            typeof getConfigValue(configRecord, 'exceptionFactRetentionDays') === 'number'
              ? (getConfigValue(configRecord, 'exceptionFactRetentionDays') as number)
              : base.exceptionFactRetentionDays,
          exceptionFactArchiveRetentionDays:
            typeof getConfigValue(configRecord, 'exceptionFactArchiveRetentionDays') === 'number'
              ? (getConfigValue(configRecord, 'exceptionFactArchiveRetentionDays') as number)
              : base.exceptionFactArchiveRetentionDays,
          exceptionAnalyticsProjectionRetentionDays:
            typeof getConfigValue(configRecord, 'exceptionAnalyticsProjectionRetentionDays') === 'number'
              ? (getConfigValue(configRecord, 'exceptionAnalyticsProjectionRetentionDays') as number)
              : base.exceptionAnalyticsProjectionRetentionDays,
          exceptionFactPurgeBatchSize:
            typeof getConfigValue(configRecord, 'exceptionFactPurgeBatchSize') === 'number'
              ? (getConfigValue(configRecord, 'exceptionFactPurgeBatchSize') as number)
              : base.exceptionFactPurgeBatchSize,
          exceptionFactJitRequestTimeoutMinutes:
            typeof getConfigValue(configRecord, 'exceptionFactJitRequestTimeoutMinutes') === 'number'
              ? (getConfigValue(configRecord, 'exceptionFactJitRequestTimeoutMinutes') as number)
              : base.exceptionFactJitRequestTimeoutMinutes,
        }
      })

      return config
    } catch {
      if (requestId !== latestAppConfigRequestRef.current) {
        return null
      }
      setAppConfigError('Unable to load application config.')
      setAppConfigErrorReferenceId(createSupportReferenceId())
      setAppConfigData(null)
      return null
    }
  }

  const handleSave = async () => {
    const saveTraceId = Date.now().toString(36)
    const logPrefix = `[ApplicationSettings][save:${saveTraceId}]`
    try {
      console.info(`${logPrefix} Save started`, { activeTab })
      setAppConfigError(null)
      setAppConfigErrorReferenceId(null)
      setSaveStatusMessage(null)
      switch (activeTab) {
        case 'application':
          if (!applicationData) return
          // Keep API base URL user-specific; global settings are persisted to app-config.
          console.info(`${logPrefix} Saving user-scoped application preferences`)
          const nextStylePackage = applicationData.stylePackage || DEFAULT_STYLE_PACKAGE
          const currentStylePackage = settings.applicationSettings?.stylePackage || DEFAULT_STYLE_PACKAGE
          await settings.updateSettings({
            category: 'application',
            data: {
              apiBaseUrl: applicationData.apiBaseUrl,
              ...(nextStylePackage !== currentStylePackage ? { stylePackage: nextStylePackage } : {}),
            },
          })
          {
            const token = getAuthToken()
            const apiBase = toApiGroupV1Base('system', applicationData.apiBaseUrl || settings.applicationSettings?.apiBaseUrl)
            const appConfigPayload = buildAppConfigPayload(appConfigData, applicationData)

            console.info(`${logPrefix} Saving /app-config payload`, {
              apiBase,
              changedFields: getChangedConfigFields(appConfigData, appConfigPayload as Record<string, unknown>),
            })

            const response = await fetch(`${apiBase}/app-config`, {
              method: 'PUT',
              headers: {
                'Content-Type': 'application/json',
                ...(token && { Authorization: `Bearer ${token}` }),
              },
              body: JSON.stringify(camelToSnake(appConfigPayload)),
            })

            console.info(`${logPrefix} /app-config response received`, { status: response.status, ok: response.ok })

            if (!response.ok) {
              const errorText = await response.text().catch(() => '')
              throw new Error(
                `Failed to save application config (${response.status})${errorText ? `: ${errorText}` : ''}`
              )
            }

            const persistedConfig = snakeToCamel<Record<string, unknown> | null>(await response.json().catch(() => null))
            const changedFields = getChangedConfigFields(
              appConfigData,
              appConfigPayload as Record<string, unknown>,
            )

            if (persistedConfig && typeof persistedConfig === 'object') {
              const rejectedFields = getRejectedConfigFields(
                appConfigPayload as Record<string, unknown>,
                persistedConfig as Record<string, unknown>,
                changedFields,
              )
              if (rejectedFields.length > 0) {
                console.warn(`${logPrefix} Save verification failed against PUT response`, {
                  rejectedFields,
                })
                throw new Error(
                  `The server rejected one or more settings: ${rejectedFields.join(', ')}. ` +
                  'Check server environment overrides or policy constraints.'
                )
              }
            }

            const reloadedConfig = await loadAppConfig(applicationData.apiBaseUrl)
            if (!reloadedConfig) {
              console.warn(`${logPrefix} Save verification failed: reload returned no config`)
              throw new Error('Unable to verify saved settings because reloading application config failed.')
            }

            const reloadedRejectedFields = getRejectedConfigFields(
              appConfigPayload as Record<string, unknown>,
              reloadedConfig as Record<string, unknown>,
              changedFields,
            )

            if (reloadedRejectedFields.length > 0) {
              console.warn(`${logPrefix} Save verification failed after reload`, {
                reloadedRejectedFields,
              })
              throw new Error(
                `The server did not persist one or more settings: ${reloadedRejectedFields.join(', ')}. ` +
                'Check server environment overrides or policy constraints.'
              )
            }

            console.info(`${logPrefix} Save verification succeeded`)

          }
          if (workspaceData && canManageWorkspaceSettings) {
            console.info(`${logPrefix} Saving workspace settings`)
            const normalizedWorkspaceData = normalizeWorkspaceSettings(workspaceData)
            if (!normalizedWorkspaceData) {
              throw new Error('Workspace settings are empty or invalid.')
            }
            const allowedSourceTypes = new Set(
              (applicationData?.allowedWorkspaceDataSourceTypes || ['adls', 's3', 'oracle', 'sql_server']).map((value) =>
                String(value || '').trim().toLowerCase(),
              ),
            )
            if (normalizedWorkspaceData.reconciliationDataSources.length) {
              for (const datasource of normalizedWorkspaceData.reconciliationDataSources) {
                const sourceType = String(datasource.sourceType || '').trim().toLowerCase()
                if (allowedSourceTypes.size > 0 && !allowedSourceTypes.has(sourceType)) {
                  throw new Error(`Datasource type "${datasource.sourceType}" is not allowed for this workspace.`)
                }
                const parameters = String(datasource.connectionParameters || '').trim()
                if (parameters) {
                  try {
                    JSON.parse(parameters)
                  } catch {
                    throw new Error(`Datasource "${datasource.name || datasource.id}" has invalid JSON connection parameters.`)
                  }
                }
              }
            }
            await settings.updateSettings({ category: 'workspace', data: normalizedWorkspaceData })
            const workspaceId = String(normalizedWorkspaceData.workspaceId || currentWorkspaceId || '').trim()
            if (workspaceId) {
              const token = getAuthToken()
              const workspaceApiBase = toApiGroupV1Base('rulebuilder', applicationData?.apiBaseUrl || settings.applicationSettings?.apiBaseUrl)
              const workspaceResponse = await fetch(`${workspaceApiBase}/workspaces/${encodeURIComponent(workspaceId)}`, {
                method: 'PUT',
                headers: {
                  'Content-Type': 'application/json',
                  ...(token && { Authorization: `Bearer ${token}` }),
                },
                body: JSON.stringify(camelToSnake({
                  alertRoutingPolicy: normalizedWorkspaceData.alertRoutingPolicy || DEFAULT_ALERT_ROUTING_POLICY,
                })),
              })
              if (!workspaceResponse.ok) {
                const errorText = await workspaceResponse.text().catch(() => '')
                throw new Error(
                  `Failed to save workspace alert routing (${workspaceResponse.status})${errorText ? `: ${errorText}` : ''}`
                )
              }
            }
          }
          break
        case 'security':
          if (!securityData) return
          console.info(`${logPrefix} Saving security settings`)
          await settings.updateSettings({ category: 'security', data: securityData })
          break
        case 'api':
          if (!apiData) return
          console.info(`${logPrefix} Saving API settings`)
          await settings.updateSettings({ category: 'api', data: apiData })
          break
      }
      setHasChanges(false)
      setShowSaveSuccess(true)
      setSaveStatusMessage('Settings saved successfully')
      console.info(`${logPrefix} Save completed successfully`)
      setTimeout(() => setShowSaveSuccess(false), 3000)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save application config'
      setAppConfigError(message)
      setAppConfigErrorReferenceId(createSupportReferenceId())
      setSaveStatusMessage(message)
      console.error('Failed to save settings:', error)
    }
  }

  const handleReset = () => {
    switch (activeTab) {
      case 'application':
        setApplicationData(normalizeApplicationSettings(settings.applicationSettings))
        setWorkspaceData(normalizeWorkspaceSettings(settings.workspaceSettings))
        loadAppConfig(settings.applicationSettings?.apiBaseUrl)
        break
      case 'security':
        setSecurityData(settings.securitySettings || null)
        break
      case 'api':
        setApiData(settings.apiSettings || null)
        break
    }
    setHasChanges(false)
  }

  const handleGenerateAPIKey = async () => {
    try {
      await settings.saveAPIKey()
      setNewApiKey(`api-key-${Date.now()}`)
      setTimeout(() => setNewApiKey(''), 5000)
    } catch (error) {
      console.error('Error generating API key:', error)
    }
  }

  const handleEnable2FA = async () => {
    try {
      const secret = await settings.enableTwoFactor()
      setQRSecret(secret)
      setShow2FAModal(true)
    } catch (error) {
      console.error('Error enabling 2FA:', error)
    }
  }

  const handleRevokeAPIKey = async (keyId: string) => {
    try {
      await settings.revokeAPIKey(keyId)
    } catch (error) {
      console.error('Error revoking API key:', error)
    }
  }

  const scrollToSection = (sectionId: string) => {
    const element = document.getElementById(sectionId)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setActiveSection(sectionId)
    }
  }

  const getSectionsForTab = (): readonly SettingsSection[] => {
    switch (activeTab) {
      case 'application':
        return APPLICATION_SECTIONS
      case 'security':
        return SECURITY_SECTIONS
      case 'api':
        return API_SECTIONS
      default:
        return APPLICATION_SECTIONS
    }
  }

  const getSelectedSectionId = (sections: readonly SettingsSection[]): string => {
    if (sections.some((section) => section.id === activeSection)) {
      return activeSection
    }

    return sections[0]?.id ?? ''
  }

  const renderSectionsNav = (sections: readonly SettingsSection[], navId: string) => (
    <div className="settings-sections-nav settings-sections-nav--header">
      <span className="settings-sections-nav-label">Jump to section:</span>
      <div className="settings-sections-nav-scroll">
        <AppTabs
          ariaLabel={navId}
          value={getSelectedSectionId(sections)}
          onChange={scrollToSection}
          className="settings-sections-nav-control"
          tabs={sections.map((section) => ({
            value: section.id,
            label: section.label,
            title: `Jump to ${section.label}`,
          }))}
        />
      </div>
    </div>
  )

  const appConfigErrorReference = useMemo(
    () => (appConfigError ? appConfigErrorReferenceId || createSupportReferenceId() : null),
    [appConfigError, appConfigErrorReferenceId]
  )

  const disabledPlaygroundSourceBundleIds = workspaceData?.disabledPlaygroundSourceBundleIds ?? []

  const setPlaygroundSourceBundleEnabled = (bundleId: string, enabled: boolean) => {
    setWorkspaceData((current) => {
      const workspace = normalizeWorkspaceSettings(current)
      if (!workspace) {
        return current
      }

      const disabledIds = workspace.disabledPlaygroundSourceBundleIds ?? []
      const nextDisabledIds = enabled
        ? disabledIds.filter((currentBundleId) => currentBundleId !== bundleId)
        : Array.from(new Set([...disabledIds, bundleId]))

      return {
        ...workspace,
        disabledPlaygroundSourceBundleIds: nextDisabledIds,
      }
    })
    setHasChanges(true)
  }

  const updateAgentAccessPolicy = (updater: (current: AgentAccessPolicy) => AgentAccessPolicy) => {
    setAppConfigData((current) => {
      const currentPolicy = normalizeAgentAccessPolicy(current?.agentAccessPolicy)
      return {
        ...(current || {}),
        agentAccessPolicy: updater(currentPolicy),
      }
    })
    setHasChanges(true)
  }

  const currentAgentAccessPolicy = useMemo(
    () => normalizeAgentAccessPolicy(appConfigData?.agentAccessPolicy),
    [appConfigData?.agentAccessPolicy],
  )

  useEffect(() => {
    setApplicationData((current) =>
      mergeApplicationDataFromSettings(current, settings.applicationSettings || null)
    )
    setWorkspaceData(normalizeWorkspaceSettings(settings.workspaceSettings))
    setSecurityData(settings.securitySettings || null)
    setApiData(settings.apiSettings || null)
    loadAppConfig(settings.applicationSettings?.apiBaseUrl, { clearExistingError: false })
    setHasChanges(false)
  }, [settings.applicationSettings, settings.workspaceSettings, settings.securitySettings, settings.apiSettings])

  const canManageEncryptionRegistry = auth.hasScope('dq:config:manage')

  useEffect(() => {
    if (!canManageEncryptionRegistry) {
      setDataEncryptionKeys([])
      return
    }

    let cancelled = false
    const loadDataEncryptionKeys = async () => {
      try {
        const apiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
        const token = getAuthToken()
        const response = await fetch(`${apiBase}/encryption-keys`, {
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        })
        if (!response.ok) {
          throw new Error(`Unable to load encryption keys (${response.status})`)
        }
        const payload = snakeToCamel<Array<Record<string, unknown>>>(await response.json())
        if (cancelled) {
          return
        }
        setDataEncryptionKeys(payload.map((key) => ({
          id: String(key.id || ''),
          keyName: String(key.keyName || ''),
          keyScope: String(key.keyScope || ''),
          workspaceId: key.workspaceId ? String(key.workspaceId) : null,
          keyAlgorithm: String(key.keyAlgorithm || ''),
          keyFingerprint: String(key.keyFingerprint || ''),
          isActive: Boolean(key.isActive),
          createdAt: key.createdAt ? String(key.createdAt) : null,
          updatedAt: key.updatedAt ? String(key.updatedAt) : null,
          createdBy: key.createdBy ? String(key.createdBy) : null,
        })))
      } catch {
        if (!cancelled) {
          setDataEncryptionKeys([])
        }
      }
    }

    void loadDataEncryptionKeys()

    return () => {
      cancelled = true
    }
  }, [canManageEncryptionRegistry, settings.applicationSettings?.apiBaseUrl])

  const createDataEncryptionKey = async () => {
    try {
      if (!canManageEncryptionRegistry) {
        setSaveStatusMessage('App-admin access is required to manage the key registry.')
        setShowSaveSuccess(false)
        return
      }
      if (!newDataEncryptionKeyName.trim() || !newDataEncryptionKeyMaterial.trim()) {
        setSaveStatusMessage('Key name and key material are required.')
        setShowSaveSuccess(false)
        return
      }

      const apiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/encryption-keys`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          key_name: newDataEncryptionKeyName.trim(),
          key_scope: newDataEncryptionKeyScope,
          workspace_id: newDataEncryptionKeyScope === 'workspace' ? newDataEncryptionKeyWorkspaceId.trim() : null,
          key_algorithm: newDataEncryptionKeyAlgorithm.trim() || 'fernet',
          key_material: newDataEncryptionKeyMaterial.trim(),
          is_active: newDataEncryptionKeyActive,
        }),
      })

      if (!response.ok) {
        throw new Error(`Unable to create encryption key (${response.status})`)
      }

      const createdKey = snakeToCamel<Record<string, unknown>>(await response.json())
      setDataEncryptionKeys((current) => [
        {
          id: String(createdKey.id || ''),
          keyName: String(createdKey.keyName || ''),
          keyScope: String(createdKey.keyScope || ''),
          workspaceId: createdKey.workspaceId ? String(createdKey.workspaceId) : null,
          keyAlgorithm: String(createdKey.keyAlgorithm || ''),
          keyFingerprint: String(createdKey.keyFingerprint || ''),
          isActive: Boolean(createdKey.isActive),
          createdAt: createdKey.createdAt ? String(createdKey.createdAt) : null,
          updatedAt: createdKey.updatedAt ? String(createdKey.updatedAt) : null,
          createdBy: createdKey.createdBy ? String(createdKey.createdBy) : null,
        },
        ...current,
      ])
      setNewDataEncryptionKeyName('')
      setNewDataEncryptionKeyScope('app')
      setNewDataEncryptionKeyWorkspaceId('')
      setNewDataEncryptionKeyAlgorithm('fernet')
      setNewDataEncryptionKeyMaterial('')
      setNewDataEncryptionKeyActive(true)
      setSaveStatusMessage('Encryption key added.')
      setShowSaveSuccess(true)
    } catch (error) {
      setSaveStatusMessage(error instanceof Error ? error.message : 'Unable to create encryption key.')
      setShowSaveSuccess(false)
    }
  }

  if (settings.error && !applicationData && !workspaceData && !securityData && !apiData) {
    return (
      <AppPageShell className="settings-container">
        <AdminPageHeader
          title="Application Settings"
          subtitle={
            <>
              {settings.error}
              {settings.errorReferenceId && (
                <>
                  <br />
                  {formatSupportReferenceId(settings.errorReferenceId)}
                </>
              )}
            </>
          }
        />
        <div className="settings-content">
          <div className="settings-panel">
            <div className="settings-actions">
              <PrimaryButton onClick={() => settings.loadSettings()}>
                Retry
              </PrimaryButton>
            </div>
          </div>
        </div>
      </AppPageShell>
    )
  }

  if (!applicationData || !workspaceData || !securityData || !apiData) {
    return (
      <AppPageShell className="settings-container">
        <AdminPageHeader title="Application Settings" subtitle="Loading application settings..." />
        <div className="settings-content">
          <div className="settings-panel" />
        </div>
      </AppPageShell>
    )
  }

  return (
    <AppPageShell className="settings-container">
      <AdminPageHeader
        title="Application Settings"
        subtitle="Configure application-wide settings, limits, and workspace defaults"
        supplementary={renderSectionsNav(getSectionsForTab(), 'Application settings sections')}
        actions={
          hasChanges ? (
            <>
              <SecondaryButton onClick={handleReset}>Cancel</SecondaryButton>
              <PrimaryButton onClick={handleSave}>Save Changes</PrimaryButton>
            </>
          ) : undefined
        }
      />
      <div className="settings-content">
        {(appConfigError || settings.error || (showSaveSuccess && saveStatusMessage)) && (
          <div className={`settings-message ${appConfigError || settings.error ? 'error' : 'success'}`} role="status" aria-live="polite">
            <AppIcon name={appConfigError || settings.error ? 'exclamation-circle' : 'check-circle'} />
            <span>
              {appConfigError || settings.error || saveStatusMessage}
              {(appConfigErrorReference || settings.errorReferenceId) && (appConfigError || settings.error) && (
                <>
                  <br />
                  {formatSupportReferenceId(appConfigErrorReference || settings.errorReferenceId || '')}
                </>
              )}
            </span>
            {(appConfigError || settings.error) && (
              <button onClick={() => { setAppConfigError(null); setAppConfigErrorReferenceId(null); settings.clearError() }}>
                Dismiss
              </button>
            )}
          </div>
        )}

        {/* Application Tab */}
        {activeTab === 'application' && (
        <div className="settings-panel">
          <div className="settings-form">
            <div id="app-behavior" className="settings-section">
              <h3>Application Behavior</h3>
              <div className="form-group">
                <label htmlFor="sessionTimeoutMinutes">Session timeout (minutes)</label>
                <input
                  id="sessionTimeoutMinutes"
                  type="number"
                  min={1}
                  max={1440}
                  value={applicationData.sessionTimeoutMinutes ?? 0}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, sessionTimeoutMinutes: parseInt(e.target.value || '0') })
                    setHasChanges(true)
                  }}
                />
                <p className="info-text">Global idle timeout enforced for all users.</p>
              </div>
              <div className="form-group">
                <label htmlFor="sessionTimeoutWarningMinutes">Session timeout warning lead time (minutes)</label>
                <input
                  id="sessionTimeoutWarningMinutes"
                  type="number"
                  min={1}
                  max={1440}
                  value={applicationData.sessionTimeoutWarningMinutes ?? 10}
                  onChange={(e) => {
                    setApplicationData({
                      ...applicationData,
                      sessionTimeoutWarningMinutes: parseInt(e.target.value || '0'),
                    })
                    setHasChanges(true)
                  }}
                />
                <p className="info-text">Shows a warning before the session expires. The warning is capped by the timeout itself.</p>
              </div>

              <div className="form-group">
                <AppSelect
                  id="iconProvider"
                  label="Icon provider"
                  value={applicationData.iconProvider || 'tabler'}
                  onChange={(value) => {
                    setApplicationData({
                      ...applicationData,
                      iconProvider: value as IconProviderName,
                    })
                    setHasChanges(true)
                  }}
                  options={[
                    { value: 'tabler', label: 'Tabler' },
                    { value: 'lucide', label: 'Lucide' },
                  ]}
                />
                <p className="info-text">Controls the package-backed icon provider used by the app-owned icon seam.</p>
              </div>

              <div className="form-group">
                <AppSelect
                  id="stylePackage"
                  label="Style package"
                  value={selectedStylePackage}
                  onChange={(value) => {
                    setApplicationData({
                      ...applicationData,
                      stylePackage: value,
                    })
                    setHasChanges(true)
                  }}
                  options={stylePackageOptions.map((option) => ({
                    value: option.value,
                    label: getStylePackageLabel(option.value),
                  }))}
                />
                <p className="info-text">Controls which package-backed stylesheet the app loads at runtime.</p>
              </div>
              {uiRegistryView && (
                <div className="form-group">
                  <h4>UI registry snapshot</h4>
                  <p className="info-text">
                    Source: {uiRegistryView.source} | Version: {uiRegistryView.version} | Styles: {uiRegistryView.styles?.length || 0} | Component bundles: {uiRegistryView.component_bundles?.length || 0}
                  </p>
                  {uiRegistryView.metadata?.storage_table && (
                    <p className="info-text">Stored in {String(uiRegistryView.metadata.storage_table)}</p>
                  )}
                </div>
              )}
            </div>
            {/* Authentication & SSO Section */}
            <div id="auth-sso" className="settings-section">
              <h3>Authentication & SSO</h3>
              
              <div className="form-group checkbox">
                <input
                  id="ssoEnabled"
                  type="checkbox"
                  checked={applicationData.ssoEnabled}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, ssoEnabled: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="ssoEnabled">Enable Single Sign-On (SSO)</label>
              </div>

              {applicationData.ssoEnabled && (
                <>
                  <div className="form-group">
                    <AppSelect
                      id="ssoProvider"
                      label="SSO Provider"
                      value={applicationData.ssoProvider}
                      onChange={(value) => {
                        setApplicationData({
                          ...applicationData,
                          ssoProvider: value as any,
                        })
                        setHasChanges(true)
                      }}
                      options={[
                        { value: 'none', label: 'None' },
                        { value: 'keycloak', label: 'Keycloak' },
                        { value: 'azure', label: 'Azure AD' },
                        { value: 'okta', label: 'Okta' },
                      ]}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="ssoIssuerUrl">SSO Issuer URL</label>
                    <input
                      id="ssoIssuerUrl"
                      type="url"
                      value={applicationData.ssoIssuerUrl}
                      onChange={(e) => {
                        setApplicationData({ ...applicationData, ssoIssuerUrl: e.target.value })
                        setHasChanges(true)
                      }}
                      placeholder="https://your-idp.example.com/realms/your-realm"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="ssoClientId">SSO Client ID</label>
                    <input
                      id="ssoClientId"
                      type="text"
                      value={applicationData.ssoClientId}
                      onChange={(e) => {
                        setApplicationData({ ...applicationData, ssoClientId: e.target.value })
                        setHasChanges(true)
                      }}
                      placeholder="dq-rules-ui"
                    />
                  </div>

                  <div className="form-group checkbox">
                    <input
                      id="allowLocalAuth"
                      type="checkbox"
                      checked={applicationData.allowLocalAuth}
                      onChange={(e) => {
                        setApplicationData({ ...applicationData, allowLocalAuth: e.target.checked })
                        setHasChanges(true)
                      }}
                    />
                    <label htmlFor="allowLocalAuth">Allow local authentication (fallback)</label>
                  </div>
                </>
              )}
            </div>

            <div id="data-protection" className="settings-section">
              <h3>Data Protection</h3>

              <div className="form-group">
                <label htmlFor="dataProtectionMaskingMethods">Masking methods</label>
                <textarea
                  id="dataProtectionMaskingMethods"
                  value={(applicationData.dataProtectionMaskingMethods || []).join('\n')}
                  onChange={(e) => {
                    setApplicationData({
                      ...applicationData,
                      dataProtectionMaskingMethods: e.target.value
                        .split('\n')
                        .map((method) => method.trim())
                        .filter(Boolean),
                    })
                    setHasChanges(true)
                  }}
                  placeholder="none\nredact\npartial\ntokenize"
                  rows={4}
                />
              </div>

              <div className="form-group">
                <label htmlFor="dataProtectionEncryptionMethods">Encryption methods</label>
                <textarea
                  id="dataProtectionEncryptionMethods"
                  value={(applicationData.dataProtectionEncryptionMethods || []).join('\n')}
                  onChange={(e) => {
                    setApplicationData({
                      ...applicationData,
                      dataProtectionEncryptionMethods: e.target.value
                        .split('\n')
                        .map((method) => method.trim())
                        .filter(Boolean),
                    })
                    setHasChanges(true)
                  }}
                  placeholder="fernet"
                  rows={3}
                />
              </div>

              {canManageEncryptionRegistry && (
                <>
                  <div className="form-group">
                    <label htmlFor="newDataEncryptionKeyName">Key name</label>
                    <input
                      id="newDataEncryptionKeyName"
                      type="text"
                      value={newDataEncryptionKeyName}
                      onChange={(e) => setNewDataEncryptionKeyName(e.target.value)}
                      placeholder="workspace-default-key"
                    />
                  </div>

                  <div className="form-group">
                    <AppSelect
                      id="newDataEncryptionKeyScope"
                      label="Key scope"
                      value={newDataEncryptionKeyScope}
                      onChange={(value) => setNewDataEncryptionKeyScope(value as 'app' | 'workspace')}
                      options={[
                        { value: 'app', label: 'App' },
                        { value: 'workspace', label: 'Workspace' },
                      ]}
                    />
                  </div>

                  {newDataEncryptionKeyScope === 'workspace' && (
                    <div className="form-group">
                      <label htmlFor="newDataEncryptionKeyWorkspaceId">Workspace ID</label>
                      <input
                        id="newDataEncryptionKeyWorkspaceId"
                        type="text"
                        value={newDataEncryptionKeyWorkspaceId}
                        onChange={(e) => setNewDataEncryptionKeyWorkspaceId(e.target.value)}
                        placeholder="workspace-uuid"
                      />
                    </div>
                  )}

                  <div className="form-group">
                    <label htmlFor="newDataEncryptionKeyAlgorithm">Algorithm</label>
                    <input
                      id="newDataEncryptionKeyAlgorithm"
                      type="text"
                      value={newDataEncryptionKeyAlgorithm}
                      onChange={(e) => setNewDataEncryptionKeyAlgorithm(e.target.value)}
                      placeholder="fernet"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="newDataEncryptionKeyMaterial">Key material</label>
                    <textarea
                      id="newDataEncryptionKeyMaterial"
                      value={newDataEncryptionKeyMaterial}
                      onChange={(e) => setNewDataEncryptionKeyMaterial(e.target.value)}
                      placeholder="Paste the secret key material here"
                      rows={4}
                    />
                  </div>

                  <div className="form-group checkbox">
                    <input
                      id="newDataEncryptionKeyActive"
                      type="checkbox"
                      checked={newDataEncryptionKeyActive}
                      onChange={(e) => setNewDataEncryptionKeyActive(e.target.checked)}
                    />
                    <label htmlFor="newDataEncryptionKeyActive">Active</label>
                  </div>

                  <div className="form-group">
                    <Button type="button" variant="primary" onClick={() => void createDataEncryptionKey()}>
                      Add encryption key
                    </Button>
                  </div>

                  <div className="form-group">
                    <h4>Registered keys</h4>
                    <div className="settings-metadata-list">
                      {dataEncryptionKeys.length === 0 ? (
                        <p className="info-text">No encryption keys registered yet.</p>
                      ) : dataEncryptionKeys.map((key) => (
                        <div key={key.id} className="settings-metadata-row">
                          <strong>{key.keyName}</strong>
                          <span>{key.keyScope}{key.workspaceId ? ` • ${key.workspaceId}` : ''}</span>
                          <span>{key.keyAlgorithm}</span>
                          <span>{key.isActive ? 'active' : 'inactive'}</span>
                          <span>{key.keyFingerprint}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>

            <hr className="settings-divider" />

            {/* API Configuration Section */}
            <div id="api-config" className="settings-section">
              <h3>API Configuration</h3>
              
              <div className="form-group">
                <label htmlFor="apiBaseUrl">API Base URL</label>
                <input
                  id="apiBaseUrl"
                  type="url"
                  value={applicationData.apiBaseUrl}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, apiBaseUrl: e.target.value })
                    setHasChanges(true)
                  }}
                  placeholder=""
                />
              </div>

              <div className="form-group">
                <label htmlFor="apiVersion">API Version</label>
                <input
                  id="apiVersion"
                  type="text"
                  value={applicationData.apiVersion}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, apiVersion: e.target.value })
                    setHasChanges(true)
                  }}
                  placeholder="v1"
                />
              </div>

              <div className="form-group">
                <label htmlFor="apiRetryAttempts">API Retry Attempts</label>
                <input
                  id="apiRetryAttempts"
                  type="number"
                  min="0"
                  max="10"
                  value={applicationData.apiRetryAttempts}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, apiRetryAttempts: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="apiRetryDelay">API Retry Delay (milliseconds)</label>
                <input
                  id="apiRetryDelay"
                  type="number"
                  min="100"
                  max="10000"
                  step="100"
                  value={applicationData.apiRetryDelay}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, apiRetryDelay: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="debounceMs">Search debounce (ms)</label>
                <input
                  id="debounceMs"
                  type="number"
                  min="0"
                  step="25"
                  value={applicationData.debounceMs}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, debounceMs: parseInt(e.target.value, 10) || 0 })
                    setHasChanges(true)
                  }}
                />
              </div>
            </div>

            <hr className="settings-divider" />

            {/* Admin Limits Section */}
            <div id="admin-limits" className="settings-section">
              <h3>Admin Limits</h3>
              
              <div className="form-group">
                <label htmlFor="maxUsersPerWorkspace">Max Users Per Workspace</label>
                <input
                  id="maxUsersPerWorkspace"
                  type="number"
                  min="1"
                  max="1000"
                  value={applicationData.maxUsersPerWorkspace}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, maxUsersPerWorkspace: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="maxWorkspaces">Max Workspaces</label>
                <input
                  id="maxWorkspaces"
                  type="number"
                  min="1"
                  max="500"
                  value={applicationData.maxWorkspaces}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, maxWorkspaces: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="maxRulesPerWorkspace">Max Rules Per Workspace</label>
                <input
                  id="maxRulesPerWorkspace"
                  type="number"
                  min="1"
                  max="10000"
                  value={applicationData.maxRulesPerWorkspace}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, maxRulesPerWorkspace: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="maxTemplatesPerWorkspace">Max Templates Per Workspace</label>
                <input
                  id="maxTemplatesPerWorkspace"
                  type="number"
                  min="1"
                  max="1000"
                  value={applicationData.maxTemplatesPerWorkspace}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, maxTemplatesPerWorkspace: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="maxConcurrentTests">Max Concurrent Tests</label>
                <input
                  id="maxConcurrentTests"
                  type="number"
                  min="1"
                  max="50"
                  value={applicationData.maxConcurrentTests}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, maxConcurrentTests: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="agentSessionTimeoutMinutes">Agent Session Timeout (minutes)</label>
                <input
                  id="agentSessionTimeoutMinutes"
                  type="number"
                  min="1"
                  max="1440"
                  value={applicationData.agentSessionTimeoutMinutes ?? 60}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, agentSessionTimeoutMinutes: parseInt(e.target.value || '0') })
                    setHasChanges(true)
                  }}
                />
                <p className="info-text">Controls the default session lifetime for agent-based workflows.</p>
              </div>

              <div className="form-group">
                <label htmlFor="maxToolCallsPerSession">Max Tool Calls Per Session</label>
                <input
                  id="maxToolCallsPerSession"
                  type="number"
                  min="1"
                  max="1000"
                  value={applicationData.maxToolCallsPerSession ?? 100}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, maxToolCallsPerSession: parseInt(e.target.value || '0') })
                    setHasChanges(true)
                  }}
                />
                <p className="info-text">Sets the quota for agent tool invocations within a single session.</p>
              </div>

              <div className="form-group">
                <label htmlFor="defaultRuleThresholdPct">Default Rule Threshold (%)</label>
                <input
                  id="defaultRuleThresholdPct"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={applicationData.defaultRuleThresholdPct}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, defaultRuleThresholdPct: parseFloat(e.target.value) || 0 })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="defaultCatalogTermMatchThresholdPct">Default Catalog Term Match Threshold (%)</label>
                <input
                  id="defaultCatalogTermMatchThresholdPct"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={applicationData.defaultCatalogTermMatchThresholdPct}
                  onChange={(e) => {
                    setApplicationData({
                      ...applicationData,
                      defaultCatalogTermMatchThresholdPct: parseFloat(e.target.value) || 0,
                    })
                    setHasChanges(true)
                  }}
                />
              </div>
            </div>

            <hr className="settings-divider" />

            <div id="workspace-configuration" className="settings-section">
              <h3>Workspace Configuration</h3>

              {!canManageWorkspaceSettings ? (
                <p className="settings-hint">
                  Workspace values are read-only here. Only a workspace admin can change them.
                </p>
              ) : null}

              <fieldset className="workspace-settings-fieldset" disabled={!canManageWorkspaceSettings}>
              <div className="form-group">
                <AppSelect
                  id="defaultRiskLevel"
                  label="Default Risk Level"
                  value={workspaceData.defaultRiskLevel}
                  disabled={workspaceSettingsDisabled}
                  onChange={(value) => {
                    setWorkspaceData({
                      ...workspaceData,
                      defaultRiskLevel: value as 'low' | 'medium' | 'high',
                    })
                    setHasChanges(true)
                  }}
                  options={[
                    { value: 'low', label: 'Low' },
                    { value: 'medium', label: 'Medium' },
                    { value: 'high', label: 'High' },
                  ]}
                />
              </div>

              <div className="form-group checkbox">
                <input
                  id="requiresApprovalForActivation"
                  type="checkbox"
                  checked={workspaceData.requiresApprovalForActivation}
                  disabled={workspaceSettingsDisabled}
                  onChange={(e) => {
                    setWorkspaceData({
                      ...workspaceData,
                      requiresApprovalForActivation: e.target.checked,
                    })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="requiresApprovalForActivation">Require approval before rule activation</label>
              </div>

              <div className="form-group checkbox">
                <input
                  id="requiresTestingBeforeApproval"
                  type="checkbox"
                  checked={workspaceData.requiresTestingBeforeApproval}
                  disabled={workspaceSettingsDisabled}
                  onChange={(e) => {
                    setWorkspaceData({
                      ...workspaceData,
                      requiresTestingBeforeApproval: e.target.checked,
                    })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="requiresTestingBeforeApproval">Require testing before approval</label>
              </div>

              <div className="form-group">
                <label htmlFor="autoRetestInterval">Auto-Retest Interval (days)</label>
                <input
                  id="autoRetestInterval"
                  type="number"
                  min="0"
                  value={workspaceData.autoRetestInterval ?? 0}
                  disabled={workspaceSettingsDisabled}
                  onChange={(e) => {
                    setWorkspaceData({
                      ...workspaceData,
                      autoRetestInterval: parseInt(e.target.value || '0', 10) || 0,
                    })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="maxListItems">Maximum list items (admin limit)</label>
                <input
                  id="maxListItems"
                  type="number"
                  min="5"
                  max="200"
                  value={workspaceData.maxListItems ?? ''}
                  disabled={workspaceSettingsDisabled}
                  onChange={(e) => {
                    const value = parseInt(e.target.value, 10)
                    setWorkspaceData({
                      ...workspaceData,
                      maxListItems: Number.isNaN(value) ? undefined : value,
                    })
                    setHasChanges(true)
                  }}
                  placeholder="e.g., 25"
                />
              </div>

              <div className="form-group">
                <label htmlFor="enabledDataSources">Enabled Data Sources</label>
                <input
                  id="enabledDataSources"
                  type="text"
                  value={workspaceData.enabledDataSources.join(', ')}
                  disabled={workspaceSettingsDisabled}
                  onChange={(e) => {
                    setWorkspaceData({
                      ...workspaceData,
                      enabledDataSources: e.target.value.split(',').map((source) => source.trim()).filter(Boolean),
                    })
                    setHasChanges(true)
                  }}
                  placeholder="comma-separated source names"
                />
              </div>

              <WorkspaceReconciliationDataSourcesEditor
                value={workspaceData.reconciliationDataSources || []}
                allowedSourceTypes={applicationData.allowedWorkspaceDataSourceTypes || []}
                disabled={workspaceSettingsDisabled}
                onChange={(value) => {
                  setWorkspaceData({
                    ...workspaceData,
                    reconciliationDataSources: value,
                  })
                  setHasChanges(true)
                }}
              />

              <div className="form-group">
                <label>Playground Source Bundles</label>
                <p className="settings-hint">
                  Playground bundles are allowed for every workspace by default. Disable only the bundles this workspace should not use.
                </p>
                <div>
                  {PLAYGROUND_SOURCE_BUNDLES.map((bundle) => {
                    const isEnabled = !disabledPlaygroundSourceBundleIds.includes(bundle.bundleId)
                    const checkboxId = `playground-bundle-${bundle.bundleId}`

                    return (
                      <div key={bundle.bundleId} className="form-group checkbox">
                        <input
                          id={checkboxId}
                          type="checkbox"
                          checked={isEnabled}
                          disabled={workspaceSettingsDisabled}
                          onChange={(event) => setPlaygroundSourceBundleEnabled(bundle.bundleId, event.target.checked)}
                        />
                        <label htmlFor={checkboxId}>
                          <span>{bundle.title}</span>
                          <span className="settings-hint"> {bundle.description}</span>
                        </label>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="ruleNamingPrefix">Rule Naming Prefix</label>
                <input
                  id="ruleNamingPrefix"
                  type="text"
                  value={workspaceData.ruleNamingPrefix || ''}
                  disabled={workspaceSettingsDisabled}
                  onChange={(e) => {
                    setWorkspaceData({
                      ...workspaceData,
                      ruleNamingPrefix: e.target.value,
                    })
                    setHasChanges(true)
                  }}
                  placeholder="e.g., DQ_"
                />
              </div>

              <div className="form-group">
                <label htmlFor="workspaceAlertDeliveryTarget">Workspace alert delivery target</label>
                <AppSelect
                  id="workspaceAlertDeliveryTarget"
                  label="Workspace alert delivery target"
                  value={workspaceData.alertRoutingPolicy?.deliveryTarget || DEFAULT_ALERT_ROUTING_POLICY.deliveryTarget}
                  disabled={workspaceSettingsDisabled}
                  onChange={(value) => {
                    setWorkspaceData({
                      ...workspaceData,
                      alertRoutingPolicy: {
                        ...(workspaceData.alertRoutingPolicy || DEFAULT_ALERT_ROUTING_POLICY),
                        deliveryTarget: value as 'app' | 'itsm' | 'both',
                      },
                    })
                    setHasChanges(true)
                  }}
                  options={[
                    { value: 'app', label: 'dq-made-easy app' },
                    { value: 'itsm', label: 'ITSM app' },
                    { value: 'both', label: 'Both' },
                  ]}
                />
              </div>

              <div className="form-group">
                <label>Workspace alert channels</label>
                <p className="settings-hint">ITSM-backed alerts should route to ITSM only. App-owned alerts can also notify in-app, email, Teams, Slack, or PagerDuty.</p>
                <div>
                  {(['in_app', 'email', 'teams', 'slack', 'pagerduty'] as const).map((channel) => {
                    const channels = workspaceData.alertRoutingPolicy?.channels || DEFAULT_ALERT_ROUTING_POLICY.channels
                    const checked = channels.includes(channel)
                    return (
                      <div key={channel} className="form-group checkbox">
                        <input
                          id={`workspaceAlertChannel-${channel}`}
                          type="checkbox"
                          checked={checked}
                          disabled={workspaceSettingsDisabled}
                          onChange={(event) => {
                            const nextChannels = event.target.checked
                              ? Array.from(new Set([...channels, channel]))
                              : channels.filter((item) => item !== channel)
                            setWorkspaceData({
                              ...workspaceData,
                              alertRoutingPolicy: {
                                ...(workspaceData.alertRoutingPolicy || DEFAULT_ALERT_ROUTING_POLICY),
                                channels: nextChannels,
                              },
                            })
                            setHasChanges(true)
                          }}
                        />
                        <label htmlFor={`workspaceAlertChannel-${channel}`}>{channel}</label>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="workspaceMandatoryCategories">Mandatory alert categories</label>
                <input
                  id="workspaceMandatoryCategories"
                  type="text"
                  value={(workspaceData.alertRoutingPolicy?.mandatoryCategories || []).join(', ')}
                  disabled={workspaceSettingsDisabled}
                  onChange={(event) => {
                    setWorkspaceData({
                      ...workspaceData,
                      alertRoutingPolicy: {
                        ...(workspaceData.alertRoutingPolicy || DEFAULT_ALERT_ROUTING_POLICY),
                        mandatoryCategories: event.target.value.split(',').map((value) => value.trim()).filter(Boolean),
                      },
                    })
                    setHasChanges(true)
                  }}
                  placeholder="anomaly, drift, root_cause"
                />
              </div>

              <div className="form-group">
                <label htmlFor="workspaceMandatoryRoles">Mandatory roles</label>
                <input
                  id="workspaceMandatoryRoles"
                  type="text"
                  value={(workspaceData.alertRoutingPolicy?.mandatoryRoles || []).join(', ')}
                  disabled={workspaceSettingsDisabled}
                  onChange={(event) => {
                    setWorkspaceData({
                      ...workspaceData,
                      alertRoutingPolicy: {
                        ...(workspaceData.alertRoutingPolicy || DEFAULT_ALERT_ROUTING_POLICY),
                        mandatoryRoles: event.target.value.split(',').map((value) => value.trim()).filter(Boolean),
                      },
                    })
                    setHasChanges(true)
                  }}
                  placeholder="admin, data-steward"
                />
              </div>
              </fieldset>
            </div>

            <hr className="settings-divider" />

            <div id="datasource-governance" className="settings-section">
              <h3>Datasource Governance</h3>

              <p className="settings-hint">
                App admins control which datasource types workspace admins may register for reconciliation.
              </p>

              <div className="form-group">
                <label htmlFor="allowedWorkspaceDataSourceTypes">Allowed workspace datasource types</label>
                <textarea
                  id="allowedWorkspaceDataSourceTypes"
                  value={(applicationData.allowedWorkspaceDataSourceTypes || []).join(', ')}
                  onChange={(event) => {
                    setApplicationData({
                      ...applicationData,
                      allowedWorkspaceDataSourceTypes: event.target.value
                        .split(',')
                        .map((value) => value.trim())
                        .filter(Boolean),
                    })
                    setHasChanges(true)
                  }}
                  rows={3}
                  placeholder="adls, s3, oracle, sql_server"
                />
                <p className="settings-hint">
                  Keep this list narrow so workspace admins only add datasource types that are supported in the reconciliation hub.
                </p>
              </div>
            </div>

            <hr className="settings-divider" />

            <div id="agent-access-control" className="settings-section">
              <h3>Agent Access Control</h3>
              <p className="settings-hint">
                Define which agents are allowed to call agent endpoints. Default policy is deny-all unless an allowlist entry matches the incoming agent identity.
              </p>

              <div className="form-group">
                <AppSelect
                  id="agentDefaultAction"
                  label="Agent default action"
                  value={currentAgentAccessPolicy.defaultAction}
                  onChange={(value) => {
                    updateAgentAccessPolicy((current) => ({
                      ...current,
                      defaultAction: value === 'allow' ? 'allow' : 'deny',
                    }))
                  }}
                  options={[
                    { value: 'deny', label: 'Deny requests unless allowlist matches' },
                    { value: 'allow', label: 'Allow requests unless explicitly constrained by allowlist' },
                  ]}
                />
              </div>

              <div className="form-group">
                <label>Allowed agents</label>
                <p className="settings-hint">
                  Each entry can match on one or more selectors. Leave fields empty only when another selector is provided for the same row.
                </p>

                {currentAgentAccessPolicy.allowedAgents.length === 0 ? (
                  <p className="settings-hint">No allowed agents configured.</p>
                ) : (
                  currentAgentAccessPolicy.allowedAgents.map((entry, index) => (
                    <div key={`agent-allow-entry-${index}`} className="settings-metadata-row">
                      <input
                        id={`allowedAgentType-${index}`}
                        type="text"
                        value={entry.agentType}
                        onChange={(event) => {
                          const nextValue = event.target.value
                          updateAgentAccessPolicy((current) => ({
                            ...current,
                            allowedAgents: current.allowedAgents.map((candidate, candidateIndex) =>
                              candidateIndex === index
                                ? { ...candidate, agentType: nextValue }
                                : candidate,
                            ),
                          }))
                        }}
                        placeholder="agent_type (e.g. mcp)"
                        aria-label={`Allowed agent type ${index + 1}`}
                      />
                      <input
                        id={`allowedAgentSource-${index}`}
                        type="text"
                        value={entry.agentSource}
                        onChange={(event) => {
                          const nextValue = event.target.value
                          updateAgentAccessPolicy((current) => ({
                            ...current,
                            allowedAgents: current.allowedAgents.map((candidate, candidateIndex) =>
                              candidateIndex === index
                                ? { ...candidate, agentSource: nextValue }
                                : candidate,
                            ),
                          }))
                        }}
                        placeholder="agent_source"
                        aria-label={`Allowed agent source ${index + 1}`}
                      />
                      <input
                        id={`allowedAgentInstance-${index}`}
                        type="text"
                        value={entry.agentInstanceId}
                        onChange={(event) => {
                          const nextValue = event.target.value
                          updateAgentAccessPolicy((current) => ({
                            ...current,
                            allowedAgents: current.allowedAgents.map((candidate, candidateIndex) =>
                              candidateIndex === index
                                ? { ...candidate, agentInstanceId: nextValue }
                                : candidate,
                            ),
                          }))
                        }}
                        placeholder="agent_instance_id"
                        aria-label={`Allowed agent instance id ${index + 1}`}
                      />
                      <input
                        id={`allowedAgentOrigin-${index}`}
                        type="text"
                        value={entry.requestOrigin}
                        onChange={(event) => {
                          const nextValue = event.target.value
                          updateAgentAccessPolicy((current) => ({
                            ...current,
                            allowedAgents: current.allowedAgents.map((candidate, candidateIndex) =>
                              candidateIndex === index
                                ? { ...candidate, requestOrigin: nextValue }
                                : candidate,
                            ),
                          }))
                        }}
                        placeholder="request_origin"
                        aria-label={`Allowed agent request origin ${index + 1}`}
                      />
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => {
                          updateAgentAccessPolicy((current) => ({
                            ...current,
                            allowedAgents: current.allowedAgents.filter((_, candidateIndex) => candidateIndex !== index),
                          }))
                        }}
                      >
                        Remove
                      </Button>
                    </div>
                  ))
                )}

                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    updateAgentAccessPolicy((current) => ({
                      ...current,
                      allowedAgents: [
                        ...current.allowedAgents,
                        {
                          agentType: '',
                          agentSource: '',
                          agentInstanceId: '',
                          requestOrigin: '',
                        },
                      ],
                    }))
                  }}
                >
                  Add allowed agent
                </Button>
              </div>
            </div>

            <hr className="settings-divider" />

            {/* Application Behavior Section */}
            <div id="app-behavior" className="settings-section">
              <h3>Application Behavior</h3>

              <div className="form-group">
                <label htmlFor="appAlertDeliveryTarget">Global alert delivery target</label>
                <AppSelect
                  id="appAlertDeliveryTarget"
                  label="Global alert delivery target"
                  value={applicationData.alertRoutingPolicy?.deliveryTarget || DEFAULT_ALERT_ROUTING_POLICY.deliveryTarget}
                  onChange={(value) => {
                    setApplicationData({
                      ...applicationData,
                      alertRoutingPolicy: {
                        ...(applicationData.alertRoutingPolicy || DEFAULT_ALERT_ROUTING_POLICY),
                        deliveryTarget: value as 'app' | 'itsm' | 'both',
                      },
                    })
                    setHasChanges(true)
                  }}
                  options={[
                    { value: 'app', label: 'dq-made-easy app' },
                    { value: 'itsm', label: 'ITSM app' },
                    { value: 'both', label: 'Both' },
                  ]}
                />
              </div>

              <div className="form-group">
                <label>Global alert channels</label>
                <p className="settings-hint">App-owned alerts can use any configured channel. ITSM-backed alerts stay routed through ITSM and do not duplicate into the app.</p>
                <div>
                  {(['in_app', 'email', 'teams', 'slack', 'pagerduty'] as const).map((channel) => {
                    const channels = applicationData.alertRoutingPolicy?.channels || DEFAULT_ALERT_ROUTING_POLICY.channels
                    const checked = channels.includes(channel)
                    return (
                      <div key={channel} className="form-group checkbox">
                        <input
                          id={`appAlertChannel-${channel}`}
                          type="checkbox"
                          checked={checked}
                          onChange={(event) => {
                            const nextChannels = event.target.checked
                              ? Array.from(new Set([...channels, channel]))
                              : channels.filter((item) => item !== channel)
                            setApplicationData({
                              ...applicationData,
                              alertRoutingPolicy: {
                                ...(applicationData.alertRoutingPolicy || DEFAULT_ALERT_ROUTING_POLICY),
                                channels: nextChannels,
                              },
                            })
                            setHasChanges(true)
                          }}
                        />
                        <label htmlFor={`appAlertChannel-${channel}`}>{channel}</label>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="appMandatoryCategories">Mandatory alert categories</label>
                <input
                  id="appMandatoryCategories"
                  type="text"
                  value={(applicationData.alertRoutingPolicy?.mandatoryCategories || []).join(', ')}
                  onChange={(event) => {
                    setApplicationData({
                      ...applicationData,
                      alertRoutingPolicy: {
                        ...(applicationData.alertRoutingPolicy || DEFAULT_ALERT_ROUTING_POLICY),
                        mandatoryCategories: event.target.value.split(',').map((value) => value.trim()).filter(Boolean),
                      },
                    })
                    setHasChanges(true)
                  }}
                  placeholder="anomaly, drift, root_cause"
                />
              </div>

              <div className="form-group">
                <label htmlFor="appMandatoryRoles">Mandatory roles</label>
                <input
                  id="appMandatoryRoles"
                  type="text"
                  value={(applicationData.alertRoutingPolicy?.mandatoryRoles || []).join(', ')}
                  onChange={(event) => {
                    setApplicationData({
                      ...applicationData,
                      alertRoutingPolicy: {
                        ...(applicationData.alertRoutingPolicy || DEFAULT_ALERT_ROUTING_POLICY),
                        mandatoryRoles: event.target.value.split(',').map((value) => value.trim()).filter(Boolean),
                      },
                    })
                    setHasChanges(true)
                  }}
                  placeholder="admin, workspace-admin"
                />
              </div>
              
              <div className="form-group checkbox">
                <input
                  id="maintenanceMode"
                  type="checkbox"
                  checked={applicationData.maintenanceMode}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, maintenanceMode: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="maintenanceMode">Maintenance Mode</label>
              </div>

              {applicationData.maintenanceMode && (
                <div className="form-group">
                  <label htmlFor="maintenanceMessage">Maintenance Message</label>
                  <textarea
                    id="maintenanceMessage"
                    value={applicationData.maintenanceMessage}
                    onChange={(e) => {
                      setApplicationData({ ...applicationData, maintenanceMessage: e.target.value })
                      setHasChanges(true)
                    }}
                    placeholder="The system is under maintenance. Please try again later."
                    rows={3}
                  />
                </div>
              )}

              <div className="form-group checkbox">
                <input
                  id="allowSignup"
                  type="checkbox"
                  checked={applicationData.allowSignup}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, allowSignup: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="allowSignup">Allow user signup</label>
              </div>

              <div className="form-group checkbox">
                <input
                  id="requireEmailVerification"
                  type="checkbox"
                  checked={applicationData.requireEmailVerification}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, requireEmailVerification: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="requireEmailVerification">Require email verification</label>
              </div>

              <div className="form-group">
                <label htmlFor="exceptionFactJitRequestTimeoutMinutes">JIT access request timeout (minutes)</label>
                <input
                  id="exceptionFactJitRequestTimeoutMinutes"
                  type="number"
                  min={1}
                  value={applicationData.exceptionFactJitRequestTimeoutMinutes}
                  onChange={(e) => {
                    const nextValue = Math.max(1, Number(e.target.value) || 1)
                    setApplicationData({ ...applicationData, exceptionFactJitRequestTimeoutMinutes: nextValue })
                    setHasChanges(true)
                  }}
                />
                <span className="settings-hint">
                  Pending exception fact access requests time out automatically after this many minutes.
                </span>
              </div>

              <div className="form-group">
                <AppSelect
                  id="defaultUserRole"
                  label="Default User Role"
                  value={applicationData.defaultUserRole}
                  onChange={(value) => {
                    setApplicationData({
                      ...applicationData,
                      defaultUserRole: value as any,
                    })
                    setHasChanges(true)
                  }}
                  options={[
                    { value: 'viewer', label: 'Viewer' },
                    { value: 'analyst', label: 'Analyst' },
                    { value: 'data-steward', label: 'Data Steward' },
                  ]}
                />
              </div>
            </div>

            <hr className="settings-divider" />

            {/* Logging & Monitoring Section */}
            <div id="logging-monitoring" className="settings-section">
              <h3>Logging & Monitoring</h3>
              
              <div className="form-group">
                <AppSelect
                  id="logLevel"
                  label="Log Level"
                  value={applicationData.logLevel}
                  onChange={(value) => {
                    setApplicationData({
                      ...applicationData,
                      logLevel: value as any,
                    })
                    setHasChanges(true)
                  }}
                  options={[
                    { value: 'debug', label: 'Debug' },
                    { value: 'info', label: 'Info' },
                    { value: 'warn', label: 'Warning' },
                    { value: 'error', label: 'Error' },
                  ]}
                />
              </div>

              <div className="form-group">
                <label>Assistance Request Destinations</label>
                <div className="support-routing-destinations">
                  {([
                    ['email', 'Email draft'],
                    ['itsm', 'ITSM ticket'],
                    ['teams', 'Microsoft Teams channel'],
                  ] as const).map(([destination, label]) => {
                    const destinations = applicationData.assistanceRequestDestinations || ['email']
                    const isSelected = destinations.includes(destination)
                    return (
                      <label key={destination} className="form-group checkbox support-routing-checkbox">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={(event) => {
                            const nextDestinations = event.target.checked
                              ? Array.from(new Set([...destinations, destination]))
                              : destinations.filter((entry) => entry !== destination)
                            setApplicationData({
                              ...applicationData,
                              assistanceRequestDestinations: nextDestinations.length > 0 ? nextDestinations : ['email'],
                              assistanceRequestMode: nextDestinations.includes('itsm') ? 'itsm' : 'email',
                            })
                            setHasChanges(true)
                          }}
                        />
                        <span>{label}</span>
                      </label>
                    )
                  })}
                </div>
                <small className="form-help-text">
                  Requests are routed to every selected destination. Email is sent by the backend, while Teams and ITSM are submitted by the backend.
                </small>
              </div>

              <div className="form-group">
                <label htmlFor="assistanceRequestEmailAddress">Operations Email Address</label>
                <input
                  id="assistanceRequestEmailAddress"
                  type="email"
                  value={applicationData.assistanceRequestEmailAddress || ''}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, assistanceRequestEmailAddress: e.target.value })
                    setHasChanges(true)
                  }}
                  placeholder="dq-made-easy-support@jaccloud.nl"
                />
                <small className="form-help-text">
                  This mailbox receives operations assistance requests.
                </small>
              </div>

              <div className="form-group">
                <label htmlFor="supportEmailSmtpHost">SMTP Host</label>
                <input
                  id="supportEmailSmtpHost"
                  type="text"
                  value={applicationData.supportEmailSmtpHost || ''}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, supportEmailSmtpHost: e.target.value })
                    setHasChanges(true)
                  }}
                  placeholder="smtp.example.com"
                />
              </div>

              <div className="form-group">
                <label htmlFor="supportEmailSmtpPort">SMTP Port</label>
                <input
                  id="supportEmailSmtpPort"
                  type="number"
                  min={1}
                  max={65535}
                  value={applicationData.supportEmailSmtpPort ?? 587}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, supportEmailSmtpPort: parseInt(e.target.value || '0', 10) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="supportEmailSmtpUsername">SMTP Username</label>
                <input
                  id="supportEmailSmtpUsername"
                  type="text"
                  value={applicationData.supportEmailSmtpUsername || ''}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, supportEmailSmtpUsername: e.target.value })
                    setHasChanges(true)
                  }}
                  placeholder="dq-made-easy-support@jaccloud.nl"
                />
              </div>

              <div className="form-group">
                <label htmlFor="supportEmailSmtpPassword">SMTP Password</label>
                <input
                  id="supportEmailSmtpPassword"
                  type="password"
                  value={applicationData.supportEmailSmtpPassword || ''}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, supportEmailSmtpPassword: e.target.value })
                    setHasChanges(true)
                  }}
                  placeholder="••••••••"
                />
              </div>

              <div className="form-group checkbox">
                <input
                  id="supportEmailSmtpUseStartTls"
                  type="checkbox"
                  checked={true}
                  disabled
                />
                <label htmlFor="supportEmailSmtpUseStartTls">Use SSL (required)</label>
              </div>

              <div className="form-group">
                <label htmlFor="supportEmailFromAddress">From Address</label>
                <input
                  id="supportEmailFromAddress"
                  type="email"
                  value={applicationData.supportEmailFromAddress || ''}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, supportEmailFromAddress: e.target.value })
                    setHasChanges(true)
                  }}
                  placeholder="dq-made-easy-support@jaccloud.nl"
                />
                <small className="form-help-text">
                  The backend authenticates to SMTP with these settings before sending the assistance email.
                </small>
              </div>

              {(applicationData.assistanceRequestDestinations || ['email']).includes('itsm') && (
                <>
                  <div className="form-group">
                    <AppSelect
                      id="assistanceRequestItsmSystem"
                      label="Ticketing System"
                      value={applicationData.assistanceRequestItsmSystem || ''}
                      placeholderLabel="Select a ticketing system"
                      onChange={(value) => {
                        setApplicationData({
                          ...applicationData,
                          assistanceRequestItsmSystem: value,
                        })
                        setHasChanges(true)
                      }}
                      options={[
                        { value: 'HaloITSM', label: 'HaloITSM' },
                        { value: 'Zammad', label: 'Zammad' },
                      ]}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="assistanceRequestItsmEndpointUrl">Ticketing API Endpoint URL</label>
                    <input
                      id="assistanceRequestItsmEndpointUrl"
                      type="url"
                      value={applicationData.assistanceRequestItsmEndpointUrl || ''}
                      onChange={(e) => {
                        setApplicationData({ ...applicationData, assistanceRequestItsmEndpointUrl: e.target.value })
                        setHasChanges(true)
                      }}
                      placeholder="https://itsm.example.com/api/v1/tickets"
                    />
                    <small className="form-help-text">
                      The backend sends a structured JSON request and expects a returned ticket number.
                    </small>
                  </div>

                  <div className="form-group">
                    <label htmlFor="assistanceRequestItsmAuthToken">Zammad API Token</label>
                    <input
                      id="assistanceRequestItsmAuthToken"
                      type="password"
                      value={applicationData.assistanceRequestItsmAuthToken || ''}
                      onChange={(e) => {
                        setApplicationData({ ...applicationData, assistanceRequestItsmAuthToken: e.target.value })
                        setHasChanges(true)
                      }}
                      placeholder="zammad-api-token"
                    />
                    <small className="form-help-text">
                      Required when the ticketing system is Zammad. The token is stored encrypted.
                    </small>
                  </div>
                </>
              )}

              {(applicationData.assistanceRequestDestinations || ['email']).includes('teams') && (
                <div className="form-group">
                  <label htmlFor="assistanceRequestTeamsWebhookUrl">Teams Workflow Webhook URL</label>
                  <input
                    id="assistanceRequestTeamsWebhookUrl"
                    type="url"
                    value={applicationData.assistanceRequestTeamsWebhookUrl || ''}
                    onChange={(e) => {
                      setApplicationData({ ...applicationData, assistanceRequestTeamsWebhookUrl: e.target.value })
                      setHasChanges(true)
                    }}
                    placeholder="https://example.com/teams/workflow-webhook"
                  />
                  <small className="form-help-text">
                    The backend posts the support request to the configured Teams workflow webhook.
                  </small>
                </div>
              )}

              <div className="form-group">
                <label htmlFor="alertingSlackWebhookUrl">Slack Incoming Webhook URL</label>
                <input
                  id="alertingSlackWebhookUrl"
                  type="url"
                  value={applicationData.alertingSlackWebhookUrl || ''}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, alertingSlackWebhookUrl: e.target.value })
                    setHasChanges(true)
                  }}
                  placeholder="https://hooks.slack.com/services/..."
                />
                <small className="form-help-text">
                  Used when alert routing includes Slack.
                </small>
              </div>

              <div className="form-group">
                <label htmlFor="alertingPagerDutyRoutingKey">PagerDuty Routing Key</label>
                <input
                  id="alertingPagerDutyRoutingKey"
                  type="password"
                  value={applicationData.alertingPagerDutyRoutingKey || ''}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, alertingPagerDutyRoutingKey: e.target.value })
                    setHasChanges(true)
                  }}
                  placeholder="pagerduty-routing-key"
                />
                <small className="form-help-text">
                  Used when alert routing includes PagerDuty.
                </small>
              </div>

              <div className="form-group checkbox">
                <input
                  id="enableAnalytics"
                  type="checkbox"
                  checked={applicationData.enableAnalytics}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, enableAnalytics: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="enableAnalytics">Enable analytics</label>
              </div>

              <div className="form-group checkbox">
                <input
                  id="enableCrashReporting"
                  type="checkbox"
                  checked={applicationData.enableCrashReporting}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, enableCrashReporting: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="enableCrashReporting">Enable crash reporting</label>
              </div>

              <div className="form-group checkbox">
                <input
                  id="siemEnabled"
                  type="checkbox"
                  checked={Boolean(appConfigData?.siemEnabled)}
                  onChange={(e) => {
                    setAppConfigData((prev) => ({
                      ...(prev || {}),
                      siemEnabled: e.target.checked,
                      siemEndpointUrl: e.target.checked
                        ? (prev?.siemEndpointUrl || '')
                        : (prev?.siemEndpointUrl || null),
                    }))
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="siemEnabled">Enable SIEM integration</label>
              </div>

              <div className="form-group">
                <label htmlFor="siemEndpointUrl">SIEM endpoint URL</label>
                <input
                  id="siemEndpointUrl"
                  type="url"
                  value={appConfigData?.siemEndpointUrl || ''}
                  disabled={!Boolean(appConfigData?.siemEnabled)}
                  onChange={(e) => {
                    setAppConfigData((prev) => ({
                      ...(prev || {}),
                      siemEndpointUrl: e.target.value,
                    }))
                    setHasChanges(true)
                  }}
                  placeholder="https://siem.example.com/api/events"
                />
                <small className="form-help-text">
                  Used when SIEM integration is enabled. Configure the connection once the external SIEM endpoint is available.
                </small>
              </div>

              <div className="form-group">
                <label htmlFor="siemApiToken">SIEM API token</label>
                <input
                  id="siemApiToken"
                  type="password"
                  value={appConfigData?.siemApiToken || ''}
                  disabled={!Boolean(appConfigData?.siemEnabled)}
                  onChange={(e) => {
                    setAppConfigData((prev) => ({
                      ...(prev || {}),
                      siemApiToken: e.target.value,
                    }))
                    setHasChanges(true)
                  }}
                  placeholder="Paste the SIEM bearer token or shared secret"
                />
                <small className="form-help-text">
                  Stored as a secret app-config value and only used when SIEM integration is enabled.
                </small>
              </div>

              <div className="form-group checkbox">
                <input
                  id="metricsForwardingEnabled"
                  type="checkbox"
                  checked={Boolean(appConfigData?.metricsForwardingEnabled)}
                  onChange={(e) => {
                    setAppConfigData((prev) => ({
                      ...(prev || {}),
                      metricsForwardingEnabled: e.target.checked,
                      metricsForwardUrl: e.target.checked
                        ? (prev?.metricsForwardUrl || '')
                        : (prev?.metricsForwardUrl || null),
                    }))
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="metricsForwardingEnabled">Forward suggestion/profiling metrics to external endpoint</label>
              </div>

              <div className="form-group">
                <label htmlFor="metricsForwardUrl">Metrics Forward URL</label>
                <input
                  id="metricsForwardUrl"
                  type="url"
                  value={appConfigData?.metricsForwardUrl || ''}
                  disabled={!Boolean(appConfigData?.metricsForwardingEnabled)}
                  onChange={(e) => {
                    setAppConfigData((prev) => ({
                      ...(prev || {}),
                      metricsForwardUrl: e.target.value,
                    }))
                    setHasChanges(true)
                  }}
                  placeholder="https://your-monitoring-endpoint.example.com/ingest"
                />
                <small className="form-help-text">
                  Application-wide setting. Disabled by default.
                </small>
              </div>

              <div className="form-group">
                <label htmlFor="openMetadataContractCacheTtlSeconds">OpenMetadata Contract Cache TTL (seconds)</label>
                <input
                  id="openMetadataContractCacheTtlSeconds"
                  type="number"
                  min="0"
                  step="1"
                  value={appConfigData?.openMetadataContractCacheTtlSeconds ?? 300}
                  onChange={(e) => {
                    const parsed = Number.parseInt(e.target.value, 10)
                    setAppConfigData((prev) => ({
                      ...(prev || {}),
                      openMetadataContractCacheTtlSeconds: Number.isNaN(parsed) ? 0 : Math.max(parsed, 0),
                    }))
                    setHasChanges(true)
                  }}
                />
                <small className="form-help-text">
                  0 disables cache usage for contract policy lookups.
                </small>
              </div>
            </div>

            <hr className="settings-divider" />

            {/* Feature Flags Section */}
            <div id="feature-flags" className="settings-section">
              <h3>Feature Flags</h3>
              
              <div className="form-group checkbox">
                <input
                  id="enableSuggestions"
                  type="checkbox"
                  checked={applicationData.enableSuggestions}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, enableSuggestions: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="enableSuggestions">Enable suggestions (AI-powered)</label>
              </div>

              <div className="form-group checkbox">
                <input
                  id="enableBulkOperations"
                  type="checkbox"
                  checked={applicationData.enableBulkOperations}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, enableBulkOperations: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="enableBulkOperations">Enable bulk operations</label>
              </div>

              <div className="form-group checkbox">
                <input
                  id="enableVersioning"
                  type="checkbox"
                  checked={applicationData.enableVersioning}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, enableVersioning: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="enableVersioning">Enable rule versioning</label>
              </div>

              <div className="form-group checkbox">
                <input
                  id="enableExport"
                  type="checkbox"
                  checked={applicationData.enableExport}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, enableExport: e.target.checked })
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="enableExport">Enable rule export</label>
              </div>

              <div className="form-group checkbox">
                <input
                  id="featureRuleDslV2"
                  type="checkbox"
                  checked={Boolean(appConfigData?.featureRuleDslV2)}
                  onChange={(e) => {
                    setAppConfigData((prev) => ({
                      ...(prev || {}),
                      featureRuleDslV2: e.target.checked,
                    }))
                    setHasChanges(true)
                  }}
                />
                <label htmlFor="featureRuleDslV2">Enable DQ7 DSL 2.0.0 rollout gate</label>
              </div>

              <small className="form-help-text">
                Operator-only rollout control. Keep user-facing guidance cards and capability discovery separate.
              </small>
            </div>

            <hr className="settings-divider" />

            {/* Preview Feature Lifecycle Section */}
            <div id="feature-lifecycle" className="settings-section">
              <h3>Preview Feature Lifecycle</h3>
              <p className="settings-subtitle" style={{ marginBottom: '12px' }}>
                Control if a feature is Off, in Preview, or Live for all users.
              </p>

              {/* Lifecycle Stage Legend */}
              <div className="settings-info-box" style={{ 
                marginBottom: '20px', 
                backgroundColor: 'var(--app-surface-primary)',
                border: '1px solid var(--app-border-subtle)',
                padding: '12px 16px'
              }}>
                <div style={{ fontSize: '13px', lineHeight: '1.6' }}>
                  <div style={{ fontWeight: 600, marginBottom: '8px', color: 'var(--app-text-primary)' }}>
                    Lifecycle Stage Behavior:
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', color: 'var(--app-text-secondary)' }}>
                    <div>
                      <strong style={{ color: 'var(--app-text-primary)' }}>Off:</strong> Feature is completely disabled — users won't see it anywhere
                    </div>
                    <div>
                      <strong style={{ color: 'var(--app-text-primary)' }}>Preview:</strong> Feature appears in its intended navigation area for users who opt in to preview features
                    </div>
                    <div>
                      <strong style={{ color: 'var(--app-text-primary)' }}>Live:</strong> Feature is fully released — appears in its intended navigation area for all users
                    </div>
                  </div>
                </div>
              </div>

              {PREVIEW_FEATURE_ADMIN_FIELDS.map((feature) => {
                const enabled =
                  (appConfigData?.[feature.enabledKey as keyof FeatureLifecycleConfig] as boolean | undefined) ??
                  (feature.enabledKey === 'featureRuleSuggestions'
                    ? applicationData.enableSuggestions
                    : true)
                const stage =
                  (appConfigData?.[feature.stageKey as keyof FeatureLifecycleConfig] as FeatureStage | undefined) ??
                  'preview'

                return (
                  <div key={feature.id} className="settings-info-box" style={{ marginBottom: '12px' }}>
                    <div style={{ width: '100%' }}>
                      <div className="form-group checkbox" style={{ marginBottom: '8px' }}>
                        <input
                          id={`${feature.id}-enabled`}
                          type="checkbox"
                          checked={enabled}
                          onChange={(e) => {
                            setAppConfigData((prev) => ({
                              ...(prev || {}),
                              [feature.enabledKey]: e.target.checked,
                            }))
                            if (feature.enabledKey === 'featureRuleSuggestions') {
                              setApplicationData({
                                ...applicationData,
                                enableSuggestions: e.target.checked,
                              })
                            }
                            setHasChanges(true)
                          }}
                        />
                        <label htmlFor={`${feature.id}-enabled`}>{feature.label} enabled</label>
                      </div>

                      <AppSelect
                        id={`${feature.id}-stage`}
                        label="Lifecycle Stage"
                        value={stage}
                        onChange={(value) => {
                          setAppConfigData((prev) => ({
                            ...(prev || {}),
                            [feature.stageKey]: value as FeatureStage,
                          }))
                          setHasChanges(true)
                        }}
                        options={[
                          { value: 'off', label: 'Off' },
                          { value: 'preview', label: 'Preview' },
                          { value: 'live', label: 'Live' },
                        ]}
                      />
                    </div>
                  </div>
                )
              })}
            </div>

            <hr className="settings-divider" />

            {/* Data Retention Section */}
            <div id="data-retention" className="settings-section">
              <h3>Data Retention</h3>
              
              <div className="form-group">
                <label htmlFor="auditLogRetentionDays">Audit Log Retention (days)</label>
                <input
                  id="auditLogRetentionDays"
                  type="number"
                  min="1"
                  max="3650"
                  value={applicationData.auditLogRetentionDays}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, auditLogRetentionDays: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="testResultsRetentionDays">Test Results Retention (days)</label>
                <input
                  id="testResultsRetentionDays"
                  type="number"
                  min="1"
                  max="365"
                  value={applicationData.testResultsRetentionDays}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, testResultsRetentionDays: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="deletedItemsRetentionDays">Deleted Items Retention (days)</label>
                <input
                  id="deletedItemsRetentionDays"
                  type="number"
                  min="1"
                  max="365"
                  value={applicationData.deletedItemsRetentionDays}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, deletedItemsRetentionDays: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="exceptionFactRetentionDays">Exception Facts Retention (days)</label>
                <input
                  id="exceptionFactRetentionDays"
                  type="number"
                  min="1"
                  max="3650"
                  value={applicationData.exceptionFactRetentionDays}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, exceptionFactRetentionDays: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="exceptionFactArchiveRetentionDays">Exception Fact Archive Retention (days)</label>
                <input
                  id="exceptionFactArchiveRetentionDays"
                  type="number"
                  min="1"
                  max="3650"
                  value={applicationData.exceptionFactArchiveRetentionDays}
                  onChange={(e) => {
                    setApplicationData({
                      ...applicationData,
                      exceptionFactArchiveRetentionDays: parseInt(e.target.value),
                    })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="exceptionAnalyticsProjectionRetentionDays">Exception Analytics Retention (days)</label>
                <input
                  id="exceptionAnalyticsProjectionRetentionDays"
                  type="number"
                  min="1"
                  max="3650"
                  value={applicationData.exceptionAnalyticsProjectionRetentionDays}
                  onChange={(e) => {
                    setApplicationData({
                      ...applicationData,
                      exceptionAnalyticsProjectionRetentionDays: parseInt(e.target.value),
                    })
                    setHasChanges(true)
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="exceptionFactPurgeBatchSize">Exception Fact Purge Batch Size</label>
                <input
                  id="exceptionFactPurgeBatchSize"
                  type="number"
                  min="1"
                  max="100000"
                  value={applicationData.exceptionFactPurgeBatchSize}
                  onChange={(e) => {
                    setApplicationData({ ...applicationData, exceptionFactPurgeBatchSize: parseInt(e.target.value) })
                    setHasChanges(true)
                  }}
                />
              </div>
            </div>

            <div className="settings-info-box">
              <AppIcon name="info-circle" />
              <p>
                These settings affect the entire application and all workspaces. 
                Changes require careful consideration and may require application restart.
              </p>
            </div>
          </div>
        </div>
        )}

        {/* Security Tab */}
        {activeTab === 'security' && (
        <div className="settings-panel">
          <h2>Security Settings</h2>

          <div className="settings-form">
            <div id="two-factor-auth" className="form-group security-info">
              <h3>Two-Factor Authentication</h3>
              <p className="info-text">
                {securityData.twoFactorEnabled ? '✓ Enabled' : '✗ Not enabled'}
              </p>
              <SecondaryButton
                className="app-settings-action-btn"
                onClick={handleEnable2FA}
                disabled={securityData.twoFactorEnabled}
              >
                {securityData.twoFactorEnabled ? 'Already Enabled' : 'Enable 2FA'}
              </SecondaryButton>
            </div>

            <hr className="settings-divider" />

            <div id="ip-whitelist" className="form-group security-info">
              <h3>IP Whitelist</h3>
              <textarea
                value={securityData.ipWhitelist.join('\n')}
                onChange={(e) => {
                  setSecurityData({
                    ...securityData,
                    ipWhitelist: e.target.value
                      .split('\n')
                      .map((ip) => ip.trim())
                      .filter((ip) => ip),
                  })
                  setHasChanges(true)
                }}
                placeholder="One IP address per line"
                rows={4}
              />
            </div>

            <hr className="settings-divider" />

            <div id="api-keys" className="form-group security-info">
              <h3>API Keys ({securityData.apiKeys.length})</h3>
              {newApiKey && (
                <div className="api-key-created">
                  <p>New API Key (copy it now, you won't see it again):</p>
                  <code>{newApiKey}</code>
                </div>
              )}
              {securityData.apiKeys.length > 0 && (
                <div className="api-keys-list">
                  {securityData.apiKeys.map((key: { id: string; name: string; createdAt: string }) => (
                    <div key={key.id} className="api-key-item">
                      <div>
                        <p className="key-name">{key.name}</p>
                        <p className="key-info">
                          Created: {new Date(key.createdAt).toLocaleDateString()}
                        </p>
                      </div>
                      <Button
                        className="app-settings-danger-btn"
                        variant="primary-destructive"
                        onClick={() => handleRevokeAPIKey(key.id)}
                      >
                        Revoke
                      </Button>
                    </div>
                  ))}
                </div>
              )}
              <SecondaryButton className="app-settings-action-btn" onClick={handleGenerateAPIKey}>
                Generate New API Key
              </SecondaryButton>
            </div>

            <hr className="settings-divider" />

            <div id="last-login" className="form-group security-info">
              <h3>Last Login</h3>
              <p className="info-text">
                {new Date(securityData.lastLogin).toLocaleString()}
              </p>
            </div>
          </div>
        </div>
        )}

        {/* API Tab */}
        {activeTab === 'api' && (
        <div className="settings-panel">
          <h2>API Configuration</h2>

          <div className="settings-form">
            <div id="api-basic">
            <div className="form-group">
              <label htmlFor="webhookUrl">Webhook URL</label>
              <input
                id="webhookUrl"
                type="url"
                value={apiData.webhookUrl}
                onChange={(e) => {
                  setApiData({ ...apiData, webhookUrl: e.target.value })
                  setHasChanges(true)
                }}
                placeholder="https://example.com/webhook"
              />
            </div>

            <div className="form-group">
              <label htmlFor="rateLimitPerMinute">Rate Limit (requests per minute)</label>
              <input
                id="rateLimitPerMinute"
                type="number"
                min="10"
                value={apiData.rateLimitPerMinute}
                onChange={(e) => {
                  setApiData({
                    ...apiData,
                    rateLimitPerMinute: parseInt(e.target.value),
                  })
                  setHasChanges(true)
                }}
              />
            </div>

            <div className="form-group">
              <label htmlFor="allowedOrigins">Allowed Origins (CORS)</label>
              <textarea
                id="allowedOrigins"
                value={apiData.allowedOrigins.join('\n')}
                onChange={(e) => {
                  setApiData({
                    ...apiData,
                    allowedOrigins: e.target.value
                      .split('\n')
                      .map((origin) => origin.trim())
                      .filter((origin) => origin),
                  })
                  setHasChanges(true)
                }}
                placeholder="One origin per line"
                rows={4}
              />
            </div>

            <div className="form-group checkbox">
              <input
                id="encryptionEnabled"
                type="checkbox"
                checked={apiData.encryptionEnabled}
                onChange={(e) => {
                  setApiData({ ...apiData, encryptionEnabled: e.target.checked })
                  setHasChanges(true)
                }}
              />
              <label htmlFor="encryptionEnabled">Enable encryption for sensitive data</label>
            </div>

            <div className="form-group checkbox">
              <input
                id="auditLoggingEnabled"
                type="checkbox"
                checked={apiData.auditLoggingEnabled}
                onChange={(e) => {
                  setApiData({ ...apiData, auditLoggingEnabled: e.target.checked })
                  setHasChanges(true)
                }}
              />
              <label htmlFor="auditLoggingEnabled">Enable audit logging</label>
            </div>

            <div className="form-group">
              <label htmlFor="apiTimeout">API Timeout (seconds)</label>
              <input
                id="apiTimeout"
                type="number"
                min="5"
                value={apiData.apiTimeout}
                onChange={(e) => {
                  setApiData({
                    ...apiData,
                    apiTimeout: parseInt(e.target.value),
                  })
                  setHasChanges(true)
                }}
              />
            </div>
            </div>
          </div>
        </div>
        )}

        {/* 2FA Modal */}
        {show2FAModal && (
          <div className="modal-overlay" onClick={() => setShow2FAModal(false)}>
            <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h3>Enable Two-Factor Authentication</h3>
                <button
                  className="modal-close"
                  onClick={() => setShow2FAModal(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body">
                <p>Scan this QR code with your authenticator app:</p>
                <div className="qr-code-placeholder">
                  <div className="qr-text">{qrSecret}</div>
                </div>
                <p className="qr-info">
                  Enter the 6-digit code from your authenticator app to confirm setup.
                </p>
              </div>
              <div className="modal-footer">
                <SecondaryButton className="app-settings-action-btn" onClick={() => setShow2FAModal(false)}>
                  Close
                </SecondaryButton>
              </div>
            </div>
          </div>
        )}

        {/* Save/Cancel Buttons */}
        {hasChanges && (
          <div className="settings-actions">
            <SecondaryButton onClick={handleReset}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={handleSave}>
              Save Changes
            </PrimaryButton>
          </div>
        )}
      </div>
    </AppPageShell>
  )
}
