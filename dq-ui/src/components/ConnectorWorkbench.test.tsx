/** @vitest-environment jsdom */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ConnectorWorkbench } from './ConnectorWorkbench'

const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useAuth: () => mockUseAuth(),
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

vi.mock('../hooks/useAgentHarness', () => ({
  useAgentHarness: () => ({
    agents: [],
    loadingAgents: false,
    error: null,
    runAgent: vi.fn(),
  }),
}))

vi.mock('../config/api', () => ({
  normalizeApiBaseUrl: (value: string | undefined) => value || 'http://localhost:8000/v1',
  toApiGroupV1Base: () => 'http://localhost:8000/rulebuilder/v1',
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

const makeResponse = (body: unknown, ok = true) => ({
  ok,
  status: ok ? 200 : 400,
  json: async () => body,
})

describe('ConnectorWorkbench', () => {
  it('opens the connector setup AI assistant from the workbench header', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'workspace-1',
      user: {
        workspaceRoles: [{ workspaceId: 'workspace-1', role: 'admin' }],
      },
      getCurrentUserRole: () => 'admin',
      hasAnyScope: () => true,
    })
    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1' },
    })

    const fetchMock = vi.fn()
      .mockResolvedValueOnce(makeResponse([
        {
          provider: 'external_api',
          display_name: 'External API',
          description: 'API connector',
          implementation_path: 'app.application.services.external_api_connector.ExternalApiConnector',
          capabilities: {
            can_configure: true,
            can_validate: true,
            can_discover: true,
            can_sync: true,
            can_health: true,
            supports_secret_refs: true,
            supports_incremental_sync: false,
          },
          supported_asset_kinds: ['api_operation'],
        },
      ]))
      .mockResolvedValueOnce(makeResponse({
        entity: 'connector_sync_job',
        statuses: [],
        transitions: [],
        allowed_transitions_by_status: {},
      }))
      .mockResolvedValueOnce(makeResponse([]))

    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    render(<ConnectorWorkbench />)

    fireEvent.click(screen.getByRole('button', { name: /use ai assistant/i }))

    expect(await screen.findByRole('heading', { name: /connector onboarding assistant/i, level: 2 })).toBeTruthy()
    expect(screen.getByDisplayValue(/help me configure an external api connector/i)).toBeTruthy()
  })

  it('supports connector validation, discovery, sync, status model loading, and persisted instances', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'workspace-1',
      user: {
        workspaceRoles: [{ workspaceId: 'workspace-1', role: 'admin' }],
      },
      getCurrentUserRole: () => 'viewer',
      hasAnyScope: () => true,
    })
    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1' },
    })

    const instancePayload = {
      id: 'connector-instance-1',
      provider: 'external_api',
      display_name: 'External API',
      workspace_id: 'workspace-1',
      tenant_id: null,
      configuration: {
        provider: 'external_api',
        workspace_id: 'workspace-1',
        display_name: 'External API',
        base_url: 'https://api.example.com',
        openapi_url: 'https://api.example.com/openapi.json',
        request_timeout_seconds: 30,
      },
      created_at: '2026-06-06T00:00:00Z',
      updated_at: '2026-06-06T00:00:00Z',
    }

    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        makeResponse([
          {
            provider: 'external_api',
            display_name: 'External API',
            description: 'API connector for systems exposed through explicit operations with optional OpenAPI augmentation.',
            implementation_path: 'app.application.services.external_api_connector.ExternalApiConnector',
            capabilities: {
              can_configure: true,
              can_validate: true,
              can_discover: true,
              can_sync: true,
              can_health: true,
              supports_secret_refs: true,
              supports_incremental_sync: false,
            },
            supported_asset_kinds: ['api_operation', 'openapi_document'],
          },
        ]),
      )
      .mockResolvedValueOnce(
        makeResponse({
          entity: 'connector_sync_job',
          statuses: [
            { value: 'queued', label: 'Queued', description: 'Queued', is_initial: true, is_terminal: false },
            { value: 'running', label: 'Running', description: 'Running', is_initial: false, is_terminal: false },
            { value: 'completed', label: 'Completed', description: 'Completed', is_initial: false, is_terminal: true },
            { value: 'failed', label: 'Failed', description: 'Failed', is_initial: false, is_terminal: true },
            { value: 'cancelled', label: 'Cancelled', description: 'Cancelled', is_initial: false, is_terminal: true },
          ],
          transitions: [
            { from_status: 'queued', to_status: 'running', label: 'Start Sync', required_any_scopes: [] },
            { from_status: 'running', to_status: 'completed', label: 'Complete Sync', required_any_scopes: [] },
          ],
          allowed_transitions_by_status: {
            queued: ['running', 'failed', 'cancelled'],
            running: ['completed', 'failed', 'cancelled'],
          },
        }),
      )
      .mockResolvedValueOnce(makeResponse([]))
      .mockResolvedValueOnce(
        makeResponse({
          provider: 'external_api',
          status: 'healthy',
          details: {
            operation_count: 1,
            correlation_id: 'corr-123',
          },
          errors: [],
        }),
      )
      .mockResolvedValueOnce(
        makeResponse({
          provider: 'external_api',
          items: [
            {
              identifier: 'https://api.example.com::GET:/customers',
              kind: 'api_operation',
              name: 'list_customers',
              metadata: { source: 'configured' },
            },
          ],
          errors: [],
        }),
      )
      .mockResolvedValueOnce(
        makeResponse({
          job_id: 'connector-sync-abcd1234',
          provider: 'external_api',
          status: 'completed',
          requested_at: '2026-06-06T00:00:00Z',
          started_at: '2026-06-06T00:00:00Z',
          completed_at: '2026-06-06T00:00:00Z',
          synced_count: 1,
          correlation_id: 'corr-123',
          result: {
            provider: 'external_api',
            synced_count: 1,
            items: [
              {
                identifier: 'https://api.example.com::GET:/customers',
                kind: 'api_operation',
                name: 'list_customers',
                metadata: { source: 'configured' },
              },
            ],
            errors: [],
          },
        }),
      )
      .mockResolvedValueOnce(makeResponse(instancePayload))
      .mockResolvedValueOnce(makeResponse([instancePayload]))
      .mockResolvedValueOnce(
        makeResponse({
          provider: 'external_api',
          status: 'healthy',
          details: {
            operation_count: 1,
            correlation_id: 'corr-456',
          },
          errors: [],
        }),
      )

    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)

    render(<ConnectorWorkbench />)

    await waitFor(() => {
      expect(screen.getByText('connector_sync_job')).toBeTruthy()
    })

    fireEvent.change(screen.getByLabelText(/base url/i), { target: { value: 'https://api.example.com' } })
    fireEvent.change(screen.getByLabelText(/openapi url/i), { target: { value: 'https://api.example.com/openapi.json' } })

    fireEvent.click(screen.getByRole('button', { name: /test connection/i }))

    await waitFor(() => {
      expect(screen.getByText('healthy')).toBeTruthy()
    })

    expect(screen.getByText('No persisted connector instances yet')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /discover assets/i }))

    await waitFor(() => {
      expect(screen.getByText('https://api.example.com::GET:/customers')).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('button', { name: /run sync/i }))

    await waitFor(() => {
      expect(screen.getByText('completed')).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('button', { name: /save instance/i }))

    await waitFor(() => {
      expect(screen.getByText('connector-instance-1')).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('button', { name: /test connection/i }))

    await waitFor(() => {
      expect(screen.getAllByText('healthy').length).toBeGreaterThan(0)
    })

    const testConnectionCalls = fetchMock.mock.calls.filter((call) => typeof call[0] === 'string' && call[0].includes('/test-connection'))
    const lastTestConnectionCall = testConnectionCalls[testConnectionCalls.length - 1]
    const lastTestConnectionBody = JSON.parse(String((lastTestConnectionCall[1] as RequestInit).body)) as Record<string, unknown>
    expect(lastTestConnectionBody.connector_instance_id).toBe('connector-instance-1')

    expect(screen.getByText('Connector setup')).toBeTruthy()
    expect(screen.getByText('Sync lifecycle')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/rulebuilder/v1/governance/status-models/connector_sync_job',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('shows access restricted for non-admin users', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'workspace-1',
      user: {
        workspaceRoles: [{ workspaceId: 'workspace-1', role: 'analyst' }],
      },
      getCurrentUserRole: () => 'analyst',
      hasAnyScope: () => true,
    })
    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1' },
    })

    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<ConnectorWorkbench />)

    expect(screen.getByText('Access restricted')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
