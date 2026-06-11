/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'

import { ReconciliationWorkbench } from './ReconciliationWorkbench'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

const mockSettings = {
  userSettings: {
    userId: 'user-1',
  },
  workspaceSettings: {
    workspaceId: 'workspace-1',
    reconciliationDataSources: [],
  },
  applicationSettings: {
    apiBaseUrl: 'http://localhost:8000/api/rulebuilder/v1',
    allowedWorkspaceDataSourceTypes: [],
  },
}

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockSettings,
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

vi.mock('./Button', () => mockButtonModule())

vi.mock('./CheckTypeForm/ReconcileForm', () => ({
  ReconcileForm: () => <div data-testid="reconcile-form" />,
}))

vi.mock('./ExecutionMetricsPanel', () => ({
  ExecutionMetricsPanel: () => <div data-testid="execution-metrics" />,
}))

vi.mock('./ExecutionDiagnosticsPanel', () => ({
  ExecutionDiagnosticsPanel: () => <div data-testid="execution-diagnostics" />,
}))

describe('ReconciliationWorkbench', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.endsWith('/gx/runs/reconciliation?workspaceId=workspace-1&limit=10')) {
        return new Response(JSON.stringify([
          {
            id: 'recon-1',
            submitted_at: '2026-04-06T12:00:00Z',
            status: 'succeeded',
            execution_contract: {
              workspace_id: 'workspace-1',
              reconciliation_params: {
                left_data_object_version_id: 'ledger-left-v17',
                right_data_object_version_id: 'ledger-right-v17',
              },
            },
            result_summary: {
              metrics: {
                match_rate: 87.5,
              },
            },
          },
        ]), { status: 200 })
      }

      return new Response('[]', { status: 200 })
    }))
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    mockSettings.workspaceSettings.reconciliationDataSources = []
  })

  it('renders persisted reconciliation history from the API', async () => {
    render(<ReconciliationWorkbench />)

    await waitFor(() => expect(screen.getByText('ledger-left-v17 → ledger-right-v17')).toBeTruthy())
    expect(screen.getByText('87.50%')).toBeTruthy()
  })

  it('disables reconciliation when a datasource is already active', async () => {
    mockSettings.workspaceSettings.reconciliationDataSources = [
      { id: 'left-feed', name: 'Left feed', sourceType: 'postgres', connectionParameters: '{}' },
      { id: 'right-feed', name: 'Right feed', sourceType: 'postgres', connectionParameters: '{}' },
    ]

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.endsWith('/gx/runs/reconciliation?workspaceId=workspace-1&limit=10')) {
        return new Response(JSON.stringify([
          {
            id: 'recon-running-1',
            submitted_at: '2026-04-06T12:00:00Z',
            status: 'running',
            execution_contract: {
              workspace_id: 'workspace-1',
              left_datasource_id: 'left-feed',
              right_datasource_id: 'right-feed',
              reconciliation_params: {
                left_data_object_version_id: 'ledger-left-v17',
                right_data_object_version_id: 'ledger-right-v17',
              },
            },
          },
        ]), { status: 200 })
      }

      return new Response('[]', { status: 200 })
    }))

    render(<ReconciliationWorkbench />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Run reconciliation' }).hasAttribute('disabled')).toBe(true))
    expect(screen.getByText('Datasource left-feed is already part of active reconciliation run recon-running-1.')).toBeTruthy()
  })
})
