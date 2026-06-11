/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { AuditTrail } from './AuditTrail'

const mockUseRules = vi.fn()
const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useRules: () => mockUseRules(),
  useAuth: () => mockUseAuth(),
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

const buildJsonResponse = (body: unknown, ok = true) => ({
  ok,
  status: ok ? 200 : 500,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

describe('AuditTrail', () => {
  beforeEach(() => {
    mockUseRules.mockReturnValue({
      rules: [
        {
          id: 'rule-1',
          name: 'Customer Email Presence',
          workspace: 'workspace-alpha',
        },
      ],
    })
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'workspace-alpha',
      isAuthenticated: true,
    })
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://api.local',
      },
      displaySettings: {
        compactMode: false,
      },
    })

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/rules/rule-1/status-history')) {
        return buildJsonResponse([
          {
            id: 'rule-history-1',
            rule_id: 'rule-1',
            action: 'approved',
            from_status: 'draft',
            to_status: 'approved',
            changed_by: 'steward-1',
            changed_at: '2026-05-01T12:00:00Z',
            reason: 'Ready for release',
          },
        ])
      }

      if (url.includes('/data-definition-tasks/requests?workspace_id=workspace-alpha&limit=20')) {
        return buildJsonResponse({
          requests: [
            {
              request_id: 'dd-1',
              current_workspace_id: 'workspace-alpha',
              prompt: 'Draft a customer email definition',
              requested_by_user_id: 'user-1',
              requested_by_email: 'user@example.com',
              requested_at: '2026-05-02T08:00:00Z',
              started_at: null,
              completed_at: null,
              status: 'completed',
              error_message: null,
              analysis_type: 'definition_task',
              analysis_provider: 'openmetadata',
            },
          ],
          count: 1,
        })
      }

      if (url.includes('/data-definition-tasks/requests/dd-1/history')) {
        return buildJsonResponse({
          requestId: 'dd-1',
          events: [
            {
              id: 'dd-history-1',
              request_id: 'dd-1',
              action: 'created',
              from_status: null,
              to_status: 'pending',
              actor_id: 'user-1',
              changed_at: '2026-05-02T08:01:00Z',
              details: { message: 'Draft created' },
            },
          ],
          count: 1,
        })
      }

      if (url.includes('/rules/validation-runs?workspace=workspace-alpha&limit=20')) {
        return buildJsonResponse({
          data: [
            {
              id: 'run-1',
              workspace: 'workspace-alpha',
              triggered_by: 'validator-1',
              run_at: '2026-05-03T09:30:00Z',
              total: 1,
              valid_count: 1,
              invalid_count: 0,
              status: 'completed',
            },
          ],
          pagination: { total: 1, page: 1, limit: 20, totalPages: 1 },
        })
      }

      if (url.includes('/gx/runs/run-1/status-history')) {
        return buildJsonResponse([
          {
            id: 'run-history-1',
            run_id: 'run-1',
            from_status: 'queued',
            to_status: 'completed',
            changed_by: 'validator-1',
            changed_at: '2026-05-03T09:45:00Z',
            reason: 'Validation finished successfully',
            details: { message: 'Run completed' },
          },
        ])
      }

      if (url.includes('/approvals/audit')) {
        return buildJsonResponse([
          {
            id: 'approval-history-1',
            approval_id: 'approval-1',
            action: 'approved',
            actor_id: 'approver-1',
            timestamp: '2026-05-04T14:15:00Z',
            details: { comment: 'Looks good to me' },
          },
        ])
      }

      throw new Error(`Unexpected fetch URL: ${url}`)
    }))
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('loads the audit reporting views from the canonical history seams', async () => {
    render(<AuditTrail initialTab="overview" />)

    expect(await screen.findByRole('heading', { name: 'Audit Trail' })).toBeTruthy()
    expect(screen.getByText('Rule history')).toBeTruthy()
    expect(screen.getByText('Data-definition history')).toBeTruthy()
    expect(screen.getByText('Validation history')).toBeTruthy()
    expect(screen.getByText('Approval history')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Rule History' }))
    expect(await screen.findByText('Customer Email Presence (rule-1)')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Data-Definition History' }))
    expect(await screen.findByText('Draft a customer email definition (dd-1)')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Validation History' }))
    expect(
      await screen.findByText(/run-1 \(completed\)/i, { selector: 'p.audit-timeline-reference' }),
    ).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Approval History' }))
    expect(await screen.findByText('Approval approval-1')).toBeTruthy()

    const fetchMock = vi.mocked(fetch)
    expect(fetchMock.mock.calls.some(([request]) => String(request).includes('/rules/rule-1/status-history'))).toBe(true)
    expect(fetchMock.mock.calls.some(([request]) => String(request).includes('/data-definition-tasks/requests?workspace_id=workspace-alpha&limit=20'))).toBe(true)
    expect(fetchMock.mock.calls.some(([request]) => String(request).includes('/data-definition-tasks/requests/dd-1/history?limit=50&offset=0'))).toBe(true)
    expect(fetchMock.mock.calls.some(([request]) => String(request).includes('/rules/validation-runs?workspace=workspace-alpha&limit=20'))).toBe(true)
    expect(fetchMock.mock.calls.some(([request]) => String(request).includes('/gx/runs/run-1/status-history'))).toBe(true)
    expect(fetchMock.mock.calls.some(([request]) => String(request).includes('/approvals/audit'))).toBe(true)
  })
})
