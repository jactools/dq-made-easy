/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import { ExecutionResultExplorer } from './ExecutionResultExplorer'
import { DASHBOARD_NAV_SELECTION_KEY } from '../utils/dashboardNavigation'

const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useAuth: () => mockUseAuth(),
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  mockUseAuth.mockReturnValue({ currentWorkspaceId: 'retail-banking' })
  mockUseSettings.mockReturnValue({ applicationSettings: { apiBaseUrl: 'http://api.local' } })
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  window.sessionStorage.removeItem(DASHBOARD_NAV_SELECTION_KEY)
})

describe('ExecutionResultExplorer', () => {
  it('sends backend-owned filters to the execution browse API', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            id: 'run-001',
            rule_name: 'Customer Order Completeness',
            owner: 'data-platform',
            domain: 'retail-banking',
            severity: 'high',
            data_object_names: ['Orders'],
            resolved_data_delivery_id: 'delivery-001',
            correlation_id: 'corr-001',
            requested_by: 'user-admin',
            engine_target: 'pyspark',
            execution_shape: 'single_object',
            status: 'failed',
            failed_record_count: 3,
            submitted_at: '2026-05-31T10:00:00Z',
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'run-001',
          suite_id: 'gx-suite-1',
          suite_version: 3,
          rule_id: 'rule-1',
          run_plan_id: 'run-plan-001',
          correlation_id: 'corr-001',
          requested_by: 'user-admin',
          engine_target: 'pyspark',
          execution_shape: 'single_object',
          status: 'failed',
          submitted_at: '2026-05-31T10:00:00Z',
          started_at: '2026-05-31T10:02:00Z',
          completed_at: '2026-05-31T10:05:00Z',
          created_at: '2026-05-31T09:59:00Z',
          updated_at: '2026-05-31T10:06:00Z',
          resolved_data_delivery_id: 'delivery-001',
          execution_progress: {
            percent: 100,
            label: 'Completed',
            completedSteps: 4,
            totalSteps: 4,
            source: 'gx-execution',
            updatedAt: '2026-05-31T10:05:00Z',
          },
          execution_contract: {
            engineType: 'gx',
            engineTarget: 'pyspark',
            executionShape: 'single_object',
            traceability: {
              ruleVersionId: 'rule-version-1',
              gxSuiteId: 'gx-suite-1',
              gxSuiteVersion: 3,
              dataObjectVersionId: 'dov-1',
            },
          },
          status_history: [
            {
              id: 'history-1',
              from_status: 'running',
              to_status: 'failed',
              changed_by: 'system',
              changed_at: '2026-05-31T10:06:00Z',
              reason: 'validation_failed',
            },
          ],
        }),
      })

    render(<ExecutionResultExplorer />)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByLabelText('Dataset ID'), { target: { value: 'dataset-123' } })
    fireEvent.change(screen.getByLabelText('Owner'), { target: { value: 'data-platform' } })
    fireEvent.change(screen.getByLabelText('Domain'), { target: { value: 'retail-banking' } })
    fireEvent.change(screen.getByLabelText('Severity'), { target: { value: 'high' } })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'failed' } })
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'corr-001' } })
    fireEvent.change(screen.getByLabelText('Lookback'), { target: { value: '48' } })
    fireEvent.change(screen.getByLabelText('Window'), { target: { value: 'days' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    fireEvent.click(screen.getByRole('button', { name: 'Open details' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))

    const secondRequestUrl = new URL(String(fetchMock.mock.calls[1]?.[0]))
    expect(secondRequestUrl.searchParams.get('workspaceId')).toBe('retail-banking')
    expect(secondRequestUrl.searchParams.get('datasetId')).toBe('dataset-123')
    expect(secondRequestUrl.searchParams.get('owner')).toBe('data-platform')
    expect(secondRequestUrl.searchParams.get('domain')).toBe('retail-banking')
    expect(secondRequestUrl.searchParams.get('severity')).toBe('high')
    expect(secondRequestUrl.searchParams.get('status')).toBe('failed')
    expect(secondRequestUrl.searchParams.get('search')).toBe('corr-001')
    expect(secondRequestUrl.searchParams.get('lookbackAmount')).toBe('48')
    expect(secondRequestUrl.searchParams.get('lookbackUnit')).toBe('days')

    expect(screen.getAllByText('run-001').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Customer Order Completeness').length).toBeGreaterThan(0)
    expect(screen.getAllByText('data-platform / retail-banking').length).toBeGreaterThan(0)
    expect(screen.getAllByText('High').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(0)
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByText(/metadata only/i)).toBeTruthy()
    expect(screen.getByText('Run overview')).toBeTruthy()
    expect(screen.getByText('Execution progress')).toBeTruthy()
    expect(screen.getByText('Contract pointers')).toBeTruthy()
    expect(screen.getByText('Recent lifecycle changes')).toBeTruthy()
    expect(screen.getByText('rule-version-1')).toBeTruthy()
    expect(screen.getByText('validation_failed')).toBeTruthy()
  })

  it('renders steward summary cards that navigate into the owning workflows', async () => {
    const onNavigate = vi.fn()

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: 'run-001',
          rule_name: 'Customer Order Completeness',
          owner: 'data-platform',
          domain: 'retail-banking',
          severity: 'critical',
          status: 'failed',
          submitted_at: '2026-05-31T10:00:00Z',
        },
        {
          id: 'run-002',
          rule_name: 'Customer Address Validity',
          owner: 'data-platform',
          domain: 'retail-banking',
          severity: 'high',
          status: 'running',
          submitted_at: '2026-05-31T11:00:00Z',
        },
      ],
    })

    render(<ExecutionResultExplorer onNavigate={onNavigate} />)

    await waitFor(() => expect(screen.getByText('Triage failed runs')).toBeTruthy())

    const monitoringCard = screen.getByText('Triage failed runs').closest('.execution-run-summary-card') as HTMLElement
    const ownerCard = screen.getByText('Most impacted owner').closest('.execution-run-summary-card') as HTMLElement
    const governanceCard = screen.getByText('High-severity results').closest('.execution-run-summary-card') as HTMLElement

    expect(within(monitoringCard).getByText('1')).toBeTruthy()
    expect(within(ownerCard).getByText('data-platform')).toBeTruthy()
    expect(within(governanceCard).getByText('2')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Open monitoring' }))
    expect(onNavigate).toHaveBeenCalledWith('reports-rule-monitoring')
    expect(JSON.parse(window.sessionStorage.getItem(DASHBOARD_NAV_SELECTION_KEY) || '{}')).toMatchObject({
      destination: 'reports-rule-monitoring',
      source: 'dashboard',
      card_id: 'failed-validation-runs',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Open rules' }))
    expect(onNavigate).toHaveBeenNthCalledWith(2, 'rules-all')

    fireEvent.click(screen.getByRole('button', { name: 'Open governance' }))
    expect(onNavigate).toHaveBeenNthCalledWith(3, 'approvals-governance')
  })
})
