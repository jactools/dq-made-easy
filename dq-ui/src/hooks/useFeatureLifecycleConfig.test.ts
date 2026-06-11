// @vitest-environment jsdom

import { describe, expect, it, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useFeatureLifecycleConfig } from './useFeatureLifecycleConfig'

const mockUseSettings = vi.fn(() => ({
  applicationSettings: {
    apiBaseUrl: 'http://localhost:9111/api/v1',
  },
}))

vi.mock('./useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

vi.mock('./useKeycloak', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}))

describe('useFeatureLifecycleConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults Rule Validation to live when app-config cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unavailable')))

    const { result } = renderHook(() => useFeatureLifecycleConfig())

    await waitFor(() => {
      expect(result.current.getFeatureState('feature_rule_validation')).toEqual({
        enabled: true,
        stage: 'live',
      })
    })
  })

  it('hydrates lifecycle states from snake_case app-config fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        feature_rule_suggestions: true,
        feature_rule_suggestions_stage: 'live',
        feature_rule_validation: true,
        feature_rule_validation_stage: 'live',
      }),
    })

    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useFeatureLifecycleConfig())

    await waitFor(() => {
      expect(result.current.getFeatureState('feature_rule_suggestions')).toEqual({
        enabled: true,
        stage: 'live',
      })
    })

    expect(result.current.getFeatureState('feature_rule_validation')).toEqual({
      enabled: true,
      stage: 'live',
    })
  })
})
