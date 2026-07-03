/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Rule } from '../types/rules'
import { Reports } from './Reports'

const mockUseRules = vi.fn()
const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()
const mockGetUiTelemetryConnectionState = vi.fn()
const mockSubscribeUiTelemetryConnectionState = vi.fn()

const buildJsonResponse = (body: unknown, ok = true) => ({
  ok,
  status: ok ? 200 : 500,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

vi.mock('../hooks/useContexts', () => ({
  useRules: () => mockUseRules(),
  useAuth: () => mockUseAuth(),
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
}))

vi.mock('./Button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
  PrimaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
  SecondaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
  TertiaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
}))

vi.mock('./HealthScorecards', () => ({
  HealthScorecards: () => <div data-testid="health-scorecards" />,
}))

vi.mock('./DataQualityMetrics', () => ({
  DataQualityMetrics: () => <div data-testid="data-quality-metrics" />,
}))

vi.mock('./ExecutionResultExplorer', () => ({
  ExecutionResultExplorer: () => <div data-testid="execution-result-explorer" />,
}))

vi.mock('./RuleDetailsModal', () => ({
  RuleDetailsModal: () => null,
}))

vi.mock('./ReconciliationWorkbench', () => ({
  ReconciliationWorkbench: () => <div data-testid="reconciliation-workbench" />,
}))

vi.mock('./discussion/DiscussionPanel', () => ({
  DiscussionPanel: () => null,
  normalizeDiscussionEntries: (entries: unknown) => entries,
}))

vi.mock('../telemetry', () => ({
  getUiTelemetryConnectionState: () => mockGetUiTelemetryConnectionState(),
  subscribeUiTelemetryConnectionState: (listener: (state: string) => void) => mockSubscribeUiTelemetryConnectionState(listener),
}))

const mockRules: Rule[] = []

