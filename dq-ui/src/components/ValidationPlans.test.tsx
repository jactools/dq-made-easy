/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ValidationPlans } from './ValidationPlans'

const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
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

vi.mock('./StatusBanner', () => ({
  StatusBanner: ({ message }: { message: string }) => <div role="status">{message}</div>,
}))

beforeEach(() => {
  mockUseAuth.mockReturnValue({ currentWorkspaceId: 'retail-banking' })
  mockUseSettings.mockReturnValue({ applicationSettings: { apiBaseUrl: 'http://api.local' } })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ValidationPlans', () => {
  it('loads and renders workspace-scoped validation plans and suites', async () => {
    let recentRunsFetchCount = 0
    const fetchMock = vi.fn(async (input) => {
      const url = String(input)
      if (url.includes('/run-plan?workspaceId=retail-banking')) {
        return new Response(JSON.stringify({
          validation_run_plans: [
            {
              run_plan_id: 'run-plan-1',
              workspace_id: 'retail-banking',
              scope_selector: { tag_ids: ['gold', 'regulatory'] },
              planning_mode: 'single_suite',
              status: 'active',
              current_active_version_id: 'run-plan-version-2',
              pending_version_id: null,
              pending_version_governance_state: null,
              activated_by: 'user-admin',
              activated_at: '2026-04-10T08:00:00Z',
              last_dispatched_run_id: 'run-1',
              created_at: '2026-04-10T07:00:00Z',
              updated_at: '2026-04-10T08:00:00Z',
              versions: [
                {
                  run_plan_version_id: 'run-plan-version-2',
                  governance_state: 'active',
                  schedule_definition: { scheduled_at: '2026-04-12T08:00:00Z' },
                  created_at: '2026-04-10T08:00:00Z',
                },
              ],
            },
          ],
          validation_suites: [
            {
              run_plan_id: 'run-plan-1',
              run_plan_version_id: 'run-plan-version-2',
              governance_state: 'active',
              artifact_id: 'suite-1',
              artifact_version: 1,
              engine_type: 'gx',
              tag_ids: ['gold', 'regulatory'],
              schedule_definition: { scheduled_at: '2026-04-12T08:00:00Z' },
              artifact_snapshot: {
                validation_artifact_id: 'suite-1',
                validation_artifact_version: 1,
                engine_type: 'gx',
              },
              created_at: '2026-04-10T08:00:00Z',
            },
          ],
        }), { status: 200 })
      }

      if (url.includes('/validation-run-plans/run-plan-1/replay')) {
        expect(url).toContain('/validation-run-plans/run-plan-1/replay')
        return new Response(JSON.stringify({
          run_id: 'run-replay-1',
          queue_message_id: 'run-replay-1',
          run_plan_id: 'run-plan-1',
          run_plan_version_id: 'run-plan-version-2',
          selection_mode: 'single_suite',
          suite_id: 'suite-1',
          suite_version: 1,
          engine_type: 'gx',
          engine_target: 'pyspark',
          execution_shape: 'single_object',
          dispatch_mode: 'queued',
          queue_key: 'dq-gx:execution-dispatch',
          scheduled_at: '2026-04-12T08:30:00Z',
          correlation_id: 'corr-replay-1',
        }), { status: 202 })
      }

      if (url.includes('/gx/runs/stats?')) {
        expect(url).toContain('workspaceId=retail-banking')
        expect(url).toContain('runPlanId=run-plan-1')
        recentRunsFetchCount += 1
        const recentRuns = recentRunsFetchCount === 1
          ? [
              {
                id: 'run-1',
                run_plan_id: 'run-plan-1',
                suite_id: 'suite-1',
                suite_version: 1,
                rule_id: 'rule-1',
                rule_name: 'Customer Order Completeness',
                data_object_names: ['Orders'],
                correlation_id: 'corr-1',
                requested_by: 'user-admin',
                engine_target: 'pyspark',
                execution_shape: 'single_object',
                status: 'succeeded',
                failed_record_count: 0,
                submitted_at: '2026-04-12T08:30:00Z',
                started_at: '2026-04-12T08:31:00Z',
                completed_at: '2026-04-12T08:32:00Z',
                created_at: '2026-04-12T08:30:00Z',
                updated_at: '2026-04-12T08:32:00Z',
              },
            ]
          : [
              {
                id: 'run-replay-1',
                run_plan_id: 'run-plan-1',
                suite_id: 'suite-1',
                suite_version: 1,
                rule_id: 'rule-1',
                rule_name: 'Customer Order Completeness',
                data_object_names: ['Orders'],
                correlation_id: 'corr-replay-1',
                requested_by: 'user-admin',
                engine_target: 'pyspark',
                execution_shape: 'single_object',
                status: 'queued',
                failed_record_count: 0,
                submitted_at: '2026-04-12T08:33:00Z',
                started_at: null,
                completed_at: null,
                created_at: '2026-04-12T08:33:00Z',
                updated_at: '2026-04-12T08:33:00Z',
              },
              {
                id: 'run-1',
                run_plan_id: 'run-plan-1',
                suite_id: 'suite-1',
                suite_version: 1,
                rule_id: 'rule-1',
                rule_name: 'Customer Order Completeness',
                data_object_names: ['Orders'],
                correlation_id: 'corr-1',
                requested_by: 'user-admin',
                engine_target: 'pyspark',
                execution_shape: 'single_object',
                status: 'succeeded',
                failed_record_count: 0,
                submitted_at: '2026-04-12T08:30:00Z',
                started_at: '2026-04-12T08:31:00Z',
                completed_at: '2026-04-12T08:32:00Z',
                created_at: '2026-04-12T08:30:00Z',
                updated_at: '2026-04-12T08:32:00Z',
              },
            ]
        return new Response(JSON.stringify({
          lookback_amount: 30,
          lookback_unit: 'days',
          recent_limit: 5,
          total_runs: 1,
          pending_runs: 0,
          running_runs: 0,
          succeeded_runs: 1,
          failed_runs: 0,
          cancelled_runs: 0,
          status_breakdown: [],
          engine_target_breakdown: [],
          execution_shape_breakdown: [],
          recent_runs: recentRuns,
        }), { status: 200 })
      }

      throw new Error(`Unexpected fetch URL: ${url}`)
    })

    vi.stubGlobal('fetch', fetchMock)

    render(<ValidationPlans />)

    expect(await screen.findByText('run-plan-1')).toBeTruthy()
    expect(screen.getByText(/Planning mode: /i)).toBeTruthy()
    expect(screen.getAllByText(/Tags: gold, regulatory/i)).toHaveLength(2)
    expect(screen.getByText(/Active version: run-plan-version-2/i)).toBeTruthy()
    expect(screen.getByText('gx')).toBeTruthy()
    expect(screen.getByText('Recent Runs')).toBeTruthy()
    expect(await screen.findByText('run-1')).toBeTruthy()
    expect(screen.getByText(/Customer Order Completeness/i)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /run again/i }))

    expect((await screen.findAllByText(/Replay scheduled for run-plan-1/i)).length).toBeGreaterThan(0)
    expect(await screen.findByText(/Queue message run-replay-1/i)).toBeTruthy()
    expect(await screen.findByText(/Newly queued replay/i)).toBeTruthy()
    expect(await screen.findByText('run-replay-1', { selector: '.admin-user-name.gx-run-plan-version-title' })).toBeTruthy()
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/validation-run-plans/run-plan-1/replay'),
        expect.objectContaining({ method: 'POST' })
      )
    })
  })
})