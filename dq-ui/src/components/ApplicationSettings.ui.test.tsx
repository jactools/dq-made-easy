/* @vitest-environment jsdom */

import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ApplicationSettings } from './ApplicationSettings'
import type { SettingsUpdatePayload } from '../types/settings'

const updateSettings = vi.fn(async (_payload: SettingsUpdatePayload) => {})

const authState = {
  currentWorkspaceId: 'ws-1',
  user: {
    workspaceRoles: [{ workspaceId: 'ws-1', role: 'admin' }],
  },
  hasScope: vi.fn(() => true),
}

const settingsMock = {
  userSettings: null,
  notificationSettings: null,
  displaySettings: null,
  workspaceSettings: {
    workspaceId: 'ws-1',
    name: 'Default Workspace',
    defaultRiskLevel: 'medium',
    requiresApprovalForActivation: true,
    requiresTestingBeforeApproval: true,
    autoRetestInterval: 30,
    maxListItems: 25,
    enabledDataSources: ['crm'],
    reconciliationDataSources: [],
    disabledPlaygroundSourceBundleIds: [],
    ruleNamingPrefix: 'DQ_',
    updatedAt: '2026-03-27T00:00:00.000Z',
  },
  securitySettings: {
    userId: 'user-1',
    twoFactorEnabled: false,
    lastPasswordChange: '2026-03-27T00:00:00.000Z',
    ipWhitelist: [],
    apiKeys: [],
    lastLogin: '2026-03-27T00:00:00.000Z',
    updatedAt: '2026-03-27T00:00:00.000Z',
  },
  apiSettings: {
    workspaceId: 'ws-1',
    webhookUrl: '',
    rateLimitPerMinute: 60,
    allowedOrigins: [],
    encryptionEnabled: true,
    auditLoggingEnabled: true,
    apiTimeout: 30,
    updatedAt: '2026-03-27T00:00:00.000Z',
  },
  applicationSettings: {
    ssoEnabled: false,
    ssoProvider: 'none',
    stylePackage: 'custom-built-package',
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
    maintenanceMode: false,
    maintenanceMessage: '',
    allowSignup: true,
    requireEmailVerification: false,
    defaultUserRole: 'viewer',
    logLevel: 'info',
    enableAnalytics: true,
    enableCrashReporting: false,
    enableSuggestions: false,
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
    updatedAt: '2026-03-27T00:00:00.000Z',
  },
  adminUsers: [],
  adminRoles: [],
  isLoading: false,
  error: null,
  updateSettings,
  loadSettings: vi.fn(async () => {}),
  loadAdminUsers: vi.fn(async () => {}),
  loadAdminRoles: vi.fn(async () => {}),
  createAdminRole: vi.fn(async () => {}),
  updateAdminRole: vi.fn(async () => {}),
  resetUserProfile: vi.fn(async () => {}),
  resetUserSettings: vi.fn(async () => {}),
  saveAPIKey: vi.fn(async () => 'api-key-1'),
  revokeAPIKey: vi.fn(async () => {}),
  enableTwoFactor: vi.fn(async () => 'secret'),
  clearError: vi.fn(() => {}),
}

const baseApplicationSettings = {
  ssoEnabled: false,
  ssoProvider: 'none',
  stylePackage: 'custom-built-package',
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
  maintenanceMode: false,
  maintenanceMessage: '',
  allowSignup: true,
  requireEmailVerification: false,
  defaultUserRole: 'viewer',
  logLevel: 'info',
  enableAnalytics: true,
  enableCrashReporting: false,
  enableSuggestions: false,
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
  updatedAt: '2026-03-27T00:00:00.000Z',
}

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => settingsMock,
  useSettingsOptional: () => settingsMock,
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => authState,
}))