beforeEach(() => {
  mockUseRules.mockReturnValue({ rules: mockRules })
  mockUseAuth.mockReturnValue({ currentWorkspaceId: 'retail-banking' })
  mockUseSettings.mockReturnValue({ applicationSettings: { apiBaseUrl: 'http://api.local' } })
  mockGetUiTelemetryConnectionState.mockReturnValue('disabled')
  mockSubscribeUiTelemetryConnectionState.mockReturnValue(() => undefined)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('Reports', () => {
  it('renders the shared operations shell and view tabs', () => {
    render(<Reports initialTab="metrics" />)

    expect(screen.getByRole('heading', { name: 'Operations' })).toBeTruthy()
    expect(screen.getByRole('tablist', { name: 'Operations views' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Health Dashboard' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Data-Definition Insights' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Result Explorer' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Validation Test Results' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Incidents' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Reconciliation' })).toBeTruthy()
    expect(screen.getByTestId('health-scorecards')).toBeTruthy()
    expect(screen.getByTestId('data-quality-metrics')).toBeTruthy()
  })

  it('shows data-definition request insights in the Operations tab', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/data-definition-tasks/requests?workspace_id=retail-banking&limit=50')) {
        return buildJsonResponse({
          requests: [
            {
              request_id: 'dd-1',
              current_workspace_id: 'retail-banking',
              prompt: 'Generate definitions for customer profile fields',
              requested_by_user_id: 'user-1',
              requested_by_email: 'user@example.com',
              requested_at: '2026-07-03T08:00:00Z',
              started_at: '2026-07-03T08:02:00Z',
              completed_at: '2026-07-03T08:05:00Z',
              status: 'completed',
              error_message: null,
              analysis_type: 'definition_task',
              analysis_provider: 'llm',
            },
            {
              request_id: 'dd-2',
              current_workspace_id: 'retail-banking',
              prompt: 'Draft payment terms definitions',
              requested_by_user_id: 'user-2',
              requested_by_email: 'user2@example.com',
              requested_at: '2026-07-03T09:00:00Z',
              started_at: null,
              completed_at: null,
              status: 'started',
              error_message: 'LLM timed out',
              analysis_type: 'definition_task',
              analysis_provider: 'llm',
            },
          ],
          count: 2,
        })
      }

      if (url.includes('/data-definition-tasks/requests/dd-2/status')) {
        return buildJsonResponse({
          success: true,
          request: {
            request_id: 'dd-2',
            current_workspace_id: 'retail-banking',
            prompt: 'Draft payment terms definitions',
            requested_by_user_id: 'user-2',
            requested_by_email: 'user2@example.com',
            requested_at: '2026-07-03T09:00:00Z',
            started_at: '2026-07-03T09:01:00Z',
            completed_at: '2026-07-03T09:04:00Z',
            status: 'completed',
            error_message: null,
            analysis_type: 'definition_task',
            analysis_provider: 'llm',
          },
        })
      }

      throw new Error(`Unexpected fetch URL: ${url}`)
    }))

    render(<Reports initialTab="data-definition" />)

    expect(await screen.findByRole('heading', { name: 'Operations' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Data-Definition Insights' })).toBeTruthy()
    expect(screen.getByText('Workspace request insights')).toBeTruthy()
    expect(screen.getByText('Total')).toBeTruthy()
    expect(screen.getByText('Completed / Failed')).toBeTruthy()
    expect(screen.getByText('Generate definitions for customer profile fields')).toBeTruthy()
    expect(screen.getByText('Draft payment terms definitions')).toBeTruthy()
    expect(screen.getAllByText('Completed')).toHaveLength(2)
    expect(screen.queryByText('LLM timed out')).toBeNull()
  })

  it('shows agent access insights in the Operations tab', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/agent/v1/audit/events?limit=200&offset=0')) {
        return buildJsonResponse({
          events: [
            {
              id: 'audit-1',
              request_id: 'req-1',
              timestamp: '2026-07-03T10:00:00Z',
              action: 'dispatch_platform_integration',
              endpoint: '/agent/v1/integrations/dispatches',
              method: 'POST',
              actor_id: 'agent-orchestrator',
              correlation_id: 'corr-1',
              agent_type: 'mistral_ai',
              agent_source: 'mistral_ai',
              agent_instance_id: 'agent-1',
              request_origin: 'webhook',
              user_agent: 'dq-test-agent',
              response_type: 'integration_dispatch_response',
              status_code: 200,
              success: true,
              details: { dispatch_id: 'agent-dispatch-abc123' },
            },
            {
              id: 'audit-2',
              request_id: 'req-2',
              timestamp: '2026-07-03T10:05:00Z',
              action: 'dispatch_platform_integration',
              endpoint: '/agent/v1/integrations/dispatches',
              method: 'POST',
              actor_id: 'agent-orchestrator',
              correlation_id: 'corr-2',
              agent_type: 'mistral_ai',
              agent_source: 'mistral_ai',
              agent_instance_id: 'agent-1',
              request_origin: 'webhook',
              user_agent: 'dq-test-agent',
              response_type: 'integration_dispatch_response',
              status_code: 200,
              success: true,
              details: { dispatch_id: 'agent-dispatch-def456' },
            },
            {
              id: 'audit-3',
              request_id: 'req-3',
              timestamp: '2026-07-03T11:00:00Z',
              action: 'list_integration_contracts',
              endpoint: '/agent/v1/integrations/contracts',
              method: 'GET',
              actor_id: 'agent-orchestrator',
              correlation_id: 'corr-3',
              agent_type: 'microsoft_copilot',
              agent_source: 'microsoft_copilot',
              agent_instance_id: 'agent-2',
              request_origin: 'job',
              user_agent: 'dq-test-agent',
              response_type: 'integration_contracts_response',
              status_code: 200,
              success: true,
              details: { contract_count: 7 },
            },
          ],
          governance_metadata: { governance_aware: true },
        })
      }

      throw new Error(`Unexpected fetch URL: ${url}`)
    }))

    render(<Reports initialTab="agent-access" />)

    expect(await screen.findByRole('heading', { name: 'Operations' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Agent Access' })).toBeTruthy()
    expect(screen.getByText('AI agent access insights')).toBeTruthy()
    expect(screen.getByText('Total events')).toBeTruthy()
    expect(screen.getByText('mistral_ai')).toBeTruthy()
    expect(screen.getByText(/dispatch platform integration/i)).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
    expect(screen.getAllByText('Success')).toHaveLength(2)
    expect(screen.getByText('Refresh')).toBeTruthy()
  })

  it('shows a telemetry warning banner when observability is unavailable', () => {
    mockGetUiTelemetryConnectionState.mockReturnValue('unavailable')

    render(<Reports initialTab="metrics" />)

    expect(screen.getByRole('status')).toBeTruthy()
    expect(screen.getByText(/observability is temporarily unavailable/i)).toBeTruthy()
  })
})
