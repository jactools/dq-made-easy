/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { HealthScorecards } from './HealthScorecards'

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))


let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('HealthScorecards', () => {
  it('renders workspace and asset scorecards from the API payload', async () => {
    const onRuleSelect = vi.fn()
    const onNavigate = vi.fn()
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        workspace_id: 'ws-1',
        generated_at: '2026-05-22T20:00:00Z',
        workspace_summary: {
          workspace_id: 'ws-1',
          generated_at: '2026-05-22T20:00:00Z',
          overall_score: 92,
          health_label: 'healthy',
          summary: 'Workspace quality remains healthy',
          top_regressions: [
            {
              bucket_start: '2026-05-22T19:00:00Z',
              previous_bucket_start: '2026-05-22T18:00:00Z',
              previous_total: 1,
              current_total: 3,
              delta: 2,
            },
          ],
          top_rules: [
            {
              rule_id: 'rule-1',
              rule_name: 'Completeness Rule',
              dimension: 'Completeness',
              total: 3,
            },
          ],
          ownership_rollups: [
            {
              scope_kind: 'domain',
              scope_id: 'Customer',
              scope_name: 'Customer',
              asset_count: 2,
              tracked_data_object_version_count: 2,
              total_runs: 3,
              pending_runs: 0,
              running_runs: 1,
              succeeded_runs: 1,
              failed_runs: 1,
              cancelled_runs: 0,
              total_failed_records: 4,
              runs_with_failures: 1,
              overall_score: 92,
              health_label: 'healthy',
              summary: '2 assets across 2 tracked source versions, 1 failed runs, 4 failed records',
            },
            {
              scope_kind: 'data_product',
              scope_id: 'customer-platform',
              scope_name: 'customer-platform',
              asset_count: 1,
              tracked_data_object_version_count: 1,
              total_runs: 2,
              pending_runs: 0,
              running_runs: 0,
              succeeded_runs: 1,
              failed_runs: 1,
              cancelled_runs: 0,
              total_failed_records: 3,
              runs_with_failures: 1,
              overall_score: 78,
              health_label: 'watch',
              summary: '1 asset across 1 tracked source version, 1 failed runs, 3 failed records',
            },
          ],
          active_incident_count: 1,
          active_incidents: [
            {
              incident_id: 'incident-1',
              title: 'Failed validation run',
              status: 'open',
              severity: 'high',
              incident_kind: 'technical_run_error',
              assigned_to: 'dq-support',
              run_id: 'run-a',
              run_plan_id: null,
            },
          ],
        },
        scorecards: [
          {
            scope_type: 'workspace',
            scope_id: 'ws-1',
            scope_name: 'Workspace ws-1',
            workspace_id: 'ws-1',
            lookback_amount: 24,
            lookback_unit: 'hours',
            generated_at: '2026-05-22T20:00:00Z',
            overall_score: 92,
            health_label: 'healthy',
            summary: '3 runs, 1 failed, 4 failed records',
            total_runs: 3,
            pending_runs: 0,
            running_runs: 1,
            succeeded_runs: 1,
            failed_runs: 1,
            cancelled_runs: 0,
            total_failed_records: 4,
            runs_with_failures: 1,
            tracked_data_object_version_ids: ['dov-1', 'dov-2'],
            dimension_rollups: [
              {
                dimension: 'Completeness',
                rule_count: 2,
                failed_record_total: 3,
                failed_run_count: 1,
                score: 25,
                status_label: 'attention',
              },
            ],
            top_rules: [
              {
                rule_id: 'rule-1',
                rule_name: 'Completeness Rule',
                dimension: 'Completeness',
                total: 3,
              },
            ],
            top_reasons: [
              {
                reason_code: 'missing_value',
                reason_text: 'Missing value',
                total: 3,
              },
            ],
            trend_buckets: [
              {
                bucket_start: '2026-05-22T18:00:00Z',
                total: 1,
              },
              {
                bucket_start: '2026-05-22T19:00:00Z',
                total: 3,
              },
            ],
            reason_trend_buckets: [
              {
                bucket_start: '2026-05-22T18:00:00Z',
                reason_code: 'missing_value',
                reason_text: 'Missing value',
                total: 1,
              },
            ],
          },
          {
            scope_type: 'data_asset',
            scope_id: 'asset-1',
            scope_name: 'Customer Health',
            workspace_id: 'ws-1',
            data_asset_id: 'asset-1',
            data_asset_name: 'Customer Health',
            data_asset_version_id: 'asset-1-v2',
            lookback_amount: 24,
            lookback_unit: 'hours',
            generated_at: '2026-05-22T20:00:00Z',
            overall_score: 78,
            health_label: 'watch',
            summary: '2 runs, 1 failed, 3 failed records',
            total_runs: 2,
            pending_runs: 0,
            running_runs: 0,
            succeeded_runs: 1,
            failed_runs: 1,
            cancelled_runs: 0,
            total_failed_records: 3,
            runs_with_failures: 1,
            tracked_data_object_version_ids: ['dov-1'],
            dimension_rollups: [],
            top_rules: [],
            top_reasons: [],
            trend_buckets: [],
            reason_trend_buckets: [],
          },
        ],
      }),
    }).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        workspace_id: 'ws-1',
        total_definitions: 2,
        active_definitions: 2,
        draft_definitions: 0,
        approved_definitions: 2,
        deprecated_definitions: 0,
        compliant_definitions: 1,
        at_risk_definitions: 1,
        definitions: [
          {
            id: 'sla-1',
            name: 'Freshness 24h',
            scope_kind: 'workspace',
            scope_id: 'ws-1',
            metric_kind: 'freshness',
            threshold_value: 24,
            threshold_operator: 'lte',
            lifecycle_status: 'active',
            approval_status: 'approved',
            adherence: {
              current_value: 36,
              threshold_value: 24,
              threshold_operator: 'lte',
              compliance_rate_pct: 66.7,
              meets_target: false,
              summary: 'Freshness target missed',
            },
          },
          {
            id: 'sla-2',
            name: 'Validity 98%',
            scope_kind: 'workspace',
            scope_id: 'ws-1',
            metric_kind: 'validity',
            threshold_value: 98,
            threshold_operator: 'gte',
            lifecycle_status: 'active',
            approval_status: 'approved',
            adherence: {
              current_value: 99,
              threshold_value: 98,
              threshold_operator: 'gte',
              compliance_rate_pct: 99,
              meets_target: true,
              summary: 'Validity target met',
            },
          },
        ],
      }),
    })

    render(<HealthScorecards workspaceId="ws-1" apiBaseUrl="http://api.local/v1" onRuleSelect={onRuleSelect} onNavigate={onNavigate} />)

    await waitFor(() => {
      expect(screen.getByText('Workspace ws-1')).toBeTruthy()
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })

    expect(screen.getByRole('heading', { name: 'DQ Health Dashboard' })).toBeTruthy()
    expect(screen.getByText('Workspace quality remains healthy')).toBeTruthy()
    expect(screen.getAllByText('92').length).toBeGreaterThan(0)
    expect(screen.getByText('Current failures')).toBeTruthy()
    expect(screen.getByText('4 failed records')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Worsening trends' })).toBeTruthy()
    expect(screen.getByText('1 → 3 failed records · +2')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Active incidents' })).toBeTruthy()
    expect(screen.getByText('Failed validation run')).toBeTruthy()
    expect(screen.getByText('Failure trend')).toBeTruthy()
    expect(screen.getAllByText('Healthy').length).toBeGreaterThan(0)
    expect(screen.getByText('Customer Health')).toBeTruthy()
    expect(screen.getAllByText('Watch').length).toBeGreaterThan(0)
    expect(screen.getByText('Missing value · 3')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Executive' }))

    expect(screen.getByText('Top degraded datasets')).toBeTruthy()
    expect(screen.getByText('Domain and product rollups')).toBeTruthy()
    expect(screen.getByText('Customer')).toBeTruthy()
    expect(screen.getByText('SLA status')).toBeTruthy()
    expect(screen.getByText('Freshness target missed')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Open service levels' }))
    expect(onNavigate).toHaveBeenCalledWith('reports-service-levels')

    screen.getAllByRole('button', { name: 'Completeness Rule' })[0].click()
    expect(onRuleSelect).toHaveBeenCalledWith('rule-1')
  })

  it('loads quality history for a selected dataset scope', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          workspace_id: 'ws-1',
          generated_at: '2026-05-22T20:00:00Z',
          workspace_summary: null,
          scorecards: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          workspace_id: 'ws-1',
          total_definitions: 0,
          active_definitions: 0,
          draft_definitions: 0,
          approved_definitions: 0,
          deprecated_definitions: 0,
          compliant_definitions: 0,
          at_risk_definitions: 0,
          definitions: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          lookback_amount: 24,
          lookback_unit: 'hours',
          total_events: 4,
          scoped_groups: 2,
          total_detections: 2,
          detections_by_type: {
            schema_change: 1,
            null_rate_shift: 1,
          },
          detections_by_severity: {
            warning: 2,
          },
          latest_observed_at: '2026-05-22T19:30:00Z',
          drifts: [
            {
              detector_type: 'schema_change',
              severity: 'warning',
              scope: { dataset_id: 'dataset-1' },
              observed_at: '2026-05-22T18:00:00Z',
              baseline_value: 3,
              current_value: 5,
              delta: 2,
              threshold: 1,
              message: 'Schema drift detected for dataset-1',
              evidence: {},
            },
            {
              detector_type: 'null_rate_shift',
              severity: 'warning',
              scope: { dataset_id: 'dataset-1' },
              observed_at: '2026-05-22T19:00:00Z',
              baseline_value: 1,
              current_value: 4,
              delta: 3,
              threshold: 2,
              message: 'Null-rate drift detected for dataset-1',
              evidence: {},
            },
          ],
        }),
      })

    render(<HealthScorecards workspaceId="ws-1" apiBaseUrl="http://api.local/v1" />)

    expect(screen.getByRole('heading', { name: 'View quality history by dataset, rule, domain, or data product' })).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Dataset ID'), { target: { value: 'dataset-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load history' }))

    await screen.findByText('Schema drift detected for dataset-1')

    expect(screen.getByText('Null-rate drift detected for dataset-1')).toBeTruthy()
    expect(screen.getByText(/Baseline 3 → current 5 · delta 2 · threshold 1/i)).toBeTruthy()
    expect(screen.getByText('Detections by severity')).toBeTruthy()
    expect(fetchMock.mock.calls.some(([calledUrl]) => String(calledUrl).includes('/result-history/drift?'))).toBe(true)
    expect(fetchMock.mock.calls.some(([calledUrl]) => String(calledUrl).includes('datasetId=dataset-1'))).toBe(true)
  })
})
