/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useCatalogTerms } from './useCatalogTerms'

const mockUseSettings = vi.fn()

vi.mock('./useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('useCatalogTerms', () => {
  it('sends the application default threshold when the user has no override', async () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://localhost:8000/v1',
        debounceMs: 125,
        defaultCatalogTermMatchThresholdPct: 72,
      },
      displaySettings: {
        catalogTermMatchThresholdPct: undefined,
      },
    })

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ terms: [], lastSynced: '2026-05-04T00:00:00Z' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useCatalogTerms('percent must be under'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('match_threshold_pct=72')
    expect(String(url)).toContain('search=percent+must+be+under')
  })

  it('uses the user display override when present', async () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://localhost:8000/v1',
        debounceMs: 125,
        defaultCatalogTermMatchThresholdPct: 72,
      },
      displaySettings: {
        catalogTermMatchThresholdPct: 88,
      },
    })

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ terms: [], lastSynced: '2026-05-04T00:00:00Z' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useCatalogTerms('percent must be under'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('match_threshold_pct=88')
  })

  it('debounces rapid search query updates into a single fetch', async () => {
    vi.useFakeTimers()

    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://localhost:8000/v1',
        debounceMs: 125,
        defaultCatalogTermMatchThresholdPct: 72,
      },
      displaySettings: {
        catalogTermMatchThresholdPct: undefined,
      },
    })

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ terms: [], lastSynced: '2026-05-04T00:00:00Z' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { rerender } = renderHook(({ query }) => useCatalogTerms(query), {
      initialProps: { query: '' },
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    fetchMock.mockClear()

    act(() => {
      rerender({ query: 'a percentage must be low' })
      rerender({ query: 'a percentage must be lowe' })
      rerender({ query: 'a percentage must be lower than 10%' })
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(125)
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('search=a+percentage+must+be+lower+than+10%25')
  })
})
