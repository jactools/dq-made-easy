/** @vitest-environment jsdom */

import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useAgentHarness } from './useAgentHarness'

const mockUseSettings = vi.fn()

vi.mock('./useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('useAgentHarness', () => {
  it('loads the agent catalog from the agent API group', async () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://localhost:8000/api',
      },
    })

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ([
        {
          id: 'general',
          name: 'General DQ Assistant',
          description: 'General-purpose DQ assistant for all data quality tasks',
          capabilities: ['Answer DQ questions'],
          tools: ['dq_connector', 'dq_rule', 'dq_definition'],
          status: 'available',
        },
      ]),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAgentHarness())

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('http://localhost:8000/api/agent/v1/agents')
    expect(result.current.agents).toHaveLength(1)
    expect(result.current.error).toBeNull()
  })
})
