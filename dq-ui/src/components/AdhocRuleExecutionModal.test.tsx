/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { AdhocRuleExecutionModal } from './AdhocRuleExecutionModal'

const mockUseSettings = vi.fn()
const mockUseAuth = vi.fn()
const mockAddNotification = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
  useAuth: () => mockUseAuth(),
  useNotifications: () => ({ addNotification: mockAddNotification }),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

vi.mock('../config/api', () => ({
  toApiGroupV1Base: () => 'http://api.local/v1',
}))

vi.mock('../utils/supportReference', () => ({
  createSupportReferenceId: () => 'SUP-123',
  formatSupportReferenceId: (value: string) => value,
}))

vi.mock('../utils/validationTerminology', () => ({
  normalizeValidationUiText: (value: string) => value,
}))

vi.mock('./ModalShell', () => ({
  ModalShell: ({ isOpen, title, children, footer }: any) => isOpen ? (
    <div>
      <h1>{title}</h1>
      <div>{children}</div>
      <div>{footer}</div>
    </div>
  ) : null,
}))

vi.mock('./Button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  PrimaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  SecondaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  TertiaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
}))

vi.mock('./GxSuiteScopePickerModal', () => ({
  GxSuiteScopePickerModal: () => null,
}))


afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('AdhocRuleExecutionModal', () => {
  it('renders aggregate delivery summary and target outcomes after materialization completes', async () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: 'http://api.local' },
    })
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'ws-1',
    })

    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ([
          {
            suite_id: 'gx-suite-1',
            suite_version: 1,
            compiled_from: { rule_ids: ['rule-1'] },
            resolved_execution_scope: { data_object_version_ids: ['dov-1', 'dov-2'] },
          },
        ]),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          request_id: 'req-1',
          status: 'queued',
          output_uri: 's3a://materializations/req-1',
          output_format: 'parquet',
          result: null,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          request_id: 'req-1',
          status: 'completed',
          output_uri: 's3a://materializations/req-1',
          output_format: 'parquet',
          result: {
            output_uri: 's3a://materializations/req-1',
            output_format: 'parquet',
            reused_existing: true,
            delivery_summary: {
              target_count: 2,
              data_delivery_count: 2,
              total_row_count: 125,
              reused_existing: true,
              output_formats: ['parquet', 'delta'],
              delivery_locations: [
                's3a://deliveries/customer/v1',
                's3a://deliveries/customer/v2',
              ],
            },
            target_results: [
              {
                data_object_version_id: 'dov-1',
                row_count: 50,
                output_uri: 's3a://deliveries/customer/v1',
                output_format: 'parquet',
                data_delivery_id: 'del-1',
                delivery_note: {
                  delivery_location: 's3a://deliveries/customer/v1',
                },
              },
              {
                data_object_version_id: 'dov-2',
                row_count: 75,
                output_uri: 's3a://deliveries/customer/v2',
                output_format: 'delta',
                data_delivery_id: 'del-2',
                delivery_note: {
                  delivery_location: 's3a://deliveries/customer/v2',
                },
              },
            ],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ([
          {
            run_id: 'run-1',
            suite_id: 'gx-suite-1',
            suite_version: 1,
            scheduled_at: '2026-05-26T00:00:00Z',
          },
        ]),
      })

    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    render(
      <AdhocRuleExecutionModal
        isOpen={true}
        onClose={vi.fn()}
        mode="data_object_version"
        dataObjectVersionId="dov-1"
        dataObjectVersionLabel="Customer v1"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /generate \/ reuse test data/i }))

    await waitFor(() => {
      expect(screen.getByText('Delivery summary')).toBeTruthy()
    })

    expect(screen.getByText('Targets: 2')).toBeTruthy()
    expect(screen.getByText('Data deliveries: 2')).toBeTruthy()
    expect(screen.getByText('Total rows: 125')).toBeTruthy()
    expect(screen.getByText('Materialization mode: Reused existing outputs')).toBeTruthy()
    expect(screen.getByText('Output formats: parquet, delta')).toBeTruthy()
    expect(screen.getByText('Target deliveries')).toBeTruthy()
    expect(screen.getAllByText('dov-1').length).toBeGreaterThan(0)
    expect(screen.getAllByText('dov-2').length).toBeGreaterThan(0)
    expect(screen.getAllByText('del-1').length).toBeGreaterThan(0)
    expect(screen.getAllByText('del-2').length).toBeGreaterThan(0)
    expect(screen.getAllByText('s3a://deliveries/customer/v1').length).toBeGreaterThan(0)
    expect(screen.getAllByText('s3a://deliveries/customer/v2').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /run rules/i }))

    await waitFor(() => {
      expect(screen.getByText('Enqueued runs')).toBeTruthy()
    })

    const dispatchCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/gx/runs/adhoc'))
    expect(dispatchCall).toBeTruthy()
    const dispatchBody = JSON.parse(String(dispatchCall?.[1]?.body || '{}'))
    expect(dispatchBody.target_data_object_version_ids).toEqual(['dov-1', 'dov-2'])
    expect(dispatchBody.source_override_options.materialization_request_id).toBe('req-1')
    expect(dispatchBody.source_override_options.delivery_summary.target_count).toBe(2)
    expect(dispatchBody.source_override_options.target_results).toHaveLength(2)
  })
})