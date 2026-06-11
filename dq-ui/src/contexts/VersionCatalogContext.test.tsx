/** @vitest-environment jsdom */

import React from 'react'
import { render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { VersionCatalogProvider } from './VersionCatalogContext'
import { useVersionCatalog } from '../hooks/useVersionCatalog'

const mockUseSettings = vi.fn(() => ({
  applicationSettings: {
    apiBaseUrl: 'http://localhost:9111/api/v1',
  },
}))

const mockUseAuth = vi.fn(() => ({
  isAuthenticated: false,
}))

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

describe('VersionCatalogProvider', () => {
  afterEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('does not fetch the version catalog before authentication', async () => {
    const fetchMock = vi.fn()

    vi.stubGlobal('fetch', fetchMock)

    const Consumer: React.FC = () => {
      const { versionCatalog } = useVersionCatalog()
      return <div data-testid="ui-version">v{versionCatalog.apps.ui}</div>
    }

    render(
      <VersionCatalogProvider>
        <Consumer />
      </VersionCatalogProvider>
    )

    await waitFor(() => {
      expect(fetchMock).not.toHaveBeenCalled()
    })

    expect(document.querySelector('[data-testid="ui-version"]')?.textContent).toMatch(/^v.+$/)
  })
})