describe('ApplicationSettings UI persistence', () => {
  beforeEach(() => {
    updateSettings.mockClear()
    authState.currentWorkspaceId = 'ws-1'
    authState.user.workspaceRoles = [{ workspaceId: 'ws-1', role: 'admin' }]
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    })

      settingsMock.applicationSettings = { ...baseApplicationSettings }

    const currentAppConfig: Record<string, unknown> = {
      sso_enabled: false,
      sso_provider: 'none',
      style_package: 'custom-built-package',
      allow_local_auth: true,
      agent_access_policy: {
        default_action: 'deny',
        allowed_agents: [],
      },
      feature_rule_suggestions: false,
      api_retry_attempts: 3,
      exception_fact_retention_days: 30,
      exception_fact_archive_retention_days: 180,
      exception_analytics_projection_retention_days: 365,
      exception_fact_purge_batch_size: 5000,
      exception_fact_jit_request_timeout_minutes: 30,
    }

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(_input)

      if (url.includes('/ui-registry')) {
        return {
          ok: true,
          json: async () => ({
            source: 'default',
            version: '1.0.0',
            cache_ttl_seconds: 300,
            styles: [
              { id: 'data-web-css', label: 'Data Web CSS' },
              { id: 'astrowind', label: 'AstroWind' },
            ],
            component_bundles: [
              { id: 'tabler', label: 'Registry Tabler', adapter: 'app.adapters.icons.tabler', fallback: 'fallback' },
              { id: 'lucide', label: 'Registry Lucide', adapter: 'app.adapters.icons.lucide', fallback: 'replace' },
              { id: 'icons', label: 'Icons', adapter: 'app.adapters.icons', fallback: 'ignore' },
            ],
            metadata: { storage_table: 'ui_registry_manifest' },
          }),
        }
      }

      if (init?.method === 'PUT') {
        const body = JSON.parse(String(init.body || '{}')) as Record<string, unknown>
        Object.assign(currentAppConfig, body)
        return {
          ok: true,
          text: async () => '',
          json: async () => ({ ...currentAppConfig }),
        }
      }

      return {
        ok: true,
        json: async () => ({ ...currentAppConfig }),
      }
    })

    vi.stubGlobal('fetch', fetchMock)
  })

  it('saves changed application setting via settings context and app-config PUT', async () => {
    render(<ApplicationSettings />)

    const suggestionsToggle = await screen.findByLabelText('Enable suggestions (AI-powered)')
    fireEvent.click(suggestionsToggle)

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: { apiBaseUrl: 'http://localhost:9111/api/v1' },
      })
    })

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')

    expect(putCall).toBeDefined()
    expect(String(putCall?.[0])).toContain('/system/v1/app-config')
    expect(String(putCall?.[0])).not.toContain('/v1/v1')

    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload.feature_rule_suggestions).toBe(true)

    expect(await screen.findByText('Settings saved successfully')).toBeTruthy()
  })

  it('persists numeric application values in app-config payload', async () => {
    render(<ApplicationSettings />)

    const retryAttemptsInput = await screen.findByLabelText('API Retry Attempts')
    fireEvent.change(retryAttemptsInput, { target: { value: '7' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: { apiBaseUrl: 'http://localhost:9111/api/v1' },
      })
    })

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')

    expect(putCall).toBeDefined()
    expect(String(putCall?.[0])).toContain('/system/v1/app-config')
    expect(String(putCall?.[0])).not.toContain('/v1/v1')

    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload.api_retry_attempts).toBe(7)
    expect(payload.assistance_request_itsm_auth_token).toBeUndefined()
    expect(payload.support_email_smtp_password).toBeUndefined()
  })

  it('persists the style package selection in app-config payload', async () => {
    render(<ApplicationSettings />)

    await screen.findByText(/Styles: data-web-css \(Data Web CSS\), astrowind \(AstroWind\)/)

    const stylePackageSelect = await screen.findByLabelText('Style package')
    expect(screen.getByText('Controls which stylesheet the app loads at runtime.')).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Custom-built CSS package (current)' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Data Web CSS' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'AstroWind' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Data Web CSS' })).toBeTruthy()
    fireEvent.change(stylePackageSelect, { target: { value: 'astrowind' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: {
          apiBaseUrl: 'http://localhost:9111/api/v1',
          stylePackage: 'astrowind',
        },
      })
    })

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')

    expect(putCall).toBeDefined()

    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload.style_package).toBe('astrowind')
  })

  it('renders registry-provided stylesheet and component bundle summaries', async () => {
    render(<ApplicationSettings />)

    expect(await screen.findByText(/Styles: data-web-css \(Data Web CSS\), astrowind \(AstroWind\)/)).toBeTruthy()
    expect(screen.getAllByText(/Component bundles: tabler \(Registry Tabler, app.adapters.icons.tabler, fallback=fallback\), lucide \(Registry Lucide, app.adapters.icons.lucide, fallback=replace\), icons \(Icons, app.adapters.icons, fallback=ignore\)/).length).toBeGreaterThan(0)
  })

  it('uses registry-backed labels for icon provider options when bundles map to known adapters', async () => {
    render(<ApplicationSettings />)

    const iconProviderSelect = await screen.findByLabelText('Icon provider')
    expect(iconProviderSelect).toBeTruthy()
    expect(screen.getAllByRole('option', { name: 'Registry Tabler' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('option', { name: 'Registry Lucide' }).length).toBeGreaterThan(0)
  })

  it('persists the data web css selection in app-config payload', async () => {
    render(<ApplicationSettings />)

    const stylePackageSelect = await screen.findByLabelText('Style package')
    fireEvent.change(stylePackageSelect, { target: { value: 'data-web-css' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: {
          apiBaseUrl: 'http://localhost:9111/api/v1',
          stylePackage: 'data-web-css',
        },
      })
    })

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')

    expect(putCall).toBeDefined()

    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload.style_package).toBe('data-web-css')
  })

  it('persists alert routing policy to both app-config and workspace settings payloads', async () => {
    render(<ApplicationSettings />)

    const appDeliveryTarget = await screen.findByLabelText('Global alert delivery target')
    fireEvent.change(appDeliveryTarget, { target: { value: 'itsm' } })

    const workspaceDeliveryTarget = await screen.findByLabelText('Workspace alert delivery target')
    fireEvent.change(workspaceDeliveryTarget, { target: { value: 'both' } })

    const workspaceMandatoryRoles = (await screen.findAllByLabelText('Mandatory roles'))[0]
    fireEvent.change(workspaceMandatoryRoles, { target: { value: 'admin, workspace-admin' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: { apiBaseUrl: 'http://localhost:9111/api/v1' },
      })
    })

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCalls = fetchMock.mock.calls.filter((call) => call[1]?.method === 'PUT')

    expect(putCalls.some((call) => String(call[0]).includes('/system/v1/app-config'))).toBe(true)
    expect(putCalls.some((call) => String(call[0]).includes('/rulebuilder/v1/workspaces/ws-1'))).toBe(true)

    const appConfigCall = putCalls.find((call) => String(call[0]).includes('/system/v1/app-config'))
    const workspaceCall = putCalls.find((call) => String(call[0]).includes('/rulebuilder/v1/workspaces/ws-1'))

    expect(appConfigCall).toBeDefined()
    expect(workspaceCall).toBeDefined()

    const appPayload = JSON.parse((appConfigCall?.[1] as RequestInit).body as string)
    const workspacePayload = JSON.parse((workspaceCall?.[1] as RequestInit).body as string)

    expect(appPayload.alert_routing_policy.delivery_target).toBe('itsm')
    expect(workspacePayload.alert_routing_policy.delivery_target).toBe('both')
    expect(workspacePayload.alert_routing_policy.mandatory_roles).toEqual(['admin', 'workspace-admin'])
  })

  it('persists Slack and PagerDuty connectivity settings in the app-config payload', async () => {
    render(<ApplicationSettings />)

    const slackWebhookInput = await screen.findByLabelText('Slack Incoming Webhook URL')
    fireEvent.change(slackWebhookInput, {
      target: { value: 'https://hooks.slack.com/services/T000/B000/XXXXX' },
    })
    await waitFor(() => {
      expect((slackWebhookInput as HTMLInputElement).value).toBe('https://hooks.slack.com/services/T000/B000/XXXXX')
    })

    const pagerDutyInput = await screen.findByLabelText('PagerDuty Routing Key')
    fireEvent.change(pagerDutyInput, {
      target: { value: 'pagerduty-routing-key' },
    })
    await waitFor(() => {
      expect((pagerDutyInput as HTMLInputElement).value).toBe('pagerduty-routing-key')
    })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: { apiBaseUrl: 'http://localhost:9111/api/v1' },
      })
    })

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')

    expect(putCall).toBeDefined()
    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload.alerting_slack_webhook_url).toBe('https://hooks.slack.com/services/T000/B000/XXXXX')
    expect(payload.alerting_pagerduty_routing_key).toBe('pagerduty-routing-key')
  })

  it('persists exception retention values in app-config payload', async () => {
    render(<ApplicationSettings />)

    const retentionInput = await screen.findByLabelText('Exception Facts Retention (days)')
    const archiveInput = await screen.findByLabelText('Exception Fact Archive Retention (days)')
    const analyticsInput = await screen.findByLabelText('Exception Analytics Retention (days)')
    const batchInput = await screen.findByLabelText('Exception Fact Purge Batch Size')

    fireEvent.change(retentionInput, { target: { value: '45' } })
    fireEvent.change(archiveInput, { target: { value: '365' } })
    fireEvent.change(analyticsInput, { target: { value: '730' } })
    fireEvent.change(batchInput, { target: { value: '2500' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: { apiBaseUrl: 'http://localhost:9111/api/v1' },
      })
    })

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')

    expect(putCall).toBeDefined()

    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload.exception_fact_retention_days).toBe(45)
    expect(payload.exception_fact_archive_retention_days).toBe(365)
    expect(payload.exception_analytics_projection_retention_days).toBe(730)
    expect(payload.exception_fact_purge_batch_size).toBe(2500)
  })

  it('persists the agent access policy values in app-config payload', async () => {
    render(<ApplicationSettings />)

    const addAllowedAgentButton = await screen.findByRole('button', { name: 'Add allowed agent' })
    fireEvent.click(addAllowedAgentButton)

    const defaultActionSelect = await screen.findByLabelText('Agent default action')
    fireEvent.change(defaultActionSelect, { target: { value: 'allow' } })

    const agentTypeInput = await screen.findByLabelText('Allowed agent type 1')
    fireEvent.change(agentTypeInput, { target: { value: 'mcp' } })
    const agentSourceInput = await screen.findByLabelText('Allowed agent source 1')
    fireEvent.change(agentSourceInput, { target: { value: 'dq-made-easy-mcp' } })
    const agentInstanceInput = await screen.findByLabelText('Allowed agent instance id 1')
    fireEvent.change(agentInstanceInput, { target: { value: 'dq-made-easy-mcp:4242' } })
    const requestOriginInput = await screen.findByLabelText('Allowed agent request origin 1')
    fireEvent.change(requestOriginInput, { target: { value: 'stdio' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: { apiBaseUrl: 'http://localhost:9111/api/v1' },
      })
    })

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')

    expect(putCall).toBeDefined()

    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload.agent_access_policy).toEqual({
      default_action: 'allow',
      allowed_agents: [
        {
          agent_type: 'mcp',
          agent_source: 'dq-made-easy-mcp',
          agent_instance_id: 'dq-made-easy-mcp:4242',
          request_origin: 'stdio',
        },
      ],
    })
  })

  it('saves the smtp password without requiring the API to echo it back', async () => {
    render(<ApplicationSettings />)

    const passwordInput = await screen.findByLabelText('SMTP Password')
    fireEvent.change(passwordInput, { target: { value: 'super-secret-password' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: { apiBaseUrl: 'http://localhost:9111/api/v1' },
      })
    })

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')

    expect(putCall).toBeDefined()
    expect(String(putCall?.[0])).toContain('/system/v1/app-config')

    const payload = JSON.parse((putCall?.[1] as RequestInit).body as string)
    expect(payload.support_email_smtp_password).toBe('super-secret-password')

    expect(await screen.findByText('Settings saved successfully')).toBeTruthy()
  })

  it('fails fast when preferences save fails and does not call app-config PUT', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    updateSettings.mockRejectedValueOnce(new Error('Failed to save settings'))
    render(<ApplicationSettings />)

    const retryAttemptsInput = await screen.findByLabelText('API Retry Attempts')
    fireEvent.change(retryAttemptsInput, { target: { value: '9' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    const statusBanner = await screen.findByRole('status')
    expect(statusBanner.textContent).toContain('Failed to save settings')

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>
    const putCalls = fetchMock.mock.calls.filter((call) => call[1]?.method === 'PUT')
    expect(putCalls).toHaveLength(0)

    consoleErrorSpy.mockRestore()
  })

  it('hydrates suggestions toggle from snake_case app-config responses', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/ui-registry')) {
        return {
          ok: true,
          json: async () => ({
            source: 'default',
            version: '1.0.0',
            styles: [],
            component_bundles: [],
          }),
        }
      }

      return {
        ok: true,
        json: async () => ({
          sso_enabled: false,
          sso_provider: 'none',
          allow_local_auth: true,
          feature_rule_suggestions: true,
        }),
      }
    })

    vi.stubGlobal('fetch', fetchMock)

    render(<ApplicationSettings />)

    await waitFor(() => {
      expect((screen.getByLabelText('Enable suggestions (AI-powered)') as HTMLInputElement).checked).toBe(true)
    })
  })

  it('renders jump to section as segmented navigation', async () => {
    render(<ApplicationSettings />)

    expect((await screen.findAllByText('Jump to section:')).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('tab', { name: 'Authentication & SSO' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('tab', { name: 'Workspace Configuration' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('tab', { name: 'Data Retention' }).length).toBeGreaterThan(0)
  })

  it('shows a registry snapshot in the application settings UI', async () => {
    render(<ApplicationSettings />)

    expect(screen.getAllByText('UI registry snapshot').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Source: default/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Version: 1.0.0/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Styles: 2/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Component bundles: 1/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Stored in ui_registry_manifest/).length).toBeGreaterThan(0)
  })
})