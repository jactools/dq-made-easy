/** @vitest-environment jsdom */

import React from 'react'
import { render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { VersionInfoModal } from './VersionInfoModal'

const mockUseSettings = vi.fn(() => ({
  applicationSettings: {
    apiBaseUrl: 'http://localhost:9111/api/v1',
  },
}))

const mockUseVersionCatalog = vi.fn(() => ({
  versionCatalog: {
    apps: {
      ui: '1.2.3',
      api: '4.5.6',
    },
    components: {},
  },
}))

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
}))

vi.mock('../hooks/useVersionCatalog', () => ({
  useVersionCatalog: () => mockUseVersionCatalog(),
}))

vi.mock('./ModalShell', () => ({
  ModalShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

describe('VersionInfoModal', () => {
  afterEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('fetches system information without auth headers', async () => {
    vi.stubGlobal('__BUILD_DATE__', '2026-04-11')

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        api: { version: '4.5.6', buildDate: '2026-04-11T00:00:00Z' },
        database: {
          schemaVersion: '2026.04.11',
          schemaUpdated: null,
          schemaGitCommit: null,
        },
        deployment: {
          deploymentVerificationDate: null,
          deploymentVerifiedBy: null,
        },
        versions: {
          apps: { ui: '1.2.3', api: '4.5.6' },
          components: {},
        },
      }),
    })

    vi.stubGlobal('fetch', fetchMock)

    render(<VersionInfoModal isOpen={true} onClose={vi.fn()} />)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:9111/system/v1/system-info')
    expect(fetchMock.mock.calls[0]?.[1]).toBeUndefined()
  })
})