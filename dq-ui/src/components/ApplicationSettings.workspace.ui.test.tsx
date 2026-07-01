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

describe('ApplicationSettings workspace configuration', () => {
  beforeEach(() => {
    updateSettings.mockClear()
    authState.currentWorkspaceId = 'ws-1'
    authState.user.workspaceRoles = [{ workspaceId: 'ws-1', role: 'admin' }]
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    })

    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL) => ({
      ok: true,
      json: async () => ({}),
    })))
  })

  it('saves workspace configuration from administration', async () => {
    render(<ApplicationSettings />)

    const namingPrefixInput = await screen.findByLabelText('Rule Naming Prefix')
    fireEvent.change(namingPrefixInput, { target: { value: 'GOV_' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'workspace',
        data: expect.objectContaining({
          ruleNamingPrefix: 'GOV_',
        }),
      })
    })
  })

  it('persists playground bundle disablement per workspace', async () => {
    render(<ApplicationSettings />)

    fireEvent.click(screen.getAllByRole('tab', { name: 'Workspace Configuration' })[0])

    const bundleToggle = await screen.findByRole('checkbox', { name: /Office for National Statistics/ })
    expect((bundleToggle as HTMLInputElement).checked).toBe(true)

    fireEvent.click(bundleToggle)

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'workspace',
        data: expect.objectContaining({
          disabledPlaygroundSourceBundleIds: expect.arrayContaining(['ons-national-statistics']),
        }),
      })
    })
  })

  it('saves reconciliation datasources from workspace settings', async () => {
    render(<ApplicationSettings />)

    fireEvent.click(screen.getAllByRole('tab', { name: 'Workspace Configuration' })[0])

    fireEvent.click(screen.getAllByRole('button', { name: 'Add datasource' })[0])

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'ADLS Bronze' } })
    fireEvent.change(screen.getByLabelText('Connection string'), { target: { value: 'abfss://bronze@storage.dfs.core.windows.net' } })
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Bronze reconciliation source' } })
    fireEvent.change(screen.getByLabelText('Connection parameters'), { target: { value: '{"container":"bronze","path":"/reconciliation"}' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'workspace',
        data: expect.objectContaining({
          reconciliationDataSources: expect.arrayContaining([
            expect.objectContaining({
              name: 'ADLS Bronze',
              sourceType: 'adls',
            }),
          ]),
        }),
      })
    })
  })

  it('renders workspace settings read-only for non-admin users', async () => {
    authState.user.workspaceRoles = [{ workspaceId: 'ws-1', role: 'viewer' }]

    render(<ApplicationSettings />)

    fireEvent.click(screen.getAllByRole('tab', { name: 'Workspace Configuration' })[0])

    expect(
      screen.getByText('Workspace values are read-only here. Only a workspace admin can change them.'),
    ).toBeTruthy()

    const retryAttemptsInput = await screen.findByLabelText('API Retry Attempts')
    fireEvent.change(retryAttemptsInput, { target: { value: '8' } })

    const saveButtons = await screen.findAllByRole('button', { name: 'Save Changes' })
    fireEvent.click(saveButtons[0])

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: { apiBaseUrl: 'http://localhost:9111/api/v1' },
      })
    })

    expect((updateSettings.mock.calls as Array<[SettingsUpdatePayload]>).some((call: [SettingsUpdatePayload]) => call[0]?.category === 'workspace')).toBe(false)

    authState.user.workspaceRoles = [{ workspaceId: 'ws-1', role: 'admin' }]
  })
})