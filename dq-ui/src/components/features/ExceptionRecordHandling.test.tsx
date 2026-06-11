/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ExceptionRecordHandling } from './ExceptionRecordHandling'

let mockAuth: any = null

vi.mock('../../hooks/useContexts', () => ({
  useAuth: () => mockAuth,
  useSettings: () => ({
    applicationSettings: {
      apiBaseUrl: 'http://example.com',
    },
  }),
}))

vi.mock('../../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

vi.mock('../../config/api', () => ({
  toApiGroupV1Base: (_group: string, baseUrl: string) => `${baseUrl}/rulebuilder/v1`,
}))

vi.mock('../../utils/caseConverters', () => ({
  snakeToCamel: (value: unknown) => value,
}))

vi.mock('../Button', () => ({
  PrimaryButton: ({ children, onClick, type, disabled }: any) => (
    <button type={type || 'button'} onClick={onClick} disabled={disabled}>{children}</button>
  ),
  SecondaryButton: ({ children, onClick, type, disabled }: any) => (
    <button type={type || 'button'} onClick={onClick} disabled={disabled}>{children}</button>
  ),
}))

vi.mock('../StatusBanner', () => ({
  StatusBanner: ({ message, onDismiss }: any) => (
    <div role="alert">
      <div>{message}</div>
      <button type="button" onClick={onDismiss}>Dismiss</button>
    </div>
  ),
}))

const analyticsResponse = {
  totalFailedRecords: 12,
  runsWithFailures: 4,
  trendBuckets: [
    { bucketStart: '2026-04-01T00:00:00Z', total: 3 },
  ],
  topRules: [
    { ruleId: 'rule-1', ruleName: 'Rule One', total: 5 },
  ],
  topDataObjects: [
    { dataObjectVersionId: 'dov-1', dataObjectName: 'Customers', total: 7 },
  ],
  topReasons: [
    { reasonCode: 'missing_value', reasonText: 'Missing value', total: 6 },
  ],
  reasonTrendBuckets: [],
  reasonFluctuations: [],
}

const factsResponse = {
  data: [
    {
      exceptionFactId: 'fact-1',
      exceptionFactContractVersion: '1.0',
      engineType: 'gx',
      executionScope: {
        deliveryId: 'delivery-1',
        executionPlanId: 'plan-1',
        executionPlanVersionId: 'plan-version-1',
        executionRunId: 'run-1',
        dataObjectVersionId: 'dov-1',
        datasetId: 'dataset-1',
        dataProductId: 'product-1',
      },
      artifactScope: {
        validationArtifactId: 'artifact-1',
        validationArtifactVersion: 1,
      },
      ruleScope: {
        ruleId: 'rule-1',
        ruleVersionId: 'rule-version-1',
      },
      recordReference: {
        identifierType: 'customer_id',
        identifierValue: '123',
        identifierFields: ['customer_id'],
        identifierHash: 'hash-1',
      },
      failure: {
        reasonCode: 'missing_value',
        reasonText: 'Missing value',
        failureClass: 'value_mismatch',
        detectedAt: '2026-04-01T12:00:00Z',
      },
      correlationId: 'corr-1',
      engineMetadata: { engine: 'gx' },
      opsMetadata: { workspace: 'retail-banking' },
    },
  ],
  pagination: {
    total: 1,
    page: 1,
    limit: 25,
    totalPages: 1,
    hasNext: false,
    hasPrevious: false,
  },
}

const analysisSessionResponse = {
  analysisSessionId: 'analysis-session-1',
  dataObjectVersionId: 'dov-1',
  executionRunId: 'run-1',
  ruleId: 'rule-1',
  anchorTotalCount: 3,
  sliceCount: 2,
  createdAt: '2026-04-06T12:00:00+00:00',
  updatedAt: '2026-04-06T12:05:00+00:00',
  analysisStatus: {
    state: 'budget_hit',
    reason: 'Budget hit after two slices.',
    remainingCount: 1,
    sliceCount: 2,
    materializedRecordCount: 2,
    maxSlices: 2,
    maxRecords: null,
    maxSeconds: null,
    budgetHit: true,
    exhausted: false,
    stalled: false,
  },
  currentSlice: {
    analysisSessionId: 'analysis-session-1',
    analysisSliceId: 'slice-1',
    sliceIndex: 1,
    dataObjectVersionId: 'dov-1',
    executionRunId: 'run-1',
    ruleId: 'rule-1',
    sliceLimit: 200,
    anchorTotalCount: 3,
    totalMatchingCount: 2,
    returnedCount: 1,
    truncated: false,
    analysisPackUri: 's3://analysis-bucket/analysis-session-1/slice-1.json.gz',
    analysisPackSha256: 'sha256:abc',
    filters: {
      dataObjectVersionId: 'dov-1',
      executionRunId: 'run-1',
      ruleId: 'rule-1',
      sliceLimit: 200,
      runUntilExhausted: true,
      maxSlices: 2,
      maxRecords: null,
      maxSeconds: null,
    },
    nextSliceSuggestion: {
      reasonCodes: ['type_mismatch'],
      failureClass: null,
      recordIdentifierType: null,
      recordIdentifierValueContains: null,
      search: null,
      remainingCount: 1,
      partitionStrategy: ['reason_code', 'hash_stripes'],
      rationale: '1 uncovered exception fact shares reason_code type_mismatch.',
    },
    createdAt: '2026-04-06T12:00:00+00:00',
    updatedAt: '2026-04-06T12:00:00+00:00',
    records: [],
  },
  slices: [
    {
      analysisSessionId: 'analysis-session-1',
      analysisSliceId: 'slice-1',
      sliceIndex: 1,
      dataObjectVersionId: 'dov-1',
      executionRunId: 'run-1',
      ruleId: 'rule-1',
      sliceLimit: 200,
      anchorTotalCount: 3,
      totalMatchingCount: 2,
      returnedCount: 1,
      truncated: false,
      analysisPackUri: 's3://analysis-bucket/analysis-session-1/slice-1.json.gz',
      analysisPackSha256: 'sha256:abc',
      filters: {
        dataObjectVersionId: 'dov-1',
        executionRunId: 'run-1',
        ruleId: 'rule-1',
        sliceLimit: 200,
        runUntilExhausted: true,
        maxSlices: 2,
        maxRecords: null,
        maxSeconds: null,
      },
      nextSliceSuggestion: {
        reasonCodes: ['type_mismatch'],
        failureClass: null,
        recordIdentifierType: null,
        recordIdentifierValueContains: null,
        search: null,
        remainingCount: 1,
        partitionStrategy: ['reason_code', 'hash_stripes'],
        rationale: '1 uncovered exception fact shares reason_code type_mismatch.',
      },
      createdAt: '2026-04-06T12:00:00+00:00',
      updatedAt: '2026-04-06T12:00:00+00:00',
    },
    {
      analysisSessionId: 'analysis-session-1',
      analysisSliceId: 'slice-2',
      sliceIndex: 2,
      dataObjectVersionId: 'dov-1',
      executionRunId: 'run-1',
      ruleId: 'rule-1',
      sliceLimit: 200,
      anchorTotalCount: 3,
      totalMatchingCount: 1,
      returnedCount: 1,
      truncated: false,
      analysisPackUri: 's3://analysis-bucket/analysis-session-1/slice-2.json.gz',
      analysisPackSha256: 'sha256:def',
      filters: {
        dataObjectVersionId: 'dov-1',
        executionRunId: 'run-1',
        ruleId: 'rule-1',
        sliceLimit: 200,
        runUntilExhausted: true,
        maxSlices: 2,
        maxRecords: null,
        maxSeconds: null,
      },
      nextSliceSuggestion: null,
      createdAt: '2026-04-06T12:04:00+00:00',
      updatedAt: '2026-04-06T12:04:00+00:00',
    },
  ],
}

const analysisSliceDetailResponse = {
  ...analysisSessionResponse.slices[1],
  records: [
    {
      ...factsResponse.data[0],
      exceptionFactId: 'fact-2',
      failure: {
        ...factsResponse.data[0].failure,
        reasonText: 'Stale value',
      },
    },
  ],
}

const detailResponse = {
  ...factsResponse.data[0],
}

const pagedFactsPageOneResponse = {
  data: factsResponse.data,
  pagination: {
    total: 50,
    page: 1,
    limit: 25,
    totalPages: 2,
    hasNext: true,
    hasPrevious: false,
  },
}

const pagedFactsPageTwoResponse = {
  data: [
    {
      ...factsResponse.data[0],
      exceptionFactId: 'fact-2',
      failure: {
        ...factsResponse.data[0].failure,
        reasonText: 'Stale value',
      },
    },
  ],
  pagination: {
    total: 50,
    page: 2,
    limit: 25,
    totalPages: 2,
    hasNext: false,
    hasPrevious: true,
  },
}

const fetchMock = vi.fn()

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ExceptionRecordHandling', () => {
  it('hides the page until JIT exception access is active', () => {
    mockAuth = {
      currentWorkspaceId: 'retail-banking',
      isAuthenticated: true,
      hasAnyScope: () => false,
    }

    render(<ExceptionRecordHandling />)

    expect(screen.getByText('Access is currently unavailable')).toBeTruthy()
    expect(screen.getByText('Open Access Requests')).toBeTruthy()
  })

  it('loads analytics and exception facts for an active JIT reader', async () => {
    mockAuth = {
      currentWorkspaceId: 'retail-banking',
      isAuthenticated: true,
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:exceptions:read'),
    }

    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/exception-summary/records/')) {
        return Promise.resolve({ ok: true, json: async () => detailResponse, text: async () => JSON.stringify(detailResponse) })
      }
      if (String(url).includes('/exception-summary/records?')) {
        return Promise.resolve({ ok: true, json: async () => factsResponse, text: async () => JSON.stringify(factsResponse) })
      }
      if (String(url).includes('/exception-summary')) {
        return Promise.resolve({ ok: true, json: async () => ({ analytics: analyticsResponse }), text: async () => JSON.stringify({ analytics: analyticsResponse }) })
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    })

    const originalFetch = global.fetch
    global.fetch = fetchMock as unknown as typeof fetch

    try {
      render(<ExceptionRecordHandling />)

      fireEvent.change(screen.getByPlaceholderText('delivery-id'), { target: { value: 'delivery-1' } })
      fireEvent.change(screen.getByPlaceholderText('data-object-version-id'), { target: { value: 'dov-1' } })
      fireEvent.click(screen.getByText('Load records'))

      await waitFor(() => {
        expect(screen.getByText('12')).toBeTruthy()
        expect(screen.getAllByText('fact-1').length).toBeGreaterThan(0)
      })
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/exception-summary/records?'),
        expect.objectContaining({ headers: { Authorization: 'Bearer test-token' } }),
      )
    } finally {
      global.fetch = originalFetch
    }
  })

  it('loads investigator detail when the selected fact changes', async () => {
    mockAuth = {
      currentWorkspaceId: 'retail-banking',
      isAuthenticated: true,
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:exceptions:detail'),
    }

    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/exception-summary/records/fact-1')) {
        return Promise.resolve({ ok: true, json: async () => detailResponse, text: async () => JSON.stringify(detailResponse) })
      }
      if (String(url).includes('/exception-summary/records?')) {
        return Promise.resolve({ ok: true, json: async () => factsResponse, text: async () => JSON.stringify(factsResponse) })
      }
      if (String(url).includes('/exception-summary')) {
        return Promise.resolve({ ok: true, json: async () => ({ analytics: analyticsResponse }), text: async () => JSON.stringify({ analytics: analyticsResponse }) })
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    })

    const originalFetch = global.fetch
    global.fetch = fetchMock as unknown as typeof fetch

    try {
      render(<ExceptionRecordHandling />)

      fireEvent.change(screen.getByPlaceholderText('delivery-id'), { target: { value: 'delivery-1' } })
      fireEvent.change(screen.getByPlaceholderText('data-object-version-id'), { target: { value: 'dov-1' } })
      fireEvent.click(screen.getByText('Load records'))

      await waitFor(() => {
        expect(screen.getAllByText('fact-1').length).toBeGreaterThan(0)
        expect(screen.getByText('Engine metadata')).toBeTruthy()
        expect(screen.getByText('Operations metadata')).toBeTruthy()
      })
    } finally {
      global.fetch = originalFetch
    }
  })

  it('pages records with explicit next and previous controls', async () => {
    mockAuth = {
      currentWorkspaceId: 'retail-banking',
      isAuthenticated: true,
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:exceptions:read'),
    }

    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/exception-summary/records/')) {
        return Promise.resolve({ ok: true, json: async () => ({ analytics: analyticsResponse }), text: async () => JSON.stringify({ analytics: analyticsResponse }) })
      }
      if (String(url).includes('/exception-summary/records?') && String(url).includes('offset=25')) {
        return Promise.resolve({ ok: true, json: async () => pagedFactsPageTwoResponse, text: async () => JSON.stringify(pagedFactsPageTwoResponse) })
      }
      if (String(url).includes('/exception-summary/records?')) {
        return Promise.resolve({ ok: true, json: async () => pagedFactsPageOneResponse, text: async () => JSON.stringify(pagedFactsPageOneResponse) })
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    })

    const originalFetch = global.fetch
    global.fetch = fetchMock as unknown as typeof fetch

    try {
      render(<ExceptionRecordHandling />)

      fireEvent.change(screen.getByPlaceholderText('delivery-id'), { target: { value: 'delivery-1' } })
      fireEvent.change(screen.getByPlaceholderText('data-object-version-id'), { target: { value: 'dov-1' } })
      fireEvent.click(screen.getByText('Load records'))

      await waitFor(() => {
        expect(screen.getByText('Page 1 of 2 · 50 total · 25 per page')).toBeTruthy()
        expect(screen.getByText('Next')).toBeTruthy()
      })

      fireEvent.click(screen.getByText('Next'))

      await waitFor(() => {
        expect(screen.getByText('Page 2 of 2 · 50 total · 25 per page')).toBeTruthy()
        expect(screen.getAllByText('fact-2').length).toBeGreaterThan(0)
      })
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('offset=25'),
        expect.objectContaining({ headers: { Authorization: 'Bearer test-token' } }),
      )
    } finally {
      global.fetch = originalFetch
    }
  })

  it('starts an analysis session and opens stored slice packs from session history', async () => {
    mockAuth = {
      currentWorkspaceId: 'retail-banking',
      isAuthenticated: true,
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:exceptions:read'),
    }

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).includes('/exception-summary/records/')) {
        return Promise.resolve({ ok: true, json: async () => ({ analytics: analyticsResponse }), text: async () => JSON.stringify({ analytics: analyticsResponse }) })
      }
      if (String(url).includes('/exception-summary/records?')) {
        return Promise.resolve({ ok: true, json: async () => factsResponse, text: async () => JSON.stringify(factsResponse) })
      }
      if (String(url).includes('/exception-summary')) {
        return Promise.resolve({ ok: true, json: async () => ({ analytics: analyticsResponse }), text: async () => JSON.stringify({ analytics: analyticsResponse }) })
      }
      if (String(url).includes('/analysis-sessions/analysis-session-1/slices/slice-2')) {
        return Promise.resolve({ ok: true, json: async () => analysisSliceDetailResponse, text: async () => JSON.stringify(analysisSliceDetailResponse) })
      }
      if (String(url).includes('/analysis-sessions') && init?.method === 'POST') {
        return Promise.resolve({ ok: true, json: async () => analysisSessionResponse, text: async () => JSON.stringify(analysisSessionResponse) })
      }
      if (String(url).includes('/analysis-sessions/analysis-session-1') && String(url).includes('summary_only=true')) {
        return Promise.resolve({ ok: true, json: async () => analysisSessionResponse, text: async () => JSON.stringify(analysisSessionResponse) })
      }
      return Promise.reject(new Error(`Unexpected fetch: ${String(url)}`))
    })

    const originalFetch = global.fetch
    global.fetch = fetchMock as unknown as typeof fetch

    try {
      render(<ExceptionRecordHandling />)

      fireEvent.change(screen.getByPlaceholderText('delivery-id'), { target: { value: 'delivery-1' } })
      fireEvent.change(screen.getByPlaceholderText('data-object-version-id'), { target: { value: 'dov-1' } })
      fireEvent.change(document.getElementById('exception-records-execution-run-id') as HTMLInputElement, { target: { value: 'run-1' } })
      fireEvent.click(screen.getByText('Load records'))

      await waitFor(() => {
        expect(screen.getByText('fact-1')).toBeTruthy()
      })

      fireEvent.change(screen.getByPlaceholderText('rule-id'), { target: { value: 'rule-1' } })
      fireEvent.click(screen.getByLabelText('Keep enqueueing slices until uncovered exception space is exhausted or a budget is hit.'))
      fireEvent.click(screen.getByText('Start session'))

      await waitFor(() => {
        expect(screen.getByText('Slice history')).toBeTruthy()
        expect(screen.getByText('Budget hit')).toBeTruthy()
      })

      fireEvent.click(screen.getByText('Refresh session'))

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          expect.stringContaining('/analysis-sessions/analysis-session-1?workspace_id=retail-banking&summary_only=true'),
          expect.objectContaining({ headers: { Authorization: 'Bearer test-token' } }),
        )
      })

      const postCall = fetchMock.mock.calls.find(([url, init]) => String(url).includes('/analysis-sessions') && init && (init as RequestInit).method === 'POST')
      expect(postCall).toBeTruthy()
      const postBody = JSON.parse(String((postCall?.[1] as RequestInit | undefined)?.body ?? '{}'))
      expect(postBody.dataObjectVersionId).toBe('dov-1')
      expect(postBody.executionRunId).toBe('run-1')
      expect(postBody.ruleId).toBe('rule-1')
      expect(postBody.summaryOnly).toBe(true)
      expect(postBody.runUntilExhausted).toBe(true)

      fireEvent.click(screen.getByText('Slice 2'))

      await waitFor(() => {
        expect(screen.getByText('fact-2')).toBeTruthy()
      })

      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/analysis-sessions/analysis-session-1/slices/slice-2'),
        expect.objectContaining({ headers: { Authorization: 'Bearer test-token' } }),
      )
    } finally {
      global.fetch = originalFetch
    }
  })
})