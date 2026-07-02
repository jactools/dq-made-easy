/* @vitest-environment jsdom */

import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { UIRegistryAdmin } from './UIRegistryAdmin'
import type { SettingsUpdatePayload } from '../types/settings'

const updateSettings = vi.fn(async (_payload: SettingsUpdatePayload) => {})

const settingsMock = {
  userSettings: null,
  notificationSettings: null,
  displaySettings: null,
  workspaceSettings: null,
  securitySettings: null,
  apiSettings: null,
  applicationSettings: {
    ssoEnabled: false,
    ssoProvider: 'none',
    stylePackage: 'custom-built-package',
    iconProvider: 'tabler',
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
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => ({
    currentWorkspaceId: 'ws-1',
    user: { workspaceRoles: [{ workspaceId: 'ws-1', role: 'admin' }] },
    hasScope: vi.fn(() => true),
  }),
}))

beforeEach(() => {
  updateSettings.mockClear()
  settingsMock.applicationSettings = {
    ...settingsMock.applicationSettings,
    stylePackage: 'custom-built-package',
    iconProvider: 'tabler',
  }

  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)

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
          ],
          metadata: { storage_table: 'ui_registry_manifest' },
        }),
      }
    }

    return {
      ok: true,
      json: async () => ({}),
    }
  }))
})

describe('UIRegistryAdmin', () => {
  it('shows the registry snapshot and icon gallery on the dedicated admin page', async () => {
    render(<UIRegistryAdmin />)

    expect(await screen.findByRole('heading', { name: 'UI Registry' })).toBeTruthy()
    expect(screen.queryByText('UI registry settings saved successfully')).toBeNull()
    expect(await screen.findByText(/Source: default/)).toBeTruthy()
    expect(await screen.findByText(/Version: 1.0.0/)).toBeTruthy()
    expect(await screen.findByText('Icon Gallery')).toBeTruthy()
  })

  it('persists registry-backed style package and icon provider selections', async () => {
    render(<UIRegistryAdmin />)

    const stylePackageSelect = await screen.findByLabelText('Style package')
    expect(screen.getByRole('option', { name: 'Custom-built CSS package (current)' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Data Web CSS' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'AstroWind' })).toBeTruthy()
    fireEvent.change(stylePackageSelect, { target: { value: 'astrowind' } })

    const iconProviderSelect = await screen.findByLabelText('Icon provider')
    expect(screen.getByRole('option', { name: 'Registry Tabler' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Registry Lucide' })).toBeTruthy()
    fireEvent.change(iconProviderSelect, { target: { value: 'lucide' } })

    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }))

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        category: 'application',
        data: {
          apiBaseUrl: 'http://localhost:9111/api/v1',
          iconProvider: 'lucide',
          stylePackage: 'astrowind',
        },
      })
    })
  })
})
