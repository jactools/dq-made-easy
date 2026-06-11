/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ServiceLevelsPage } from './ServiceLevelsPage'

const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useAuth: () => mockUseAuth(),
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const buildDefinition = (approved: boolean) => ({
  id: 'service-level-1',
  workspace_id: 'retail-banking',
  name: 'Customer dataset availability',
  description: 'Track the quality score for the customer dataset',
  scope_kind: 'dataset',
  scope_id: 'dataset-1',
  metric_kind: 'quality_score',
  threshold_value: 90,
  threshold_operator: 'gte',
  lookback_amount: 30,
  lookback_unit: 'day',
  lifecycle_status: approved ? 'active' : 'draft',
  approval_status: approved ? 'approved' : 'draft',
  requested_by: 'Analyst One',
  requested_at: '2026-05-27T00:00:00Z',
  reviewed_by: approved ? 'Approver One' : null,
  reviewed_at: approved ? '2026-05-27T01:00:00Z' : null,
  itsm_system: approved ? 'HaloITSM' : null,
  itsm_ticket_id: approved ? 'HAL-4321' : null,
  itsm_ticket_number: approved ? 'HAL-4321' : null,
  itsm_ticket_url: approved ? 'https://itsm.example.com/tickets/HAL-4321' : null,
  created_at: '2026-05-27T00:00:00Z',
  updated_at: approved ? '2026-05-27T01:00:00Z' : '2026-05-27T00:00:00Z',
  adherence: {
    metric_value: 85,
    threshold_value: 90,
    threshold_operator: 'gte',
    observed_event_count: 2,
    compliant_event_count: 1,
    non_compliant_event_count: 1,
    compliance_rate_pct: 50,
    current_value: 85,
    current_observed_at: '2026-05-28T00:00:00Z',
    latest_observed_at: '2026-05-28T00:00:00Z',
    meets_target: false,
    summary: '1 of 2 observed runs met the quality score target.',
  },
})

const buildSummary = (approved: boolean) => ({
  workspace_id: 'retail-banking',
  definitions: [buildDefinition(approved)],
  total_definitions: 1,
  active_definitions: approved ? 1 : 0,
  draft_definitions: approved ? 0 : 1,
  approved_definitions: approved ? 1 : 0,
  deprecated_definitions: 0,
  compliant_definitions: 0,
  at_risk_definitions: approved ? 1 : 0,
})

describe('ServiceLevelsPage', () => {
  it('loads the backend summary and syncs approvals to ITSM', async () => {
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { name: 'Operations User', workspaceRoles: [{ workspaceId: 'retail-banking', role: 'analyst' }] },
    })
    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: '/api' },
    })

    let approved = false
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)

      if (url.includes('/service-levels?workspace_id=retail-banking') && (!init || init.method === 'GET')) {
        return new Response(JSON.stringify(buildSummary(approved)), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      if (url.includes('/service-levels/service-level-1/approve')) {
        approved = true
        expect(JSON.parse(String(init?.body || '{}'))).toMatchObject({ comments: 'Review completed in dq-made-easy.' })
        return new Response(JSON.stringify(buildDefinition(true)), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      if (url.includes('/service-levels/evaluate')) {
        return new Response(JSON.stringify({
          workspace_id: 'retail-banking',
          evaluated_at: '2026-05-27T01:30:00Z',
          evaluated_definitions: 1,
          breached_definitions: 1,
          breach_events_recorded: 1,
          breaches: [
            {
              definition_id: 'service-level-1',
              definition_name: 'Customer dataset availability',
              scope_kind: 'dataset',
              scope_id: 'dataset-1',
              metric_kind: 'quality_score',
              threshold_value: 90,
              threshold_operator: 'gte',
              current_value: 85,
              observed_event_count: 2,
              emitted_at: '2026-05-28T00:00:00Z',
              correlation_id: 'sla-slo:service-level-1:2026-05-28T00:00:00Z',
              severity: 'warning',
              summary: '1 of 2 observed runs met the quality score target.',
            },
          ],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      throw new Error(`Unexpected fetch call: ${url}`)
    })

    vi.stubGlobal('fetch', fetchMock)

    render(<ServiceLevelsPage />)

    expect(await screen.findByText('1 of 2 observed runs met the quality score target.', { selector: '.service-level-card-adherence span' })).toBeTruthy()
    expect(screen.getByText('50%')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Evaluate breaches' }))

    await waitFor(() => {
      expect(screen.getByText(/Recorded 1 breach event across 1 definition\./)).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Approve and sync to ITSM' }))

    await waitFor(() => {
      expect(screen.getByText(/was approved and synchronized to ITSM ticket HAL-4321\./)).toBeTruthy()
    })

    expect(fetchMock).toHaveBeenCalled()
    expect(fetchMock.mock.calls.some(([calledUrl]) => String(calledUrl).includes('/service-levels/evaluate'))).toBe(true)
    expect(fetchMock.mock.calls.some(([calledUrl]) => String(calledUrl).includes('/service-levels/service-level-1/approve'))).toBe(true)
  })
})
