/* @vitest-environment jsdom */

import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

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
  useSettingsOptional: () => settingsMock,
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

  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)

    if (url.includes('/ui-registry/assets/upload')) {
      const formData = init?.body as FormData
      const kind = formData?.get('kind') === 'component' ? 'component' : 'style'
      const file = formData?.get('file') as File | null
      const kindSegment = kind === 'component' ? 'component-bundles' : 'styles'

      return {
        ok: true,
        json: async () => ({
          kind: kindSegment,
          source_url: file ? `upload://${file.name}` : 'upload://bundle.zip',
          file_name: file?.name || 'uploaded-bundle.css',
          content_type: file?.type || 'application/octet-stream',
          asset_path: `/tmp/ui-registry-assets/${kindSegment}/uploaded-bundle.css`,
          public_url: `/system/v1/ui-registry/assets/${kindSegment}/uploaded-bundle.css`,
          byte_count: 24,
        }),
      }
    }

    if (url.includes('/ui-registry/assets/import')) {
      const body = typeof init?.body === 'string' ? JSON.parse(init.body) : {}
      const kindSegment = body.kind === 'component' ? 'component-bundles' : 'styles'

      return {
        ok: true,
        json: async () => ({
          kind: kindSegment,
          source_url: body.source_url,
          file_name: body.filename || 'uploaded-asset.css',
          content_type: 'text/css',
          asset_path: `/tmp/ui-registry-assets/${kindSegment}/uploaded-asset.css`,
          public_url: `/system/v1/ui-registry/assets/${kindSegment}/uploaded-asset.css`,
          byte_count: 24,
        }),
      }
    }

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
  const getSection = async (container: HTMLElement, headingName: string): Promise<HTMLElement> => {
    const heading = await within(container).findByRole('heading', { name: headingName })
    const section = heading.closest('.settings-section')
    if (!section) {
      throw new Error(`Missing settings section for ${headingName}`)
    }
    return section as HTMLElement
  }

  it('shows dedicated import sections for style and component bundles', async () => {
    const view = render(<UIRegistryAdmin />)

    expect(await view.findByRole('heading', { name: 'Import Style Bundle' })).toBeTruthy()
    expect(view.getByRole('heading', { name: 'Import Component Bundle' })).toBeTruthy()
  })

  it('shows the registry snapshot and icon gallery on the dedicated admin page', async () => {
    const view = render(<UIRegistryAdmin />)

    expect(within(view.container).getByRole('heading', { name: 'UI Registry' })).toBeTruthy()
    expect(within(view.container).queryByText('UI registry settings saved successfully')).toBeNull()
    expect(await within(view.container).findByText(/Source: default/)).toBeTruthy()
    expect(await within(view.container).findByText(/Version: 1.0.0/)).toBeTruthy()
    expect(await within(view.container).findByText('Icon Gallery')).toBeTruthy()
  })

  it('persists registry-backed style package and icon provider selections', async () => {
    const view = render(<UIRegistryAdmin />)

    const stylePackageSelect = await view.findByLabelText('Style package')
    expect(within(stylePackageSelect).getByRole('option', { name: 'Custom-built CSS package (current)' })).toBeTruthy()
    expect(within(stylePackageSelect).getByRole('option', { name: 'Data Web CSS' })).toBeTruthy()
    expect(within(stylePackageSelect).getByRole('option', { name: 'AstroWind' })).toBeTruthy()
    fireEvent.change(stylePackageSelect, { target: { value: 'astrowind' } })

    const iconProviderSelect = await view.findByLabelText('Icon provider')
    expect(within(iconProviderSelect).getByRole('option', { name: 'Registry Tabler' })).toBeTruthy()
    expect(within(iconProviderSelect).getByRole('option', { name: 'Registry Lucide' })).toBeTruthy()
    fireEvent.change(iconProviderSelect, { target: { value: 'lucide' } })

    fireEvent.click(view.getByRole('button', { name: 'Save Changes' }))

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

  it('imports a style bundle through the ui registry asset endpoint', async () => {
    const view = render(<UIRegistryAdmin />)

    const styleSection = await getSection(view.container, 'Import Style Bundle')
    const styleSourceInput = document.getElementById('styleBundleSourceUrl') as HTMLInputElement | null
    const styleFilenameInput = document.getElementById('styleBundleFilename') as HTMLInputElement | null

    if (!styleSourceInput || !styleFilenameInput) {
      throw new Error('Missing style bundle inputs')
    }

    fireEvent.change(styleSourceInput, {
      target: { value: 'https://example.com/theme.css' },
    })
    fireEvent.change(styleFilenameInput, {
      target: { value: 'theme.css' },
    })

    expect(within(styleSection).getByRole('button', { name: 'Import Style Bundle' })).toBeTruthy()
    expect((document.getElementById('styleBundleSourceUrl') as HTMLInputElement).value).toBe('https://example.com/theme.css')
    expect((document.getElementById('styleBundleFilename') as HTMLInputElement).value).toBe('theme.css')
    expect(updateSettings).not.toHaveBeenCalledWith(expect.objectContaining({ category: 'application' }))
  })

  it('uploads a style bundle archive through the ui registry asset endpoint', async () => {
    const view = render(<UIRegistryAdmin />)

    const styleSection = await getSection(view.container, 'Import Style Bundle')
    const styleArchiveInput = document.getElementById('styleBundleArchive') as HTMLInputElement | null

    if (!styleArchiveInput) {
      throw new Error('Missing style bundle archive input')
    }

    const archive = new File([new Uint8Array([80, 75, 3, 4])], 'theme.zip', { type: 'application/zip' })
    fireEvent.change(styleArchiveInput, {
      target: { files: [archive] },
    })

    expect(within(styleSection).getByRole('button', { name: 'Upload Style Bundle Archive' })).toBeTruthy()
    expect(document.getElementById('styleBundleArchive')).toBeTruthy()
  })

  it('uploads a component bundle archive through the ui registry asset endpoint', async () => {
    const view = render(<UIRegistryAdmin />)

    const componentSection = await getSection(view.container, 'Import Component Bundle')
    const componentArchiveInput = document.getElementById('componentBundleArchive') as HTMLInputElement | null

    if (!componentArchiveInput) {
      throw new Error('Missing component bundle archive input')
    }

    const archive = new File([new Uint8Array([31, 139, 8, 0])], 'icons.tgz', { type: 'application/gzip' })
    fireEvent.change(componentArchiveInput, {
      target: { files: [archive] },
    })

    expect(within(componentSection).getByRole('button', { name: 'Upload Component Bundle Archive' })).toBeTruthy()
    expect(document.getElementById('componentBundleArchive')).toBeTruthy()
  })
})
