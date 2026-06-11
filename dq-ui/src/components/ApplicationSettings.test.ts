import { describe, expect, it } from 'vitest'

import { buildAppConfigPayload, mergeApplicationDataFromSettings } from './ApplicationSettings'
import { ApplicationSettings } from '../types/settings'

const makeApplicationSettings = (): ApplicationSettings => ({
  debounceMs: 500,
  ssoEnabled: false,
  ssoProvider: 'none',
  ssoIssuerUrl: '',
  ssoClientId: '',
  allowLocalAuth: true,
  apiBaseUrl: 'http://localhost:9111/api/v1',
  apiVersion: 'v1',
  apiRetryAttempts: 3,
  apiRetryDelay: 1000,
  maxUsersPerWorkspace: 100,
  maxWorkspaces: 50,
  maxRulesPerWorkspace: 500,
  maxTemplatesPerWorkspace: 100,
  maxConcurrentTests: 5,
  allowedWorkspaceDataSourceTypes: ['adls', 's3', 'oracle', 'sql_server'],
  defaultRuleThresholdPct: 7.5,
  defaultCatalogTermMatchThresholdPct: 75,
  maintenanceMode: false,
  maintenanceMessage: '',
  allowSignup: true,
  requireEmailVerification: false,
  defaultUserRole: 'viewer',
  assistanceRequestMode: 'email',
  assistanceRequestDestinations: ['email'],
  assistanceRequestEmailAddress: 'prototype@jaccloud.nl',
  assistanceRequestItsmSystem: 'HaloITSM',
  assistanceRequestItsmEndpointUrl: 'http://itsm.example.com/api/v1/tickets',
  assistanceRequestItsmAuthToken: '',
  assistanceRequestTeamsWebhookUrl: '',
  alertingSlackWebhookUrl: '',
  alertingPagerDutyRoutingKey: '',
  alertRoutingPolicy: {
    deliveryTarget: 'app',
    channels: ['in_app'],
    mandatoryCategories: [],
    mandatoryRoles: [],
  },
  supportEmailSmtpHost: 'smtp.example.com',
  supportEmailSmtpPort: 587,
  supportEmailSmtpUsername: 'noreply@example.com',
  supportEmailSmtpPassword: '',
  supportEmailSmtpUseStartTls: true,
  supportEmailFromAddress: 'noreply@example.com',
  dataProtectionMaskingMethods: ['none', 'redact', 'partial', 'tokenize'],
  dataProtectionEncryptionMethods: ['fernet'],
  logLevel: 'info',
  enableAnalytics: true,
  enableCrashReporting: false,
  enableSuggestions: true,
  enableBulkOperations: true,
  enableVersioning: true,
  enableExport: true,
  auditLogRetentionDays: 365,
  testResultsRetentionDays: 90,
  deletedItemsRetentionDays: 30,
  exceptionFactRetentionDays: 30,
  exceptionFactArchiveRetentionDays: 180,
  exceptionAnalyticsProjectionRetentionDays: 365,
  exceptionFactPurgeBatchSize: 5000,
  exceptionFactJitRequestTimeoutMinutes: 30,
  sessionTimeoutMinutes: 60,
  sessionTimeoutWarningMinutes: 10,
  agentSessionTimeoutMinutes: 60,
  maxToolCallsPerSession: 100,
  updatedAt: '2026-03-27T00:00:00.000Z',
})

