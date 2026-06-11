/** @vitest-environment jsdom */
/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useSuggestions } from './useSuggestions'

const mockUseSettings = vi.fn()
const mockUseAuth = vi.fn()
const mockStartTimer = vi.fn(() => 'timer-1')
const mockEndTimer = vi.fn()

vi.mock('./useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

vi.mock('./useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../contexts/PerformanceMonitoringContext', () => ({
  usePerformanceMonitoringContext: () => ({
    startTimer: mockStartTimer,
    endTimer: mockEndTimer,
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

const buildJsonResponse = (body: unknown) => ({
  ok: true,
  status: 200,
  statusText: 'OK',
  text: async () => JSON.stringify(body),
})

const buildSuggestionPayload = () => ({
  suggestions: [
    {
      id: 'sug-1',
      user_id: 'user-1',
      data_source_id: 'nl-preview:retail-banking',
      suggested_rule: {
        name: 'Uniqueness draft for customer_id',
        description: 'Created from natural-language request.',
        expression: 'COUNT(DISTINCT customer_id) = COUNT(customer_id)',
        dimension: 'Uniqueness',
        rule_type: 'UNIQUENESS',
        check_type: 'UNIQUENESS',
        check_type_params: {
          attributes: ['customer_id'],
        },
        workspace_id: 'retail-banking',
        target_terms: ['customer_id'],
        search_scope: 'current',
        selected_attribute_ids: ['attr-retail-customer-id'],
        selected_attributes: [
          {
            attribute_id: 'attr-retail-customer-id',
            attribute_name: 'customer_id',
            version_id: 'version-retail',
            data_object_id: 'object-retail',
            data_object_name: 'customer_master',
            data_set_id: 'dataset-retail',
            data_set_name: 'Customer Records',
            data_product_id: 'product-retail',
            data_product_name: 'Retail Banking',
            workspace_id: 'retail-banking',
            parent_path: ['Retail Banking', 'Customer Records', 'customer_master'],
            confidence_score: 0.99,
            match_reasons: ['Exact attribute-name match'],
            current_context: true,
            match_roles: ['target'],
          },
        ],
        draft_summary: 'Uniqueness draft',
        parsed_condition: null,
        dsl: {
          schema_version: '2.0.0',
          rule: {
            kind: 'metric_threshold',
            scope: {
              dataset: {
                data_object_id: 'object-retail',
              },
            },
            measure: {
              type: 'metric',
              metric: 'duplicate_count',
              subject: {
                columns: ['customer_id'],
              },
            },
            expectation: {
              type: 'threshold',
              operator: 'lte',
              value: 0,
              unit: 'count',
            },
            evidence: {
              failed_rows: {
                mode: 'sample',
                limit: 25,
                include_row_identifier: true,
                include_primary_key: true,
              },
              emit_compiled_artifact: true,
              emit_generated_sql: false,
            },
            operations: {
              severity: 'critical',
              preferred_engines: ['gx', 'sql'],
              fail_if_not_native: false,
            },
          },
        },
        prompt: 'I want a uniqueness rule for attribute customer_id',
        original_prompt_text: 'I want a uniqueness rule for attribute customer_id',
      },
      confidence_score: 0.99,
      reason: 'Natural-language draft created from current scope after steward confirmation.',
      rule_type: 'UNIQUENESS',
      created_from_profiling_request_id: null,
      status: 'pending',
      created_at: '2026-04-27T00:00:00+00:00',
      expires_at: null,
    },
  ],
})

const fetchMock = vi.fn()

fetchMock.mockImplementation(async (input, init) => {
  const url = String(input)

  if (url.includes('/suggestions?')) {
    return buildJsonResponse(buildSuggestionPayload())
  }

  if (url.includes('/suggestions/data-sources')) {
    return buildJsonResponse({ data_sources: [], can_request_profiling: false })
  }

  if (url.includes('/profiling/requests?') && String(init?.method || '').toUpperCase() === 'POST') {
    return buildJsonResponse({ success: true, profiling_request_id: 'req-1', message: 'Data profiling started.' })
  }

  if (url.includes('/profiling/requests')) {
    return buildJsonResponse({ profiling_requests: [] })
  }

  if (url.includes('/rules')) {
    return buildJsonResponse({ id: 'rule-1' })
  }

  if (url.includes('/accept')) {
    const body = init?.body ? JSON.parse(String(init.body)) : {}
    return buildJsonResponse({ success: true, rule_id: body.rule_id })
  }

  if (url.includes('/apply')) {
    const body = init?.body ? JSON.parse(String(init.body)) : {}
    return buildJsonResponse({ success: true, rule_id: body.rule_id })
  }

  return buildJsonResponse({})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('useSuggestions', () => {
  it('creates a rule before accepting a suggestion', async () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://localhost:8000/api/v1',
      },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
    })

    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSuggestions())

    await waitFor(() => {
      expect(result.current.suggestions).toHaveLength(1)
    })

    await act(async () => {
      await result.current.acceptSuggestion('sug-1')
    })

    const ruleRequestIndex = fetchMock.mock.calls.findIndex(([url]) => String(url).includes('/rules'))
    const acceptRequestIndex = fetchMock.mock.calls.findIndex(([url]) => String(url).includes('/accept'))

    expect(ruleRequestIndex).toBeGreaterThan(-1)
    expect(acceptRequestIndex).toBeGreaterThan(ruleRequestIndex)

    const ruleRequest = fetchMock.mock.calls[ruleRequestIndex]
    const acceptRequest = fetchMock.mock.calls[acceptRequestIndex]

    expect(String(ruleRequest[0])).toContain('/rules')
    expect(String(acceptRequest[0])).toContain('/accept')

    expect(ruleRequest[1]?.method).toBe('POST')
    expect(acceptRequest[1]?.method).toBe('POST')
    expect(JSON.parse(String(acceptRequest[1]?.body))).toEqual({ rule_id: 'rule-1', workspace_id: 'retail-banking' })

    await waitFor(() => {
      expect(result.current.suggestions).toHaveLength(0)
    })
  })

  it('sends the active workspace with profiling requests', async () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://localhost:8000/api/v1',
      },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
    })

    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSuggestions())

    await waitFor(() => {
      expect(result.current.suggestions).toHaveLength(1)
    })

    await act(async () => {
      await result.current.requestProfiling('source-1')
    })

    const profilingRequest = fetchMock.mock.calls.find(([url, init]) => (
      String(url).includes('/profiling/requests?') && String(init?.method || '').toUpperCase() === 'POST'
    ))

    expect(profilingRequest).toBeTruthy()
    expect(String(profilingRequest?.[0])).toContain('/data-catalog/v1/profiling/requests?')
    expect(String(profilingRequest?.[0])).not.toContain('/suggestions/profiling/requests')
    expect(String(profilingRequest?.[0])).toContain('workspace_id=retail-banking')
    expect(String(profilingRequest?.[0])).toContain('data_source_id=source-1')
  })

  it('fetches profiling requests for the selected data source via the API filter', async () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://localhost:8000/api/v1',
      },
    })
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
    })

    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useSuggestions('source-42'))

    await waitFor(() => {
      const profilingRequestsCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/profiling/requests?'))
      expect(profilingRequestsCall).toBeTruthy()
      expect(String(profilingRequestsCall?.[0])).toContain('/data-catalog/v1/profiling/requests?')
      expect(String(profilingRequestsCall?.[0])).not.toContain('/suggestions/profiling/requests')
      expect(String(profilingRequestsCall?.[0])).toContain('limit=20')
      expect(String(profilingRequestsCall?.[0])).toContain('data_source_id=source-42')
    })
  })
})