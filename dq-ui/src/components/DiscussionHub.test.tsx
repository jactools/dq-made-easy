/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { DiscussionHub } from './DiscussionHub'

const mockUseAuth = vi.fn()
const mockUseRules = vi.fn()
const mockUseSettings = vi.fn()
const mockGetAuthToken = vi.fn(() => null)

const jsonResponse = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
})

vi.mock('../hooks/useContexts', () => ({
  useAuth: () => mockUseAuth(),
  useRules: () => mockUseRules(),
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => mockGetAuthToken(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('DiscussionHub', () => {
  const setupMocks = () => {
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { name: 'Hub User' },
    })
    mockUseRules.mockReturnValue({
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          workspaceId: 'retail-banking',
          requestType: 'deactivation',
          status: 'pending',
          requestedAt: '2026-04-05T09:00:00Z',
          requesterName: 'Alice Reviewer',
          commentThread: [
            {
              id: 'approval-comment-1',
              author_name: 'Alice Reviewer',
              comment: 'Please confirm the approval path before deactivation.',
              comment_type: 'concern',
              created_at: '2026-04-05T09:05:00Z',
            },
          ],
        },
      ],
      rules: [
        {
          id: 'rule-1',
          name: 'Customer Address Completeness',
          workspace: 'retail-banking',
        },
      ],
    })
    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1' },
    })

    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/incidents?')) {
        return Promise.resolve(jsonResponse({
          incidents: [
            {
              id: 'incident-1',
              incident_kind: 'technical_run_error',
              status: 'open',
              title: 'Broken validation run',
              severity: 'high',
              source_correlation_id: 'corr-incident-1',
              source_parent_correlation_id: 'corr-parent-1',
              source_request_id: 'req-incident-1',
              source_queue_message_id: 'queue-incident-1',
              source_trace_id: 'trace-incident-1',
              source_system: 'dq-engine',
              updated_at: '2026-04-06T10:00:00Z',
              comments: [
                {
                  id: 'incident-comment-1',
                  author_name: 'Incident Lead',
                  comment: 'Need another review before closing this incident.',
                  comment_type: 'question',
                  created_at: '2026-04-06T10:05:00Z',
                },
              ],
            },
          ],
          count: 1,
          offset: 0,
          limit: 200,
        }))
      }

      if (url.endsWith('/data-assets')) {
        return Promise.resolve(jsonResponse([
          {
            id: 'asset-1',
            workspace_id: 'retail-banking',
            name: 'Customer Data Contract',
            description: 'Primary customer profile contract.',
          },
        ]))
      }

      if (url.includes('/data-assets/asset-1/contract/analysis')) {
        return Promise.resolve(jsonResponse({
          success: true,
          data_asset_id: 'asset-1',
          contract: {
            version: 'v1',
            name: 'Customer Data Contract',
            status: 'reviewed',
          },
          latest_contract_version: {
            review_status: 'approved',
            reviewed_by: 'Contract Reviewer',
            reviewed_at: '2026-04-06T11:00:00Z',
            review_comments: 'Review the mapping before publishing the contract.',
          },
        }))
      }

      throw new Error(`Unexpected fetch request: ${url}`)
    }))
  }

  it('filters threads by search text and topic chips', async () => {
    setupMocks()

    render(<DiscussionHub />)

    await screen.findByText('Customer Address Completeness')
    await screen.findByText('Broken validation run')
    await screen.findByText('Customer Data Contract')
    await screen.findByText(/Correlation corr-incident-1/)

    fireEvent.change(screen.getByLabelText('Search discussions'), { target: { value: 'mapping publish' } })

    await waitFor(() => {
      expect(screen.getByText('Customer Data Contract')).toBeTruthy()
      expect(screen.queryByText('Broken validation run')).toBeNull()
      expect(screen.queryByText('Customer Address Completeness')).toBeNull()
    })

    fireEvent.click(screen.getByLabelText('Clear discussion search'))

    fireEvent.click(screen.getByTitle('Show Incidents'))

    await waitFor(() => {
      expect(screen.getByText('Broken validation run')).toBeTruthy()
      expect(screen.queryByText('Customer Data Contract')).toBeNull()
    })

    fireEvent.change(screen.getByLabelText('Search discussions'), { target: { value: 'trace-incident-1' } })

    await waitFor(() => {
      expect(screen.getByText('Broken validation run')).toBeTruthy()
      expect(screen.queryByText('Customer Data Contract')).toBeNull()
      expect(screen.queryByText('Customer Address Completeness')).toBeNull()
    })
  })

  it('filters by comment type', async () => {
    setupMocks()

    render(<DiscussionHub />)

    await screen.findByText('Customer Address Completeness')

    fireEvent.change(screen.getByLabelText('Comment type'), { target: { value: 'concern' } })

    await waitFor(() => {
      expect(screen.getByText('Customer Address Completeness')).toBeTruthy()
      expect(screen.queryByText('Broken validation run')).toBeNull()
      expect(screen.queryByText('Customer Data Contract')).toBeNull()
    })

    fireEvent.change(screen.getByLabelText('Comment type'), { target: { value: 'general' } })

    await waitFor(() => {
      expect(screen.getByText('No discussion threads match your search and topic filters.')).toBeTruthy()
    })
  })
})