describe('buildAppConfigPayload', () => {
  it('uses current UI suggestion toggle even when loaded config was false', () => {
    const appData = makeApplicationSettings()

    const payload = buildAppConfigPayload(
      {
        featureRuleSuggestions: false,
      },
      appData,
    )

    expect(payload.featureRuleSuggestions).toBe(true)
  })

  it('includes configured OpenMetadata contract cache TTL', () => {
    const appData = makeApplicationSettings()

    const payload = buildAppConfigPayload(
      {
        openMetadataContractCacheTtlSeconds: 45,
      },
      appData,
    )

    expect(payload.openMetadataContractCacheTtlSeconds).toBe(45)
  })

  it('defaults OpenMetadata contract cache TTL to 300 when not provided', () => {
    const appData = makeApplicationSettings()

    const payload = buildAppConfigPayload({}, appData)

    expect(payload.openMetadataContractCacheTtlSeconds).toBe(300)
  })

  it('persists the DQ7 DSL 2.0.0 rollout gate from loaded config', () => {
    const appData = makeApplicationSettings()

    const payload = buildAppConfigPayload(
      {
        featureRuleDslV2: true,
      },
      appData,
    )

    expect(payload.featureRuleDslV2).toBe(true)
  })

  it('includes agent session limits in the app-config payload', () => {
    const appData = {
      ...makeApplicationSettings(),
      agentSessionTimeoutMinutes: 45,
      maxToolCallsPerSession: 250,
    }

    const payload = buildAppConfigPayload({}, appData)

    expect(payload.agentSessionTimeoutMinutes).toBe(45)
    expect(payload.maxToolCallsPerSession).toBe(250)
  })

  it('includes exception retention policy values in the app-config payload', () => {
    const appData = makeApplicationSettings()

    const payload = buildAppConfigPayload({}, appData)

    expect(payload.exceptionFactRetentionDays).toBe(30)
    expect(payload.exceptionFactArchiveRetentionDays).toBe(180)
    expect(payload.exceptionAnalyticsProjectionRetentionDays).toBe(365)
    expect(payload.exceptionFactPurgeBatchSize).toBe(5000)
  })

  it('includes alert routing policy values in the app-config payload', () => {
    const appData = {
      ...makeApplicationSettings(),
      alertRoutingPolicy: {
        deliveryTarget: 'itsm' as const,
        channels: ['in_app', 'email', 'teams'],
        mandatoryCategories: ['anomaly', 'drift'],
        mandatoryRoles: ['admin'],
      },
    }

    const payload = buildAppConfigPayload({}, appData)

    expect(payload.alertRoutingPolicy).toEqual(appData.alertRoutingPolicy)
  })

  it('includes Slack and PagerDuty connectivity values in the app-config payload', () => {
    const appData = {
      ...makeApplicationSettings(),
      alertingSlackWebhookUrl: 'https://hooks.slack.com/services/T000/B000/XXXXX',
      alertingPagerDutyRoutingKey: 'pagerduty-routing-key',
    }

    const payload = buildAppConfigPayload({}, appData)

    expect(payload.alertingSlackWebhookUrl).toBe(appData.alertingSlackWebhookUrl)
    expect(payload.alertingPagerDutyRoutingKey).toBe(appData.alertingPagerDutyRoutingKey)
  })

  it('includes SIEM connection settings in the app-config payload', () => {
    const appData = {
      ...makeApplicationSettings(),
      siemEnabled: true,
      siemEndpointUrl: 'https://siem.example.com/api/events',
      siemApiToken: 'secret-token',
    } as any

    const payload = buildAppConfigPayload({}, appData)

    expect(payload.siemEnabled).toBe(true)
    expect(payload.siemEndpointUrl).toBe('https://siem.example.com/api/events')
    expect(payload.siemApiToken).toBe('secret-token')
  })

  it('includes the agent access policy values in the app-config payload', () => {
    const appData = makeApplicationSettings()

    const payload = buildAppConfigPayload(
      {
        agentAccessPolicy: {
          defaultAction: 'deny',
          allowedAgents: [
            {
              agentType: 'mcp',
              agentSource: 'dq-made-easy-mcp',
              agentInstanceId: 'dq-made-easy-mcp:1234',
              requestOrigin: 'stdio',
            },
          ],
        },
      },
      appData,
    )

    expect(payload.agentAccessPolicy).toEqual({
      defaultAction: 'deny',
      allowedAgents: [
        {
          agentType: 'mcp',
          agentSource: 'dq-made-easy-mcp',
          agentInstanceId: 'dq-made-easy-mcp:1234',
          requestOrigin: 'stdio',
        },
      ],
    })
  })
})

describe('mergeApplicationDataFromSettings', () => {
  it('only syncs apiBaseUrl from settings context', () => {
    const current = {
      ...makeApplicationSettings(),
      ssoEnabled: true,
      enableSuggestions: true,
      apiBaseUrl: 'http://runtime.example.com/api/v1',
    }
    const settingsApplicationData = {
      ...makeApplicationSettings(),
      ssoEnabled: false,
      enableSuggestions: false,
      apiBaseUrl: 'http://prefs.example.com/api/v1',
    }

    const merged = mergeApplicationDataFromSettings(current, settingsApplicationData)

    expect(merged?.apiBaseUrl).toBe('http://prefs.example.com/api/v1')
    expect(merged?.ssoEnabled).toBe(true)
    expect(merged?.enableSuggestions).toBe(true)
  })

  it('returns settings values when current state is empty', () => {
    const settingsApplicationData = makeApplicationSettings()

    const merged = mergeApplicationDataFromSettings(null, settingsApplicationData)

    expect(merged).toEqual(settingsApplicationData)
  })

  it('keeps runtime toggles from current state on remount re-sync', () => {
    const current = {
      ...makeApplicationSettings(),
      ssoEnabled: true,
      enableSuggestions: true,
    }
    const settingsApplicationData = {
      ...makeApplicationSettings(),
      ssoEnabled: false,
      enableSuggestions: false,
    }

    const merged = mergeApplicationDataFromSettings(current, settingsApplicationData)

    expect(merged?.ssoEnabled).toBe(true)
    expect(merged?.enableSuggestions).toBe(true)
  })
})
