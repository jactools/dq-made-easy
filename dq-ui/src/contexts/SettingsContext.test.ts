/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import {
  normalizeApplicationPreferences,
  normalizeDisplayPreferences,
  serializePreferencesForApi,
  SettingsProvider,
  SettingsContext,
} from './SettingsContext'

const createJsonResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

const SettingsProbe = () => {
  const settings = React.useContext(SettingsContext)

  if (!settings) {
    throw new Error('Expected SettingsContext to be available')
  }

  return React.createElement(
    React.Fragment,
    null,
    React.createElement(
      'div',
      { 'data-testid': 'default-rule-threshold' },
      String(settings.applicationSettings?.defaultRuleThresholdPct ?? ''),
    ),
    React.createElement(
      'div',
      { 'data-testid': 'style-package' },
      String(settings.applicationSettings?.stylePackage ?? ''),
    ),
  )
}

beforeEach(() => {
  localStorage.setItem('authToken', 'test-token')
  localStorage.setItem(
    'authState',
    JSON.stringify({
      isAuthenticated: true,
      currentWorkspaceId: 'default',
    }),
  )

  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/admin/v1/me')) {
        return createJsonResponse({
          id: 'user-1',
          email: 'tester@example.com',
          preferences: {
            application: {
              apiBaseUrl: 'http://localhost:9111/api/v1',
            },
          },
        })
      }

      if (url.includes('/app-config')) {
        return createJsonResponse({
          defaultRuleThresholdPct: 95,
        })
      }

      return createJsonResponse({})
    }),
  )
})

afterEach(() => {
  cleanup()
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('SettingsContext display preference mapping', () => {
  it('hydrates the default rule threshold from runtime app-config', async () => {
    render(
      React.createElement(SettingsProvider, null, React.createElement(SettingsProbe)),
    )

    await waitFor(() => {
      expect(screen.getByTestId('default-rule-threshold').textContent).toBe('95')
    })
  })

  it('hydrates display settings from snake_case /me preferences', () => {
    const normalized = normalizeDisplayPreferences({
      user_id: 'user-1',
      theme: 'auto',
      items_per_page: 25,
      compact_mode: true,
      show_tooltips: false,
      preferred_date_format: 'YYYY-MM-DD',
      participate_in_previews: true,
      updated_at: '2026-03-28T10:00:00Z',
    })

    expect(normalized).toEqual({
      userId: 'user-1',
      theme: 'auto',
      itemsPerPage: 25,
      compactMode: true,
      showTooltips: false,
      preferredDateFormat: 'YYYY-MM-DD',
      participateInPreviews: true,
      updatedAt: '2026-03-28T10:00:00Z',
    })
  })

  it('hydrates application settings from snake_case /me preferences', () => {
    const normalized = normalizeApplicationPreferences({
      api_base_url: 'http://localhost:9111/api/v1/',
      style_package: 'astrowind',
    })

    expect(normalized).toMatchObject({
      apiBaseUrl: 'http://localhost:9111',
      stylePackage: 'astrowind',
    })
  })

  it('preserves unknown application style package ids during normalization', () => {
    const normalized = normalizeApplicationPreferences({
      style_package: 'custom-registry-theme',
    })

    expect(normalized).toMatchObject({
      stylePackage: 'custom-registry-theme',
    })
  })

  it('preserves unknown application icon provider ids during normalization', () => {
    const normalized = normalizeApplicationPreferences({
      icon_provider: 'custom-registry-icons',
    })

    expect(normalized).toMatchObject({
      iconProvider: 'custom-registry-icons',
    })
  })

  it('keeps the saved style package when /me returns snake_case preferences', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)

        if (url.includes('/admin/v1/me')) {
          return createJsonResponse({
            id: 'user-1',
            email: 'tester@example.com',
            preferences: {
              application: {
                api_base_url: 'http://localhost:9111/api/v1',
                style_package: 'astrowind',
              },
            },
          })
        }

        if (url.includes('/app-config')) {
          return createJsonResponse({
            default_rule_threshold_pct: 95,
          })
        }

        return createJsonResponse({})
      }),
    )

    render(
      React.createElement(SettingsProvider, null, React.createElement(SettingsProbe)),
    )

    await waitFor(() => {
      expect(screen.getByTestId('style-package').textContent).toBe('astrowind')
    })
  })

  it('serializes display settings to snake_case before /me save', () => {
    const serialized = serializePreferencesForApi({
      display: {
        userId: 'user-9',
        theme: 'dark',
        itemsPerPage: 50,
        compactMode: true,
        showTooltips: false,
        preferredDateFormat: 'DD/MM/YYYY',
        participateInPreviews: true,
        updatedAt: '2026-03-28T11:00:00Z',
      },
    })

    expect(serialized).toEqual({
      display: {
        user_id: 'user-9',
        theme: 'dark',
        items_per_page: 50,
        compact_mode: true,
        show_tooltips: false,
        preferred_date_format: 'DD/MM/YYYY',
        participate_in_previews: true,
        updated_at: '2026-03-28T11:00:00Z',
      },
    })
  })
})
